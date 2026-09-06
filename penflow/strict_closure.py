"""Fail-closed, read-only validation for one complete Penflow closure run."""

from __future__ import annotations

import copy
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .actual_provenance import (
    ProvenanceError,
    actual_provenance_path,
    validate_actual_provenance,
)
from .evidence import validate_visual_evidence
from .pencil_persistence import validate_pencil_persistence_receipt
from .reference_fidelity import validate_reference_fidelity
from .schema_cache import validator_for
from .theme import theme_fingerprint

KIND = "penflow-strict-closure-report"
VERSION = 1
REPORT_DIR = ".penflow-run"
REPORT_FILENAME = "strict-closure.json"
PERSISTENCE_FILENAME = "pencil-persistence-receipt.json"
DEFAULT_ACTUAL_MAX_AGE_SECONDS = 86_400.0


class StrictClosureError(RuntimeError):
    """Raised when the strict closure request itself is invalid."""


def validate_strict_closure(
    target: str | Path,
    *,
    references: str | Path | None = None,
    theme_css: str | Path | None = None,
    actual_max_age_seconds: float | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Validate C6 closure evidence and write only its structured run receipt."""
    workspace = Path(target).resolve()
    if not workspace.is_dir():
        raise StrictClosureError(f"workspace not found: {workspace}")
    run_dir = workspace / REPORT_DIR
    run_dir.mkdir(parents=True, exist_ok=True)
    report_path = run_dir / REPORT_FILENAME
    before = _workspace_snapshot(workspace)
    gate_issues, run_id = _closure_gate_issues(
        workspace,
        references=references,
        theme_css=theme_css,
        actual_max_age_seconds=actual_max_age_seconds,
        now=now,
    )
    report = _closure_report(workspace, report_path, before, gate_issues, run_id)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def _closure_gate_issues(
    workspace: Path,
    *,
    references: str | Path | None,
    theme_css: str | Path | None,
    actual_max_age_seconds: float | None,
    now: datetime | None,
) -> tuple[dict[str, list[dict[str, Any]]], str | None]:
    """Evaluate unchanged C47 validators in their historical order."""
    records, loading = _closure_records(workspace)
    persistence, actual_receipt = records["persistence"], records["actual"]
    manifest, vision = records["manifest"], records["vision"]
    persistence_load_issues = loading["persistence"]
    actual_load_issues = loading["actual"]
    visual_load_issues = [*loading["manifest"], *loading["vision"]]
    actual_path = workspace / "actual-ui-tree.json"
    expected_path = workspace / "expected-ui-tree.json"
    evidence_dir = workspace / ".mockup-validation" / "visual-evidence"
    references_dir = _resolve_optional_path(workspace, references)
    theme_path = _resolve_optional_path(workspace, theme_css)

    persistence_issues = [*persistence_load_issues, *_persistence_issues(persistence)]
    actual_issues = _actual_gate_issues(
        actual_path, expected_path, now, actual_max_age_seconds, actual_load_issues
    )
    visual_issues = [
        *visual_load_issues,
        *_visual_issues(
            evidence_dir,
            expected_path=expected_path,
            theme_path=theme_path,
            vision=vision,
        ),
    ]
    reference_issues = _reference_issues(
        evidence_dir,
        references_dir=references_dir,
        manifest=manifest,
    )
    run_issues, run_id = _same_run_issues(persistence, actual_receipt, manifest, vision)
    return {
        "persistence": persistence_issues,
        "actual_provenance": actual_issues,
        "visual_evidence": visual_issues,
        "reference_fidelity": reference_issues,
        "same_run": run_issues,
    }, run_id


def _closure_records(
    workspace: Path,
) -> tuple[dict[str, dict[str, Any] | None], dict[str, list[dict[str, Any]]]]:
    """Read the four historical evidence objects while retaining each boundary finding."""
    evidence = workspace / ".mockup-validation" / "visual-evidence"
    paths = {
        "persistence": (workspace / REPORT_DIR / PERSISTENCE_FILENAME, "strict.persistence"),
        "actual": (
            actual_provenance_path(workspace / "actual-ui-tree.json"),
            "strict.actual_provenance",
        ),
        "manifest": (evidence / "manifest.json", "strict.visual_manifest"),
        "vision": (evidence / "vision-report.json", "strict.vision_report"),
    }
    records, loading = {}, {}
    for name, (path, code) in paths.items():
        findings: list[dict[str, Any]] = []
        records[name] = _load_object(path, code, findings)
        loading[name] = findings
    return records, loading


def _closure_report(
    workspace: Path,
    report_path: Path,
    before: dict[str, str],
    gate_issues: dict[str, list[dict[str, Any]]],
    run_id: str | None,
) -> dict[str, Any]:
    """Join gate findings with the unchanged-files invariant and stable report envelope."""
    issues = [item for findings in gate_issues.values() for item in findings]
    after = _workspace_snapshot(workspace)
    unchanged = before == after
    if not unchanged:
        issues.append(
            _issue(
                "strict.filesystem.evidence_mutated",
                "$.filesystem",
                "strict validation changed files outside the selected .penflow-run directory",
            )
        )
    issues.sort(key=_issue_sort_key)
    gates = {name: _gate(findings) for name, findings in gate_issues.items()}
    status = "PASS" if not issues else "FAIL"
    report: dict[str, Any] = {
        "kind": KIND,
        "version": VERSION,
        "strict_closure": True,
        "status": status,
        "exit": 0 if status == "PASS" else 1,
        "run_id": run_id,
        "target": str(workspace),
        "gates": gates,
        "inputs": [{"path": path, "sha256": digest} for path, digest in sorted(before.items())],
        "filesystem": {
            "report_path": str(report_path),
            "outside_run_dir_unchanged": unchanged,
        },
        "issues": issues,
    }
    report["integrity"] = {"sha256": _report_digest(report)}
    return report


def validate_strict_closure_report(
    report: dict[str, Any],
    report_path: str | Path,
) -> list[dict[str, Any]]:
    """Re-read all bound inputs and reject a stale, moved, or tampered report."""
    issues: list[dict[str, Any]] = []
    path = Path(report_path).resolve()
    target_value = report.get("target")
    if not isinstance(target_value, str):
        return issues
    workspace = Path(target_value).resolve()
    expected_path = workspace / REPORT_DIR / REPORT_FILENAME
    if path != expected_path:
        issues.append(
            _issue(
                "strict.report.location",
                "$",
                f"strict closure report must be {expected_path}",
            )
        )
    integrity = report.get("integrity")
    declared = integrity.get("sha256") if isinstance(integrity, dict) else None
    if declared != _report_digest(report):
        issues.append(
            _issue(
                "strict.report.integrity",
                "$.integrity.sha256",
                "strict closure report integrity digest does not match its contents",
            )
        )
        return issues
    expected_inputs = {
        item["path"]: item["sha256"]
        for item in report.get("inputs", [])
        if isinstance(item, dict)
        and isinstance(item.get("path"), str)
        and isinstance(item.get("sha256"), str)
    }
    current_inputs = _workspace_snapshot(workspace)
    if expected_inputs != current_inputs:
        issues.append(
            _issue(
                "strict.report.inputs_changed",
                "$.inputs",
                "strict closure inputs are missing, added, or changed since validation",
            )
        )
    return sorted(issues, key=_issue_sort_key)


def _persistence_issues(receipt: dict[str, Any] | None) -> list[dict[str, Any]]:
    if receipt is None:
        return []
    issues = [
        _issue("strict.persistence.schema", _json_path(error.absolute_path), error.message)
        for error in validator_for("pencil-persistence-receipt.schema.json").iter_errors(receipt)
    ]
    issues.extend(
        issue if "code" in issue else {"code": "strict.persistence.invalid", **issue}
        for issue in validate_pencil_persistence_receipt(receipt)
    )
    if (
        receipt.get("status") != "PASS"
        or receipt.get("closes_persistence") is not True
        or receipt.get("verifier", {}).get("result") != "pass"
    ):
        issues.append(
            _issue(
                "strict.persistence.not_closing",
                "$.status",
                "persistence receipt must independently close with PASS",
            )
        )
    return sorted(issues, key=_issue_sort_key)


def _visual_issues(
    evidence_dir: Path,
    *,
    expected_path: Path,
    theme_path: Path | None,
    vision: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    if vision is not None and vision.get("status") != "PASS":
        issues.append(
            _issue(
                "strict.visual.status",
                "$.status",
                "strict closure requires visual status PASS; skips and warnings do not close",
            )
        )
    try:
        fingerprint = theme_fingerprint(theme_path) if theme_path is not None else None
        issues.extend(
            validate_visual_evidence(
                evidence_dir,
                expected_tree_path=expected_path,
                theme_fingerprint=fingerprint,
            )
        )
    except (FileNotFoundError, ValueError, OSError) as error:
        issues.append(_issue("strict.visual.invalid", "$", str(error)))
    return sorted(issues, key=_issue_sort_key)


def _reference_issues(
    evidence_dir: Path,
    *,
    references_dir: Path | None,
    manifest: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    declaration = manifest.get("references_manifest") if manifest is not None else None
    if not isinstance(declaration, str) or not declaration:
        issues.append(
            _issue(
                "strict.references.undeclared",
                "$.references_manifest",
                "strict closure requires a declared references manifest",
            )
        )
    if references_dir is None:
        issues.append(
            _issue(
                "strict.references.missing",
                "$.references",
                "strict closure requires --references",
            )
        )
        return issues
    if isinstance(declaration, str) and declaration:
        declared_path = (evidence_dir / declaration).resolve()
        selected_path = (references_dir / "references-manifest.json").resolve()
        if declared_path != selected_path:
            issues.append(
                _issue(
                    "strict.references.mismatch",
                    "$.references_manifest",
                    "declared and selected references manifests differ",
                )
            )
    try:
        report = validate_reference_fidelity(evidence_dir, references_dir)
        issues.extend(report.get("issues", []))
        if report.get("status") != "PASS":
            issues.append(
                _issue(
                    "strict.references.not_closing",
                    "$.status",
                    "reference fidelity must close with PASS",
                )
            )
    except (FileNotFoundError, ValueError, OSError) as error:
        issues.append(_issue("strict.references.invalid", "$", str(error)))
    return sorted(issues, key=_issue_sort_key)


def _same_run_issues(
    persistence: dict[str, Any] | None,
    actual_receipt: dict[str, Any] | None,
    manifest: dict[str, Any] | None,
    vision: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], str]:
    values = {
        "persistence": persistence.get("run_id") if persistence else None,
        "actual_provenance": actual_receipt.get("sessionId") if actual_receipt else None,
        "visual_manifest": manifest.get("runId") if manifest else None,
        "vision_report": vision.get("runId") if vision else None,
    }
    issues = [
        _issue(
            "strict.run_id.missing",
            f"$.{name}",
            f"{name} does not declare the strict closure run id",
        )
        for name, value in values.items()
        if not isinstance(value, str) or not value
    ]
    declared = {value for value in values.values() if isinstance(value, str) and value}
    if len(declared) > 1:
        issues.append(
            _issue(
                "strict.run_id.mismatch",
                "$.run_id",
                "persistence, actual provenance, manifest, and vision report are not from one run",
            )
        )
    run_id = next(iter(declared)) if len(declared) == 1 else "UNBOUND"
    return sorted(issues, key=_issue_sort_key), run_id


def _workspace_snapshot(workspace: Path) -> dict[str, str]:
    snapshot: dict[str, str] = {}
    for path in sorted(workspace.rglob("*")):
        if not path.is_file():
            continue
        relative_path = path.relative_to(workspace)
        if relative_path == Path(REPORT_DIR) / REPORT_FILENAME:
            continue
        relative = relative_path.as_posix()
        snapshot[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return snapshot


def _load_object(
    path: Path,
    code: str,
    issues: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if not path.is_file():
        issues.append(_issue(f"{code}.missing", "$", f"required evidence not found: {path}"))
        return None
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        issues.append(_issue(f"{code}.invalid", "$", f"invalid JSON in {path}: {error}"))
        return None
    if not isinstance(parsed, dict):
        issues.append(_issue(f"{code}.invalid", "$", f"evidence must be an object: {path}"))
        return None
    return parsed


def _resolve_optional_path(workspace: Path, value: str | Path | None) -> Path | None:
    if value is None:
        return None
    path = Path(value)
    return (workspace / path).resolve() if not path.is_absolute() else path.resolve()


def _gate(issues: list[dict[str, Any]]) -> dict[str, Any]:
    return {"status": "PASS" if not issues else "FAIL", "issues": issues}


def _issue(code: str, path: str, message: str) -> dict[str, Any]:
    return {"severity": "error", "code": code, "path": path, "message": message}


def _issue_sort_key(issue: dict[str, Any]) -> tuple[str, str, str]:
    return str(issue.get("code", "")), str(issue.get("path", "")), str(issue.get("message", ""))


def _json_path(parts: Any) -> str:
    return "$" + "".join(f".{part}" if isinstance(part, str) else f"[{part}]" for part in parts)


def _report_digest(report: dict[str, Any]) -> str:
    bound = copy.deepcopy(report)
    bound.pop("integrity", None)
    payload = json.dumps(bound, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _actual_gate_issues(
    actual_path: Path,
    expected_path: Path,
    now: datetime | None,
    actual_max_age_seconds: float | None,
    actual_load_issues: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    try:
        actual_issues = [
            *actual_load_issues,
            *validate_actual_provenance(
                actual_path,
                expected_path=expected_path,
                now=now or datetime.now(UTC),
                max_age_seconds=(
                    DEFAULT_ACTUAL_MAX_AGE_SECONDS
                    if actual_max_age_seconds is None
                    else actual_max_age_seconds
                ),
                require_fresh=True,
            ),
        ]
    except ProvenanceError as error:
        raise StrictClosureError(str(error)) from error
    return actual_issues
