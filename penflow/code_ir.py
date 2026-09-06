"""Pencil context to runtime-agnostic code IR and its public validation."""

from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from .context import Context, infer_role
from .flow_contract import (
    FlowContractValidationError,
    contract_registries,
    validate_flow_contract_v2,
)
from .pen import load_pen
from .pen_lifecycle import select_active_canvas_region_entries
from .schema_cache import validator_for


def code_ir_from_pen(
    pen_path: str | Path,
    *,
    flow_id: str | None = None,
    flow_name: str | None = None,
    semantic_tree: dict[str, Any] | str | Path | None = None,
    context_map: dict[str, Any] | str | Path | None = None,
    contract: dict[str, Any] | str | Path | None = None,
    pen_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    # @spec FR-008: Preserve v2 contract semantics in code IR — .specs/features/045-penflow-json-only-strict-contract-v2/spec.md#fr-008
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
    pen = load_pen(pen_path) if pen_data is None else pen_data
    # @spec FR-005: Code handoff consumes active regions only — .specs/features/074-penflow-doctor-consumer-project-hygiene/spec.md#fr-005
    active_regions = select_active_canvas_region_entries(pen)
    screens = [
        _screen_ir_from_pen_node(dict(region.raw_node), (region.source_index,), flow_id=flow_id)
        for region in active_regions
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
    if contract is not None:
        inputs["contract"] = _input_marker(contract)
        ir["contract"] = _contract_projection(contract)
    if inputs:
        ir["inputs"] = inputs
    return ir


def _contract_projection(contract: dict[str, Any] | str | Path) -> dict[str, Any]:
    contract_data = _load_optional_input(contract)
    issues = validate_flow_contract_v2(contract_data)
    errors = [issue for issue in issues if issue["severity"] == "error"]
    if errors:
        first = errors[0]
        raise FlowContractValidationError(
            f"contract validation failed: {first['path']}: {first['message']}"
        )
    registries = contract_registries(contract_data)
    contract_nodes = {str(node["id"]): node for node in contract_data.get("nodes", [])}
    return {
        "contract_id": contract_data["contract_id"],
        **{
            key: contract_data[key]
            for key in ("requirements", "outcome_expectations", "verification_policy")
            if key in contract_data
        },
        **(
            {"system_returns": contract_data["system_returns"]}
            if "system_returns" in contract_data
            else {}
        ),
        "actors": sorted(registries["actors"].values(), key=lambda item: item["id"]),
        "entities": sorted(registries["entities"].values(), key=lambda item: item["id"]),
        "screens": sorted(registries["screens"].values(), key=lambda item: item["id"]),
        "actions": sorted(
            (
                _semantic_contract_action(action, contract_nodes)
                for action in registries["actions"].values()
            ),
            key=lambda item: item["id"],
        ),
        "mutations": sorted(registries["mutations"].values(), key=lambda item: item["id"]),
        "guards": sorted(registries["guards"].values(), key=lambda item: item["id"]),
        "permissions": sorted(registries["permissions"].values(), key=lambda item: item["id"]),
        "bindings": sorted(registries["fields"]),
        "states": sorted(
            {
                f"{screen['id']}.{state['id']}"
                for screen in contract_data.get("screens", []) or []
                for state in screen.get("states", []) or []
            }
        ),
        "transitions": sorted(registries["transitions"].values(), key=lambda item: item["id"]),
    }


def assert_contextualized_pen_input(pen_path: str | Path) -> None:
    """Fail early when `code-ir --from-context` receives the wrong artifact."""
    path = Path(pen_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(_code_ir_context_message(path, "input JSON is not an object"))
    if "children" in data:
        return
    if "screens" in data:
        raise ValueError(
            _code_ir_context_message(path, "got expected-ui-tree.json or actual-ui-tree.json")
        )
    raise ValueError(_code_ir_context_message(path, "missing Pencil document children"))


def _code_ir_context_message(path: Path, reason: str) -> str:
    return (
        "code-ir --from-context expects the contextualized .pen file with Pencil "
        "`context` metadata, not expected-ui-tree.json; "
        f"received {path} ({reason})"
    )


def _semantic_contract_action(
    action: dict[str, Any], contract_nodes: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    handoff = dict(action)
    node = contract_nodes.get(str(action.get("node")))
    if node and node.get("semantic_id"):
        handoff["node"] = node["semantic_id"]
    return handoff


def _load_optional_input(value: dict[str, Any] | str | Path) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return json.loads(Path(value).read_text(encoding="utf-8"))


def _input_marker(value: dict[str, Any] | str | Path) -> str:
    if isinstance(value, dict):
        return "inline"
    return str(value)


def raise_if_no_context(screens: list[dict[str, Any]], pen_path: str | Path) -> None:
    """Raise PenflowError when no screen-tree node carries a semantic_id.

    Args:
        screens: Built IR screens to inspect without mutation.
        pen_path: Source Pencil path included in a missing-context diagnostic.

    Raises:
        PenflowError: No node has a semantic ID; includes the first node ID and path.
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
    means the IR is valid. ``jsonschema`` is a hard dependency (feature 049);
    the full draft 2020-12 validator is the only validation path.
    """
    validator = validator_for("code-ir.schema.json")
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
    for key in ("intent", "binding", "entity", "test_id", "permission"):
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
            "children": [
                {
                    "id": child.get("semantic_id") or child.get("pencil_node_id"),
                    "role": child.get("role"),
                    "text": child.get("text"),
                }
                for child in node.get("children", []) or []
                if isinstance(child, dict)
            ],
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


def _issue(severity: str, path: str, message: str) -> dict[str, str]:
    return {"severity": severity, "path": path, "message": message}


# Compatibility for existing embedding imports; new callers use the public name.
_raise_if_no_context = raise_if_no_context
