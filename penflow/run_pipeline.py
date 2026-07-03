"""Single-command Penflow gate orchestration for an existing workspace."""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable

from .consistency import check_consistency, write_consistency_report
from .contracts import (
    assert_contextualized_pen_input,
    code_ir_from_pen,
    validate_code_ir,
)
from .drift import detect_drift
from .evidence import validate_visual_evidence
from .flow_contract import (
    FlowContractValidationError,
    interactive_coverage_report,
    load_flow_contract_v2,
    validate_flow_contract_v2,
)
from .pen import (
    bbox_issues,
    load_pen,
    parse_pen,
    validate_pen_context,
    validate_pen_context_against_contract,
)
from .pencil_sync import PencilSyncError, sync_pencil_to_disk
from .reference_fidelity import validate_reference_fidelity
from .semantic import write_semantic_tree
from .semantic_mapping import write_pencil_context_map
from .semantic_validation import validate_semantic_tree, validate_semantic_tree_file
from .theme import theme_fingerprint
from .token_lint import lint_tokens
from .tree import write_expected_tree
from .visual_metrics import audit_visual, write_visual_metrics_report


REPORT_DIR = ".penflow-run"
RUN_REPORT = "run-report.json"
GATE_STATUS_PASS = "PASS"
GATE_STATUS_FAIL = "FAIL"
GATE_STATUS_ERROR = "ERROR"
GATE_STATUS_SKIP = "SKIP"


class RunPipelineError(RuntimeError):
    """Raised when the `penflow run` boundary receives invalid inputs."""


def run_pipeline(
    target: str | Path,
    *,
    theme_css: str | Path | None = None,
    references: str | Path | None = None,
    strict: bool = False,
) -> dict[str, Any]:
    """Run the deterministic Penflow gate chain for a workspace.

    Args:
        target: Workspace containing `flow-ui-contract/`, `ui.pen`, and optional
            `.mockup-validation/visual-evidence/`.
        theme_css: Optional theme CSS path; relative paths resolve inside target.
        references: Optional references directory; relative paths resolve inside
            target and arm the reference-fidelity gate.
        strict: When true, warning-only reports fail. Errors fail in all modes.

    Returns:
        Stable JSON-compatible run summary with one entry per gate and an
        aggregate exit code.
    """
    workspace = Path(target)
    if not workspace.is_dir():
        raise RunPipelineError(f"target workspace not found: {workspace}")

    paths = _workspace_paths(workspace)
    theme_path = _resolve_optional(workspace, theme_css)
    references_path = _resolve_optional(workspace, references)
    report_dir = workspace / REPORT_DIR
    report_dir.mkdir(parents=True, exist_ok=True)

    gates: dict[str, dict[str, Any]] = {}
    _record_gate(
        gates,
        "validate-flow-contract",
        report_dir / "validate-flow-contract.json",
        lambda: _gate_validate_flow_contract(paths["contract"], strict),
    )
    _record_gate(
        gates,
        "export-semantic-tree",
        paths["semantic_tree"],
        lambda: _gate_export_semantic_tree(paths["contract"], paths["semantic_tree"], strict),
    )
    _record_pencil_sync(gates, paths["pen"], report_dir / "pencil-sync.json")
    _record_gate(
        gates,
        "map-pencil-context",
        paths["context_map"],
        lambda: _gate_map_pencil_context(
            paths["pen"], paths["semantic_tree"], paths["context_map"]
        ),
    )
    _record_gate(
        gates,
        "validate-pen",
        report_dir / "validate-pen.json",
        lambda: _gate_validate_pen(paths["pen"], paths["contract"], strict),
    )
    _record_gate(
        gates,
        "export-expected",
        paths["expected_tree"],
        lambda: _gate_export_expected(paths["pen"], paths["expected_tree"], strict),
    )
    _record_gate(
        gates,
        "lint-tokens",
        paths["token_report"],
        lambda: _gate_lint_tokens(paths["pen"], theme_path, paths["token_report"], strict),
    )
    _record_gate(
        gates,
        "check-consistency",
        paths["consistency_report"],
        lambda: _gate_check_consistency(
            paths["expected_tree"], paths["consistency_report"], strict
        ),
    )
    _record_gate(
        gates,
        "audit-visual",
        paths["visual_report"],
        lambda: _gate_audit_visual(
            paths["expected_tree"],
            theme_path,
            paths["layout_snapshot"],
            paths["visual_report"],
            strict,
        ),
    )
    _record_gate(
        gates,
        "detect-drift",
        paths["drift_report"],
        lambda: _gate_detect_drift(
            paths["flow_contract_dir"],
            paths["semantic_tree"],
            paths["pen"],
            paths["drift_report"],
            paths["drift_markdown"],
            strict,
        ),
    )
    _record_gate(
        gates,
        "validate-visual-evidence",
        report_dir / "validate-visual-evidence.json",
        lambda: _gate_validate_visual_evidence(
            paths["visual_evidence_dir"],
            paths["expected_tree"],
            theme_path,
            strict,
        ),
    )
    _record_reference_fidelity(gates, paths["visual_evidence_dir"], references_path, report_dir)
    _record_gate(
        gates,
        "code-ir",
        paths["code_ir"],
        lambda: _gate_code_ir(
            paths["pen"],
            paths["semantic_tree"],
            paths["context_map"],
            paths["contract"],
            paths["code_ir"],
        ),
    )

    exit_code = _aggregate_exit(gates)
    summary = {
        "kind": "penflow-run-summary",
        "version": 1,
        "status": GATE_STATUS_PASS if exit_code == 0 else GATE_STATUS_FAIL,
        "target": str(workspace),
        "strict": strict,
        "exit": exit_code,
        "gates": gates,
    }
    _write_json(workspace / RUN_REPORT, summary)
    return summary


def _workspace_paths(workspace: Path) -> dict[str, Path]:
    visual_evidence_dir = _visual_evidence_dir(workspace)
    return {
        "flow_contract_dir": workspace / "flow-ui-contract",
        "contract": workspace / "flow-ui-contract" / "contract.json",
        "pen": workspace / "ui.pen",
        "semantic_tree": workspace / "semantic-ui-tree.json",
        "context_map": workspace / "pencil-context-map.json",
        "expected_tree": workspace / "expected-ui-tree.json",
        "token_report": workspace / "token-lint-report.json",
        "consistency_report": workspace / "consistency-report.json",
        "visual_report": workspace / "visual-metrics-report.json",
        "drift_report": workspace / "drift-report.json",
        "drift_markdown": workspace / "drift-report.md",
        "visual_evidence_dir": visual_evidence_dir,
        "layout_snapshot": visual_evidence_dir / "layout-snapshot.json",
        "code_ir": workspace / "code-ir.json",
    }


def _visual_evidence_dir(workspace: Path) -> Path:
    local = workspace / ".mockup-validation" / "visual-evidence"
    if local.exists():
        return local
    handoff = workspace.parent / "validation" / "mockup-validation" / "visual-evidence"
    if handoff.exists():
        return handoff
    return local


def _resolve_optional(workspace: Path, value: str | Path | None) -> Path | None:
    if value is None:
        return None
    path = Path(value)
    return path if path.exists() or path.is_absolute() else workspace / path


def _record_gate(
    gates: dict[str, dict[str, Any]],
    gate: str,
    report_path: Path,
    action: Callable[[], tuple[dict[str, Any], int]],
) -> None:
    try:
        report, exit_code = action()
        if report_path.suffix == ".json" and (
            _is_run_gate_report(report_path) or not report_path.exists()
        ):
            _write_json(report_path, report)
    except (
        FileNotFoundError,
        ValueError,
        json.JSONDecodeError,
        OSError,
        FlowContractValidationError,
        PencilSyncError,
    ) as error:
        exit_code = 2
        report = {
            "kind": "penflow-run-gate-error",
            "status": GATE_STATUS_ERROR,
            "gate": gate,
            "message": str(error),
        }
        _write_json(report_path, report)
    gates[gate] = {
        "status": _gate_status(report, exit_code),
        "report_path": str(report_path),
        "exit": exit_code,
    }


def _record_pencil_sync(gates: dict[str, dict[str, Any]], pen: Path, report_path: Path) -> None:
    if os.environ.get("PENFLOW_RUN_PENCIL_SYNC") != "1":
        report = {
            "kind": "penflow-pencil-sync",
            "status": GATE_STATUS_SKIP,
            "pen": str(pen),
            "message": "pencil-sync is skipped unless PENFLOW_RUN_PENCIL_SYNC=1 is set.",
        }
        _write_json(report_path, report)
        gates["pencil-sync"] = {
            "status": GATE_STATUS_SKIP,
            "report_path": str(report_path),
            "exit": 0,
        }
        return

    def action() -> tuple[dict[str, Any], int]:
        report = sync_pencil_to_disk(pen)
        return report, 0 if report["status"] == GATE_STATUS_PASS else 1

    _record_gate(gates, "pencil-sync", report_path, action)


def _record_reference_fidelity(
    gates: dict[str, dict[str, Any]],
    evidence_dir: Path,
    references: Path | None,
    report_dir: Path,
) -> None:
    report_path = report_dir / "reference-fidelity.json"
    if references is None:
        report = {
            "kind": "penflow-reference-fidelity-report",
            "status": GATE_STATUS_SKIP,
            "message": "reference-fidelity skipped because --references was not provided.",
        }
        _write_json(report_path, report)
        gates["reference-fidelity"] = {
            "status": GATE_STATUS_SKIP,
            "report_path": str(report_path),
            "exit": 0,
        }
        return

    _record_gate(
        gates,
        "reference-fidelity",
        report_path,
        lambda: _gate_reference_fidelity(evidence_dir, references, report_path),
    )


def _gate_validate_flow_contract(contract_path: Path, strict: bool) -> tuple[dict[str, Any], int]:
    contract = load_flow_contract_v2(contract_path)
    issues = validate_flow_contract_v2(contract)
    report = {
        "status": _status_from_issues(issues, strict),
        "issues": issues,
        "interactive_coverage": interactive_coverage_report(contract),
    }
    return report, _exit_from_issues(issues, strict)


def _gate_export_semantic_tree(
    contract_path: Path, semantic_tree_path: Path, strict: bool
) -> tuple[dict[str, Any], int]:
    tree = write_semantic_tree(contract_path, semantic_tree_path)
    issues = validate_semantic_tree(tree)
    return {
        "status": _status_from_issues(issues, strict),
        "out": str(semantic_tree_path),
        "flows": len(tree["flows"]),
        "screens": len(tree["screens"]),
        "issues": issues,
    }, _exit_from_issues(issues, strict)


def _gate_map_pencil_context(
    pen_path: Path, semantic_tree_path: Path, context_map_path: Path
) -> tuple[dict[str, Any], int]:
    passed, issues = validate_semantic_tree_file(semantic_tree_path)
    if not passed:
        return {"status": GATE_STATUS_FAIL, "issues": issues}, 1
    report = write_pencil_context_map(pen_path, semantic_tree_path, context_map_path)
    return report | {"out": str(context_map_path)}, 0 if report["status"] == GATE_STATUS_PASS else 1


def _gate_validate_pen(
    pen_path: Path, contract_path: Path, strict: bool
) -> tuple[dict[str, Any], int]:
    raw = load_pen(pen_path)
    roots = parse_pen(raw)
    contract = load_flow_contract_v2(contract_path)
    contract_issues = validate_flow_contract_v2(contract)
    if _has_error(contract_issues):
        issues = contract_issues
    else:
        issues = [asdict(issue) for issue in validate_pen_context_against_contract(roots, contract)]
    issues = (
        issues
        + [asdict(issue) for issue in validate_pen_context(roots)]
        + [asdict(issue) for issue in bbox_issues(raw)]
    )
    return {"status": _status_from_issues(issues, strict), "issues": issues}, _exit_from_issues(
        issues, strict
    )


def _gate_export_expected(
    pen_path: Path, expected_tree_path: Path, strict: bool
) -> tuple[dict[str, Any], int]:
    tree = write_expected_tree(pen_path, expected_tree_path)
    return {
        "status": _status_from_issues(tree["issues"], strict),
        "out": str(expected_tree_path),
        "screens": len(tree["screens"]),
        "issues": len(tree["issues"]),
    }, _exit_from_issues(tree["issues"], strict)


def _gate_lint_tokens(
    pen_path: Path, theme_css: Path | None, report_path: Path, strict: bool
) -> tuple[dict[str, Any], int]:
    theme = None
    if theme_css is not None:
        from .theme import load_theme

        theme = load_theme(theme_css)
    report = lint_tokens(pen_path, theme=theme, theme_css=str(theme_css) if theme_css else None)
    _write_json(report_path, report)
    return report, _exit_from_issues(report["violations"], strict)


def _gate_check_consistency(
    expected_tree_path: Path, report_path: Path, strict: bool
) -> tuple[dict[str, Any], int]:
    report = check_consistency(
        expected_tree_path,
        group_by="role+intent+variant+size-class",
        lenient=False,
    )
    write_consistency_report(report, report_path)
    return report, _exit_from_issues(report["issues"], strict)


def _gate_audit_visual(
    expected_tree_path: Path,
    theme_css: Path | None,
    layout_snapshot: Path,
    report_path: Path,
    strict: bool,
) -> tuple[dict[str, Any], int]:
    theme = None
    if theme_css is not None:
        from .theme import load_theme

        theme = load_theme(theme_css)
    snapshot: Path | None = layout_snapshot if layout_snapshot.exists() else None
    report = audit_visual(
        expected_tree_path,
        theme=theme,
        theme_css=str(theme_css) if theme_css else None,
        layout_snapshot=snapshot,
    )
    write_visual_metrics_report(report, report_path)
    return report, _exit_from_issues(report["issues"], strict)


def _gate_detect_drift(
    flow_contract_dir: Path,
    semantic_tree_path: Path,
    pen_path: Path,
    report_path: Path,
    markdown_path: Path,
    strict: bool,
) -> tuple[dict[str, Any], int]:
    report = detect_drift(
        flow_contract_dir,
        semantic_tree_path,
        pen_path,
        report_path,
        markdown_path=markdown_path,
    )
    if report["status"] == GATE_STATUS_PASS:
        return report, 0
    if report["status"] == "BLOCKED" or report["summary"]["errors"] > 0:
        return report, 1
    return report, 1 if strict else 0


def _gate_validate_visual_evidence(
    evidence_dir: Path,
    expected_tree_path: Path,
    theme_css: Path | None,
    strict: bool,
) -> tuple[dict[str, Any], int]:
    fingerprint = theme_fingerprint(theme_css) if theme_css is not None else None
    issues = validate_visual_evidence(
        evidence_dir,
        expected_tree_path=expected_tree_path,
        theme_fingerprint=fingerprint,
    )
    report = {
        "status": _status_from_issues(issues, strict),
        "dir": str(evidence_dir),
        "expected": str(expected_tree_path),
        "issues": issues,
    }
    return report, _exit_from_issues(issues, strict)


def _gate_reference_fidelity(
    evidence_dir: Path, references: Path, report_path: Path
) -> tuple[dict[str, Any], int]:
    report = validate_reference_fidelity(evidence_dir, references)
    _write_json(report_path, report)
    return report, 0 if report["status"] == GATE_STATUS_PASS else 1


def _gate_code_ir(
    pen_path: Path,
    semantic_tree_path: Path,
    context_map_path: Path,
    contract_path: Path,
    code_ir_path: Path,
) -> tuple[dict[str, Any], int]:
    assert_contextualized_pen_input(pen_path)
    ir = code_ir_from_pen(
        pen_path,
        semantic_tree=semantic_tree_path,
        context_map=context_map_path,
        contract=contract_path,
    )
    issues = validate_code_ir(ir)
    if _has_error(issues):
        return {"status": GATE_STATUS_FAIL, "issues": issues}, 1
    _write_json(code_ir_path, ir)
    return {
        "status": GATE_STATUS_PASS,
        "out": str(code_ir_path),
        "screens": len(ir["screens"]),
        "kind": ir["kind"],
        "issues": issues,
    }, 0


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _is_run_gate_report(path: Path) -> bool:
    return path.parent.name == REPORT_DIR


def _exit_from_issues(issues: list[dict[str, Any]], strict: bool) -> int:
    severities = {issue.get("severity") for issue in issues}
    if "error" in severities:
        return 1
    if strict and "warning" in severities:
        return 1
    return 0


def _status_from_issues(issues: list[dict[str, Any]], strict: bool) -> str:
    return GATE_STATUS_PASS if _exit_from_issues(issues, strict) == 0 else GATE_STATUS_FAIL


def _gate_status(report: dict[str, Any], exit_code: int) -> str:
    if exit_code == 2:
        return GATE_STATUS_ERROR
    if exit_code != 0:
        return GATE_STATUS_FAIL
    status = report.get("status")
    if isinstance(status, str):
        return status
    return GATE_STATUS_PASS


def _has_error(issues: list[dict[str, Any]]) -> bool:
    return any(issue.get("severity") == "error" for issue in issues)


def _aggregate_exit(gates: dict[str, dict[str, Any]]) -> int:
    exits = [int(gate["exit"]) for gate in gates.values()]
    if any(exit_code == 2 for exit_code in exits):
        return 2
    if any(exit_code != 0 for exit_code in exits):
        return 1
    return 0
