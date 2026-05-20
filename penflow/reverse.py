"""Reverse Pencil `.pen` files into flow-ui-contract specs and semantic trees."""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

from .context import Context, format_context_string, infer_role

CLARIFICATION = "[NEEDS CLARIFICATION]"


def reverse_pen(
    pen_path: str | Path, out_dir: str | Path, *, enrich: bool = False
) -> dict[str, Any]:
    """Reverse an existing Pencil file into specs and a semantic UI tree.

    Args:
        pen_path: Source Pencil `.pen` path.
        out_dir: Destination reverse output directory.
        enrich: Whether to also write `ui.enriched.pen` with context metadata only.

    Returns:
        Scriptable report containing generated file paths and screen count.
    """
    pen = json.loads(Path(pen_path).read_text(encoding="utf-8"))
    out = Path(out_dir)
    specs_dir = out / "flow-ui-contract"
    flows_dir = specs_dir / "flows"
    screens_dir = specs_dir / "screens"
    flows_dir.mkdir(parents=True, exist_ok=True)
    screens_dir.mkdir(parents=True, exist_ok=True)

    screen_specs = [_screen_from_pen_node(node, (index,)) for index, node in _root_nodes(pen)]
    flow_specs = [_flow_from_screen(screen) for screen in screen_specs]
    semantic_tree = _semantic_tree(screen_specs, flow_specs, pen_path, Path("flow-ui-contract"))

    for flow in flow_specs:
        (flows_dir / f"{flow['id']}.md").write_text(_flow_markdown(flow), encoding="utf-8")
    for screen in screen_specs:
        (screens_dir / f"{screen['id']}.md").write_text(_screen_markdown(screen), encoding="utf-8")
    semantic_path = out / "semantic-ui-tree.json"
    semantic_path.write_text(
        json.dumps(semantic_tree, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    files = [str(semantic_path), *(str(path) for path in sorted(specs_dir.rglob("*.md")))]

    if enrich:
        enriched = _enriched_pen(pen, semantic_tree)
        enriched_path = out / "ui.enriched.pen"
        enriched_path.write_text(
            json.dumps(enriched, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        files.append(str(enriched_path))

    return {"status": "PASS", "out": str(out), "screens": len(screen_specs), "files": files}


def _root_nodes(pen: dict[str, Any]) -> list[tuple[int, dict[str, Any]]]:
    return [
        (index, child)
        for index, child in enumerate(pen.get("children", []) or [])
        if isinstance(child, dict)
    ]


def _screen_from_pen_node(node: dict[str, Any], path: tuple[int, ...]) -> dict[str, Any]:
    context = Context.from_raw(node.get("context"))
    screen_id = str(context.semantic_id or _slug(node.get("name") or node.get("id") or "screen"))
    children = [
        _semantic_node_from_pen(child, screen_id, (*path, child_index), child_index)
        for child_index, child in enumerate(node.get("children", []) or [])
        if isinstance(child, dict)
    ]
    return {
        "id": screen_id,
        "title": str(node.get("name") or screen_id),
        "node": node,
        "path": path,
        "children": children,
        "viewport": {
            "width": node.get("width", 390)
            if isinstance(node.get("width", 390), (int, float))
            else 390,
            "height": node.get("height", 844)
            if isinstance(node.get("height", 844), (int, float))
            else 844,
        },
    }


def _semantic_node_from_pen(
    node: dict[str, Any], screen_id: str, path: tuple[int, ...], order: int
) -> dict[str, Any]:
    context = Context.from_raw(node.get("context"))
    role = _reverse_role(node, context)
    semantic_id = str(context.semantic_id or f"{screen_id}.{_node_slug(node, role, order)}")
    result: dict[str, Any] = {
        "semantic_id": semantic_id,
        "role": role,
        "source_map": _source_map(node, path),
    }
    if text := _node_text(node):
        result["text"] = text
    for key in ("intent", "binding", "repeat", "entity", "test_id"):
        value = getattr(context, key)
        if value:
            result[key] = value
    if role in {"button", "link", "input", "select", "toggle", "form"} and not result.get("intent"):
        result["intent"] = CLARIFICATION
    children = [
        _semantic_node_from_pen(child, screen_id, (*path, child_index), child_index)
        for child_index, child in enumerate(node.get("children", []) or [])
        if isinstance(child, dict)
    ]
    if children and role not in {"button", "input", "select", "toggle"}:
        result["children"] = children
    return result


def _flow_from_screen(screen: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": screen["id"],
        "title": screen["title"],
        "entry_screen": screen["id"],
        "steps": [
            {
                "id": f"{screen['id']}-step",
                "screen_id": screen["id"],
                "intent": CLARIFICATION,
                "actor": CLARIFICATION,
            }
        ],
        "transitions": [],
    }


def _semantic_tree(
    screens: list[dict[str, Any]],
    flows: list[dict[str, Any]],
    pen_path: str | Path,
    specs_dir: Path,
) -> dict[str, Any]:
    return {
        "version": 1,
        "kind": "semantic-ui-tree",
        "tree_id": _slug(Path(pen_path).stem or "reverse"),
        "source": {"mockup": str(pen_path), "notes": ["Reverse-engineered from Pencil .pen."]},
        "flows": [
            {
                "id": flow["id"],
                "title": flow["title"],
                "entry_screen": flow["entry_screen"],
                "steps": flow["steps"],
                "transitions": flow["transitions"],
                "source_map": {
                    "flow_spec": _posix(specs_dir / "flows" / f"{flow['id']}.md"),
                    "mockup": str(pen_path),
                },
            }
            for flow in flows
        ],
        "screens": [_semantic_screen(screen, pen_path, specs_dir) for screen in screens],
    }


def _semantic_screen(
    screen: dict[str, Any], pen_path: str | Path, specs_dir: Path
) -> dict[str, Any]:
    screen_spec = _posix(specs_dir / "screens" / f"{screen['id']}.md")
    root = {
        "semantic_id": screen["id"],
        "role": "screen",
        "states": [{"name": "default"}],
        "source_map": _source_map(screen["node"], screen["path"]) | {"screen_spec": screen_spec},
        "children": screen["children"],
    }
    return {
        "id": screen["id"],
        "flow_id": screen["id"],
        "surface": "web",
        "viewport": screen["viewport"],
        "states": [{"name": "default"}],
        "validations": [],
        "side_effects": [],
        "source_map": {
            "screen_spec": screen_spec,
            "mockup": str(pen_path),
            "pencil_node_id": screen["node"].get("id"),
        },
        "root": root,
    }


def _flow_markdown(flow: dict[str, Any]) -> str:
    return (
        f"---\n"
        f"flow: {flow['id']}\n"
        f"title: {flow['title']}\n"
        f"priority: P3\n"
        f"status: draft\n"
        f"---\n\n"
        f"# Flow {flow['title']}\n\n"
        f"## Primary Actor\n\n{CLARIFICATION}\n\n"
        f"## User Scenarios & Testing\n\n"
        f"- Entry screen: `{flow['entry_screen']}`\n"
        f"- Business intent: {CLARIFICATION}\n"
        f"- Transitions: {CLARIFICATION}\n"
    )


def _screen_markdown(screen: dict[str, Any]) -> str:
    visible_text = sorted(
        {
            node.get("text", "")
            for node in _walk_semantic_nodes(screen["children"])
            if node.get("text")
        }
    )
    actions = [
        node for node in _walk_semantic_nodes(screen["children"]) if node["role"] == "button"
    ]
    data_lines = "\n".join(f"- {text}" for text in visible_text) or f"- {CLARIFICATION}"
    action_lines = "\n".join(
        f"| {action.get('text', action['semantic_id'])} | button | {CLARIFICATION} |"
        for action in actions
    )
    if not action_lines:
        action_lines = f"| {CLARIFICATION} | {CLARIFICATION} | {CLARIFICATION} |"
    return (
        f"---\n"
        f"screen: {screen['id']}\n"
        f"flow: {screen['id']}\n"
        f"title: {screen['title']}\n"
        f"status: draft\n"
        f"sourceNodeId: {screen['node'].get('id')}\n"
        f"---\n\n"
        f"# Screen {screen['title']}\n\n"
        f"## Displayed Data\n\n{data_lines}\n\n"
        f"## Actions\n\n"
        f"| Element | Type | Effect |\n"
        f"|---|---|---|\n"
        f"{action_lines}\n\n"
        f"## UI States\n\ndefault\n\n"
        f"## Validations\n\n- {CLARIFICATION}\n\n"
        f"## Local Side Effects\n\n- {CLARIFICATION}\n"
    )


def _enriched_pen(pen: dict[str, Any], tree: dict[str, Any]) -> dict[str, Any]:
    enriched = copy.deepcopy(pen)
    semantic_by_node_id = {
        node["source_map"]["pencil_node_id"]: node
        for screen in tree["screens"]
        for node in [screen["root"], *_walk_semantic_nodes(screen["root"].get("children", []))]
        if node.get("source_map", {}).get("pencil_node_id")
    }

    def visit(node: dict[str, Any]) -> None:
        semantic = semantic_by_node_id.get(node.get("id"))
        if semantic:
            current = Context.from_raw(node.get("context")).to_dict()
            for key in ("semantic_id", "role", "intent", "binding", "repeat", "entity", "test_id"):
                if semantic.get(key):
                    current[key] = semantic[key]
            node["context"] = format_context_string(current)
            node["source_map"] = semantic["source_map"]
        for child in node.get("children", []) or []:
            if isinstance(child, dict):
                visit(child)

    for child in enriched.get("children", []) or []:
        if isinstance(child, dict):
            visit(child)
    return enriched


def _walk_semantic_nodes(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for node in nodes:
        result.append(node)
        result.extend(_walk_semantic_nodes(node.get("children", []) or []))
    return result


def _reverse_role(node: dict[str, Any], context: Context) -> str:
    if context.role:
        return str(context.role)
    if node.get("type") == "frame" and _node_text(node):
        return "button"
    return infer_role(str(node.get("type", "frame")), context)


def _node_slug(node: dict[str, Any], role: str, order: int) -> str:
    if role == "text" and node.get("content"):
        content_slug = _slug(str(node["content"]))
        return "title" if order == 0 else content_slug
    return _slug(str(node.get("name") or node.get("id") or f"{role}-{order}"))


def _node_text(node: dict[str, Any]) -> str | None:
    if isinstance(node.get("content"), str) and node["content"].strip():
        return str(node["content"])
    for child in node.get("children", []) or []:
        if (
            isinstance(child, dict)
            and isinstance(child.get("content"), str)
            and child["content"].strip()
        ):
            return str(child["content"])
    return None


def _source_map(node: dict[str, Any], path: tuple[int, ...]) -> dict[str, Any]:
    return {"pencil_node_id": node.get("id"), "notes": [f"pencil_path: {_path_string(path)}"]}


def _path_string(path: tuple[int, ...]) -> str:
    return ".".join(str(part) for part in path)


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "screen"


def _posix(path: Path) -> str:
    return path.as_posix()
