"""Flow, screen, draft, token, and IR helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .pen import load_pen, parse_pen, update_pen_by_semantic_id


def validate_flow_contract(flow: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for key in ("id", "screens"):
        if key not in flow:
            issues.append(_issue("error", f"$.{key}", f"{key} is required"))
    if not isinstance(flow.get("screens", []), list):
        issues.append(_issue("error", "$.screens", "screens must be a list"))
    for index, screen in enumerate(flow.get("screens", []) or []):
        if "id" not in screen:
            issues.append(_issue("error", f"$.screens[{index}].id", "screen id is required"))
    return issues


def validate_screen_contract(screen: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for key in ("id", "viewport", "components"):
        if key not in screen:
            issues.append(_issue("error", f"$.{key}", f"{key} is required"))
    if not isinstance(screen.get("components", []), list):
        issues.append(_issue("error", "$.components", "components must be a list"))
    return issues


def screen_contracts_from_flow(flow: dict[str, Any]) -> list[dict[str, Any]]:
    contracts = []
    for screen in flow.get("screens", []) or []:
        contracts.append(
            {
                "id": screen["id"],
                "surface": flow.get("surface", "default"),
                "viewport": screen.get("viewport", {"width": 390, "height": 844}),
                "data": screen.get("data", flow.get("fixtures", {})),
                "actions": screen.get("actions", []),
                "components": screen.get("components", []),
                "states": screen.get("states", ["default"]),
                "source": {"flow_id": flow.get("id"), "pencil": screen.get("pencil")},
            }
        )
    return contracts


def pencil_draft_from_screen(screen: dict[str, Any]) -> dict[str, Any]:
    viewport = screen.get("viewport", {"width": 390, "height": 844})
    root = {
        "id": f"{screen['id']}-screen",
        "type": "frame",
        "name": screen["id"],
        "width": viewport.get("width", 390),
        "height": viewport.get("height", 844),
        "layout": "vertical",
        "gap": 16,
        "padding": 24,
        "context": {"semantic_id": screen["id"], "role": "screen"},
        "children": [],
    }
    for index, component in enumerate(screen.get("components", []) or []):
        root["children"].append(_component_to_pen(component, index))
    return {"version": 1, "children": [root]}


def write_pencil_draft(screen_path: str | Path, out_path: str | Path) -> dict[str, Any]:
    screen = json.loads(Path(screen_path).read_text(encoding="utf-8"))
    draft = pencil_draft_from_screen(screen)
    Path(out_path).write_text(json.dumps(draft, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return draft


def update_pencil(path: str | Path, updates_path: str | Path, out_path: str | Path) -> None:
    updates = json.loads(Path(updates_path).read_text(encoding="utf-8"))
    update_pen_by_semantic_id(path, updates, out_path)


def extract_design_tokens(pen_path: str | Path) -> dict[str, Any]:
    nodes = [node for root in parse_pen(pen_path) for node in root.walk()]
    tokens: dict[str, Any] = {
        "colors": sorted({value for node in nodes for key, value in node.visual.items() if key in {"fill", "stroke"}}),
        "spacing": sorted({value for node in nodes for key, value in node.visual.items() if key in {"gap", "padding"}}),
        "radius": sorted({node.visual["cornerRadius"] for node in nodes if "cornerRadius" in node.visual}),
        "typography": sorted(
            {
                f"{node.visual.get('fontFamily', 'system')}:{node.visual.get('fontSize')}:{node.visual.get('fontWeight', 'regular')}"
                for node in nodes
                if "fontSize" in node.visual
            }
        ),
    }
    tokens["proposals"] = {
        "primary_color": tokens["colors"][0] if tokens["colors"] else None,
        "base_spacing": 16 if 16 in tokens["spacing"] else (tokens["spacing"][0] if tokens["spacing"] else None),
        "base_radius": tokens["radius"][0] if tokens["radius"] else None,
    }
    return tokens


def code_ir_from_contract(screen: dict[str, Any], expected_tree: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "version": 1,
        "screen": screen["id"],
        "viewport": screen.get("viewport", {}),
        "imports": [],
        "state": sorted({component.get("binding") for component in screen.get("components", []) if component.get("binding")}),
        "actions": screen.get("actions", []),
        "components": [
            {
                "id": component.get("semantic_id") or component.get("id"),
                "role": component.get("role", "container"),
                "text": component.get("text"),
                "binding": component.get("binding"),
                "intent": component.get("intent"),
            }
            for component in screen.get("components", [])
        ],
        "expected_tree_source": bool(expected_tree),
    }


def _component_to_pen(component: dict[str, Any], index: int) -> dict[str, Any]:
    role = component.get("role", "text")
    semantic_id = component.get("semantic_id") or component.get("id") or f"component-{index}"
    base = {
        "id": f"{semantic_id.replace('.', '-')}-{index}",
        "name": semantic_id,
        "width": component.get("width", 320),
        "height": component.get("height", 44),
        "context": {
            "semantic_id": semantic_id,
            "role": role,
            **({"intent": component["intent"]} if component.get("intent") else {}),
            **({"binding": component["binding"]} if component.get("binding") else {}),
            **({"repeat": component["repeat"]} if component.get("repeat") else {}),
        },
    }
    if role == "button":
        return {**base, "type": "frame", "layout": "horizontal", "children": [_text_child(semantic_id, component.get("text", "Button"))]}
    if role == "list":
        return {**base, "type": "frame", "layout": "vertical", "gap": 8, "children": [_text_child(semantic_id, component.get("text", "Item"))]}
    return {**base, "type": "text", "content": component.get("text", semantic_id)}


def _text_child(parent: str, text: str) -> dict[str, Any]:
    return {
        "id": f"{parent.replace('.', '-')}-label",
        "type": "text",
        "content": text,
        "context": {"semantic_id": f"{parent}.label", "role": "text"},
    }


def _issue(severity: str, path: str, message: str) -> dict[str, str]:
    return {"severity": severity, "path": path, "message": message}

