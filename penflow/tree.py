"""Expected and actual UI tree normalization."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .models import PenNode
from .pen import parse_pen, validate_pen_context

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


def validate_actual_tree(tree: dict[str, Any]) -> list[dict[str, Any]]:
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
    return issues


def normalize_actual_tree(tree: dict[str, Any]) -> dict[str, Any]:
    if "screens" in tree:
        return tree
    return {
        "version": tree.get("version", 1),
        "screens": [
            {
                "screen_id": tree.get("screen_id", "screen"),
                "viewport": tree.get("viewport", {}),
                "root": tree.get("root") or {"id": "root", "role": "container", "children": tree.get("nodes", [])},
            }
        ],
    }


def flatten_nodes(node: dict[str, Any], parent_id: str | None = None, order: int = 0) -> list[dict[str, Any]]:
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
