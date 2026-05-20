"""Pencil .pen parsing, inspection, and update helpers."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .context import Context, ContextIssue, format_context_string, validate_context
from .models import BBox, PenNode

VISUAL_KEYS = {
    "fill",
    "stroke",
    "strokeThickness",
    "cornerRadius",
    "fontSize",
    "fontFamily",
    "fontWeight",
    "textAlign",
    "layout",
    "gap",
    "padding",
}


def load_pen(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def parse_pen(path_or_data: str | Path | dict[str, Any]) -> list[PenNode]:
    data = load_pen(path_or_data) if isinstance(path_or_data, (str, Path)) else path_or_data
    roots: list[PenNode] = []
    for index, child in enumerate(data.get("children", [])):
        roots.append(_parse_node(child, None, index))
    return roots


def _parse_node(data: dict[str, Any], parent_id: str | None, order: int) -> PenNode:
    context = Context.from_raw(data.get("context"))
    visual = {key: data[key] for key in VISUAL_KEYS if key in data}
    node = PenNode(
        id=str(data.get("id") or data.get("name") or f"node-{order}"),
        type=str(data.get("type") or "frame"),
        name=data.get("name"),
        content=data.get("content"),
        context=context,
        bbox=BBox.from_node(data),
        visual=visual,
        parent_id=parent_id,
        order=order,
    )
    for child_index, child in enumerate(data.get("children", []) or []):
        if isinstance(child, dict):
            node.children.append(_parse_node(child, node.id, child_index))
    return node


def all_nodes(roots: list[PenNode]) -> list[PenNode]:
    nodes: list[PenNode] = []
    for root in roots:
        nodes.extend(root.walk())
    return nodes


def inspect_pen(path: str | Path) -> dict[str, Any]:
    roots = parse_pen(path)
    nodes = all_nodes(roots)
    contextual = [node for node in nodes if node.context.to_dict()]
    buttons = [node for node in nodes if node.role == "button"]
    lists = [node for node in nodes if node.role in {"list", "list_item"}]
    dynamic_text = [node for node in nodes if node.context.binding and node.type == "text"]
    warnings = [issue for issue in validate_pen_context(roots) if issue.severity == "warning"]
    errors = [issue for issue in validate_pen_context(roots) if issue.severity == "error"]
    return {
        "screens": [
            {
                "id": root.id,
                "name": root.name,
                "children": len(root.children),
                "semantic_id": root.semantic_id,
            }
            for root in roots
        ],
        "node_count": len(nodes),
        "contextual_nodes": [node.semantic_id or node.id for node in contextual],
        "buttons": [node.semantic_id or node.id for node in buttons],
        "lists": [node.semantic_id or node.id for node in lists],
        "dynamic_text": [node.semantic_id or node.id for node in dynamic_text],
        "warnings": [asdict(issue) for issue in warnings],
        "errors": [asdict(issue) for issue in errors],
    }


def validate_pen_context(roots: list[PenNode]) -> list[ContextIssue]:
    issues: list[ContextIssue] = []
    seen: dict[str, str] = {}
    for node in all_nodes(roots):
        issues.extend(validate_context(node.id, node.type, node.context))
        if node.semantic_id:
            if node.semantic_id in seen:
                issues.append(
                    ContextIssue(
                        "error",
                        "context.semantic_id_duplicate",
                        f"semantic_id also used by {seen[node.semantic_id]}",
                        node.id,
                        node.semantic_id,
                    )
                )
            seen[node.semantic_id] = node.id
    return issues


def update_pen_by_semantic_id(
    path: str | Path, updates: dict[str, dict[str, Any]], out: str | Path
) -> None:
    data = load_pen(path)

    def visit(node: dict[str, Any]) -> None:
        raw_context = node.get("context")
        context = Context.from_raw(raw_context)
        if context.semantic_id in updates:
            update = updates[str(context.semantic_id)]
            if "context" in update:
                current = context.to_dict()
                current.update(update["context"])
                node["context"] = (
                    format_context_string(current) if isinstance(raw_context, str) else current
                )
            for key in ("content", "name"):
                if key in update:
                    node[key] = update[key]
        for child in node.get("children", []) or []:
            if isinstance(child, dict):
                visit(child)

    for child in data.get("children", []) or []:
        if isinstance(child, dict):
            visit(child)
    Path(out).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
