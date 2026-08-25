# @spec(FR-001)
# @spec(FR-002)
# @spec(FR-003)
# @spec(FR-004)
# @spec(FR-005)
# @spec(FR-007)
# @spec(FR-008)
# @spec(FR-009)

# @spec(FR-010)
"""Penflow command line interface."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .codegen import react, rust_dioxus, swiftui
from .compare import compare_tree_files
from .consistency import check_consistency, write_consistency_report
from .contracts import (
    _raise_if_no_context,
    assert_contextualized_pen_input,
    code_ir_from_contract,
    code_ir_from_pen,
    extract_design_tokens,
    screen_contracts_from_flow,
    update_pencil,
    validate_code_ir,
    validate_flow_contract,
    validate_screen_contract,
    write_pencil_draft,
)
from .demo import build_demo
from .evidence import validate_visual_evidence
from .llm import fix_compare_report, review_compare_report
from .reference_fidelity import validate_reference_fidelity
from .theme import load_theme, theme_fingerprint
from .token_lint import (
    lint_tokens,
)
from .tree import load_tree, write_expected_tree
from .visual_metrics import audit_visual, write_visual_metrics_report

from .cli_reporting import (
    PenflowError,
    _exit_code,
    _has_errors,
    _is_lenient,
    _print,
    _resolve_threshold,
    _status,
    _validate_report_schema,
)


def cmd_compare_tree(args: argparse.Namespace) -> int:
    # @spec FR-004: strict threshold default 0.98 — .specs/features/049-strict-mode-default-blocking-drift/spec.md#fr-004
    threshold = _resolve_threshold(args.threshold, _is_lenient(args))
    report = compare_tree_files(
        args.expected,
        args.actual,
        json_out=args.out,
        markdown_out=None,
        threshold=threshold,
    )
    code = 1 if report["status"] != "PASS" else _exit_code(report["issues"], _is_lenient(args))
    _print(
        {
            "status": _status(code),
            "score": report["score"],
            "threshold": threshold,
            "out": args.out,
        },
        args.json,
    )
    return code


def cmd_check_consistency(args: argparse.Namespace) -> int:
    # @spec FR-003: check-consistency CLI with exit codes 0/1/2 — .specs/features/047-cross-screen-consistency-check/spec.md#fr-003
    tree_path = Path(args.expected)
    if not tree_path.exists():
        raise PenflowError(f"expected tree not found: {tree_path}")
    try:
        report = check_consistency(tree_path, group_by=args.group_by, lenient=_is_lenient(args))
    except json.JSONDecodeError as error:
        raise PenflowError(f"expected tree is not valid JSON: {tree_path}: {error}") from error
    except ValueError as error:
        raise PenflowError(str(error)) from error
    if args.out:
        write_consistency_report(report, args.out)
    code = _exit_code(report["issues"], _is_lenient(args))
    _print(
        {
            "status": _status(code),
            "issues": len(report["issues"]),
            "out": args.out,
        },
        args.json,
    )
    return code


def cmd_audit_visual(args: argparse.Namespace) -> int:
    # @spec FR-007: audit-visual CLI with exit codes 0/1/2 — .specs/features/050-deterministic-visual-metrics-audit/spec.md#fr-007
    tree_path = Path(args.expected)
    if not tree_path.exists():
        raise PenflowError(f"expected tree not found: {tree_path}")
    try:
        theme = load_theme(args.theme_css) if args.theme_css else None
    except FileNotFoundError as error:
        raise PenflowError(str(error)) from error
    try:
        report = audit_visual(
            tree_path,
            theme=theme,
            theme_css=args.theme_css,
            layout_snapshot=args.layout_snapshot,
        )
    except json.JSONDecodeError as error:
        raise PenflowError(f"expected tree is not valid JSON: {tree_path}: {error}") from error
    except ValueError as error:
        raise PenflowError(str(error)) from error
    if args.out:
        write_visual_metrics_report(report, args.out)
    code = _exit_code(report["issues"], _is_lenient(args))
    _print(
        {
            "status": _status(code),
            "issues": len(report["issues"]),
            "out": args.out,
        },
        args.json,
    )
    return code


def cmd_validate_visual_evidence(args: argparse.Namespace) -> int:
    # @spec FR-004: validate-visual-evidence CLI with exit codes 0/1/2 — .specs/features/051-vision-report-contract-evidence-validator/spec.md#fr-004
    directory = Path(args.evidence_dir)
    if not directory.is_dir():
        raise PenflowError(f"evidence directory not found: {directory}")
    if args.expected is not None and not Path(args.expected).exists():
        raise PenflowError(f"expected tree not found: {args.expected}")
    # @spec FR-004: --theme-css boundary + gate arming — .specs/features/056-evidence-run-identity-theme-fingerprint/spec.md#fr-004
    # The fingerprint is armed BEFORE packet validation so a missing theme
    # file is a usage boundary (exit 2) and never a packet-level issue.
    fingerprint = None
    if args.theme_css is not None:
        try:
            fingerprint = theme_fingerprint(args.theme_css)
        except OSError as error:
            raise PenflowError(str(error)) from error
    try:
        issues = validate_visual_evidence(
            directory, expected_tree_path=args.expected, theme_fingerprint=fingerprint
        )
    except json.JSONDecodeError as error:
        raise PenflowError(f"expected tree is not valid JSON: {args.expected}: {error}") from error
    except (TypeError, ValueError) as error:
        raise PenflowError(str(error)) from error
    code = _exit_code(issues, _is_lenient(args))
    _print(
        {
            "status": _status(code),
            "dir": str(directory),
            "expected": args.expected,
            "issues": issues,
        },
        args.json,
    )
    return code


def cmd_validate_reference_fidelity(args: argparse.Namespace) -> int:
    # @spec FR-004: validate-reference-fidelity CLI with exits 0/1/2 — .specs/features/063-reference-fidelity/spec.md#fr-004
    try:
        report = validate_reference_fidelity(args.evidence_dir, args.references)
    except (FileNotFoundError, ValueError, json.JSONDecodeError, OSError) as error:
        raise PenflowError(str(error)) from error
    _print(report, args.json)
    return 0 if report["status"] == "PASS" else 1


def cmd_validate_flow(args: argparse.Namespace) -> int:
    issues = validate_flow_contract(load_tree(args.flow))
    code = _exit_code(issues, _is_lenient(args))
    _print({"status": _status(code), "issues": issues}, args.json)
    return code


def cmd_validate_screen(args: argparse.Namespace) -> int:
    issues = validate_screen_contract(load_tree(args.screen))
    code = _exit_code(issues, _is_lenient(args))
    _print({"status": _status(code), "issues": issues}, args.json)
    return code


def cmd_flow_to_screens(args: argparse.Namespace) -> int:
    flow = load_tree(args.flow)
    issues = validate_flow_contract(flow)
    if _has_errors(issues):
        _print({"status": "FAIL", "issues": issues}, args.json)
        return 1
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    for screen in screen_contracts_from_flow(flow):
        path = out / f"{screen['id']}.json"
        path.write_text(json.dumps(screen, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        paths.append(str(path))
    _print({"status": "PASS", "screens": paths}, args.json)
    return 0


def cmd_draft_pen(args: argparse.Namespace) -> int:
    write_pencil_draft(args.screen, args.out)
    _print({"status": "PASS", "out": args.out}, args.json)
    return 0


def cmd_update_pen(args: argparse.Namespace) -> int:
    update_pencil(args.pen, args.updates, args.out)
    _print({"status": "PASS", "out": args.out}, args.json)
    return 0


def cmd_extract_tokens(args: argparse.Namespace) -> int:
    # @spec FR-007: extract-tokens surfaces unparsable values — .specs/features/049-strict-mode-default-blocking-drift/spec.md#fr-007
    tokens = extract_design_tokens(args.pen)
    code = _exit_code(tokens["issues"], _is_lenient(args))
    if args.out:
        Path(args.out).write_text(
            json.dumps(tokens, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    _print(tokens | {"status": _status(code)} | ({"out": args.out} if args.out else {}), args.json)
    return code


def cmd_lint_tokens(args: argparse.Namespace) -> int:
    # @spec FR-004: lint-tokens CLI with exit codes 0/1/2 — .specs/features/046-lint-design-tokens/spec.md#fr-004
    pen_path = Path(args.pen)
    if not pen_path.exists():
        raise PenflowError(f"pen file not found: {pen_path}")
    try:
        theme = load_theme(args.theme_css) if args.theme_css else None
    except FileNotFoundError as error:
        raise PenflowError(str(error)) from error
    report = lint_tokens(
        pen_path,
        theme=theme,
        theme_css=args.theme_css,
        spacing_scale=_parse_scale(args.spacing_scale, "--spacing-scale"),
        radius_scale=_parse_scale(args.radius_scale, "--radius-scale"),
        fontsize_scale=_parse_scale(args.fontsize_scale, "--fontsize-scale"),
    )
    if args.out:
        Path(args.out).write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    code = _exit_code(report["violations"], _is_lenient(args))
    _print(
        {
            "status": _status(code),
            "violations": len(report["violations"]),
            "out": args.out,
        },
        args.json,
    )
    return code


def cmd_theme_fingerprint(args: argparse.Namespace) -> int:
    # @spec FR-003: Subcommand with exits 0/2 and _print envelope — .specs/features/056-evidence-run-identity-theme-fingerprint/spec.md#fr-003
    try:
        payload = theme_fingerprint(args.theme_css)
    except OSError as error:
        # Usage/IO boundary (lint-tokens AC-012 parity): ERROR on stderr, exit 2.
        raise PenflowError(str(error)) from error
    _print(payload, args.json)
    return 0


def _parse_scale(raw: str | None, flag: str) -> tuple[float, ...] | None:
    if raw is None:
        return None
    parts = [part.strip() for part in raw.split(",")]
    if any(part == "" for part in parts):
        raise PenflowError(f"{flag} must not be empty")
    try:
        return tuple(float(part) for part in parts)
    except ValueError as error:
        raise PenflowError(f"{flag} must be comma-separated numbers, got: {raw!r}") from error


def cmd_export_ir(args: argparse.Namespace) -> int:
    screen = load_tree(args.screen)
    expected = load_tree(args.expected) if args.expected else None
    ir = code_ir_from_contract(screen, expected)
    Path(args.out).write_text(json.dumps(ir, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _print({"status": "PASS", "out": args.out}, args.json)
    return 0


def cmd_code_ir(args: argparse.Namespace) -> int:
    # @spec FR-008: v2 contract handoff in code IR — .specs/features/045-penflow-json-only-strict-contract-v2/spec.md#fr-008
    try:
        assert_contextualized_pen_input(args.from_context)
    except (ValueError, json.JSONDecodeError, OSError) as error:
        raise PenflowError(str(error)) from error
    ir = code_ir_from_pen(
        args.from_context,
        flow_id=args.flow_id,
        flow_name=args.flow_name,
        semantic_tree=args.semantic_tree,
        context_map=args.context_map,
        contract=args.contract,
    )
    _raise_if_no_context(ir["screens"], args.from_context)
    issues = validate_code_ir(ir)
    errors = [issue for issue in issues if issue.get("severity") == "error"]
    if errors:
        raise PenflowError(
            f"code IR failed schema validation: {errors[0]['path']}: {errors[0]['message']}"
        )
    Path(args.out).write_text(json.dumps(ir, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _print(
        {"status": "PASS", "out": args.out, "screens": len(ir["screens"]), "kind": ir["kind"]},
        args.json,
    )
    return 0


def cmd_validate_code_ir(args: argparse.Namespace) -> int:
    # @spec FR-008: Strict code IR validation CLI — .specs/features/045-penflow-json-only-strict-contract-v2/spec.md#fr-008
    issues = validate_code_ir(load_tree(args.code_ir))
    code = _exit_code(issues, _is_lenient(args))
    _print({"status": _status(code), "issues": issues}, args.json)
    return code


def cmd_codegen(args: argparse.Namespace) -> int:
    ir = load_tree(args.ir)
    generators = {"swiftui": swiftui, "react": react, "rust": rust_dioxus}
    Path(args.out).write_text(generators[args.target](ir), encoding="utf-8")
    _print({"status": "PASS", "out": args.out}, args.json)
    return 0


def cmd_ci(args: argparse.Namespace) -> int:
    # @spec FR-004: strict threshold default 0.98 — .specs/features/049-strict-mode-default-blocking-drift/spec.md#fr-004
    threshold = _resolve_threshold(args.threshold, _is_lenient(args))
    expected_path = Path("expected-ui-tree.json")
    write_expected_tree(args.pen, expected_path)
    report = compare_tree_files(
        expected_path,
        args.actual,
        json_out="compare-report.json",
        markdown_out="compare-report.md",
        threshold=threshold,
    )
    code = 1 if report["status"] != "PASS" else _exit_code(report["issues"], _is_lenient(args))
    _print({"status": _status(code), "score": report["score"], "threshold": threshold}, args.json)
    return code


def cmd_review_report(args: argparse.Namespace) -> int:
    # @spec FR-009: JSON-only review report artifact — .specs/features/045-penflow-json-only-strict-contract-v2/spec.md#fr-009
    report = review_compare_report(args.report)
    if args.out:
        Path(args.out).write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    _print(report | {"out": args.out}, args.json)
    return 0


def cmd_fix_report(args: argparse.Namespace) -> int:
    # @spec FR-009: JSON-only fix report artifact — .specs/features/045-penflow-json-only-strict-contract-v2/spec.md#fr-009
    report = fix_compare_report(args.report)
    if args.out:
        Path(args.out).write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    _print(report | {"out": args.out}, args.json)
    return 0


def cmd_validate_report(args: argparse.Namespace) -> int:
    # @spec FR-009: Structured report schema validation — .specs/features/045-penflow-json-only-strict-contract-v2/spec.md#fr-009
    report = load_tree(args.report)
    issues = _validate_report_schema(report, args.report) if args.schema else []
    code = _exit_code(issues, _is_lenient(args))
    _print({"status": _status(code), "issues": issues}, args.json)
    return code


def cmd_demo(args: argparse.Namespace) -> int:
    files = build_demo(args.out)
    _print({"status": "PASS", "files": files}, args.json)
    return 0
