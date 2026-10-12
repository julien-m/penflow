# @spec(FR-001)
# @spec(FR-002)
# @spec(FR-003)
# @spec(FR-004)
# @spec(FR-005)
# @spec(FR-007)
# @spec(FR-008)
# @spec(FR-009)
# @spec FR-001 FR-002 FR-003 FR-004 FR-007: Feature 075 Doctor command boundary.

# @spec(FR-010)
"""Penflow command line interface."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from .actual_provenance import (
    ProvenanceError,
    actual_provenance_path,
    validate_actual_provenance,
)
from .causal_evidence import validate_causal_evidence
from .checklist import ChecklistSeedError, seed_checklist_from_drift
from .drift import detect_drift
from .export_operator import (
    verify_export_operation,
)
from .flow_contract import (
    interactive_coverage_report,
    load_flow_contract_v2,
    validate_flow_contract_v2,
)
from .flow_contract_migration import migrate_flow_md_to_contract_json
from .flow_specs import validate_flow_specs_dir
from .pen import (
    bbox_issues,
    inspect_pen,
    load_pen,
    parse_pen,
    validate_pen_context,
    validate_pen_context_against_contract,
)
from .project_doctor import (
    resolve_project_context,
    run_project_doctor,
)
from .pencil_persistence import (
    verify_pencil_persistence,
)
from .pencil_sync import PencilSyncError
from .save_helper import install_save_helper_report
from .reverse import reverse_pen
from .run_lifecycle import (
    LifecycleLock,
    capture_owner_identity,
)
from .run_pipeline import RunPipelineError
from .semantic import write_semantic_tree
from .semantic_draft import write_pen_draft_from_semantic_tree
from .semantic_enrichment import enrich_pen_from_semantic_tree
from .semantic_validation import validate_semantic_tree, validate_semantic_tree_file
from .strict_closure import StrictClosureError
from .tree import load_tree, validate_actual_tree, write_expected_tree

from .cli_reporting import (
    PenflowError,
    _exit_code,
    _has_errors,
    _is_lenient,
    _print,
    _status,
)
from .cli_governance import ProjectBoundaryError


@dataclass(frozen=True, slots=True)
class CommandDependencies:
    """Runtime callables injected by the CLI entry point.

    Attributes:
        run_pipeline: Execute the ordered local Penflow pipeline.
        sync_pencil_to_disk: Persist and verify a Pencil document.
        validate_strict_closure: Validate strict same-run evidence closure.
    """

    run_pipeline: Callable[..., dict[str, Any]]
    sync_pencil_to_disk: Callable[..., dict[str, Any]]
    validate_strict_closure: Callable[..., dict[str, Any]]


def _dependencies(args: argparse.Namespace) -> CommandDependencies:
    """Return dependencies injected by :func:`penflow.cli.main`.

    Args:
        args: Parsed command arguments.

    Returns:
        The command runtime dependency bundle.

    Raises:
        RuntimeError: If a caller bypasses the public CLI entry point.
    """
    dependencies = getattr(args, "dependencies", None)
    if not isinstance(dependencies, CommandDependencies):
        raise RuntimeError("command dependencies were not injected by penflow.cli.main")
    return dependencies


def cmd_doctor(args: argparse.Namespace) -> int:
    """Run the consumer-project Doctor and print its complete report."""
    if getattr(args, "install_save_helper", False):
        report, exit_code = install_save_helper_report(args.save_helper_dir)
        _print(report, args.json)
        return exit_code
    if args.fix and args.check:
        raise ProjectBoundaryError("doctor --check and --fix are mutually exclusive", exit_code=2)
    context = resolve_project_context(args.project)
    if args.fix and not args.dry_run:
        owner = capture_owner_identity()
        with LifecycleLock.acquire(context.project_root, owner, operation="doctor:fix"):
            result = run_project_doctor(context, fix=True)
    else:
        result = run_project_doctor(
            context,
            fix=bool(args.fix),
            dry_run=bool(args.dry_run),
        )
    _print(result.report.to_dict(), args.json)
    return result.exit_code


def cmd_inspect(args: argparse.Namespace) -> int:
    result = inspect_pen(args.pen)
    _print(result, args.json)
    return 1 if result["errors"] else 0


def cmd_run(args: argparse.Namespace) -> int:
    if getattr(args, "profile", None):
        from .cli_verification import run_verification_command

        return run_verification_command(args)
    dependencies = _dependencies(args)
    if args.strict_closure:
        try:
            summary = dependencies.validate_strict_closure(
                args.target,
                theme_css=args.theme_css,
                references=args.references,
                actual_max_age_seconds=args.actual_max_age_seconds,
            )
        except StrictClosureError as error:
            raise PenflowError(str(error)) from error
        _print(summary, args.json)
        return int(summary["exit"])
    try:
        summary = dependencies.run_pipeline(
            args.target,
            theme_css=args.theme_css,
            references=args.references,
            strict=args.strict,
            actual_max_age_seconds=args.actual_max_age_seconds,
        )
    except RunPipelineError as error:
        raise PenflowError(str(error)) from error
    _print(summary, args.json)
    return int(summary["exit"])


def cmd_pencil_sync(args: argparse.Namespace) -> int:
    dependencies = _dependencies(args)
    try:
        result = dependencies.sync_pencil_to_disk(
            args.pen,
            expect_min_nodes=args.expect_min_nodes,
            expect_screens=args.expect_screens,
            app=args.app,
            save_timeout=args.save_timeout,
        )
    except PencilSyncError as error:
        raise PenflowError(str(error)) from error
    _print(result, args.json)
    return 0 if result["status"] == "PASS" else 1


def cmd_verify_pencil_persistence(args: argparse.Namespace) -> int:
    try:
        receipt = verify_pencil_persistence(
            args.observation,
            document=args.document,
            run_id=args.run_id,
            operation=args.operation,
            out=args.out,
        )
    except OSError as error:
        raise PenflowError(f"could not write persistence receipt: {error}") from error
    _print(receipt, args.json)
    return 0 if receipt["status"] == "PASS" else 1


def cmd_verify_export_operation(args: argparse.Namespace) -> int:
    try:
        receipt = verify_export_operation(
            args.request,
            source_pen=args.source_pen,
            run_id=args.run_id,
            out=args.out,
        )
    except OSError as error:
        raise PenflowError(f"could not write export receipt: {error}") from error
    _print(receipt, args.json)
    return 0 if receipt["status"] == "PASS" else 1


def cmd_validate_pen(args: argparse.Namespace) -> int:
    raw = load_pen(args.pen)
    roots = parse_pen(raw)
    if args.contract:
        contract = load_flow_contract_v2(args.contract)
        contract_issues = validate_flow_contract_v2(contract)
        if _has_errors(contract_issues):
            issues = contract_issues
        else:
            issues = [
                asdict(issue) for issue in validate_pen_context_against_contract(roots, contract)
            ]
    else:
        issues = [asdict(issue) for issue in validate_pen_context(roots)]
    # Raw re-scan (feature 049): parse_pen coerces invalid bbox strings to 0,
    # so the silent-coercion warning must come from the raw JSON values.
    issues = issues + [asdict(issue) for issue in bbox_issues(raw)]
    code = _exit_code(issues, _is_lenient(args))
    _print({"status": _status(code), "issues": issues}, args.json)
    return code


def cmd_export_expected(args: argparse.Namespace) -> int:
    tree = write_expected_tree(args.pen, args.out)
    code = _exit_code(tree["issues"], _is_lenient(args))
    _print(
        {"out": args.out, "screens": len(tree["screens"]), "issues": len(tree["issues"])}, args.json
    )
    return code


def cmd_export_semantic_tree(args: argparse.Namespace) -> int:
    # @spec FR-005: export-semantic-tree validates its output — .specs/features/049-strict-mode-default-blocking-drift/spec.md#fr-005
    tree = write_semantic_tree(args.specs_dir, args.out)
    issues = validate_semantic_tree(tree)
    code = _exit_code(issues, _is_lenient(args))
    _print(
        {
            "status": _status(code),
            "out": args.out,
            "flows": len(tree["flows"]),
            "screens": len(tree["screens"]),
            "issues": issues,
        },
        args.json,
    )
    return code


def cmd_validate_flow_specs(args: argparse.Namespace) -> int:
    # @spec FR-006: Deprecated compatibility surface — .specs/features/045-penflow-json-only-strict-contract-v2/spec.md#fr-006
    report = validate_flow_specs_dir(args.specs_dir)
    code = _exit_code(report["issues"], _is_lenient(args))
    if report["status"] == "FAIL":
        code = 1
    _print(report | {"status": _status(code)}, args.json)
    return code


def cmd_validate_flow_contract(args: argparse.Namespace) -> int:
    # @spec FR-004: Primary strict contract CLI — .specs/features/045-penflow-json-only-strict-contract-v2/spec.md#fr-004
    contract = load_flow_contract_v2(args.contract)
    issues = validate_flow_contract_v2(contract)
    if getattr(args, "require_test_ids", False):
        from .contract_preparation import contract_test_id_issues

        issues.extend(contract_test_id_issues(contract))
    code = _exit_code(issues, _is_lenient(args))
    _print(
        {
            "status": _status(code),
            "issues": issues,
            "interactive_coverage": interactive_coverage_report(contract),
        },
        args.json,
    )
    return code


def cmd_validate_causal_evidence(args: argparse.Namespace) -> int:
    """Validate local adapter observations without executing a runtime."""
    try:
        report = validate_causal_evidence(args.contract, args.evidence)
    except (FileNotFoundError, json.JSONDecodeError, ValueError, OSError) as error:
        raise PenflowError(str(error)) from error
    _print(report, args.json)
    return 0 if report["status"] == "PASS" else 1


def cmd_migrate_flow_contract(args: argparse.Namespace) -> int:
    report = migrate_flow_md_to_contract_json(args.specs_dir, args.out)
    _print(report, args.json)
    return 0 if report["status"] == "PASS" else 1


def cmd_validate_semantic_tree(args: argparse.Namespace) -> int:
    _, issues = validate_semantic_tree_file(args.semantic_tree)
    code = _exit_code(issues, _is_lenient(args))
    _print({"status": _status(code), "issues": issues}, args.json)
    return code


def cmd_draft_pen_from_tree(args: argparse.Namespace) -> int:
    passed, issues = validate_semantic_tree_file(args.semantic_tree)
    if not passed:
        _print({"status": "FAIL", "issues": issues}, args.json)
        return 1
    try:
        draft = write_pen_draft_from_semantic_tree(
            args.semantic_tree, args.out, theme_css_path=args.theme_css
        )
    except FileNotFoundError as error:
        _print(
            {"status": "FAIL", "issues": [{"severity": "error", "message": str(error)}]}, args.json
        )
        return 1
    _print(
        {
            "status": "PASS",
            "out": args.out,
            "screens": len(draft["children"]),
            "fidelity": "wireframe",
            "theme_css": args.theme_css,
        },
        args.json,
    )
    return 0


def cmd_enrich_pen(args: argparse.Namespace) -> int:
    passed, issues = validate_semantic_tree_file(args.semantic_tree)
    if not passed:
        _print({"status": "FAIL", "issues": issues}, args.json)
        return 1
    report = enrich_pen_from_semantic_tree(args.pen, args.semantic_tree, args.out)
    _print(report, args.json)
    return 0


def cmd_reverse_pen(args: argparse.Namespace) -> int:
    # @spec FR-006: reverse-pen surfaces clarification issues — .specs/features/049-strict-mode-default-blocking-drift/spec.md#fr-006
    report = reverse_pen(args.pen, args.out, enrich=args.enrich)
    code = _exit_code(report["issues"], _is_lenient(args))
    _print(report | {"status": _status(code)}, args.json)
    return code


def cmd_detect_drift(args: argparse.Namespace) -> int:
    # @spec FR-008: blocking drift exit policy — .specs/features/049-strict-mode-default-blocking-drift/spec.md#fr-008
    report = detect_drift(
        args.specs_dir,
        args.semantic_tree,
        args.pen,
        args.out,
        markdown_path=args.markdown,
    )
    _print(report | {"out": args.out, "markdown": args.markdown}, args.json)
    # Blocking issues and errors fail in both modes; warning-only DRIFT is
    # forgiven only with --lenient.
    if report["status"] == "PASS":
        return 0
    if report["status"] == "BLOCKED" or report["summary"]["errors"] > 0:
        return 1
    return 0 if _is_lenient(args) else 1


def cmd_checklist_from_drift(args: argparse.Namespace) -> int:
    # @spec FR-002: exit-1 fail-closed error boundary — .specs/features/055-checklist-from-drift-seeding/spec.md#fr-002
    try:
        checklist = seed_checklist_from_drift(args.drift_report, args.out, group=args.group)
    except (ChecklistSeedError, OSError) as error:
        # Exit 1, not PenflowError (exit 2): the spec pins exit 1 for every
        # input failure, including an unwritable --out destination.
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    _print(
        {"status": checklist["status"], "items": len(checklist["items"]), "out": args.out},
        args.json,
    )
    return 0


def cmd_validate_actual(args: argparse.Namespace) -> int:
    issues = validate_actual_tree(load_tree(args.actual), schema=args.schema)
    code = _exit_code(issues, _is_lenient(args))
    _print({"status": _status(code), "issues": issues}, args.json)
    return code


# @spec(FR-016)
# @spec(FR-017)
def cmd_validate_actual_provenance(args: argparse.Namespace) -> int:
    target = Path(args.target)
    if args.actual is not None:
        actual_path = Path(args.actual)
    elif target.is_dir():
        actual_path = target / "actual-ui-tree.json"
    else:
        actual_path = target
    if args.expected is not None:
        expected_path: Path | None = Path(args.expected)
    elif target.is_dir():
        candidate = target / "expected-ui-tree.json"
        expected_path = candidate if candidate.is_file() else None
    else:
        expected_path = None
    try:
        issues = validate_actual_provenance(
            actual_path,
            expected_path=expected_path,
            now=datetime.now(UTC),
            max_age_seconds=args.max_age_seconds,
            require_fresh=args.require_fresh,
            allowed_surfaces=args.surface,
        )
    except ProvenanceError as error:
        # Structured, non-zero exit before any JSON body is printed.
        raise PenflowError(str(error)) from error
    code = _exit_code(issues, _is_lenient(args))
    _print(
        {
            "status": _status(code),
            "actual": str(actual_path),
            "receipt": str(actual_provenance_path(actual_path)),
            "issues": issues,
        },
        args.json,
    )
    return code
