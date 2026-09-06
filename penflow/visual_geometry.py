"""Legacy layout snapshot parsing and geometry overlays for visual metric checks."""

import json
from pathlib import Path
from typing import Any
from .compare import _canonical_number, _is_number


def load_layout_snapshot(
    layout_snapshot: str | Path | dict[str, Any] | None,
) -> dict[tuple[str | None, str], dict[str, Any]] | None:
    """Load and index legacy snapshot geometry by optional screen and node identity.

    Args:
        layout_snapshot: JSON file, parsed snapshot, or None when no overlay is supplied.

    Returns:
        Normalized bounding boxes by identity, or None for an absent snapshot.

    Raises:
        ValueError: The file cannot be read/parsed or the snapshot is not an object.
    """
    if layout_snapshot is None:
        return None
    if isinstance(layout_snapshot, (str, Path)):
        path = Path(layout_snapshot)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise ValueError(f"layout snapshot is not valid JSON: {path}: {error}") from error
        except OSError as error:
            raise ValueError(f"layout snapshot could not be read: {path}: {error}") from error
    else:
        raw = layout_snapshot
    if not isinstance(raw, dict):
        raise ValueError("layout snapshot must be a JSON object")
    bboxes: dict[tuple[str | None, str], dict[str, Any]] = {}
    _collect_snapshot_bboxes(raw, None, bboxes)
    return bboxes


def layout_snapshot_input(layout_snapshot: str | Path | dict[str, Any] | None) -> str | None:
    """Return the file provenance marker for a layout overlay.

    Args:
        layout_snapshot: File path, inline snapshot, or absent overlay.

    Returns:
        The supplied path as text, or None for inline or absent snapshots.
    """
    if isinstance(layout_snapshot, (str, Path)):
        return str(layout_snapshot)
    return None


def _collect_snapshot_bboxes(
    item: Any,
    screen_id: str | None,
    bboxes: dict[tuple[str | None, str], dict[str, Any]],
) -> None:
    if isinstance(item, list):
        for child in item:
            _collect_snapshot_bboxes(child, screen_id, bboxes)
        return
    if not isinstance(item, dict):
        return
    current_screen_id = _snapshot_screen_id(item) or screen_id
    bbox = _snapshot_bbox_from_item(item)
    if bbox is not None:
        for identifier in _snapshot_identifiers(item):
            bboxes[(current_screen_id, identifier)] = bbox
    for key in ("screens", "root", "nodes", "children"):
        if key in item:
            _collect_snapshot_bboxes(item[key], current_screen_id, bboxes)


def _snapshot_screen_id(item: dict[str, Any]) -> str | None:
    raw = item.get("screen_id") or item.get("screenId")
    return str(raw) if raw is not None else None


def _snapshot_identifiers(item: dict[str, Any]) -> list[str]:
    identifiers: list[str] = []
    for key in (
        "semantic_id",
        "semanticId",
        "id",
        "node_id",
        "nodeId",
        "pencil_node_id",
        "pencilId",
    ):
        raw = item.get(key)
        if raw is not None:
            identifiers.append(str(raw))
    return sorted(set(identifiers))


def _snapshot_bbox_from_item(item: dict[str, Any]) -> dict[str, Any] | None:
    raw_bbox = item.get("bbox")
    if isinstance(raw_bbox, dict):
        return _normalize_snapshot_bbox(raw_bbox)
    if _is_number(item.get("width")) and _is_number(item.get("height")):
        return {
            "x": _canonical_number(float(item["x"])) if _is_number(item.get("x")) else 0,
            "y": _canonical_number(float(item["y"])) if _is_number(item.get("y")) else 0,
            "width": _canonical_number(float(item["width"])),
            "height": _canonical_number(float(item["height"])),
        }
    return None


def _normalize_snapshot_bbox(bbox: dict[str, Any]) -> dict[str, Any] | None:
    if not all(_is_number(bbox.get(key)) for key in ("x", "y", "width", "height")):
        return None
    return {
        "x": _canonical_number(float(bbox["x"])),
        "y": _canonical_number(float(bbox["y"])),
        "width": _canonical_number(float(bbox["width"])),
        "height": _canonical_number(float(bbox["height"])),
    }


def overlay_geometry_nodes(
    screen_id: str,
    nodes: list[dict[str, Any]],
    snapshot_bboxes: dict[tuple[str | None, str], dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Overlay measured geometry while preserving original node records.

    Args:
        screen_id: Screen identity used before unscoped snapshot lookup.
        nodes: Flattened nodes with semantic keys.
        snapshot_bboxes: Indexed measurements, or None to disable the overlay.

    Returns:
        Original nodes if no snapshot is supplied; otherwise shallow node copies
        with matched bounding boxes and _layout_snapshot_bbox availability flags.
    """
    if snapshot_bboxes is None:
        return nodes
    geometry_nodes: list[dict[str, Any]] = []
    for node in nodes:
        geometry_node = dict(node)
        bbox = _snapshot_bbox_for_node(screen_id, node, snapshot_bboxes)
        if bbox is not None:
            geometry_node["bbox"] = bbox
            geometry_node["_layout_snapshot_bbox"] = True
        else:
            geometry_node["_layout_snapshot_bbox"] = False
        geometry_nodes.append(geometry_node)
    return geometry_nodes


def _snapshot_bbox_for_node(
    screen_id: str,
    node: dict[str, Any],
    snapshot_bboxes: dict[tuple[str | None, str], dict[str, Any]],
) -> dict[str, Any] | None:
    candidates = _snapshot_identifiers(node) + [str(node["_semantic_key"])]
    for identifier in dict.fromkeys(candidates):
        bbox = snapshot_bboxes.get((screen_id, identifier)) or snapshot_bboxes.get(
            (None, identifier)
        )
        if bbox is not None:
            return bbox
    return None
