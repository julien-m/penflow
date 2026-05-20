"""Flow, screen, draft, token, and IR helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .context import Context, format_context_string, infer_role
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
    return {"version": "2.11", "children": [root]}


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
        "colors": sorted(
            {
                value
                for node in nodes
                for key, value in node.visual.items()
                if key in {"fill", "stroke"}
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
    tokens["proposals"] = {
        "primary_color": tokens["colors"][0] if tokens["colors"] else None,
        "base_spacing": 16
        if 16 in tokens["spacing"]
        else (tokens["spacing"][0] if tokens["spacing"] else None),
        "base_radius": tokens["radius"][0] if tokens["radius"] else None,
    }
    return tokens


def _spacing_values(value: Any) -> list[int | float]:
    if isinstance(value, (int, float)):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, (int, float))]
    return []


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


def code_ir_from_pen(
    pen_path: str | Path,
    *,
    flow_id: str | None = None,
    flow_name: str | None = None,
    semantic_tree: dict[str, Any] | str | Path | None = None,
    context_map: dict[str, Any] | str | Path | None = None,
) -> dict[str, Any]:
    """Build code IR from contextualized Pencil data.

    Args:
        pen_path: Pencil `.pen` file containing Penflow `context` metadata.
        flow_id: Optional flow identifier to attach to every exported screen.
        flow_name: Optional human-readable flow name.
        semantic_tree: Optional semantic UI tree (path or dict) — advisory only,
            attached to the IR top-level `inputs` for traceability.
        context_map: Optional Pencil context map (path or dict) — advisory only,
            attached to the IR top-level `inputs` for traceability.

    Returns:
        Deterministic runtime-agnostic code IR preserving hierarchy, context, states,
        validations, errors, test IDs, and source mapping.
    """
    pen = load_pen(pen_path)
    screens = [
        _screen_ir_from_pen_node(node, (index,), flow_id=flow_id)
        for index, node in enumerate(pen.get("children", []) or [])
        if isinstance(node, dict)
    ]
    inferred_flow_id = flow_id or (screens[0]["id"] if screens else Path(pen_path).stem)
    flow = {"id": inferred_flow_id, "name": flow_name or inferred_flow_id}
    ir: dict[str, Any] = {
        "version": 1,
        "kind": "penflow-code-ir",
        "source": "pencil-context",
        "flow": flow,
        "screens": screens,
        "bindings": sorted(_collect_node_values(screens, "binding")),
        "test_ids": sorted(_collect_node_values(screens, "test_id")),
        "actions": sorted(
            _collect_actions(screens),
            key=lambda item: (item.get("intent", ""), item.get("entity", "")),
        ),
        "components": _flat_components(screens),
    }
    inputs: dict[str, str] = {}
    if semantic_tree is not None:
        _load_optional_input(semantic_tree)  # validate it parses
        inputs["semantic_tree"] = _input_marker(semantic_tree)
    if context_map is not None:
        _load_optional_input(context_map)
        inputs["context_map"] = _input_marker(context_map)
    if inputs:
        ir["inputs"] = inputs
    return ir


def _load_optional_input(value: dict[str, Any] | str | Path) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return json.loads(Path(value).read_text(encoding="utf-8"))


def _input_marker(value: dict[str, Any] | str | Path) -> str:
    if isinstance(value, dict):
        return "inline"
    return str(value)


def _raise_if_no_context(screens: list[dict[str, Any]], pen_path: str | Path) -> None:
    """Raise PenflowError when no screen-tree node carries a semantic_id.

    Walks the IR screens (already built) and, when no `semantic_id` is found at all,
    raises with the first pencil node id + path that is missing context.
    """
    semantic_ids = _collect_node_values(screens, "semantic_id")
    if semantic_ids:
        return
    first_id = ""
    first_path = ""
    for screen in screens:
        for node in _walk_ir_nodes(screen["root"]):
            first_id = node.get("pencil_node_id", "")
            first_path = node.get("path", "")
            break
        if first_id:
            break
    # Local import to avoid a cli<->contracts cycle at module load time.
    from .cli import PenflowError

    raise PenflowError(
        f"no Penflow context found in {pen_path}; "
        f"first node missing semantic_id: id={first_id} path={first_path}"
    )


def validate_code_ir(ir: dict[str, Any]) -> list[dict[str, Any]]:
    """Validate a code IR against the bundled JSON Schema.

    Returns a list of structured issues `{severity, path, message}`. Empty list
    means the IR is valid. Falls back to a minimal structural check when the
    `jsonschema` library is unavailable.
    """
    schema_path = Path(__file__).parent / "schemas" / "code-ir.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    try:
        from jsonschema import Draft202012Validator  # type: ignore[import-not-found]
    except ImportError:
        return _validate_code_ir_minimal(ir, schema)
    validator = Draft202012Validator(schema)
    issues: list[dict[str, Any]] = []
    for error in sorted(validator.iter_errors(ir), key=lambda err: list(err.absolute_path)):
        issues.append(
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
    return issues


def _validate_code_ir_minimal(ir: dict[str, Any], schema: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for key in schema.get("required", []):
        if key not in ir:
            issues.append(_issue("error", f"$.{key}", f"{key} is required"))
    properties = schema.get("properties", {})
    if "kind" in properties and ir.get("kind") != properties["kind"].get("const"):
        issues.append(_issue("error", "$.kind", "kind must be penflow-code-ir"))
    if "source" in properties and ir.get("source") != properties["source"].get("const"):
        issues.append(_issue("error", "$.source", "source must be pencil-context"))
    allowed_state_kinds = {"empty", "error", "loading"}
    for screen in ir.get("screens", []) or []:
        for node in _walk_ir_nodes(screen.get("root", {})):
            for kind in node.get("state_kinds", []) or []:
                if kind not in allowed_state_kinds:
                    issues.append(
                        _issue(
                            "error",
                            f"$.screens[].state_kinds.{kind}",
                            f"state_kinds must be one of {sorted(allowed_state_kinds)}",
                        )
                    )
    return issues


def _screen_ir_from_pen_node(
    node: dict[str, Any],
    path: tuple[int, ...],
    *,
    flow_id: str | None,
) -> dict[str, Any]:
    root = _node_ir_from_pen_node(node, path)
    screen_id = root.get("semantic_id") or root.get("pencil_node_id") or root.get("id")
    return {
        "id": screen_id,
        "name": node.get("name") or screen_id,
        "flow_id": flow_id or screen_id,
        "viewport": {
            "width": node.get("width", 0) if isinstance(node.get("width", 0), (int, float)) else 0,
            "height": node.get("height", 0)
            if isinstance(node.get("height", 0), (int, float))
            else 0,
        },
        "states": root.get("states", []),
        "errors": root.get("errors", []),
        "test_id": root.get("test_id"),
        "source_map": root["source_map"],
        "root": root,
    }


def _node_ir_from_pen_node(node: dict[str, Any], path: tuple[int, ...]) -> dict[str, Any]:
    context = Context.from_raw(node.get("context"))
    raw_semantic = node.get("semantic")
    semantic: dict[str, Any] = raw_semantic if isinstance(raw_semantic, dict) else {}
    node_ir: dict[str, Any] = {
        "id": context.semantic_id or node.get("id"),
        "semantic_id": context.semantic_id,
        "pencil_node_id": str(node.get("id")),
        "path": _path_string(path),
        "name": node.get("name"),
        "text": node.get("content") or _first_child_text(node),
        "role": infer_role(str(node.get("type", "frame")), context),
        "type": str(node.get("type", "frame")),
        "source_map": _code_ir_source_map(node, context, path),
        "children": [
            _node_ir_from_pen_node(child, (*path, child_index))
            for child_index, child in enumerate(node.get("children", []) or [])
            if isinstance(child, dict)
        ],
    }
    for key in ("intent", "binding", "entity", "test_id"):
        value = getattr(context, key)
        if value:
            node_ir[key] = value
    for key in ("states", "validations", "side_effects", "errors"):
        value = semantic.get(key)
        if value:
            node_ir[key] = value
    if context.intent:
        node_ir["actions"] = [
            {
                "intent": context.intent,
                **({"entity": context.entity} if context.entity else {}),
            }
        ]
    if states := node_ir.get("states"):
        node_ir["state_kinds"] = _state_kinds(states)
    return {key: value for key, value in node_ir.items() if value not in (None, [], {})}


def _code_ir_source_map(
    node: dict[str, Any], context: Context, path: tuple[int, ...]
) -> dict[str, Any]:
    raw_source_map = node.get("source_map")
    source_map: dict[str, Any] = raw_source_map if isinstance(raw_source_map, dict) else {}
    return {
        **source_map,
        "pencil_node_id": str(node.get("id")),
        "pencil_path": _path_string(path),
        **({"semantic_id": context.semantic_id} if context.semantic_id else {}),
        **({"context": context.to_dict()} if context.to_dict() else {}),
    }


def _first_child_text(node: dict[str, Any]) -> str | None:
    for child in node.get("children", []) or []:
        if isinstance(child, dict) and isinstance(child.get("content"), str):
            return child["content"]
    return None


def _state_kinds(states: list[Any]) -> list[str]:
    names = {
        state.get("name")
        for state in states
        if isinstance(state, dict) and state.get("name") in {"empty", "error", "loading"}
    }
    return sorted(str(name) for name in names)


def _collect_node_values(screens: list[dict[str, Any]], key: str) -> set[str]:
    return {
        str(node[key])
        for screen in screens
        for node in _walk_ir_nodes(screen["root"])
        if node.get(key)
    }


def _collect_actions(screens: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [
        action
        for screen in screens
        for node in _walk_ir_nodes(screen["root"])
        for action in node.get("actions", []) or []
        if isinstance(action, dict)
    ]


def _flat_components(screens: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": node.get("semantic_id") or node.get("pencil_node_id"),
            "role": node.get("role"),
            "type": node.get("type"),
            "text": node.get("text"),
            "binding": node.get("binding"),
            "intent": node.get("intent"),
            "test_id": node.get("test_id"),
        }
        for screen in screens
        for node in _walk_ir_nodes(screen["root"])
    ]


def _walk_ir_nodes(node: dict[str, Any]) -> list[dict[str, Any]]:
    nodes = [node]
    for child in node.get("children", []) or []:
        nodes.extend(_walk_ir_nodes(child))
    return nodes


def _path_string(path: tuple[int, ...]) -> str:
    return ".".join(str(part) for part in path)


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
