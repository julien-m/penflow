"""Small deterministic code generators from Penflow IR."""

from __future__ import annotations

import re
from typing import Any


def swiftui(ir: dict[str, Any]) -> str:
    model = _normalize_ir(ir)
    name = _pascal(model["screen"]) + "View"
    lines = [
        "import SwiftUI",
        "",
        f"struct {name}: View {{",
        "    var body: some View {",
        "        VStack(alignment: .leading, spacing: 16) {",
    ]
    for component in model["components"]:
        lines.extend(_swift_component(component))
    lines.extend(["        }", "        .padding(24)", "    }", "}", ""])
    return "\n".join(lines)


def react(ir: dict[str, Any]) -> str:
    model = _normalize_ir(ir)
    name = _pascal(model["screen"])
    lines = [
        f"export function {name}() {{",
        "  return (",
        f'    <main data-penflow-id="{model["screen"]}">',
    ]
    for component in model["components"]:
        lines.extend(_react_component(component))
    lines.extend(["    </main>", "  );", "}", ""])
    return "\n".join(lines)


def rust_dioxus(ir: dict[str, Any]) -> str:
    model = _normalize_ir(ir)
    name = _pascal(model["screen"])
    lines = [
        "use dioxus::prelude::*;",
        "",
        "#[component]",
        f"pub fn {name}() -> Element {{",
        "    rsx! {",
        f'        main {{ "data-penflow-id": "{model["screen"]}",',
    ]
    for component in model["components"]:
        lines.extend(_rust_component(component))
    lines.extend(["        }", "    }", "}", ""])
    return "\n".join(lines)


def _normalize_ir(ir: dict[str, Any]) -> dict[str, Any]:
    """Return the legacy generator view for both supported Code IR shapes.

    The codegen commands originally consumed feature-018 IR (`screen` plus flat
    `components`). Feature-036 contextualized IR uses `screens[]` and may expose
    global `components`; keep both shapes valid until the legacy command is removed.
    """
    if "screen" in ir:
        return {
            "screen": str(ir["screen"]),
            "components": _component_list(ir.get("components", [])),
        }

    screens = _screen_list(ir.get("screens", []))
    screen = screens[0] if screens else {}
    flow = ir.get("flow")
    flow_id = flow.get("id") if isinstance(flow, dict) else None
    screen_id = str(screen.get("id") or flow_id or "screen")
    components: list[dict[str, Any]] = []
    if isinstance(screen.get("root"), dict):
        components = _flatten_components(screen["root"])
    if not components:
        components = _component_list(ir.get("components", []))
    return {"screen": screen_id, "components": components}


def _screen_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _component_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [
        item for item in value if isinstance(item, dict) and item.get("role") in {"text", "button"}
    ]


def _flatten_components(node: dict[str, Any]) -> list[dict[str, Any]]:
    components = [node] if node.get("role") in {"text", "button"} else []
    if node.get("role") == "button":
        return components
    for child in node.get("children", []) or []:
        if isinstance(child, dict):
            components.extend(_flatten_components(child))
    return components


def _swift_component(component: dict[str, Any]) -> list[str]:
    text = component.get("text") or component.get("id") or ""
    sid = component.get("id") or "component"
    if component.get("role") == "button":
        return [
            f'            Button("{_escape(text)}") {{',
            f"                // intent: {component.get('intent', sid)}",
            "            }",
        ]
    return [f'            Text("{_escape(text)}")']


def _react_component(component: dict[str, Any]) -> list[str]:
    text = _escape(component.get("text") or component.get("id") or "")
    sid = component.get("id") or "component"
    if component.get("role") == "button":
        return [
            f'      <button data-penflow-id="{sid}" onClick={{() => undefined}}>{text}</button>'
        ]
    return [f'      <span data-penflow-id="{sid}">{text}</span>']


def _rust_component(component: dict[str, Any]) -> list[str]:
    text = _escape(component.get("text") or component.get("id") or "")
    sid = component.get("id") or "component"
    if component.get("role") == "button":
        return [f'            button {{ "data-penflow-id": "{sid}", "{text}" }}']
    return [f'            span {{ "data-penflow-id": "{sid}", "{text}" }}']


def _pascal(value: str) -> str:
    return (
        "".join(part.capitalize() for part in re.split(r"[^a-zA-Z0-9]+", value) if part) or "Screen"
    )


def _escape(value: Any) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"')
