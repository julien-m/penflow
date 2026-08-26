"""Deterministic semantic-to-Pencil context mapping."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from .context import Context, infer_role
from .json_filesystem import write_json_atomically
from .semantic_enrichment import (
    PenRecord,
    SemanticRecord,
    active_pen_records,
    _enrich_node,
    _is_candidate_in_scope,
    _labels_match,
    _pen_records_by_semantic_id,
    _role_is_compatible,
    _semantic_records,
    _normalize,
)
from .semantic_validation import validate_semantic_tree
from .semantic_context_coverage import audit_semantic_context

MAP_VERSION = 1


# @spec FR-003: One canonical coverage service — .specs/features/076-exhaustive-bidirectional-semantic-context/spec.md#fr-003
def exhaustive_context_coverage(
    contract: dict[str, Any],
    pen: dict[str, Any],
    *,
    contract_path: str,
    pen_path: str,
    legacy: bool = False,
) -> dict[str, Any]:
    """Expose the canonical reverse-inclusive coverage result to mapping callers."""
    return audit_semantic_context(
        contract,
        pen,
        contract_path=contract_path,
        pen_path=pen_path,
        legacy=legacy,
    )


# @spec FR-005: Canonical producer migration — .specs/features/074-penflow-doctor-consumer-project-hygiene/spec.md#fr-005
def pencil_context_map(
    pen: dict[str, Any],
    tree: dict[str, Any],
    *,
    create_missing: bool = False,
) -> dict[str, Any]:
    """Build a deterministic mapping from semantic nodes to Pencil nodes.

    Args:
        pen: Parsed Pencil document.
        tree: Parsed semantic UI tree.
        create_missing: When true, place safe missing semantic nodes in `created`.

    Returns:
        Scriptable context map with matched, created, ambiguous, and unmapped buckets.

    Raises:
        ValueError: If the semantic tree is invalid.
    """
    issues = validate_semantic_tree(tree)
    if _has_errors(issues):
        raise ValueError(f"semantic UI tree is invalid: {issues[0]['code']}")

    semantic_records = _semantic_records(tree)
    pen_records = active_pen_records(pen)
    matched: list[dict[str, Any]] = []
    created: list[dict[str, Any]] = []
    ambiguous: list[dict[str, Any]] = []
    unmapped: list[dict[str, Any]] = []
    semantic_to_path: dict[str, tuple[int, ...]] = {}
    matched_paths: set[tuple[int, ...]] = set()

    _match_existing_semantic_ids(
        semantic_records, pen_records, matched, ambiguous, semantic_to_path, matched_paths
    )
    _match_conservative_candidates(
        semantic_records,
        pen_records,
        matched,
        created,
        ambiguous,
        unmapped,
        semantic_to_path,
        matched_paths,
        create_missing=create_missing,
    )
    return {
        "version": MAP_VERSION,
        "kind": "pencil-context-map",
        "status": "PARTIAL" if created or ambiguous or unmapped else "PASS",
        "matched": matched,
        "created": created,
        "ambiguous": ambiguous,
        "unmapped": unmapped,
    }


# @spec FR-005: Canonical producer migration — .specs/features/074-penflow-doctor-consumer-project-hygiene/spec.md#fr-005
def write_pencil_context_map(
    pen_path: str | Path,
    tree_path: str | Path,
    out_path: str | Path,
    *,
    pen_out: str | Path | None = None,
    create_placeholders: bool = False,
) -> dict[str, Any]:
    """Write `pencil-context-map.json` and optionally a mapped Pencil copy.

    Args:
        pen_path: Existing Pencil `.pen` file.
        tree_path: Valid `semantic-ui-tree.json`.
        out_path: Destination context-map JSON file.
        pen_out: Optional canonical Pencil destination enriched only on matched
            active nodes. When provided, it must resolve to ``pen_path``.
        create_placeholders: When true, unresolved semantic nodes are recorded as placeholders.

    Returns:
        The generated mapping artifact.

    Raises:
        ValueError: If ``pen_out`` is a peer Pencil path, if ``out_path``
            resolves to the canonical Pencil input, or if the semantic tree is invalid.

    Side Effects:
        When ``pen_out`` is provided, atomically replaces the canonical Pencil
        document before atomically writing the context map.
    """
    canonical_path = Path(pen_path).resolve()
    tree_input_path = Path(tree_path).resolve()
    map_path = Path(out_path).resolve()
    if pen_out is not None and Path(pen_out).resolve() != canonical_path:
        raise ValueError("mapped Pencil output must resolve to the canonical input ui.pen")
    if map_path == canonical_path:
        raise ValueError("context-map output must not overwrite canonical input ui.pen")
    pen = json.loads(canonical_path.read_text(encoding="utf-8"))
    tree = json.loads(tree_input_path.read_text(encoding="utf-8"))
    context_map = pencil_context_map(pen, tree, create_missing=create_placeholders)
    if pen_out is not None:
        write_json_atomically(canonical_path, _mapped_pen_copy(pen, tree, context_map))
    # The canonical Pencil bytes must be durable before the map advertises
    # their semantic bindings; a stale map is safer than a map for unwritten UI.
    write_json_atomically(map_path, context_map)
    return context_map


def _match_existing_semantic_ids(
    semantic_records: list[SemanticRecord],
    pen_records: list[PenRecord],
    matched: list[dict[str, Any]],
    ambiguous: list[dict[str, Any]],
    semantic_to_path: dict[str, tuple[int, ...]],
    matched_paths: set[tuple[int, ...]],
) -> None:
    by_semantic_id = _pen_records_by_semantic_id(pen_records)
    for semantic in semantic_records:
        exact_matches = by_semantic_id.get(semantic.semantic_id, [])
        if len(exact_matches) == 1:
            matched.append(_matched_entry(semantic, exact_matches[0], "semantic_id"))
            semantic_to_path[semantic.semantic_id] = exact_matches[0].path
            matched_paths.add(exact_matches[0].path)
        elif len(exact_matches) > 1:
            ambiguous.append(_ambiguous_entry(semantic, exact_matches, "semantic_id"))


def _match_conservative_candidates(
    semantic_records: list[SemanticRecord],
    pen_records: list[PenRecord],
    matched: list[dict[str, Any]],
    created: list[dict[str, Any]],
    ambiguous: list[dict[str, Any]],
    unmapped: list[dict[str, Any]],
    semantic_to_path: dict[str, tuple[int, ...]],
    matched_paths: set[tuple[int, ...]],
    *,
    create_missing: bool,
) -> None:
    for semantic in semantic_records:
        if semantic.semantic_id in semantic_to_path or _is_already_ambiguous(
            semantic.semantic_id, ambiguous
        ):
            continue
        parent_path = (
            semantic_to_path.get(semantic.parent_semantic_id)
            if semantic.parent_semantic_id
            else None
        )
        candidates = [
            record
            for record in pen_records
            if record.path not in matched_paths
            and _is_candidate_in_scope(record, parent_path)
            and _role_is_compatible(record.node, semantic.role)
            and _labels_match(record.node, semantic.node)
        ]
        if len(candidates) == 1:
            matched.append(_matched_entry(semantic, candidates[0], "hierarchy_label_role"))
            semantic_to_path[semantic.semantic_id] = candidates[0].path
            matched_paths.add(candidates[0].path)
        elif len(candidates) > 1:
            ambiguous.append(_ambiguous_entry(semantic, candidates, "hierarchy_label_role"))
        elif create_missing:
            created.append(_created_entry(semantic))
        else:
            unmapped.append(_unmapped_entry(semantic, pen_records))


def _mapped_pen_copy(
    pen: dict[str, Any], tree: dict[str, Any], context_map: dict[str, Any]
) -> dict[str, Any]:
    mapped_pen = copy.deepcopy(pen)
    records_by_path = {
        _path_string(record.path): record.node for record in active_pen_records(mapped_pen)
    }
    semantic_by_id = {record.semantic_id: record.node for record in _semantic_records(tree)}
    for item in context_map["matched"]:
        node = records_by_path.get(item["pencil_path"])
        semantic = semantic_by_id.get(item["semantic_id"])
        if node is not None and semantic is not None:
            _enrich_node(node, semantic)
    return mapped_pen


def _matched_entry(
    semantic: SemanticRecord, pen_record: PenRecord, strategy: str
) -> dict[str, Any]:
    return {
        "semantic_id": semantic.semantic_id,
        "role": semantic.role,
        "pencil_node_id": str(pen_record.node.get("id")),
        "pencil_path": _path_string(pen_record.path),
        "strategy": strategy,
    }


def _created_entry(semantic: SemanticRecord) -> dict[str, Any]:
    return {
        "semantic_id": semantic.semantic_id,
        "role": semantic.role,
        "parent_semantic_id": semantic.parent_semantic_id,
        "strategy": "create_placeholder",
        "placeholder": {
            "name": semantic.semantic_id,
            "role": semantic.role,
            "text": semantic.node.get("text"),
        },
    }


def _ambiguous_entry(
    semantic: SemanticRecord, candidates: list[PenRecord], strategy: str
) -> dict[str, Any]:
    return {
        "semantic_id": semantic.semantic_id,
        "screen_id": _screen_id(semantic),
        "role": semantic.role,
        "strategy": strategy,
        "candidates": [_candidate_entry(record) for record in candidates[:3]],
    }


def _unmapped_entry(semantic: SemanticRecord, candidates: list[PenRecord]) -> dict[str, Any]:
    return {
        "semantic_id": semantic.semantic_id,
        "screen_id": _screen_id(semantic),
        "role": semantic.role,
        "parent_semantic_id": semantic.parent_semantic_id,
        "reason": "no conservative Pencil match found",
        "candidates": [
            _candidate_entry(record) for record in _closest_candidates(semantic, candidates)
        ],
    }


def _closest_candidates(semantic: SemanticRecord, candidates: list[PenRecord]) -> list[PenRecord]:
    semantic_label = _normalize(
        str(semantic.node.get("text") or semantic.semantic_id.rsplit(".", 1)[-1])
    )

    def score(record: PenRecord) -> tuple[int, str]:
        labels = _pen_label_strings(record.node)
        value = 0
        if _role_is_compatible(record.node, semantic.role):
            value += 4
        if semantic_label in {_normalize(label) for label in labels}:
            value += 3
        if any(semantic_label in _normalize(label) for label in labels):
            value += 2
        if _screen_id(semantic) and record.path[:1] == (0,):
            value += 1
        return (-value, _path_string(record.path))

    return sorted(candidates, key=score)[:3]


def _candidate_entry(record: PenRecord) -> dict[str, Any]:
    context = Context.from_raw(record.node.get("context"))
    labels = _pen_label_strings(record.node)
    return {
        "pencil_node_id": str(record.node.get("id")),
        "pencil_path": _path_string(record.path),
        "name": record.node.get("name"),
        "label": labels[0] if labels else None,
        "role": infer_role(str(record.node.get("type") or "frame"), context),
    }


def _pen_label_strings(node: dict[str, Any]) -> list[str]:
    labels = [
        str(value)
        for value in (node.get("name"), node.get("content"))
        if isinstance(value, str) and value.strip()
    ]
    for child in node.get("children", []) or []:
        if isinstance(child, dict) and isinstance(child.get("content"), str):
            labels.append(str(child["content"]))
    return labels


def _screen_id(semantic: SemanticRecord) -> str:
    return semantic.semantic_id.split(".", 1)[0]


def _is_already_ambiguous(semantic_id: str, ambiguous: list[dict[str, Any]]) -> bool:
    return any(item["semantic_id"] == semantic_id for item in ambiguous)


def _path_string(path: tuple[int, ...]) -> str:
    return ".".join(str(part) for part in path)


def _has_errors(issues: list[dict[str, Any]]) -> bool:
    return any(issue.get("severity") == "error" for issue in issues)
