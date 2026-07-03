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
import re
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .checklist import ChecklistSeedError, seed_checklist_from_drift
from .codegen import react, rust_dioxus, swiftui
from .compare import LENIENT_THRESHOLD, STRICT_THRESHOLD, compare_tree_files
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
from .drift import detect_drift
from .evidence import validate_visual_evidence
from .flow_contract import (
    FlowContractValidationError,
    interactive_coverage_report,
    load_flow_contract_v2,
    validate_flow_contract_v2,
)
from .flow_contract_migration import migrate_flow_md_to_contract_json
from .flow_specs import validate_flow_specs_dir
from .llm import fix_compare_report, review_compare_report
from .pen import (
    bbox_issues,
    inspect_pen,
    load_pen,
    parse_pen,
    validate_pen_context,
    validate_pen_context_against_contract,
)
from .pencil_sync import PencilSyncError, sync_pencil_to_disk
from .reference_fidelity import validate_reference_fidelity
from .reverse import reverse_pen
from .run_pipeline import RunPipelineError, run_pipeline
from .semantic import write_semantic_tree
from .semantic_draft import write_pen_draft_from_semantic_tree
from .semantic_enrichment import enrich_pen_from_semantic_tree
from .semantic_mapping import write_pencil_context_map
from .semantic_validation import validate_semantic_tree, validate_semantic_tree_file
from .schema_cache import load_schema
from .theme import load_theme, theme_fingerprint
from .token_lint import (
    DEFAULT_FONTSIZE_SCALE,
    DEFAULT_RADIUS_SCALE,
    DEFAULT_SPACING_SCALE,
    lint_tokens,
)
from .tree import load_tree, validate_actual_tree, write_expected_tree
from .visual_metrics import audit_visual, write_visual_metrics_report


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except (PenflowError, FlowContractValidationError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="penflow")
    parser.add_argument(
        "--json", action="store_true", help="print machine-readable JSON when supported"
    )
    # Distinct dest: argparse subparser defaults must not clobber the global flag.
    parser.add_argument(
        "--lenient",
        dest="lenient_global",
        action="store_true",
        help="do not fail on warning-severity issues (strict is the default)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run the full Penflow gate chain for a workspace")
    run.add_argument("--target", required=True, help="workspace containing Penflow artifacts")
    run.add_argument("--theme-css", default=None, help="optional theme.css path")
    run.add_argument("--references", default=None, help="optional references directory")
    run.add_argument("--strict", action="store_true", help="fail on warning-only gates")
    run.add_argument("--json", action="store_true", help="print machine-readable JSON")
    run.set_defaults(func=cmd_run)

    inspect_cmd = sub.add_parser("inspect", help="inspect a .pen file")
    inspect_cmd.add_argument("--json", action="store_true", help="print machine-readable JSON")
    inspect_cmd.add_argument("pen")
    inspect_cmd.set_defaults(func=cmd_inspect)

    pencil_sync = sub.add_parser("pencil-sync", help="save Pencil editor state and re-inspect disk")
    pencil_sync.add_argument("pen")
    pencil_sync.add_argument("--expect-min-nodes", type=int, default=None)
    pencil_sync.add_argument("--expect-screens", type=int, default=None)
    pencil_sync.add_argument("--json", action="store_true", help="print machine-readable JSON")
    pencil_sync.set_defaults(func=cmd_pencil_sync)

    validate_pen = sub.add_parser(
        "validate-pen", aliases=["validate"], help="validate .pen context"
    )
    validate_pen.add_argument("--json", action="store_true", help="print machine-readable JSON")
    validate_pen.add_argument("--contract", default=None, help="v2 flow contract.json")
    validate_pen.add_argument("pen")
    _add_lenient(validate_pen)
    validate_pen.set_defaults(func=cmd_validate_pen)

    expected = sub.add_parser("export-expected", help="export expected UI tree from .pen")
    expected.add_argument("--json", action="store_true", help="print machine-readable JSON")
    expected.add_argument("pen")
    expected.add_argument("-o", "--out", default="expected-ui-tree.json")
    _add_lenient(expected)
    expected.set_defaults(func=cmd_export_expected)

    semantic = sub.add_parser(
        "export-semantic-tree", help="export semantic UI tree from flow-ui-contract specs"
    )
    semantic.add_argument("--json", action="store_true", help="print machine-readable JSON")
    semantic.add_argument("specs_dir")
    semantic.add_argument("-o", "--out", default="semantic-ui-tree.json")
    _add_lenient(semantic)
    semantic.set_defaults(func=cmd_export_semantic_tree)

    validate_flow_specs = sub.add_parser(
        "validate-flow-specs", help="validate flow-ui-contract Markdown specs"
    )
    validate_flow_specs.add_argument(
        "--json", action="store_true", help="print machine-readable JSON"
    )
    validate_flow_specs.add_argument("specs_dir")
    _add_lenient(validate_flow_specs)
    validate_flow_specs.set_defaults(func=cmd_validate_flow_specs)

    validate_flow_contract_cmd = sub.add_parser(
        "validate-flow-contract", help="validate strict v2 flow contract JSON"
    )
    validate_flow_contract_cmd.add_argument(
        "--json", action="store_true", help="print machine-readable JSON"
    )
    validate_flow_contract_cmd.add_argument("contract")
    _add_lenient(validate_flow_contract_cmd)
    validate_flow_contract_cmd.set_defaults(func=cmd_validate_flow_contract)

    migrate_flow_contract_cmd = sub.add_parser(
        "migrate-flow-md-to-contract-json",
        help="explicitly migrate legacy Markdown flow specs to review-blocked v2 JSON",
    )
    migrate_flow_contract_cmd.add_argument(
        "--json", action="store_true", help="print machine-readable JSON"
    )
    migrate_flow_contract_cmd.add_argument("specs_dir")
    migrate_flow_contract_cmd.add_argument("--out", required=True)
    migrate_flow_contract_cmd.set_defaults(func=cmd_migrate_flow_contract)

    validate_semantic = sub.add_parser(
        "validate-semantic-tree", help="validate semantic UI tree contract"
    )
    validate_semantic.add_argument(
        "--json", action="store_true", help="print machine-readable JSON"
    )
    validate_semantic.add_argument("semantic_tree")
    _add_lenient(validate_semantic)
    validate_semantic.set_defaults(func=cmd_validate_semantic_tree)

    semantic_draft = sub.add_parser(
        "draft-pen-from-tree", help="generate Pencil draft from semantic UI tree"
    )
    semantic_draft.add_argument("--json", action="store_true", help="print machine-readable JSON")
    semantic_draft.add_argument("semantic_tree")
    semantic_draft.add_argument("-o", "--out", default="ui.pen")
    semantic_draft.add_argument("--theme-css", default=None, help="project theme.css to apply")
    semantic_draft.set_defaults(func=cmd_draft_pen_from_tree)

    enrich = sub.add_parser("enrich-pen", help="enrich existing Pencil file from semantic UI tree")
    enrich.add_argument("--json", action="store_true", help="print machine-readable JSON")
    enrich.add_argument("pen")
    enrich.add_argument("semantic_tree")
    enrich.add_argument("-o", "--out", required=True)
    enrich.set_defaults(func=cmd_enrich_pen)

    map_context = sub.add_parser("map-pencil-context", help="map semantic nodes to Pencil nodes")
    map_context.add_argument("--json", action="store_true", help="print machine-readable JSON")
    map_context.add_argument("pen")
    map_context.add_argument("semantic_tree")
    map_context.add_argument("-o", "--out", required=True)
    map_context.add_argument("--pen-out", default=None)
    map_context.add_argument(
        "--strict-anchors",
        action="store_true",
        help="exit 1 when mapping leaves ambiguous, unmapped, or placeholder anchors",
    )
    map_context.add_argument(
        "--create-placeholders",
        action="store_true",
        help="record missing semantic nodes as placeholders; report status stays PARTIAL",
    )
    map_context.set_defaults(func=cmd_map_pencil_context)

    reverse = sub.add_parser("reverse-pen", help="reverse Pencil file into flow specs")
    reverse.add_argument("--json", action="store_true", help="print machine-readable JSON")
    reverse.add_argument("pen")
    reverse.add_argument("--out", required=True)
    reverse.add_argument("--enrich", action="store_true")
    _add_lenient(reverse)
    reverse.set_defaults(func=cmd_reverse_pen)

    drift = sub.add_parser(
        "detect-drift", help="detect drift across specs, semantic tree, and Pencil"
    )
    drift.add_argument("--json", action="store_true", help="print machine-readable JSON")
    drift.add_argument("specs_dir")
    drift.add_argument("semantic_tree")
    drift.add_argument("pen")
    drift.add_argument("--out", required=True)
    drift.add_argument("--markdown", default=None)
    _add_lenient(drift)
    drift.set_defaults(func=cmd_detect_drift)

    # @spec FR-001: checklist-from-drift subcommand — .specs/features/055-checklist-from-drift-seeding/spec.md#fr-001
    # No _add_lenient: generation command with a fail-closed input contract,
    # not a validating command governed by the 049 exit policy.
    checklist_seed = sub.add_parser(
        "checklist-from-drift", help="seed a Mockup Factory checklist from a drift report"
    )
    checklist_seed.add_argument("--json", action="store_true", help="print machine-readable JSON")
    checklist_seed.add_argument("drift_report")
    checklist_seed.add_argument("--out", required=True)
    checklist_seed.add_argument("--group", default=None)
    checklist_seed.set_defaults(func=cmd_checklist_from_drift)

    actual = sub.add_parser("validate-actual", help="validate actual runtime UI tree")
    actual.add_argument("--json", action="store_true", help="print machine-readable JSON")
    actual.add_argument(
        "--schema",
        action="store_true",
        help="also run JSON Schema validation (draft 2020-12)",
    )
    actual.add_argument("actual")
    _add_lenient(actual)
    actual.set_defaults(func=cmd_validate_actual)

    compare = sub.add_parser("compare-tree", help="compare expected and actual UI trees")
    compare.add_argument("--json", action="store_true", help="print machine-readable JSON")
    compare.add_argument("expected")
    compare.add_argument("actual")
    compare.add_argument("--out", default="compare-report.json")
    # Default None: distinguish an explicit threshold from the mode default.
    compare.add_argument("--threshold", type=float, default=None)
    _add_lenient(compare)
    compare.set_defaults(func=cmd_compare_tree)

    consistency = sub.add_parser(
        "check-consistency",
        help="check cross-screen component consistency in an expected UI tree",
    )
    consistency.add_argument("--json", action="store_true", help="print machine-readable JSON")
    consistency.add_argument("expected")
    consistency.add_argument("-o", "--out", default="consistency-report.json")
    consistency.add_argument(
        "--group-by",
        choices=["role", "role+intent", "role+intent+variant", "role+intent+variant+size-class"],
        default=None,
        help="component signature granularity (default: role+intent+variant)",
    )
    _add_lenient(consistency)
    consistency.set_defaults(func=cmd_check_consistency)

    visual_metrics = sub.add_parser(
        "audit-visual",
        help="audit deterministic visual metrics (contrast, touch targets, geometry)"
        " in an expected UI tree",
    )
    visual_metrics.add_argument("--json", action="store_true", help="print machine-readable JSON")
    visual_metrics.add_argument("expected")
    visual_metrics.add_argument(
        "--theme-css", default=None, help="project theme.css resolving $pf-* fill references"
    )
    visual_metrics.add_argument(
        "--layout-snapshot",
        default=None,
        help="Pencil snapshot_layout JSON whose real bboxes drive overlap/overflow checks",
    )
    visual_metrics.add_argument("-o", "--out", default="visual-metrics-report.json")
    _add_lenient(visual_metrics)
    visual_metrics.set_defaults(func=cmd_audit_visual)

    visual_evidence = sub.add_parser(
        "validate-visual-evidence",
        help="validate a Pencil visual-evidence packet"
        " (manifest, screen PNGs, locked vision report, optional layout snapshot)",
    )
    visual_evidence.add_argument("--json", action="store_true", help="print machine-readable JSON")
    visual_evidence.add_argument("evidence_dir")
    visual_evidence.add_argument(
        "--expected",
        default=None,
        help="expected-ui-tree.json enabling screen coverage and snapshot bbox cross-checks",
    )
    visual_evidence.add_argument(
        "--theme-css",
        default=None,
        help="theme.css whose sha256 must match the manifest theme stamp",
    )
    _add_lenient(visual_evidence)
    visual_evidence.set_defaults(func=cmd_validate_visual_evidence)

    reference_fidelity = sub.add_parser(
        "validate-reference-fidelity",
        help="validate exported evidence PNGs against reference images",
    )
    reference_fidelity.add_argument(
        "--json", action="store_true", help="print machine-readable JSON"
    )
    reference_fidelity.add_argument("evidence_dir")
    reference_fidelity.add_argument(
        "--references",
        required=True,
        help="references directory containing references-manifest.json",
    )
    reference_fidelity.set_defaults(func=cmd_validate_reference_fidelity)

    flow = sub.add_parser("validate-flow", help="validate flow contract")
    flow.add_argument("--json", action="store_true", help="print machine-readable JSON")
    flow.add_argument("flow")
    _add_lenient(flow)
    flow.set_defaults(func=cmd_validate_flow)

    screen = sub.add_parser("validate-screen", help="validate screen contract")
    screen.add_argument("--json", action="store_true", help="print machine-readable JSON")
    screen.add_argument("screen")
    _add_lenient(screen)
    screen.set_defaults(func=cmd_validate_screen)

    flow_to_screen = sub.add_parser("flow-to-screens", help="generate screen contracts from flow")
    flow_to_screen.add_argument("--json", action="store_true", help="print machine-readable JSON")
    flow_to_screen.add_argument("flow")
    flow_to_screen.add_argument("--out-dir", default="screen-contracts")
    flow_to_screen.set_defaults(func=cmd_flow_to_screens)

    draft = sub.add_parser("draft-pen", help="generate Pencil draft from screen contract")
    draft.add_argument("--json", action="store_true", help="print machine-readable JSON")
    draft.add_argument("screen")
    draft.add_argument("-o", "--out", default="draft.pen")
    draft.set_defaults(func=cmd_draft_pen)

    update = sub.add_parser("update-pen", help="update .pen nodes by semantic_id")
    update.add_argument("--json", action="store_true", help="print machine-readable JSON")
    update.add_argument("pen")
    update.add_argument("updates")
    update.add_argument("-o", "--out", required=True)
    update.set_defaults(func=cmd_update_pen)

    tokens = sub.add_parser("extract-tokens", help="extract design tokens from .pen")
    tokens.add_argument("--json", action="store_true", help="print machine-readable JSON")
    tokens.add_argument("pen")
    tokens.add_argument("-o", "--out", default=None)
    _add_lenient(tokens)
    tokens.set_defaults(func=cmd_extract_tokens)

    lint = sub.add_parser(
        "lint-tokens", help="lint .pen design tokens against a theme and numeric scales"
    )
    lint.add_argument("--json", action="store_true", help="print machine-readable JSON")
    lint.add_argument("pen")
    lint.add_argument("--theme-css", default=None, help="project theme.css defining the palette")
    lint.add_argument("-o", "--out", default="token-lint-report.json")
    lint.add_argument(
        "--spacing-scale",
        default=None,
        help=f"comma-separated gap/padding scale (default: {','.join(str(int(v)) for v in DEFAULT_SPACING_SCALE)})",
    )
    lint.add_argument(
        "--radius-scale",
        default=None,
        help=f"comma-separated cornerRadius scale (default: {','.join(str(int(v)) for v in DEFAULT_RADIUS_SCALE)}; theme radius is always allowed)",
    )
    lint.add_argument(
        "--fontsize-scale",
        default=None,
        help=f"comma-separated fontSize scale (default: {','.join(str(int(v)) for v in DEFAULT_FONTSIZE_SCALE)})",
    )
    _add_lenient(lint)
    lint.set_defaults(func=cmd_lint_tokens)

    # @spec FR-003: theme-fingerprint subcommand — .specs/features/056-evidence-run-identity-theme-fingerprint/spec.md#fr-003
    # No _add_lenient: the command emits no issues, so there is nothing for
    # the 049 exit policy to relax.
    fingerprint_cmd = sub.add_parser(
        "theme-fingerprint", help="fingerprint a theme CSS file (sha256 of raw bytes)"
    )
    fingerprint_cmd.add_argument("--json", action="store_true", help="print machine-readable JSON")
    fingerprint_cmd.add_argument("theme_css")
    fingerprint_cmd.set_defaults(func=cmd_theme_fingerprint)

    ir = sub.add_parser("export-ir", help="export code IR from screen contract")
    ir.add_argument("--json", action="store_true", help="print machine-readable JSON")
    ir.add_argument("screen")
    ir.add_argument("--expected", default=None)
    ir.add_argument("-o", "--out", default="code-ir.json")
    ir.set_defaults(func=cmd_export_ir)

    code_ir = sub.add_parser(
        "code-ir", help="export deterministic code IR from contextualized Pencil context"
    )
    code_ir.add_argument("--json", action="store_true", help="print machine-readable JSON")
    code_ir.add_argument("--from-context", dest="from_context", required=True)
    code_ir.add_argument("--semantic-tree", dest="semantic_tree", default=None)
    code_ir.add_argument("--context-map", dest="context_map", default=None)
    code_ir.add_argument("--contract", dest="contract", default=None)
    code_ir.add_argument("--flow-id", dest="flow_id", default=None)
    code_ir.add_argument("--flow-name", dest="flow_name", default=None)
    code_ir.add_argument("-o", "--out", required=True)
    code_ir.set_defaults(func=cmd_code_ir)

    validate_code_ir_cmd = sub.add_parser("validate-code-ir", help="validate code IR JSON")
    validate_code_ir_cmd.add_argument(
        "--json", action="store_true", help="print machine-readable JSON"
    )
    validate_code_ir_cmd.add_argument("code_ir")
    _add_lenient(validate_code_ir_cmd)
    validate_code_ir_cmd.set_defaults(func=cmd_validate_code_ir)

    codegen = sub.add_parser("codegen", help="generate SwiftUI, React, or Rust Dioxus code from IR")
    codegen.add_argument("--json", action="store_true", help="print machine-readable JSON")
    codegen.add_argument("target", choices=["swiftui", "react", "rust"])
    codegen.add_argument("ir")
    codegen.add_argument("-o", "--out", required=True)
    codegen.set_defaults(func=cmd_codegen)

    ci = sub.add_parser("ci", help="run CI-style validation")
    ci.add_argument("--json", action="store_true", help="print machine-readable JSON")
    ci.add_argument("pen")
    ci.add_argument("actual")
    # Default None: distinguish an explicit threshold from the mode default.
    ci.add_argument("--threshold", type=float, default=None)
    _add_lenient(ci)
    ci.set_defaults(func=cmd_ci)

    review = sub.add_parser("review-report", help="explain a compare report in stable Markdown")
    review.add_argument("--json", action="store_true", help="print machine-readable JSON")
    review.add_argument("report")
    review.add_argument("-o", "--out", default=None)
    review.set_defaults(func=cmd_review_report)

    fix = sub.add_parser(
        "fix-report", help="suggest fixes from a compare report in stable Markdown"
    )
    fix.add_argument("--json", action="store_true", help="print machine-readable JSON")
    fix.add_argument("report")
    fix.add_argument("-o", "--out", default=None)
    fix.set_defaults(func=cmd_fix_report)

    validate_report = sub.add_parser("validate-report", help="validate JSON report artifacts")
    validate_report.add_argument("--json", action="store_true", help="print machine-readable JSON")
    validate_report.add_argument("--schema", action="store_true", help="run bundled JSON Schema")
    validate_report.add_argument("report")
    _add_lenient(validate_report)
    validate_report.set_defaults(func=cmd_validate_report)

    demo = sub.add_parser("demo", help="write an end-to-end demo project")
    demo.add_argument("--json", action="store_true", help="print machine-readable JSON")
    demo.add_argument("--out", default="examples/generated-demo")
    demo.set_defaults(func=cmd_demo)
    return parser


def cmd_inspect(args: argparse.Namespace) -> int:
    result = inspect_pen(args.pen)
    _print(result, args.json)
    return 1 if result["errors"] else 0


def cmd_run(args: argparse.Namespace) -> int:
    try:
        summary = run_pipeline(
            args.target,
            theme_css=args.theme_css,
            references=args.references,
            strict=args.strict,
        )
    except RunPipelineError as error:
        raise PenflowError(str(error)) from error
    _print(summary, args.json)
    return int(summary["exit"])


def cmd_pencil_sync(args: argparse.Namespace) -> int:
    try:
        result = sync_pencil_to_disk(
            args.pen,
            expect_min_nodes=args.expect_min_nodes,
            expect_screens=args.expect_screens,
        )
    except PencilSyncError as error:
        raise PenflowError(str(error)) from error
    _print(result, args.json)
    return 0 if result["status"] == "PASS" else 1


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


def cmd_map_pencil_context(args: argparse.Namespace) -> int:
    passed, issues = validate_semantic_tree_file(args.semantic_tree)
    if not passed:
        _print({"status": "FAIL", "issues": issues}, args.json)
        return 1
    context_map = write_pencil_context_map(
        args.pen,
        args.semantic_tree,
        args.out,
        pen_out=args.pen_out,
        create_placeholders=args.create_placeholders,
    )
    _print(context_map | {"out": args.out, "pen_out": args.pen_out}, args.json)
    if args.strict_anchors and context_map["status"] != "PASS":
        return 1
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
    except ValueError as error:
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


def _add_lenient(sub_parser: argparse.ArgumentParser) -> None:
    """Mirror the global --lenient flag so it works before or after the subcommand."""
    sub_parser.add_argument(
        "--lenient",
        action="store_true",
        help="do not fail on warning-severity issues (strict is the default)",
    )


def _is_lenient(args: argparse.Namespace) -> bool:
    return bool(getattr(args, "lenient_global", False) or getattr(args, "lenient", False))


def _exit_code(issues: list[dict[str, Any]], lenient: bool) -> int:
    """Strict-by-default exit policy (feature 049).

    Errors always fail; warnings fail unless ``lenient`` is set.
    """
    severities = {issue.get("severity") for issue in issues}
    if "error" in severities:
        return 1
    if "warning" in severities and not lenient:
        return 1
    return 0


def _status(exit_code: int) -> str:
    return "PASS" if exit_code == 0 else "FAIL"


def _print(data: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(data, indent=2, sort_keys=True))
        return
    if "status" in data:
        print(f"Status: {data['status']}")
    for key, value in data.items():
        if key == "status":
            continue
        print(f"{key}: {value}")


def _has_errors(issues: list[dict[str, Any]]) -> bool:
    return any(issue.get("severity") == "error" for issue in issues)


def _resolve_threshold(explicit: float | None, lenient: bool) -> float:
    """An explicit --threshold always wins; otherwise the mode picks the default."""
    if explicit is not None:
        return explicit
    return LENIENT_THRESHOLD if lenient else STRICT_THRESHOLD


_SUPPORTED_REPORT_SCHEMA_KEYWORDS = frozenset(
    {
        "$comment",
        "$id",
        "$schema",
        "additionalProperties",
        "const",
        "description",
        "enum",
        "items",
        "minLength",
        "pattern",
        "properties",
        "required",
        "title",
        "type",
    }
)


def _validate_report_schema(report: Any, report_path: str | Path) -> list[dict[str, Any]]:
    if not isinstance(report, dict):
        return [{"severity": "error", "path": "$", "message": "report must be an object"}]
    schema_name = _report_schema_name(report, Path(report_path).name)
    schema = load_schema(schema_name)
    issues = _validate_json_schema_subset(report, schema, "$")
    if report.get("kind") == "penflow-mockup-audit":
        issues.extend(_validate_mockup_audit_receipts(report, Path(report_path)))
    return sorted(issues, key=lambda item: (item["path"], item["message"]))


def _validate_mockup_audit_receipts(
    report: dict[str, Any], report_path: Path
) -> list[dict[str, Any]]:
    gates = report.get("gates")
    if not isinstance(gates, list):
        return []
    base = report_path.parent
    issues: list[dict[str, Any]] = []
    for index, gate in enumerate(gates):
        if not isinstance(gate, dict):
            continue
        result = gate.get("result")
        exit_code = gate.get("exit_code")
        referenced_report = gate.get("report_path")
        path_prefix = f"$.gates[{index}]"
        if result == "not_run":
            if exit_code is not None or referenced_report is not None:
                issues.append(
                    {
                        "severity": "error",
                        "path": path_prefix,
                        "message": "not_run gates must use null exit_code and null report_path",
                    }
                )
            continue
        if result == "pass" and exit_code != 0:
            issues.append(
                {
                    "severity": "error",
                    "path": f"{path_prefix}.exit_code",
                    "message": "pass gate must have exit_code 0",
                }
            )
        if result == "fail" and (not isinstance(exit_code, int) or exit_code == 0):
            issues.append(
                {
                    "severity": "error",
                    "path": f"{path_prefix}.exit_code",
                    "message": "fail gate must have a non-zero exit_code",
                }
            )
        if not isinstance(referenced_report, str) or not referenced_report:
            issues.append(
                {
                    "severity": "error",
                    "path": f"{path_prefix}.report_path",
                    "message": "executed gates must reference an existing report_path",
                }
            )
            continue
        resolved_report = (
            Path(referenced_report)
            if Path(referenced_report).is_absolute()
            else base / referenced_report
        )
        if not resolved_report.is_file():
            issues.append(
                {
                    "severity": "error",
                    "path": f"{path_prefix}.report_path",
                    "message": f"referenced report_path does not exist: {referenced_report}",
                }
            )
    return issues


def _validate_json_schema_subset(
    value: Any, schema: dict[str, Any], path: str
) -> list[dict[str, Any]]:
    """Validate the strict subset used by bundled report schemas."""
    issues = _unsupported_schema_keyword_issues(schema, path)
    if issues:
        return issues
    expected_type = schema.get("type")
    if expected_type and not _matches_json_type(value, expected_type):
        issues.append({"severity": "error", "path": path, "message": f"expected {expected_type}"})
        return issues
    if "const" in schema and value != schema["const"]:
        issues.append(
            {"severity": "error", "path": path, "message": f"expected {schema['const']!r}"}
        )
    if "enum" in schema and value not in schema["enum"]:
        issues.append(
            {"severity": "error", "path": path, "message": f"expected one of {schema['enum']}"}
        )
    if "minLength" in schema and isinstance(value, str) and len(value) < schema["minLength"]:
        issues.append(
            {
                "severity": "error",
                "path": path,
                "message": f"expected at least {schema['minLength']} characters",
            }
        )
    # @spec FR-001: validate-report path accepts the new schema — .specs/features/056-evidence-run-identity-theme-fingerprint/spec.md#fr-001
    # re.search is the JSON Schema `pattern` semantics; anchored patterns
    # (^...$, like the manifest sha256) therefore behave as exact matches.
    if "pattern" in schema and isinstance(value, str):
        pattern = schema["pattern"]
        if not isinstance(pattern, str):
            # Fail-closed on malformed bundled schemas: report deterministically
            # instead of crashing the validator on a non-string pattern.
            issues.append(
                {
                    "severity": "error",
                    "path": f"{path}.__schema__.pattern",
                    "message": "schema pattern must be a string",
                }
            )
        else:
            try:
                matched = re.search(pattern, value)
            except re.error as exc:
                issues.append(
                    {
                        "severity": "error",
                        "path": f"{path}.__schema__.pattern",
                        "message": f"schema pattern is not a valid regex: {exc}",
                    }
                )
            else:
                if matched is None:
                    issues.append(
                        {
                            "severity": "error",
                            "path": path,
                            "message": f"expected string matching {pattern}",
                        }
                    )
    if isinstance(value, dict):
        for key in schema.get("required", []) or []:
            if key not in value:
                issues.append(
                    {"severity": "error", "path": f"{path}.{key}", "message": f"{key} is required"}
                )
        properties = (
            schema.get("properties", {}) if isinstance(schema.get("properties"), dict) else {}
        )
        if schema.get("additionalProperties") is False:
            for key in sorted(set(value) - set(properties)):
                issues.append(
                    {
                        "severity": "error",
                        "path": f"{path}.{key}",
                        "message": "additional property is not allowed",
                    }
                )
        for key, child_schema in properties.items():
            if key in value and isinstance(child_schema, dict):
                issues.extend(
                    _validate_json_schema_subset(value[key], child_schema, f"{path}.{key}")
                )
    elif isinstance(value, list) and isinstance(schema.get("items"), dict):
        for index, item in enumerate(value):
            issues.extend(_validate_json_schema_subset(item, schema["items"], f"{path}[{index}]"))
    return issues


def _unsupported_schema_keyword_issues(schema: dict[str, Any], path: str) -> list[dict[str, Any]]:
    issues = [
        {
            "severity": "error",
            "path": f"{path}.__schema__.{keyword}",
            "message": f"unsupported schema keyword: {keyword}",
        }
        for keyword in sorted(set(schema) - _SUPPORTED_REPORT_SCHEMA_KEYWORDS)
    ]
    properties = schema.get("properties", {})
    if isinstance(properties, dict):
        for key, child_schema in properties.items():
            if isinstance(child_schema, dict):
                issues.extend(_unsupported_schema_keyword_issues(child_schema, f"{path}.{key}"))
    items = schema.get("items")
    if isinstance(items, dict):
        issues.extend(_unsupported_schema_keyword_issues(items, f"{path}[]"))
    additional_properties = schema.get("additionalProperties")
    if isinstance(additional_properties, dict):
        issues.extend(_unsupported_schema_keyword_issues(additional_properties, f"{path}.*"))
    return issues


def _matches_json_type(value: Any, expected: str | list[str]) -> bool:
    expected_types = [expected] if isinstance(expected, str) else expected
    checks = {
        "object": lambda item: isinstance(item, dict),
        "array": lambda item: isinstance(item, list),
        "string": lambda item: isinstance(item, str),
        "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
        "number": lambda item: isinstance(item, (int, float)) and not isinstance(item, bool),
        "boolean": lambda item: isinstance(item, bool),
        "null": lambda item: item is None,
    }
    return any(
        checks[schema_type](value) for schema_type in expected_types if schema_type in checks
    )


def _report_schema_name(report: dict[str, Any], filename: str) -> str:
    kind = report.get("kind")
    if kind == "penflow-review-report":
        return "review-report.schema.json"
    if kind == "penflow-fix-report":
        return "fix-report.schema.json"
    if kind == "penflow-drift-report":
        return "drift-report.schema.json"
    if kind == "penflow-token-lint-report":
        # @spec FR-005: Strict report schema registration — .specs/features/046-lint-design-tokens/spec.md#fr-005
        return "token-lint-report.schema.json"
    if kind == "penflow-consistency-report":
        # @spec FR-004: Strict consistency report schema registration — .specs/features/047-cross-screen-consistency-check/spec.md#fr-004
        return "consistency-report.schema.json"
    if kind == "penflow-visual-metrics-report":
        # @spec FR-007: Strict visual metrics report schema registration — .specs/features/050-deterministic-visual-metrics-audit/spec.md#fr-007
        # Must match by kind: the filename heuristic below would route
        # "visual-metrics-report.json" to the mockup visual-report schema.
        return "visual-metrics-report.schema.json"
    if kind == "penflow-vision-report":
        # @spec FR-005: Strict vision report schema registration — .specs/features/051-vision-report-contract-evidence-validator/spec.md#fr-005
        return "vision-report.schema.json"
    if kind == "penflow-mockup-audit":
        # @spec FR-003: Hardened audit report schema registration — .specs/features/052-prescriptive-rubric-bounded-fix-loop/spec.md#fr-003
        return "mockup-validation-audit.schema.json"
    if kind == "penflow-mockup-checklist":
        # @spec FR-003: Hardened checklist schema registration — .specs/features/052-prescriptive-rubric-bounded-fix-loop/spec.md#fr-003
        return "mockup-validation-checklist.schema.json"
    if "compare" in filename or {"score", "summary", "issues"}.issubset(report):
        return "compare-report.schema.json"
    if "visual" in filename:
        return "mockup-validation-visual-report.schema.json"
    if "checklist" in filename:
        return "mockup-validation-checklist.schema.json"
    if "audit" in filename:
        return "mockup-validation-audit.schema.json"
    if "manifest" in filename:
        return "mockup-validation-manifest.schema.json"
    raise PenflowError(f"Unknown report schema for {filename}")


class PenflowError(RuntimeError):
    pass
