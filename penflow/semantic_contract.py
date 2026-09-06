"""Validated canonical v2 contract conversion, separate from legacy Markdown export."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .contract_semantics import canonical_node_slots
from .flow_contract import (
    FlowContractValidationError,
    load_flow_contract_v2,
    validate_flow_contract_v2,
)


def semantic_tree_from_contract(
    path_or_contract: str | Path | dict[str, Any], *, source_path: str | None = None
) -> dict[str, Any]:
    # @spec FR-005: Semantic export reads v2 contract.json — .specs/features/045-penflow-json-only-strict-contract-v2/spec.md#fr-005
    """Build a semantic UI tree from canonical v2 `contract.json`.

    Args:
        path_or_contract: Path to `contract.json`, or an already loaded v2 contract object.

    Returns:
        Deterministic semantic UI tree generated from the strict JSON contract.
    """
    contract_path: str | None = source_path
    if isinstance(path_or_contract, dict):
        contract = path_or_contract
    else:
        contract_path = str(path_or_contract)
        contract = load_flow_contract_v2(path_or_contract)
    _require_valid_contract(contract)
    nodes = {str(node["id"]): node for node in contract["nodes"]}
    node_paths = {
        str(node["id"]): f"$.nodes[{index}]" for index, node in enumerate(contract["nodes"])
    }
    actions = {str(action["id"]): action for action in contract["actions"]}
    behaviors = _screen_behaviors(contract)
    screens = []
    for screen_index, screen in enumerate(contract["screens"]):
        root = _contract_node(
            nodes[str(screen["root_node"])],
            nodes,
            actions,
            node_paths,
            contract_path,
        )
        screen_behaviors = behaviors.get(str(screen["id"]), {})
        screens.append(
            {
                "id": screen["id"],
                "flow_id": screen["flow_id"],
                "surface": screen.get("surface", "web"),
                "viewport": screen.get("viewport", {}),
                "states": [{"name": state["id"]} for state in screen.get("states", [])],
                "validations": screen_behaviors.get("validations", []),
                "side_effects": screen_behaviors.get("side_effects", []),
                "source_map": {
                    "contract": contract_path or "inline",
                    "contract_path": f"$.screens[{screen_index}]",
                },
                "root": root,
            }
        )
    return _semantic_envelope(contract, contract_path, screens)


def _semantic_envelope(
    contract: dict[str, Any], contract_path: str | None, screens: list[dict[str, Any]]
) -> dict[str, Any]:
    return {
        "version": 1,
        "kind": "semantic-ui-tree",
        **{
            key: contract[key]
            for key in ("requirements", "outcome_expectations", "verification_policy")
            if key in contract
        },
        "tree_id": contract["contract_id"],
        "source": {
            "contract": contract_path or "inline",
            "notes": ["Generated deterministically from v2 contract.json."],
        },
        "flows": _contract_flows(contract, contract_path),
        "screens": screens,
        **({"system_returns": contract["system_returns"]} if "system_returns" in contract else {}),
    }


def _contract_node(
    node: dict[str, Any],
    nodes: dict[str, dict[str, Any]],
    actions: dict[str, dict[str, Any]],
    node_paths: dict[str, str],
    contract_path: str | None,
) -> dict[str, Any]:
    built: dict[str, dict[str, Any]] = {}
    pending = [(node["id"], False)]
    while pending:
        node_id, visited = pending.pop()
        source = nodes[node_id]
        if not visited:
            pending.append((node_id, True))
            pending.extend((child, False) for child in reversed(source.get("children", [])))
        else:
            children = [built[child] for child in source.get("children", [])]
            built[node_id] = _project_node(source, actions, node_paths, contract_path, children)
    return built[node["id"]]


def _project_node(
    node: dict[str, Any],
    actions: dict[str, dict[str, Any]],
    node_paths: dict[str, str],
    contract_path: str | None,
    children: list[dict[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "semantic_id": node["semantic_id"],
        "role": node["role"],
        "source_map": {
            "contract": contract_path or "inline",
            "contract_path": node_paths[node["id"]],
        },
        "children": children,
    }
    for key in ("text", "binding", "entity", "test_id"):
        if node.get(key):
            result[key] = node[key]
    repeat_model = node.get("repeat_model")
    if isinstance(repeat_model, dict):
        result["repeat"] = _repeat_expression(repeat_model)
    slots = canonical_node_slots(node, actions)
    for key in ("entity", "permission"):
        if slots[key]:
            result[key] = slots[key]
    if node.get("action") and node["action"] in actions:
        action = dict(actions[node["action"]])
        action["node"] = node["semantic_id"]
        result["actions"] = [action]
        result["intent"] = node["action"]
    return {key: value for key, value in result.items() if value not in (None, [], {})}


def _repeat_expression(repeat_model: dict[str, Any]) -> str:
    """Project a v2 repeat model into the semantic v1 repeat expression.

    The semantic tree schema stores only the iterable expression. The canonical
    contract remains authoritative for the item model and instance template.
    """
    return f"{repeat_model['item_key']} in {repeat_model['collection']}"


def _screen_behaviors(contract: dict[str, Any]) -> dict[str, dict[str, list[dict[str, Any]]]]:
    """Derive semantic screen behaviors from guards, permissions, and mutations."""
    nodes = {str(node["id"]): node for node in contract.get("nodes", [])}
    guards = {str(item["id"]): item for item in contract.get("guards", [])}
    permissions = {str(item["id"]): item for item in contract.get("permissions", [])}
    mutations = {str(item["id"]): item for item in contract.get("mutations", [])}
    by_screen: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for action in contract.get("actions", []) or []:
        node = nodes.get(str(action.get("node")))
        if not node:
            continue
        bucket = by_screen.setdefault(
            str(node.get("screen_id")), {"validations": [], "side_effects": []}
        )
        if action.get("guard"):
            bucket["validations"].append(
                {
                    "kind": "guard",
                    "id": action["guard"],
                    "source": guards.get(str(action["guard"]), {}),
                }
            )
        if action.get("permission"):
            bucket["validations"].append(
                {
                    "kind": "permission",
                    "id": action["permission"],
                    "source": permissions.get(str(action["permission"]), {}),
                }
            )
        if action.get("mutation"):
            bucket["side_effects"].append(
                {
                    "kind": "mutation",
                    "id": action["mutation"],
                    "source": mutations.get(str(action["mutation"]), {}),
                }
            )
    return by_screen


def _contract_transition(transition: dict[str, Any]) -> dict[str, Any]:
    condition = str(transition["guard"]) if transition.get("guard") else None
    return {
        "id": transition["id"],
        "from": transition.get("from_screen"),
        "to": transition.get("to_screen"),
        "trigger": transition.get("trigger"),
        **({"action": transition["action"]} if transition.get("action") else {}),
        **({"guard": transition["guard"]} if transition.get("guard") else {}),
        **({"condition": condition} if condition else {}),
        **({"kind": transition["kind"]} if transition.get("kind") else {}),
        **({"label": transition["label"]} if transition.get("label") else {}),
        **({"causal": transition["causal"]} if transition.get("causal") else {}),
    }


def _contract_flows(contract: dict[str, Any], contract_path: str | None) -> list[dict[str, Any]]:
    return [
        {
            "id": flow["id"],
            "title": flow.get("title", flow["id"]),
            "entry_screen": flow["entry_screen"],
            "steps": [
                {
                    "id": f"{flow['id']}-entry",
                    "screen_id": flow["entry_screen"],
                    "intent": flow["id"],
                }
            ],
            "transitions": [
                _contract_transition(transition)
                for transition in contract.get("transitions", [])
                if transition.get("flow") == flow["id"]
            ],
            "source_map": {
                "contract": contract_path or "inline",
                "contract_path": f"$.flows[{flow_index}]",
            },
        }
        for flow_index, flow in enumerate(contract["flows"])
    ]


def _require_valid_contract(contract: dict[str, Any]) -> None:
    issues = validate_flow_contract_v2(contract)
    if any(issue["severity"] == "error" for issue in issues):
        first = next(issue for issue in issues if issue["severity"] == "error")
        raise FlowContractValidationError(
            f"contract validation failed: {first['path']}: {first['message']}"
        )
