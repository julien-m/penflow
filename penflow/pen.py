"""Pencil .pen parsing, inspection, and update helpers."""

from __future__ import annotations

import json
import re
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .context import Context, ContextIssue, format_context_string, validate_context
from .flow_contract import contract_registries
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
    raw_semantic = data.get("semantic")
    semantic = raw_semantic if isinstance(raw_semantic, dict) else {}
    node = PenNode(
        id=str(data.get("id") or data.get("name") or f"node-{order}"),
        type=str(data.get("type") or "frame"),
        name=data.get("name"),
        content=data.get("content"),
        semantic=semantic,
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
    raw = load_pen(path)
    roots = parse_pen(raw)
    nodes = all_nodes(roots)
    contextual = [node for node in nodes if node.context.to_dict()]
    buttons = [node for node in nodes if node.role == "button"]
    lists = [node for node in nodes if node.role in {"list", "list_item"}]
    dynamic_text = [node for node in nodes if node.context.binding and node.type == "text"]
    issues = validate_pen_context(roots)
    # Raw re-scan (feature 049): coerced bbox strings are only visible in raw JSON.
    warnings = [issue for issue in issues if issue.severity == "warning"] + bbox_issues(raw)
    errors = [issue for issue in issues if issue.severity == "error"]
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


# Matches Pencil sizing keywords: "fill_container", "fit_content", and
# "fit_content(<number>)" — legitimate string dimensions, not corruption.
_PEN_SIZING_KEYWORD_RE = re.compile(r"^(?:fill_container|fit_content(?:\(\d+(?:\.\d+)?\))?)$")


def bbox_issues(data: dict[str, Any]) -> list[ContextIssue]:
    # @spec FR-010: surface coerced bbox values — .specs/features/049-strict-mode-default-blocking-drift/spec.md#fr-010
    """Warn about raw bbox string values that ``BBox.from_node`` coerces to 0.

    Args:
        data: Raw `.pen` JSON object (before ``parse_pen`` loses raw values).

    Returns:
        One ``pen.bbox.invalid`` warning per non-empty string ``x``/``y``/
        ``width``/``height`` value that is not a recognized Pencil sizing
        keyword. Coercion behavior itself is unchanged.
    """
    issues: list[ContextIssue] = []

    def visit(node: dict[str, Any], order: int) -> None:
        node_id = str(node.get("id") or node.get("name") or f"node-{order}")
        semantic_id = Context.from_raw(node.get("context")).semantic_id
        for key in ("x", "y", "width", "height"):
            value = node.get(key)
            if (
                isinstance(value, str)
                and value.strip()
                and not _PEN_SIZING_KEYWORD_RE.match(value.strip())
            ):
                issues.append(
                    ContextIssue(
                        "warning",
                        "pen.bbox.invalid",
                        f"bbox {key} is a string coerced to 0: {value!r}",
                        node_id,
                        semantic_id,
                    )
                )
        for child_order, child in enumerate(node.get("children", []) or []):
            if isinstance(child, dict):
                visit(child, child_order)

    for order, child in enumerate(data.get("children", []) or []):
        if isinstance(child, dict):
            visit(child, order)
    return issues


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


# @spec FR-007: Validate .pen against contract — .specs/features/045-penflow-json-only-strict-contract-v2/spec.md#fr-007
def validate_pen_context_against_contract(
    roots: list[PenNode], contract: dict[str, Any]
) -> list[ContextIssue]:
    """Validate `.pen` context identifiers against a v2 flow contract."""
    issues = validate_pen_context(roots)
    registries = contract_registries(contract)
    seen: dict[str, set[str]] = {
        "semantic_ids": set(),
        "test_ids": set(),
        "actions": set(),
        "permissions": set(),
        "fields": set(),
        "entities": set(),
    }
    for node in all_nodes(roots):
        context = node.context
        semantic_id = context.semantic_id
        if semantic_id:
            seen["semantic_ids"].add(str(semantic_id))
        if semantic_id and semantic_id not in registries["semantic_ids"]:
            issues.append(
                ContextIssue(
                    "error",
                    "contract.semantic_id_missing",
                    "semantic_id is absent from contract nodes",
                    node.id,
                    semantic_id,
                )
            )
        if context.intent and context.intent in registries["actions"]:
            seen["actions"].add(str(context.intent))
            permission = registries["actions"][str(context.intent)].get("permission")
            if permission:
                seen["permissions"].add(str(permission))
        if context.test_id:
            seen["test_ids"].add(str(context.test_id))
        if context.test_id and context.test_id not in registries["test_ids"]:
            issues.append(
                ContextIssue(
                    "error",
                    "contract.test_id_missing",
                    "test_id is absent from contract nodes",
                    node.id,
                    semantic_id,
                )
            )
        if context.action:
            seen["actions"].add(str(context.action))
            permission = registries["actions"].get(str(context.action), {}).get("permission")
            if permission:
                seen["permissions"].add(str(permission))
        if context.action and context.action not in registries["actions"]:
            issues.append(
                ContextIssue(
                    "error",
                    "contract.action_missing",
                    "action is absent from contract actions",
                    node.id,
                    semantic_id,
                )
            )
        if context.permission:
            seen["permissions"].add(str(context.permission))
        if context.permission and context.permission not in registries["permissions"]:
            issues.append(
                ContextIssue(
                    "error",
                    "contract.permission_missing",
                    "permission is absent from contract permissions",
                    node.id,
                    semantic_id,
                )
            )
        if context.binding:
            seen["fields"].add(str(context.binding))
        if context.binding and context.binding not in registries["fields"]:
            issues.append(
                ContextIssue(
                    "error",
                    "contract.binding_missing",
                    "binding field is absent from contract entities",
                    node.id,
                    semantic_id,
                )
            )
        if context.entity:
            seen["entities"].add(str(context.entity))
        if context.entity and context.entity not in registries["entities"]:
            issues.append(
                ContextIssue(
                    "error",
                    "contract.entity_missing",
                    "entity is absent from contract entities",
                    node.id,
                    semantic_id,
                )
            )
        contract_node = registries["semantic_ids"].get(str(semantic_id)) if semantic_id else None
        contract_screen_id = (
            contract_node.get("screen_id") if isinstance(contract_node, dict) else None
        )
        if contract_screen_id:
            screen_states = {
                str(state["id"])
                for screen in contract.get("screens", []) or []
                if isinstance(screen, dict) and screen.get("id") == contract_screen_id
                for state in screen.get("states", []) or []
                if isinstance(state, dict) and isinstance(state.get("id"), str)
            }
            for state in _node_state_names(node):
                if state not in screen_states:
                    issues.append(
                        ContextIssue(
                            "error",
                            "contract.state_missing",
                            "state is absent from contract screen states",
                            node.id,
                            semantic_id,
                        )
                    )
    required = {
        "semantic_ids": set(registries["semantic_ids"]),
        "test_ids": set(registries["test_ids"]),
        "actions": set(registries["actions"]),
        "permissions": set(registries["permissions"]),
        "fields": {
            str(node["binding"])
            for node in registries["nodes"].values()
            if isinstance(node.get("binding"), str)
        },
        "entities": {
            str(node["entity"])
            for node in registries["nodes"].values()
            if isinstance(node.get("entity"), str)
        },
    }
    labels = {
        "semantic_ids": (
            "contract.semantic_id_unmapped",
            "contract semantic_id is absent from .pen context",
        ),
        "test_ids": ("contract.test_id_unmapped", "contract test_id is absent from .pen context"),
        "actions": ("contract.action_unmapped", "contract action is absent from .pen context"),
        "permissions": (
            "contract.permission_unmapped",
            "contract permission is absent from .pen context",
        ),
        "fields": (
            "contract.binding_unmapped",
            "contract binding field is absent from .pen context",
        ),
        "entities": ("contract.entity_unmapped", "contract entity is absent from .pen context"),
    }
    for registry_name, expected_values in required.items():
        code, message = labels[registry_name]
        for value in sorted(expected_values - seen[registry_name]):
            issues.append(ContextIssue("error", code, message, "contract", value))
    return issues


def _node_state_names(node: PenNode) -> set[str]:
    states = node.semantic.get("states")
    if not isinstance(states, list):
        return set()
    result: set[str] = set()
    for state in states:
        if isinstance(state, str):
            result.add(state)
        elif isinstance(state, dict):
            value = state.get("id", state.get("name"))
            if isinstance(value, str):
                result.add(value)
    return result


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
