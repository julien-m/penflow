"""Verify Pencil document persistence from independently read byte snapshots.

Pencil and MCP stay outside this module. An operator produces one observation
plus immutable pre/post snapshots; Penflow re-reads those files and the current
document, computes every digest itself, and emits a content-bound receipt.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from .schema_cache import validator_for

OBSERVATION_KIND = "penflow-pencil-persistence-observation"
RECEIPT_KIND = "penflow-pencil-persistence-receipt"
PERSISTENCE_VERSION = 1
_OBSERVATION_SCHEMA = "pencil-persistence-observation.schema.json"


def verify_pencil_persistence(
    observation: str | Path,
    *,
    document: str | Path,
    run_id: str,
    operation: str,
    out: str | Path | None = None,
) -> dict[str, Any]:
    """Verify one operator observation against independent document bytes.

    Args:
        observation: Operator-produced JSON with pre/post snapshot paths and digests.
        document: Current `.pen` document that must equal the post snapshot.
        run_id: Exact run expected by the caller; old-run observations are rejected.
        operation: Exact requested operation expected by the caller.
        out: Optional path for the structured persistence receipt.

    Returns:
        A deterministic PASS/FAIL receipt. PASS alone closes persistence.

    Side effects:
        Reads the observation, pre/post snapshots, and current document. Writes
        `out` only after all checks have been computed.
    """
    observation_path = Path(observation).resolve()
    document_path = Path(document).resolve()
    issues: list[dict[str, str]] = []
    observed, observation_sha256 = _load_observation(observation_path, issues)
    checks = _empty_checks()

    if isinstance(observed, dict):
        issues.extend(_observation_schema_issues(observed))
        if observed.get("kind") == "penflow-pencil-sync":
            issues.append(
                _issue(
                    "persistence.trigger_only",
                    "$.kind",
                    "a pencil-sync trigger claim cannot close persistence",
                )
            )
        checks["trigger_declared"] = _trigger_declared(observed)
        checks["run_matches"] = observed.get("run_id") == run_id
        checks["operation_matches"] = observed.get("operation") == operation
        _binding_issues(
            observed,
            observation_path,
            document_path,
            run_id,
            operation,
            checks,
            issues,
        )
        pre = _snapshot_result(
            observed,
            "pre",
            observation_path,
            "$.document.pre",
            issues,
        )
        post = _snapshot_result(
            observed,
            "post",
            observation_path,
            "$.document.post",
            issues,
        )
    else:
        pre = _empty_snapshot()
        post = _empty_snapshot()

    _snapshot_independence_issues(pre, post, document_path, checks, issues)
    current_sha256 = _read_current_digest(document_path, issues)
    checks["pre_digest_matches"] = _digest_matches(pre)
    checks["post_digest_matches"] = _digest_matches(post)
    checks["content_changed"] = _content_changed(pre, post)
    checks["current_matches_post"] = bool(
        current_sha256
        and isinstance(post.get("actual_sha256"), str)
        and current_sha256 == post["actual_sha256"]
    )
    _digest_issues(pre, post, current_sha256, checks, issues)
    issues.sort(key=lambda issue: (issue["path"], issue["code"], issue["message"]))
    status = "PASS" if not issues and all(checks.values()) else "FAIL"
    receipt = {
        "kind": RECEIPT_KIND,
        "version": PERSISTENCE_VERSION,
        "status": status,
        "closes_persistence": status == "PASS",
        "run_id": run_id,
        "operation": operation,
        "observation": {
            "path": str(observation_path),
            "sha256": observation_sha256,
        },
        "document": {
            "path": str(document_path),
            "pre": pre,
            "post": post,
            "current_sha256": current_sha256,
        },
        "checks": checks,
        "verifier": {
            "name": "penflow",
            "method": "independent-byte-digest",
            "result": "pass" if status == "PASS" else "fail",
        },
        "issues": issues,
    }
    receipt["integrity"] = {
        "algorithm": "sha256",
        "sha256": _receipt_digest(receipt),
    }
    if out is not None:
        output_path = Path(out)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return receipt


def validate_pencil_persistence_receipt(
    receipt: dict[str, Any],
) -> list[dict[str, str]]:
    """Re-read a receipt's evidence and reject stale or tampered contents.

    Args:
        receipt: Parsed `penflow-pencil-persistence-receipt` object.

    Returns:
        Report-schema issues. An empty list means the stored receipt exactly
        matches a fresh independent verification.
    """
    issues: list[dict[str, str]] = []
    integrity = receipt.get("integrity")
    declared_integrity = integrity.get("sha256") if isinstance(integrity, dict) else None
    if declared_integrity != _receipt_digest(receipt):
        issues.append(
            _report_issue(
                "$.integrity.sha256",
                "persistence receipt integrity digest does not match its contents",
            )
        )
        return issues

    observation = receipt.get("observation")
    document = receipt.get("document")
    if not isinstance(observation, dict) or not isinstance(document, dict):
        return issues
    observation_path = observation.get("path")
    document_path = document.get("path")
    run_id = receipt.get("run_id")
    operation = receipt.get("operation")
    if (
        not isinstance(observation_path, str)
        or not observation_path
        or not isinstance(document_path, str)
        or not document_path
        or not isinstance(run_id, str)
        or not run_id
        or not isinstance(operation, str)
        or not operation
    ):
        return issues

    fresh = verify_pencil_persistence(
        observation_path,
        document=document_path,
        run_id=run_id,
        operation=operation,
    )
    if _without_integrity(fresh) != _without_integrity(receipt):
        issues.append(
            _report_issue(
                "$",
                "persistence receipt is stale or tampered relative to independently read bytes",
            )
        )
    return issues


def _load_observation(
    path: Path,
    issues: list[dict[str, str]],
) -> tuple[dict[str, Any] | None, str | None]:
    if not path.is_file():
        issues.append(
            _issue(
                "persistence.observation.missing",
                "$",
                f"observation file does not exist: {path}",
            )
        )
        return None, None
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    try:
        parsed = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        issues.append(
            _issue(
                "persistence.observation.invalid_json",
                "$",
                f"observation is not valid UTF-8 JSON: {error}",
            )
        )
        return None, digest
    if not isinstance(parsed, dict):
        issues.append(
            _issue(
                "persistence.observation.invalid_root",
                "$",
                "observation root must be an object",
            )
        )
        return None, digest
    return parsed, digest


def _observation_schema_issues(observation: dict[str, Any]) -> list[dict[str, str]]:
    return [
        _issue(
            "persistence.observation.schema",
            _json_path(error.absolute_path),
            error.message,
        )
        for error in validator_for(_OBSERVATION_SCHEMA).iter_errors(observation)
    ]


def _binding_issues(
    observation: dict[str, Any],
    observation_path: Path,
    document_path: Path,
    run_id: str,
    operation: str,
    checks: dict[str, bool],
    issues: list[dict[str, str]],
) -> None:
    if not checks["trigger_declared"]:
        issues.append(
            _issue(
                "persistence.trigger.missing",
                "$.trigger",
                "operator observation must declare a completed trigger",
            )
        )
    if not checks["run_matches"]:
        issues.append(
            _issue(
                "persistence.run.replayed",
                "$.run_id",
                f"observation run does not match expected run {run_id!r}",
            )
        )
    if not checks["operation_matches"]:
        issues.append(
            _issue(
                "persistence.operation.mismatch",
                "$.operation",
                f"observation operation does not match {operation!r}",
            )
        )
    document = observation.get("document")
    declared_path = document.get("path") if isinstance(document, dict) else None
    resolved_path = _resolve_artifact(observation_path, declared_path)
    checks["document_matches"] = resolved_path == document_path
    if not checks["document_matches"]:
        issues.append(
            _issue(
                "persistence.document.mismatch",
                "$.document.path",
                "observation document does not match the independently supplied document",
            )
        )


def _snapshot_result(
    observation: dict[str, Any],
    name: str,
    observation_path: Path,
    path: str,
    issues: list[dict[str, str]],
) -> dict[str, str | None]:
    document = observation.get("document")
    snapshot = document.get(name) if isinstance(document, dict) else None
    declared_path = snapshot.get("path") if isinstance(snapshot, dict) else None
    declared_sha256 = snapshot.get("sha256") if isinstance(snapshot, dict) else None
    resolved_path = _resolve_artifact(observation_path, declared_path)
    actual_sha256: str | None = None
    if resolved_path is None or not resolved_path.is_file():
        issues.append(
            _issue(
                f"persistence.snapshot.{name}_missing",
                f"{path}.path",
                f"{name} snapshot file does not exist",
            )
        )
    else:
        actual_sha256 = hashlib.sha256(resolved_path.read_bytes()).hexdigest()
    return {
        "path": str(resolved_path) if resolved_path is not None else None,
        "declared_sha256": declared_sha256 if isinstance(declared_sha256, str) else None,
        "actual_sha256": actual_sha256,
    }


def _snapshot_independence_issues(
    pre: dict[str, str | None],
    post: dict[str, str | None],
    document: Path,
    checks: dict[str, bool],
    issues: list[dict[str, str]],
) -> None:
    pre_path = pre.get("path")
    post_path = post.get("path")
    checks["snapshots_distinct"] = bool(pre_path and post_path and pre_path != post_path)
    if not checks["snapshots_distinct"]:
        issues.append(
            _issue(
                "persistence.snapshot.reused",
                "$.document",
                "pre and post snapshots must be distinct files",
            )
        )
    if str(document) in {pre_path, post_path}:
        checks["snapshots_distinct"] = False
        issues.append(
            _issue(
                "persistence.snapshot.not_independent",
                "$.document",
                "pre/post snapshots must not alias the current document",
            )
        )


def _read_current_digest(document: Path, issues: list[dict[str, str]]) -> str | None:
    if not document.is_file():
        issues.append(
            _issue(
                "persistence.document.missing",
                "$.document.path",
                f"current document does not exist: {document}",
            )
        )
        return None
    return hashlib.sha256(document.read_bytes()).hexdigest()


def _digest_issues(
    pre: dict[str, str | None],
    post: dict[str, str | None],
    current_sha256: str | None,
    checks: dict[str, bool],
    issues: list[dict[str, str]],
) -> None:
    if not checks["pre_digest_matches"]:
        issues.append(
            _issue(
                "persistence.digest.pre_mismatch",
                "$.document.pre.sha256",
                "declared pre digest does not match independently read bytes",
            )
        )
    if not checks["post_digest_matches"]:
        issues.append(
            _issue(
                "persistence.digest.post_mismatch",
                "$.document.post.sha256",
                "declared post digest does not match independently read bytes",
            )
        )
    if not checks["content_changed"]:
        issues.append(
            _issue(
                "persistence.digest.same",
                "$.document",
                "pre and post document digests are identical; persistence is a no-op",
            )
        )
    if current_sha256 is not None and not checks["current_matches_post"]:
        issues.append(
            _issue(
                "persistence.document.stale",
                "$.document.path",
                "current document bytes do not match the verified post snapshot",
            )
        )


def _trigger_declared(observation: dict[str, Any]) -> bool:
    trigger = observation.get("trigger")
    return bool(isinstance(trigger, dict) and trigger.get("status") == "triggered")


def _resolve_artifact(observation: Path, value: Any) -> Path | None:
    if not isinstance(value, str) or not value:
        return None
    candidate = Path(value)
    return (candidate if candidate.is_absolute() else observation.parent / candidate).resolve()


def _digest_matches(snapshot: dict[str, str | None]) -> bool:
    declared = snapshot.get("declared_sha256")
    actual = snapshot.get("actual_sha256")
    return bool(declared and actual and declared == actual)


def _content_changed(
    pre: dict[str, str | None],
    post: dict[str, str | None],
) -> bool:
    pre_digest = pre.get("actual_sha256")
    post_digest = post.get("actual_sha256")
    return bool(pre_digest and post_digest and pre_digest != post_digest)


def _empty_checks() -> dict[str, bool]:
    return {
        "trigger_declared": False,
        "run_matches": False,
        "operation_matches": False,
        "document_matches": False,
        "snapshots_distinct": False,
        "pre_digest_matches": False,
        "post_digest_matches": False,
        "content_changed": False,
        "current_matches_post": False,
    }


def _empty_snapshot() -> dict[str, str | None]:
    return {"path": None, "declared_sha256": None, "actual_sha256": None}


def _receipt_digest(receipt: dict[str, Any]) -> str:
    canonical = _without_integrity(receipt)
    payload = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _without_integrity(receipt: dict[str, Any]) -> dict[str, Any]:
    canonical = copy.deepcopy(receipt)
    canonical.pop("integrity", None)
    return canonical


def _json_path(parts: Any) -> str:
    return "$" + "".join(f".{part}" if isinstance(part, str) else f"[{part}]" for part in parts)


def _issue(code: str, path: str, message: str) -> dict[str, str]:
    return {"severity": "error", "code": code, "path": path, "message": message}


def _report_issue(path: str, message: str) -> dict[str, str]:
    return {"severity": "error", "path": path, "message": message}
