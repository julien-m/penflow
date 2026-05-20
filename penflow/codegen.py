"""Small deterministic code generators from Penflow IR."""

from __future__ import annotations

import re
from typing import Any


def swiftui(ir: dict[str, Any]) -> str:
    name = _pascal(ir["screen"]) + "View"
    lines = [
        "import SwiftUI",
        "",
        f"struct {name}: View {{",
        "    var body: some View {",
        "        VStack(alignment: .leading, spacing: 16) {",
    ]
    for component in ir.get("components", []):
        lines.extend(_swift_component(component))
    lines.extend(["        }", "        .padding(24)", "    }", "}", ""])
    return "\n".join(lines)


def react(ir: dict[str, Any]) -> str:
    name = _pascal(ir["screen"])
    lines = [
        f"export function {name}() {{",
        "  return (",
        f'    <main data-penflow-id="{ir["screen"]}">',
    ]
    for component in ir.get("components", []):
        lines.extend(_react_component(component))
    lines.extend(["    </main>", "  );", "}", ""])
    return "\n".join(lines)


def rust_dioxus(ir: dict[str, Any]) -> str:
    name = _pascal(ir["screen"])
    lines = [
        "use dioxus::prelude::*;",
        "",
        "#[component]",
        f"pub fn {name}() -> Element {{",
        "    rsx! {",
        f'        main {{ "data-penflow-id": "{ir["screen"]}",',
    ]
    for component in ir.get("components", []):
        lines.extend(_rust_component(component))
    lines.extend(["        }", "    }", "}", ""])
    return "\n".join(lines)


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
