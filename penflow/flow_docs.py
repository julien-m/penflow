# @spec FR-011: Deterministic flow docs — .specs/features/076-exhaustive-bidirectional-semantic-context/spec.md#fr-011
# @spec FR-012: Manifest-bound files — .specs/features/076-exhaustive-bidirectional-semantic-context/spec.md#fr-012
# @spec FR-013: Exact freshness — .specs/features/076-exhaustive-bidirectional-semantic-context/spec.md#fr-013
# @spec FR-014: Complete-or-absent state — .specs/features/076-exhaustive-bidirectional-semantic-context/spec.md#fr-014
"""Canonical contract-to-Markdown export and read-only freshness checks."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from .flow_contract import load_flow_contract_v2, validate_flow_contract_v2
from .schema_cache import validator_for

GENERATOR = "penflow.flow-docs/1"
MANIFEST = "generated-docs.json"


class FlowDocsError(ValueError):
    """Generated documentation cannot be safely read or published."""


def export_flow_docs(contract_path: str | Path, out_dir: str | Path) -> dict[str, Any]:
    """Render and transactionally publish all manifest-owned documentation."""
    contract_file, output = Path(contract_path), Path(out_dir)
    contract_bytes = contract_file.read_bytes()
    contract = load_flow_contract_v2(contract_file)
    issues = validate_flow_contract_v2(contract)
    if any(issue["severity"] == "error" for issue in issues):
        raise FlowDocsError(f"invalid contract: {issues[0]['code']}")
    rendered = _render_documents(contract)
    manifest = _manifest(contract_file, contract_bytes, rendered)
    _publish(output, rendered, manifest)
    return manifest


def check_generated_docs(
    contract_path: str | Path, out_dir: str | Path, *, explicit: bool
) -> dict[str, Any]:
    """Validate exact membership and hashes without mutating the output tree."""
    contract_file, output = Path(contract_path), Path(out_dir)
    armed = any((output / name).exists() for name in ("flows", "screens", MANIFEST))
    if not armed:
        if explicit:
            return _check_report([_issue("docs.missing", "generated docs are absent")])
        return {
            "kind": "penflow-generated-docs-check",
            "version": 1,
            "status": "DISABLED",
            "issues": [],
        }
    issues = _triplet_issues(output)
    manifest = _load_manifest(output, issues) if (output / MANIFEST).is_file() else None
    if manifest is not None:
        issues.extend(_freshness_issues(contract_file, output, manifest))
    return _check_report(issues)


def _render_documents(contract: dict[str, Any]) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    for flow in sorted(contract.get("flows", []), key=lambda item: str(item.get("id", ""))):
        flow_id = str(flow["id"])
        records = {
            "flow": flow,
            "screens": _records(contract, "screens", "flow_id", flow_id),
            "transitions": _records(contract, "transitions", "flow", flow_id),
            "actions": sorted(
                contract.get("actions", []), key=lambda item: str(item.get("id", ""))
            ),
            "relations": sorted(
                contract.get("relations", []), key=lambda item: str(item.get("id", ""))
            ),
        }
        files[f"flows/{flow_id}.md"] = _markdown("Flow", flow_id, records)
    for screen in sorted(contract.get("screens", []), key=lambda item: str(item.get("id", ""))):
        screen_id = str(screen["id"])
        nodes = _records(contract, "nodes", "screen_id", screen_id)
        node_ids = {node.get("id") for node in nodes}
        records = {
            "screen": screen,
            "nodes": nodes,
            "actions": [
                action
                for action in sorted(
                    contract.get("actions", []), key=lambda item: str(item.get("id", ""))
                )
                if action.get("node") in node_ids or action.get("source_node") in node_ids
            ],
            "relations": sorted(
                contract.get("relations", []), key=lambda item: str(item.get("id", ""))
            ),
        }
        files[f"screens/{screen_id}.md"] = _markdown("Screen", screen_id, records)
    if not any(path.startswith("flows/") for path in files) or not any(
        path.startswith("screens/") for path in files
    ):
        raise FlowDocsError("docs.empty")
    return files


def _records(
    contract: dict[str, Any], collection: str, field: str, value: str
) -> list[dict[str, Any]]:
    return sorted(
        [item for item in contract.get(collection, []) if item.get(field) == value],
        key=lambda item: str(item.get("id", "")),
    )


def _markdown(kind: str, stable_id: str, records: dict[str, Any]) -> bytes:
    body = json.dumps(records, indent=2, sort_keys=True, ensure_ascii=False)
    text = (
        "<!-- Generated from contract.json; do not edit. -->\n"
        f"<!-- @spec(FR-011) -->\n\n# {kind}: {stable_id}\n\n"
        f"Generator: `{GENERATOR}`\n\n```json\n{body}\n```\n"
    )
    return text.encode("utf-8")


def _manifest(
    contract_path: Path, contract_bytes: bytes, rendered: dict[str, bytes]
) -> dict[str, Any]:
    return {
        "kind": "penflow-generated-docs",
        "version": 1,
        "status": "PASS",
        "generator": GENERATOR,
        "contract": {"path": str(contract_path), "sha256": _digest(contract_bytes)},
        "files": [
            {"path": path, "sha256": _digest(data)} for path, data in sorted(rendered.items())
        ],
    }


def _publish(output: Path, rendered: dict[str, bytes], manifest: dict[str, Any]) -> None:
    owned = _owned_paths(output)
    _reject_collisions(output, set(rendered), owned)
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".flow-docs-stage-", dir=output.parent))
    backup = Path(tempfile.mkdtemp(prefix=".flow-docs-backup-", dir=output.parent))
    journal = output.parent / f".{output.name}-generated-docs-transaction.json"
    try:
        _stage_files(stage, rendered, manifest)
        _write_journal(journal, output, sorted(owned))
        _replace_transaction(output, stage, backup, owned, set(rendered))
        journal.unlink(missing_ok=True)
    except Exception:
        _restore_backup(output, backup)
        raise
    finally:
        shutil.rmtree(stage, ignore_errors=True)
        shutil.rmtree(backup, ignore_errors=True)


def _stage_files(stage: Path, rendered: dict[str, bytes], manifest: dict[str, Any]) -> None:
    for relative, data in sorted(rendered.items()):
        target = stage / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        _durable_write(target, data)
    manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    _durable_write(stage / MANIFEST, manifest_bytes)


def _replace_transaction(
    output: Path, stage: Path, backup: Path, owned: set[str], planned: set[str]
) -> None:
    output.mkdir(parents=True, exist_ok=True)
    for relative in sorted(owned | {MANIFEST}):
        source = output / relative
        if source.is_file():
            target = backup / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(source, target)
    for relative in sorted(planned):
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(stage / relative, target)
    os.replace(stage / MANIFEST, output / MANIFEST)
    _fsync_dir(output)


def _restore_backup(output: Path, backup: Path) -> None:
    for source in sorted(backup.rglob("*"), reverse=True):
        if source.is_file():
            target = output / source.relative_to(backup)
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(source, target)


def _owned_paths(output: Path) -> set[str]:
    manifest_path = output / MANIFEST
    if not manifest_path.is_file():
        return set()
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        return {str(item["path"]) for item in manifest.get("files", [])}
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise FlowDocsError("docs.manifest_invalid") from exc


def _reject_collisions(output: Path, planned: set[str], owned: set[str]) -> None:
    if not output.exists():
        return
    authored = {
        str(path.relative_to(output))
        for root in (output / "flows", output / "screens")
        if root.exists()
        for path in root.rglob("*.md")
    }
    if (output / "flows").exists() or (output / "screens").exists():
        if not owned:
            raise FlowDocsError("docs.unowned_collision")
    collisions = (authored & planned) - owned
    if collisions:
        raise FlowDocsError(f"docs.unowned_collision: {sorted(collisions)}")


def _triplet_issues(output: Path) -> list[dict[str, str]]:
    flows, screens, manifest = output / "flows", output / "screens", output / MANIFEST
    if (flows.exists() and not any(flows.glob("*.md"))) or (
        screens.exists() and not any(screens.glob("*.md"))
    ):
        return [_issue("docs.empty", "generated documentation directory is empty")]
    if not (flows.is_dir() and screens.is_dir() and manifest.is_file()):
        return [_issue("docs.partial", "generated documentation triplet is incomplete")]
    return []


def _load_manifest(output: Path, issues: list[dict[str, str]]) -> dict[str, Any] | None:
    try:
        manifest = json.loads((output / MANIFEST).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        issues.append(_issue("docs.manifest_invalid", "manifest is unreadable"))
        return None
    errors = list(validator_for("generated-docs.schema.json").iter_errors(manifest))
    if errors:
        issues.append(_issue("docs.manifest_invalid", errors[0].message))
        return None
    return manifest


def _freshness_issues(
    contract: Path, output: Path, manifest: dict[str, Any]
) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    if manifest["contract"]["sha256"] != _digest(contract.read_bytes()):
        issues.append(_issue("docs.contract_stale", "contract digest differs from manifest"))
    expected = {item["path"]: item["sha256"] for item in manifest["files"]}
    actual = {
        str(path.relative_to(output))
        for root in (output / "flows", output / "screens")
        for path in root.glob("*.md")
    }
    if actual != set(expected):
        issues.append(_issue("docs.membership_mismatch", "generated membership differs"))
    for relative, digest in sorted(expected.items()):
        path = output / relative
        if not path.is_file() or not path.read_bytes():
            issues.append(_issue("docs.empty", f"missing or empty generated file: {relative}"))
        elif _digest(path.read_bytes()) != digest:
            issues.append(_issue("docs.hash_mismatch", f"generated file changed: {relative}"))
    return issues


def _check_report(issues: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "kind": "penflow-generated-docs-check",
        "version": 1,
        "status": "FAIL" if issues else "PASS",
        "issues": sorted(issues, key=lambda item: (item["code"], item["message"])),
    }


def _issue(code: str, message: str) -> dict[str, str]:
    return {"severity": "error", "code": code, "message": message}


def _write_journal(journal: Path, output: Path, owned: list[str]) -> None:
    _durable_write(
        journal,
        (
            json.dumps({"version": 1, "output": str(output), "owned": owned}, sort_keys=True) + "\n"
        ).encode(),
    )


def _durable_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def _fsync_dir(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
