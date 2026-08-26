"""Report construction and stable input helpers for semantic coverage."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .context import Context
from .pencil_graph import PencilGraphNode


class CoverageInputError(ValueError):
    """An input could not be safely read or remained unstable."""


def node_finding(
    buckets: dict[str, list[dict[str, Any]]],
    bucket: str,
    code: str,
    node: PencilGraphNode,
    context: Context,
    message: str,
    *,
    blocking: bool = True,
) -> None:
    append_finding(
        buckets,
        bucket,
        code,
        "pencil",
        node_id=node.node_id,
        node_path=node.node_path,
        semantic_id=context.semantic_id,
        owner_screen=node.screen_id,
        message=message,
        correction="add or repair explicit semantic context fields",
        blocking=blocking,
    )


def append_finding(
    buckets: dict[str, list[dict[str, Any]]],
    bucket: str,
    code: str,
    document: str,
    *,
    node_id: str | None = None,
    node_path: str | None = None,
    semantic_id: str | None = None,
    contract_path: str | None = None,
    owner_screen: str | None = None,
    message: str,
    correction: str,
    blocking: bool = True,
) -> None:
    finding = {
        "code": code,
        "document": document,
        "node_id": node_id,
        "node_path": node_path,
        "semantic_id": semantic_id,
        "contract_path": contract_path,
        "owner_screen": owner_screen,
        "severity": "error" if blocking else "info",
        "blocking": blocking,
        "message": message,
        "correction": correction,
    }
    key = (code, contract_path, node_path)
    if not any(
        (item["code"], item["contract_path"], item["node_path"]) == key for item in buckets[bucket]
    ):
        buckets[bucket].append(finding)


def empty_summary(contract_total: int, metadata: int) -> dict[str, int]:
    return {
        "anchored_unique": 0,
        "blocking": 0,
        "classification_conflict": 0,
        "contract_anchor_duplicate": 0,
        "contract_anchor_missing": 0,
        "contract_total": contract_total,
        "decorative": 0,
        "inherited": 0,
        "out_of_scope_metadata": metadata,
        "pencil_records_seen": 0,
        "pencil_total": 0,
        "semantic": 0,
        "semantic_resolved": 0,
        "unclassified": 0,
    }


def finish_summary(summary: dict[str, int], buckets: dict[str, list[dict[str, Any]]]) -> None:
    summary["pencil_total"] = sum(
        summary[key]
        for key in (
            "semantic",
            "inherited",
            "decorative",
            "unclassified",
            "classification_conflict",
        )
    )
    summary["pencil_records_seen"] = summary["pencil_total"] + summary["out_of_scope_metadata"]
    summary["blocking"] = sum(
        1 for values in buckets.values() for finding in values if finding["blocking"]
    )


def sort_buckets(buckets: dict[str, list[dict[str, Any]]]) -> None:
    for values in buckets.values():
        values.sort(
            key=lambda item: (
                item["owner_screen"] or "",
                item["semantic_id"] or "",
                item["node_path"] or "",
                item["code"],
            )
        )


def coverage_status(blocking: int, legacy: bool) -> str:
    return "LEGACY_PARTIAL" if legacy else "FAIL" if blocking else "PASS"


def parse_input(data: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CoverageInputError(f"input.{label}_invalid") from exc
    if not isinstance(value, dict):
        raise CoverageInputError(f"input.{label}_invalid")
    return value


def read_input(path: Path) -> bytes:
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise CoverageInputError("input.unreadable") from exc
    if not data:
        raise CoverageInputError("input.empty")
    return data


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def digest_json(value: dict[str, Any]) -> str:
    return digest(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())
