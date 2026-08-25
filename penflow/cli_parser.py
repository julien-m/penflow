# @spec(FR-001)
# @spec(FR-002)
# @spec(FR-003)
# @spec(FR-004)
# @spec(FR-005)
# @spec(FR-007)
# @spec(FR-008)
# @spec(FR-009)

import argparse
from typing import Any

from . import __version__
from .artifact_policy import COMMAND_POLICIES, CommandClassification
from .cli_commands_b import (
    cmd_audit_visual,
    cmd_check_consistency,
    cmd_ci,
    cmd_code_ir,
    cmd_codegen,
    cmd_compare_tree,
    cmd_demo,
    cmd_draft_pen,
    cmd_export_ir,
    cmd_extract_tokens,
    cmd_fix_report,
    cmd_flow_to_screens,
    cmd_lint_tokens,
    cmd_review_report,
    cmd_theme_fingerprint,
    cmd_update_pen,
    cmd_validate_code_ir,
    cmd_validate_flow,
    cmd_validate_reference_fidelity,
    cmd_validate_report,
    cmd_validate_screen,
    cmd_validate_visual_evidence,
)
from .cli_reporting import _add_lenient
from .token_lint import DEFAULT_FONTSIZE_SCALE, DEFAULT_RADIUS_SCALE, DEFAULT_SPACING_SCALE


from .cli_parser_basics import (
    _register_actual,
    _register_causal_migration,
    _register_doctor_run,
    _register_drift,
    _register_inspect_persistence,
    _register_semantic_producers,
    _register_validation_contracts,
)


def _register_compare(sub: Any) -> None:
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


def _register_visual(sub: Any) -> None:
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


def _register_flow_tools(sub: Any) -> None:
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
    draft.add_argument("-o", "--out", default="ui.pen")
    draft.set_defaults(func=cmd_draft_pen)

    update = sub.add_parser("update-pen", help="update .pen nodes by semantic_id")
    update.add_argument("--json", action="store_true", help="print machine-readable JSON")
    update.add_argument("pen")
    update.add_argument("updates")
    update.add_argument("-o", "--out", default="ui.pen")
    update.set_defaults(func=cmd_update_pen)

    tokens = sub.add_parser("extract-tokens", help="extract design tokens from .pen")
    tokens.add_argument("--json", action="store_true", help="print machine-readable JSON")
    tokens.add_argument("pen")
    tokens.add_argument("-o", "--out", default=None)
    _add_lenient(tokens)
    tokens.set_defaults(func=cmd_extract_tokens)


def _register_token_tools(sub: Any) -> None:
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


def _register_ir_tools(sub: Any) -> None:
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


def _register_codegen_reports(sub: Any) -> None:
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


def _register_demo_projects(sub: Any) -> None:
    demo = sub.add_parser("demo", help="write an end-to-end demo project")
    demo.add_argument("--json", action="store_true", help="print machine-readable JSON")
    demo.add_argument("--out", default="examples/generated-demo")
    demo.set_defaults(func=cmd_demo)


def _register_project_health_arguments(sub: Any) -> None:
    """Add the shared consumer-project option to every governed command."""
    configured_parsers: set[int] = set()
    governed_commands = {
        policy.command
        for policy in COMMAND_POLICIES
        if policy.category is not CommandClassification.LIFECYCLE_EXEMPT
    }
    # Argparse aliases share a parser object, so identity deduplication avoids
    # registering --project twice on compatibility spellings.
    for command in sorted(governed_commands):
        command_parser = sub.choices.get(command)
        if command == "migrate-flow-contract":
            command_parser = sub.choices.get("migrate-flow-md-to-contract-json")
        if command_parser is None or id(command_parser) in configured_parsers:
            continue
        command_parser.add_argument(
            "--project",
            default=None,
            help="consumer Git project root for Doctor health governance",
        )
        configured_parsers.add(id(command_parser))


def build_parser() -> argparse.ArgumentParser:
    """Build the complete deterministic Penflow command parser."""
    parser = argparse.ArgumentParser(prog="penflow")
    parser.add_argument("--version", action="version", version=f"penflow {__version__}")
    parser.add_argument(
        "--json", action="store_true", help="print machine-readable JSON when supported"
    )
    parser.add_argument(
        "--lenient", dest="lenient_global", action="store_true", help="do not fail on warnings"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    _register_doctor_run(sub)
    _register_inspect_persistence(sub)
    _register_validation_contracts(sub)
    _register_causal_migration(sub)
    _register_semantic_producers(sub)
    _register_drift(sub)
    _register_actual(sub)
    _register_compare(sub)
    _register_visual(sub)
    _register_flow_tools(sub)
    _register_token_tools(sub)
    _register_ir_tools(sub)
    _register_codegen_reports(sub)
    _register_demo_projects(sub)
    _register_project_health_arguments(sub)
    return parser
