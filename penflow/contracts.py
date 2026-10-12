# @spec(FR-001)
# @spec(FR-002)
# @spec(FR-003)
# @spec(FR-006)
# @spec(FR-007)
# @spec(FR-008)
"""Flow, screen, draft, token, and IR helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .context import format_context_string

# Preserve established imports while keeping IR conversion in its own domain module.
from .code_ir import (
    raise_if_no_context as raise_if_no_context,
    code_ir_from_pen as code_ir_from_pen,
    validate_code_ir as validate_code_ir,
    assert_contextualized_pen_input as assert_contextualized_pen_input,
)
from .schema_cache import validator_for as validator_for
from .models import PenNode
from .pen import parse_pen, update_pen_by_semantic_id
from .pen_schema import PEN_WRITE_VERSION

# Prefer the design-token spacing scale's base (16 px) when it is observed.
DEFAULT_BASE_SPACING = 16


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
        "id": _node_id(screen["id"], "screen"),
        "type": "frame",
        "name": screen["id"],
        "x": 0,
        "y": 0,
        "width": viewport.get("width", 390),
        "height": viewport.get("height", 844),
        "layout": "vertical",
        "gap": 16,
        "padding": 24,
        "alignItems": "center",
        "fill": "#FFFFFF",
        "context": _context({"semantic_id": screen["id"], "role": "screen"}),
        "children": [],
    }
    for index, component in enumerate(screen.get("components", []) or []):
        root["children"].append(_component_to_pen(component, index))
    return {"version": PEN_WRITE_VERSION, "children": [root]}


def write_pencil_draft(screen_path: str | Path, out_path: str | Path) -> dict[str, Any]:
    screen = json.loads(Path(screen_path).read_text(encoding="utf-8"))
    draft = pencil_draft_from_screen(screen)
    Path(out_path).write_text(json.dumps(draft, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return draft


def update_pencil(path: str | Path, updates_path: str | Path, out_path: str | Path) -> None:
    updates = json.loads(Path(updates_path).read_text(encoding="utf-8"))
    update_pen_by_semantic_id(path, updates, out_path)


def extract_design_tokens(
    pen_path: str | Path, *, theme: dict[str, Any] | None = None
) -> dict[str, Any]:
    # @spec FR-006: Optional theme adds violations — .specs/features/046-lint-design-tokens/spec.md#fr-006
    """Extract design tokens from a `.pen` file, optionally linting against a theme.

    Args:
        pen_path: Path to the `.pen` file.
        theme: Optional loaded theme (`penflow.theme.load_theme` shape). When
            provided, the returned dict gains a `violations` list computed by
            the token lint engine; without it the legacy shape is unchanged.

    Returns:
        Token summary with `colors`, `spacing`, `radius`, `typography`,
        `proposals`, `issues` (`tokens.value.unparsed` warnings for values the
        extractor cannot interpret, feature 049), and (with `theme`)
        `violations`.
    """
    nodes = [node for root in parse_pen(pen_path) for node in root.walk()]
    tokens: dict[str, Any] = {
        "colors": sorted(
            {
                color
                for node in nodes
                for key, value in node.visual.items()
                if key in {"fill", "stroke"}
                for color in _color_values(value)
            }
        ),
        "spacing": sorted(
            {
                spacing
                for node in nodes
                for key, value in node.visual.items()
                if key in {"gap", "padding"}
                for spacing in _spacing_values(value)
            }
        ),
        "radius": sorted(
            {node.visual["cornerRadius"] for node in nodes if "cornerRadius" in node.visual}
        ),
        "typography": sorted(
            {
                f"{node.visual.get('fontFamily', 'system')}:{node.visual.get('fontSize')}:{node.visual.get('fontWeight', 'regular')}"
                for node in nodes
                if "fontSize" in node.visual
            }
        ),
    }
    tokens["proposals"] = _token_proposals(tokens)
    tokens["issues"] = _unparsed_token_issues(nodes)
    if theme is not None:
        # Local import to keep module load order stable (token_lint imports pen).
        from .token_lint import lint_tokens

        tokens["violations"] = lint_tokens(pen_path, theme=theme)["violations"]
    return tokens


def _color_values(value: Any) -> list[str]:
    # Drafted strokes are objects {"fill": ..., "thickness": ...}; unwrap them.
    if isinstance(value, dict):
        fill = value.get("fill")
        return [fill] if isinstance(fill, str) else []
    return [value] if isinstance(value, str) else []


def _spacing_values(value: Any) -> list[int | float]:
    if isinstance(value, (int, float)):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, (int, float))]
    return []


def _unparsed_token_issues(nodes: list[PenNode]) -> list[dict[str, Any]]:
    # @spec FR-007: surface dropped token values — .specs/features/049-strict-mode-default-blocking-drift/spec.md#fr-007
    """Report visual token values that the extractor silently drops.

    `_color_values`/`_spacing_values` discard anything they cannot interpret;
    this scan turns each dropped value into a `tokens.value.unparsed` warning
    so `extract-tokens` can exit non-zero instead of laundering bad data.
    """
    issues: list[dict[str, Any]] = []
    for node in nodes:
        for key in ("fill", "stroke"):
            value = node.visual.get(key)
            if value is None:
                continue
            if not _color_values(value):
                issues.append(_unparsed_token_issue(node.id, key, value))
        for key in ("gap", "padding"):
            value = node.visual.get(key)
            if value is None:
                continue
            parsed = _spacing_values(value)
            expected = len(value) if isinstance(value, list) else 1
            if len(parsed) != expected:
                issues.append(_unparsed_token_issue(node.id, key, value))
    issues.sort(key=lambda issue: (issue["path"], issue["message"]))
    return issues


def _unparsed_token_issue(node_id: str, key: str, value: Any) -> dict[str, Any]:
    return {
        "severity": "warning",
        "code": "tokens.value.unparsed",
        "path": f"{node_id}.{key}",
        "message": f"token value cannot be interpreted: {value!r}",
    }


def code_ir_from_contract(
    screen: dict[str, Any], expected_tree: dict[str, Any] | None = None
) -> dict[str, Any]:
    return {
        "version": 1,
        "screen": screen["id"],
        "viewport": screen.get("viewport", {}),
        "imports": [],
        "state": sorted(
            {
                component.get("binding")
                for component in screen.get("components", [])
                if component.get("binding")
            }
        ),
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
        "id": _node_id(semantic_id, str(index)),
        "name": semantic_id,
        "context": _context(
            {
                "semantic_id": semantic_id,
                "role": role,
                **({"intent": component["intent"]} if component.get("intent") else {}),
                **({"binding": component["binding"]} if component.get("binding") else {}),
                **({"repeat": component["repeat"]} if component.get("repeat") else {}),
            }
        ),
    }
    if role == "button":
        return {
            **base,
            "type": "frame",
            "layout": "horizontal",
            "width": component.get("width", "fill_container"),
            "height": "fit_content(44)",
            "padding": [12, 16],
            "gap": 8,
            "alignItems": "center",
            "justifyContent": "center",
            "cornerRadius": 8,
            "fill": "#0057FF",
            "children": [_text_child(semantic_id, component.get("text", "Button"), fill="#FFFFFF")],
        }
    if role == "list":
        return {
            **base,
            "type": "frame",
            "layout": "vertical",
            "width": component.get("width", "fill_container"),
            "height": "fit_content(44)",
            "gap": 8,
            "alignItems": "start",
            "children": [_text_child(semantic_id, component.get("text", "Item"))],
        }
    return {
        **base,
        "type": "text",
        "content": component.get("text", semantic_id),
        "textGrowth": "fixed-width",
        "width": component.get("width", "fill_container"),
        "fontSize": component.get("fontSize", 24 if index == 0 else 16),
        "fontWeight": component.get("fontWeight", "600" if index == 0 else "400"),
        "fill": component.get("fill", "#111827"),
    }


def _text_child(parent: str, text: str, *, fill: str = "#111827") -> dict[str, Any]:
    return {
        "id": _node_id(parent, "label"),
        "type": "text",
        "content": text,
        "fontSize": 16,
        "fontWeight": "600",
        "fill": fill,
        "context": _context({"semantic_id": f"{parent}.label", "role": "text"}),
    }


def _context(context: dict[str, Any]) -> str:
    return format_context_string(context)


def _node_id(*parts: str) -> str:
    raw = "".join(part.title() for part in parts)
    safe = "".join(char for char in raw if char.isalnum())
    return safe[:1].lower() + safe[1:] if safe else "node"


def _issue(severity: str, path: str, message: str) -> dict[str, str]:
    return {"severity": severity, "path": path, "message": message}


def _token_proposals(tokens: dict[str, Any]) -> dict[str, Any]:
    return {
        "primary_color": tokens["colors"][0] if tokens["colors"] else None,
        "base_spacing": DEFAULT_BASE_SPACING
        if DEFAULT_BASE_SPACING in tokens["spacing"]
        else (tokens["spacing"][0] if tokens["spacing"] else None),
        "base_radius": tokens["radius"][0] if tokens["radius"] else None,
    }


# Compatibility for existing embedding imports; new callers use the public name.
_raise_if_no_context = raise_if_no_context
