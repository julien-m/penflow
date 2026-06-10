"""Expected and actual UI tree normalization."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .models import PenNode
from .pen import parse_pen, validate_pen_context
from .schema_cache import validator_for

REQUIRED_ACTUAL_NODE_KEYS = {"id", "role", "bbox"}
REQUIRED_BBOX_KEYS = {"x", "y", "width", "height"}


def expected_tree_from_pen(path: str | Path) -> dict[str, Any]:
    roots = parse_pen(path)
    issues = validate_pen_context(roots)
    return {
        "version": 1,
        "source": str(path),
        "screens": [_screen_to_expected(root) for root in roots],
        "issues": [asdict(issue) for issue in issues],
    }


def _screen_to_expected(root: PenNode) -> dict[str, Any]:
    return {
        "screen_id": root.semantic_id or root.id,
        "pencil_id": root.id,
        "name": root.name,
        "viewport": root.bbox.to_dict(),
        "root": root.to_expected(),
    }


def write_expected_tree(pen_path: str | Path, out_path: str | Path) -> dict[str, Any]:
    tree = expected_tree_from_pen(pen_path)
    Path(out_path).write_text(json.dumps(tree, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return tree


def load_tree(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def validate_actual_tree(tree: dict[str, Any], *, schema: bool = False) -> list[dict[str, Any]]:
    """Validate an actual UI tree.

    Args:
        tree: Actual UI tree dict (contract C12).
        schema: When True, also run JSON Schema validation against
            ``penflow/schemas/actual-ui-tree.schema.json`` (draft 2020-12) and
            merge schema errors into the returned issues list. Default ``False``
            preserves byte-identical v0 behavior shipped by features 007/008.

    Returns:
        List of structured issues ``{severity, path, message}``. Empty list
        means the tree is valid.
    """
    issues: list[dict[str, Any]] = []
    if not isinstance(tree, dict):
        return [_issue("error", "$", "actual tree must be an object")]
    if "version" not in tree:
        issues.append(_issue("error", "$.version", "version is required"))
    if "screen_id" not in tree and "screens" not in tree:
        issues.append(_issue("error", "$.screen_id", "screen_id or screens is required"))

    screens = tree.get("screens")
    if screens is None:
        screens = [tree]
    if not isinstance(screens, list):
        issues.append(_issue("error", "$.screens", "screens must be a list"))
        return issues
    for screen_index, screen in enumerate(screens):
        path = f"$.screens[{screen_index}]"
        if not isinstance(screen, dict):
            issues.append(_issue("error", path, "screen must be an object"))
            continue
        if not isinstance(screen.get("viewport", {}), dict):
            issues.append(_issue("error", f"{path}.viewport", "viewport must be an object"))
        root = screen.get("root") or {"children": screen.get("nodes", [])}
        issues.extend(_validate_actual_node(root, f"{path}.root"))
    if schema:
        # Normalize the legacy flat single-screen form before schema check so
        # existing v0 fixtures (feature 025) continue to validate against the
        # canonical {version, screens:[…]} shape declared by C12 (FR-006).
        canonical = normalize_actual_tree(tree) if isinstance(tree, dict) else tree
        issues.extend(_validate_actual_tree_schema(canonical))
    return issues


def _validate_actual_tree_schema(tree: Any) -> list[dict[str, Any]]:
    """Run the JSON Schema (draft 2020-12) validator on an actual UI tree.

    ``jsonschema`` is a hard dependency (feature 049); the full draft 2020-12
    validator is the only validation path. Errors are sorted deterministically
    by ``(absolute_path, message)`` so the merged list is reproducible across
    runs.
    """
    if not isinstance(tree, dict):
        return [_issue("error", "$", "actual tree must be an object")]
    validator = validator_for("actual-ui-tree.schema.json")
    raw_errors = list(validator.iter_errors(tree))
    formatted: list[dict[str, Any]] = []
    for error in raw_errors:
        formatted.append(
            _issue(
                "error",
                "$"
                + "".join(
                    f".{part}" if isinstance(part, str) else f"[{part}]"
                    for part in error.absolute_path
                ),
                error.message,
            )
        )
    formatted.sort(key=lambda item: (item["path"], item["message"]))
    return formatted


def normalize_actual_tree(tree: dict[str, Any]) -> dict[str, Any]:
    if "screens" in tree:
        return tree
    return {
        "version": tree.get("version", 1),
        "screens": [
            {
                "screen_id": tree.get("screen_id", "screen"),
                "viewport": tree.get("viewport", {}),
                "root": tree.get("root")
                or {"id": "root", "role": "container", "children": tree.get("nodes", [])},
            }
        ],
    }


def flatten_nodes(
    node: dict[str, Any], parent_id: str | None = None, order: int = 0
) -> list[dict[str, Any]]:
    semantic_id = node.get("semantic_id") or node.get("id")
    item = dict(node)
    item["_semantic_key"] = semantic_id
    item["_parent_key"] = parent_id
    item["_order"] = order
    children = item.pop("children", []) or []
    flattened = [item]
    for child_order, child in enumerate(children):
        if isinstance(child, dict):
            flattened.extend(flatten_nodes(child, semantic_id, child_order))
    return flattened


def _validate_actual_node(node: Any, path: str) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    if not isinstance(node, dict):
        return [_issue("error", path, "node must be an object")]
    if node.get("id") != "root" or node.keys() & REQUIRED_ACTUAL_NODE_KEYS:
        for key in REQUIRED_ACTUAL_NODE_KEYS:
            if key not in node:
                issues.append(_issue("error", f"{path}.{key}", f"{key} is required"))
        bbox = node.get("bbox", {})
        if not isinstance(bbox, dict):
            issues.append(_issue("error", f"{path}.bbox", "bbox must be an object"))
        else:
            for key in REQUIRED_BBOX_KEYS:
                if key not in bbox:
                    issues.append(_issue("error", f"{path}.bbox.{key}", f"{key} is required"))
    for index, child in enumerate(node.get("children", []) or []):
        issues.extend(_validate_actual_node(child, f"{path}.children[{index}]"))
    return issues


def _issue(severity: str, path: str, message: str) -> dict[str, Any]:
    return {"severity": severity, "path": path, "message": message}
