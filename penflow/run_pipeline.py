"""Single-command Penflow gate orchestration for an existing workspace."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from copy import deepcopy
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .actual_provenance import (
    ProvenanceError,
    ensure_valid_max_age_seconds,
    validate_actual_provenance,
)
from .consistency import check_consistency, write_consistency_report
from .contracts import (
    assert_contextualized_pen_input,
    code_ir_from_pen,
    validate_code_ir,
)
from .drift import detect_drift
from .evidence import (
    build_run_identity,
    validate_run_identity,
    validate_visual_evidence,
)
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
RUN_RENDERER = "penflow:expected-tree-export"

# Documented default freshness window for a `runtime-capture` actual tree
# consumed by `penflow run`: its `capturedAt` must be no older than 24h before
# the current run's export boundary (and never in the future). A
# `static-demo-fixture` is exempt by design. Override with
# `--actual-max-age-seconds`.
RUN_ACTUAL_FRESHNESS_MAX_AGE_SECONDS = 86400.0


class RunPipelineError(RuntimeError):
    """Raised when the `penflow run` boundary receives invalid inputs."""


def run_pipeline(
    target: str | Path,
    *,
    theme_css: str | Path | None = None,
    references: str | Path | None = None,
    strict: bool = False,
    actual_max_age_seconds: float | None = None,
) -> dict[str, Any]:
    """Run the deterministic Penflow gate chain for a workspace.

    Args:
        target: Workspace containing `flow-ui-contract/`, `ui.pen`, and optional
            `.mockup-validation/visual-evidence/`.
        theme_css: Optional theme CSS path; relative paths resolve inside target.
        references: Optional references directory; relative paths resolve inside
            target and arm the reference-fidelity gate.
        strict: When true, warning-only reports fail. Errors fail in all modes.
        actual_max_age_seconds: Freshness window for a `runtime-capture` actual
            tree; defaults to ``RUN_ACTUAL_FRESHNESS_MAX_AGE_SECONDS``. A
            `static-demo-fixture` is exempt.

    Returns:
        Stable JSON-compatible run summary with one entry per gate and an
        aggregate exit code.
    """
    workspace = Path(target)
    if not workspace.is_dir():
        raise RunPipelineError(f"target workspace not found: {workspace}")

    # Fail closed on a pathological freshness window before any report is
    # written, so no non-standard JSON (NaN/Infinity) can ever be produced.
    try:
        ensure_valid_max_age_seconds(actual_max_age_seconds)
    except ProvenanceError as error:
        raise RunPipelineError(str(error)) from error

    paths = _workspace_paths(workspace)
    theme_path = _resolve_optional(workspace, theme_css)
    references_path = _resolve_optional(workspace, references)
    report_dir = workspace / REPORT_DIR
    report_dir.mkdir(parents=True, exist_ok=True)

    _prime_expected_tree(paths["pen"], paths["expected_tree"])
    export_timestamp = _current_export_timestamp()
    run_boundary = _parse_run_boundary(export_timestamp)
    if run_boundary is None:
        # The boundary is produced internally; if it cannot be parsed we fail
        # explicitly rather than pass now=None and silently disable freshness.
        raise RunPipelineError(
            f"could not parse run export boundary for freshness: {export_timestamp!r}"
        )
    actual_freshness_window = (
        RUN_ACTUAL_FRESHNESS_MAX_AGE_SECONDS
        if actual_max_age_seconds is None
        else actual_max_age_seconds
    )

    def current_identity() -> dict[str, Any]:
        return _build_current_identity(
            paths,
            theme_path=theme_path,
            references_path=references_path,
            renderer=RUN_RENDERER,
            export_timestamp=export_timestamp,
        )

    identity = current_identity()

    gates: dict[str, dict[str, Any]] = {}

    def record_gate(
        gate: str,
        report_path: Path,
        action: Callable[[], tuple[dict[str, Any], int]],
    ) -> None:
        _record_gate(
            gates,
            gate,
            report_path,
            action,
            identity=identity,
            current_identity=current_identity,
        )

    record_gate(
        "validate-flow-contract",
        report_dir / "validate-flow-contract.json",
        lambda: _gate_validate_flow_contract(paths["contract"], strict),
    )
    record_gate(
        "export-semantic-tree",
        paths["semantic_tree"],
        lambda: _gate_export_semantic_tree(paths["contract"], paths["semantic_tree"], strict),
    )
    _record_pencil_sync(
        gates,
        paths["pen"],
        report_dir / "pencil-sync.json",
        identity=identity,
        current_identity=current_identity,
    )
    record_gate(
        "map-pencil-context",
        paths["context_map"],
        lambda: _gate_map_pencil_context(
            paths["pen"], paths["semantic_tree"], paths["context_map"]
        ),
    )
    record_gate(
        "validate-pen",
        report_dir / "validate-pen.json",
        lambda: _gate_validate_pen(paths["pen"], paths["contract"], strict),
    )
    record_gate(
        "export-expected",
        paths["expected_tree"],
        lambda: _gate_export_expected(paths["pen"], paths["expected_tree"], strict),
    )
    record_gate(
        "lint-tokens",
        paths["token_report"],
        lambda: _gate_lint_tokens(paths["pen"], theme_path, paths["token_report"], strict),
    )
    record_gate(
        "check-consistency",
        paths["consistency_report"],
        lambda: _gate_check_consistency(
            paths["expected_tree"], paths["consistency_report"], strict
        ),
    )
    record_gate(
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
    record_gate(
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
    record_gate(
        "validate-visual-evidence",
        report_dir / "validate-visual-evidence.json",
        lambda: _gate_validate_visual_evidence(
            paths["visual_evidence_dir"],
            paths["expected_tree"],
            theme_path,
            strict,
        ),
    )
    _record_reference_fidelity(
        gates,
        paths["visual_evidence_dir"],
        references_path,
        report_dir,
        identity=identity,
        current_identity=current_identity,
    )
    record_gate(
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
    record_gate(
        "validate-actual-provenance",
        report_dir / "validate-actual-provenance.json",
        lambda: _gate_validate_actual_provenance(
            paths["actual_tree"],
            paths["expected_tree"],
            paths["contract"],
            strict,
            now=run_boundary,
            max_age_seconds=actual_freshness_window,
        ),
    )

    _validate_gate_citations(gates, identity)
    exit_code = _aggregate_exit(gates)
    summary = {
        "kind": "penflow-run-summary",
        "status": GATE_STATUS_PASS if exit_code == 0 else GATE_STATUS_FAIL,
        "target": str(workspace),
        "strict": strict,
        "exit": exit_code,
        "gates": gates,
    } | deepcopy(identity)
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
        "actual_tree": workspace / "actual-ui-tree.json",
        "theme": workspace / "theme.css",
        "references_manifest": workspace / "references" / "references-manifest.json",
        "token_report": workspace / "token-lint-report.json",
        "consistency_report": workspace / "consistency-report.json",
        "visual_report": workspace / "visual-metrics-report.json",
        "drift_report": workspace / "drift-report.json",
        "drift_markdown": workspace / "drift-report.md",
        "visual_evidence_dir": visual_evidence_dir,
        "evidence_manifest": visual_evidence_dir / "manifest.json",
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


def _prime_expected_tree(pen_path: Path, expected_tree_path: Path) -> None:
    """Materialize the deterministic expected tree before lineage capture.

    The ordered export gate repeats this operation and reports any error. This
    best-effort priming only ensures a first run and a rerun hash the same
    expected-tree bytes.
    """
    try:
        write_expected_tree(pen_path, expected_tree_path)
    except (FileNotFoundError, ValueError, json.JSONDecodeError, OSError):
        return


def _build_current_identity(
    paths: dict[str, Path],
    *,
    theme_path: Path | None,
    references_path: Path | None,
    renderer: str,
    export_timestamp: str,
) -> dict[str, Any]:
    return build_run_identity(
        ui_pen=paths["pen"],
        contract=paths["contract"],
        expected=paths["expected_tree"],
        actual=paths["actual_tree"],
        theme=_optional_lineage_path(theme_path, paths["theme"]),
        references=(
            _references_manifest_path(references_path)
            if references_path is not None
            else _optional_lineage_path(None, paths["references_manifest"])
        ),
        renderer=renderer,
        export_timestamp=export_timestamp,
    )


def _optional_lineage_path(explicit: Path | None, conventional: Path) -> Path | None:
    """Resolve an optional lineage input without weakening explicit failures."""
    if explicit is not None:
        return explicit
    return conventional if conventional.is_file() else None


# @spec(FR-014)
def _current_export_timestamp() -> str:
    """Return the UTC timestamp for the current expected-tree export run."""
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _references_manifest_path(references_path: Path | None) -> Path | None:
    if references_path is None:
        return None
    if references_path.is_dir():
        return references_path / "references-manifest.json"
    return references_path


def _gate_entry(
    *,
    status: str,
    report_path: Path,
    exit_code: int,
    identity: dict[str, Any],
    current_identity: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    lineage_issues = validate_run_identity(current_identity(), identity)
    if lineage_issues and exit_code != 2:
        exit_code = 1
        status = GATE_STATUS_FAIL
    entry = {
        "status": status,
        "report_path": str(report_path),
        "exit": exit_code,
    } | deepcopy(identity)
    if lineage_issues:
        entry["lineage_issues"] = lineage_issues
    return entry


# @spec(FR-011)
# @spec(FR-012)
def _validate_gate_citations(
    gates: dict[str, dict[str, Any]],
    identity: dict[str, Any],
) -> None:
    """Fail any gate whose cited identity differs from the run identity."""
    for gate in gates.values():
        citation = {key: gate.get(key) for key in ("runId", "version", "lineage", "provenance")}
        issues = validate_run_identity(citation, identity)
        if not issues:
            continue
        gate["lineage_issues"] = sorted(
            [*gate.get("lineage_issues", []), *issues],
            key=lambda issue: (issue["code"], issue["path"], issue["message"]),
        )
        if gate["exit"] != 2:
            gate["exit"] = 1
            gate["status"] = GATE_STATUS_FAIL


def _record_gate(
    gates: dict[str, dict[str, Any]],
    gate: str,
    report_path: Path,
    action: Callable[[], tuple[dict[str, Any], int]],
    *,
    identity: dict[str, Any],
    current_identity: Callable[[], dict[str, Any]],
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
    gates[gate] = _gate_entry(
        status=_gate_status(report, exit_code),
        report_path=report_path,
        exit_code=exit_code,
        identity=identity,
        current_identity=current_identity,
    )


def _record_pencil_sync(
    gates: dict[str, dict[str, Any]],
    pen: Path,
    report_path: Path,
    *,
    identity: dict[str, Any],
    current_identity: Callable[[], dict[str, Any]],
) -> None:
    if os.environ.get("PENFLOW_RUN_PENCIL_SYNC") != "1":
        report = {
            "kind": "penflow-pencil-sync",
            "status": GATE_STATUS_SKIP,
            "pen": str(pen),
            "message": "pencil-sync is skipped unless PENFLOW_RUN_PENCIL_SYNC=1 is set.",
        }
        _write_json(report_path, report)
        gates["pencil-sync"] = _gate_entry(
            status=GATE_STATUS_SKIP,
            report_path=report_path,
            exit_code=0,
            identity=identity,
            current_identity=current_identity,
        )
        return

    def action() -> tuple[dict[str, Any], int]:
        report = sync_pencil_to_disk(pen)
        return report, 0 if report["status"] == GATE_STATUS_PASS else 1

    _record_gate(
        gates,
        "pencil-sync",
        report_path,
        action,
        identity=identity,
        current_identity=current_identity,
    )


def _record_reference_fidelity(
    gates: dict[str, dict[str, Any]],
    evidence_dir: Path,
    references: Path | None,
    report_dir: Path,
    *,
    identity: dict[str, Any],
    current_identity: Callable[[], dict[str, Any]],
) -> None:
    report_path = report_dir / "reference-fidelity.json"
    if references is None:
        report = {
            "kind": "penflow-reference-fidelity-report",
            "status": GATE_STATUS_SKIP,
            "message": "reference-fidelity skipped because --references was not provided.",
        }
        _write_json(report_path, report)
        gates["reference-fidelity"] = _gate_entry(
            status=GATE_STATUS_SKIP,
            report_path=report_path,
            exit_code=0,
            identity=identity,
            current_identity=current_identity,
        )
        return

    _record_gate(
        gates,
        "reference-fidelity",
        report_path,
        lambda: _gate_reference_fidelity(evidence_dir, references, report_path),
        identity=identity,
        current_identity=current_identity,
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


# @spec(FR-016)
# @spec(FR-019)
# @spec(FR-020)
def _gate_validate_actual_provenance(
    actual_tree_path: Path,
    expected_tree_path: Path,
    contract_path: Path,
    strict: bool,
    *,
    now: datetime | None,
    max_age_seconds: float | None,
) -> tuple[dict[str, Any], int]:
    """Validate the actual tree's content-bound provenance receipt.

    The pipeline gate arms freshness against the current run's export boundary
    (``now``) with a documented ``max_age_seconds``: a `runtime-capture` whose
    ``capturedAt`` is invalid, in the future, or older than the window fails.
    A `static-demo-fixture` is exempt (it declares itself frozen and cannot be a
    `runtime-capture`). A capture byte-identical to the expected tree is
    rejected, and the surface must match the contract.
    """
    surfaces = _contract_surfaces(contract_path)
    issues = validate_actual_provenance(
        actual_tree_path,
        expected_path=expected_tree_path,
        now=now,
        max_age_seconds=max_age_seconds,
        allowed_surfaces=surfaces,
    )
    report = {
        "status": _status_from_issues(issues, strict),
        "actual": str(actual_tree_path),
        "now": now.isoformat() if now is not None else None,
        "max_age_seconds": max_age_seconds,
        "issues": issues,
    }
    return report, _exit_from_issues(issues, strict)


def _parse_run_boundary(export_timestamp: str) -> datetime | None:
    """Parse the current-run export timestamp into a UTC datetime for freshness.

    Returns ``None`` if the boundary cannot be parsed so the freshness check
    degrades safely rather than raising; the boundary is produced internally by
    ``_current_export_timestamp`` and is normally always parseable.
    """
    text = export_timestamp.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _contract_surfaces(contract_path: Path) -> list[str] | None:
    """Collect declared screen surfaces from the flow contract, if readable.

    Returns ``None`` when the contract cannot be parsed so the provenance gate
    does not raise; the ordered contract gate already reports that failure.
    """
    try:
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError, json.JSONDecodeError, OSError):
        return None
    screens = contract.get("screens") if isinstance(contract, dict) else None
    if not isinstance(screens, list):
        return None
    surfaces = [
        screen["surface"]
        for screen in screens
        if isinstance(screen, dict) and isinstance(screen.get("surface"), str)
    ]
    return surfaces or None


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # allow_nan=False: never emit non-standard JSON (NaN/Infinity); raise instead.
    path.write_text(
        json.dumps(data, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8"
    )


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
