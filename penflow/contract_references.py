"""Canonical contract cross-record references by record category."""

from __future__ import annotations

import re
from typing import Any

from .contract_actions import action_binding_issues, local_submit_transition_issues
from .contract_records import (
    record_items,
    screen_state_ids,
    append_missing_reference,
    contract_issue,
    interactive_binding_kind,
)
from .contract_causality import (
    _validate_guard_semantics,
    _validate_transition_semantics,
    _validate_transition_fanout,
)
from .flow_contract_context import semantic_context_reference_issues

BINDING_RE = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
INTERACTIVE_ROLES = {"button", "link", "input", "select", "toggle", "form", "component"}
VISUALLY_INTERACTIVE_ROLES = {"button", "link", "input"}


def validate_references(
    contract: dict[str, Any],
    registries: dict[str, Any],
    transition_triggers: set[str],
    issues: list[dict[str, Any]],
) -> None:
    """Validate all canonical cross-record references using prebuilt registries."""
    _duplicate_id_issues(contract, issues)
    if contract.get("needs_clarification"):
        issues.append(
            contract_issue(
                "error",
                "contract.clarification.unresolved",
                "$.needs_clarification",
                "clarification items must be resolved before strict validation",
            )
        )
    _validate_screens(contract, registries, transition_triggers, issues)
    _validate_nodes(contract, registries, transition_triggers, issues)
    _validate_actions(contract, registries, transition_triggers, issues)
    _validate_permissions(contract, registries, transition_triggers, issues)
    screen_states = screen_state_ids(contract)
    action_screens = {
        str(action["id"]): str(node["screen_id"])
        for action in record_items(contract, "actions")
        if isinstance(action.get("id"), str)
        for node in [registries["nodes"].get(action.get("node"))]
        if isinstance(node, dict) and isinstance(node.get("screen_id"), str)
    }
    _validate_mutations(
        contract, registries, transition_triggers, issues, screen_states, action_screens
    )
    _validate_transitions(
        contract, registries, transition_triggers, issues, screen_states, action_screens
    )
    _validate_guard_semantics(contract, issues)
    _validate_transition_fanout(contract, registries, issues)
    issues.extend(semantic_context_reference_issues(contract, registries, screen_states))
    _unused_reference_issues(contract, issues)


def _validate_transitions(
    contract: dict[str, Any],
    registries: dict[str, Any],
    transition_triggers: set[str],
    issues: list[dict[str, Any]],
    screen_states: dict[str, set[str]],
    action_screens: dict[str, str],
) -> None:
    for index, transition in enumerate(record_items(contract, "transitions")):
        path = f"$.transitions[{index}]"
        if transition.get("flow") not in registries["flows"]:
            append_missing_reference("flow", transition.get("flow"), f"{path}.flow", issues)
        for field in ("from_screen", "to_screen"):
            if transition.get(field) not in registries["screens"]:
                append_missing_reference("screen", transition.get(field), f"{path}.{field}", issues)
        for field in ("from_state", "to_state"):
            screen_field = "from_screen" if field == "from_state" else "to_screen"
            screen_id = transition.get(screen_field)
            states = screen_states.get(str(screen_id), set())
            if transition.get(field) not in states:
                append_missing_reference("state", transition.get(field), f"{path}.{field}", issues)
        if transition.get("action") and transition.get("action") not in registries["actions"]:
            append_missing_reference("action", transition.get("action"), f"{path}.action", issues)
        trigger = transition.get("trigger")
        if trigger not in registries["actions"]:
            trigger_node = registries["nodes"].get(trigger)
            if trigger_node is None:
                append_missing_reference("trigger", trigger, f"{path}.trigger", issues)
            elif trigger_node.get("role") not in INTERACTIVE_ROLES:
                issues.append(
                    contract_issue(
                        "error",
                        "contract.reference.non_interactive_trigger",
                        f"{path}.trigger",
                        "transition trigger node must be interactive",
                    )
                )
        _validate_transition_semantics(transition, path, registries, issues)


def _validate_mutations(
    contract: dict[str, Any],
    registries: dict[str, Any],
    transition_triggers: set[str],
    issues: list[dict[str, Any]],
    screen_states: dict[str, set[str]],
    action_screens: dict[str, str],
) -> None:
    for index, mutation in enumerate(record_items(contract, "mutations")):
        if mutation.get("entity") not in registries["entities"]:
            append_missing_reference(
                "entity", mutation.get("entity"), f"$.mutations[{index}].entity", issues
            )
        mutation_actions = [
            str(action["id"])
            for action in record_items(contract, "actions")
            if action.get("mutation") == mutation.get("id") and isinstance(action.get("id"), str)
        ]
        for state_field in ("success_state", "error_state"):
            value = mutation.get(state_field)
            if mutation_actions:
                for action_id in mutation_actions:
                    screen_id = action_screens.get(action_id)
                    if screen_id and value not in screen_states.get(screen_id, set()):
                        append_missing_reference(
                            "state",
                            value,
                            f"$.mutations[{index}].{state_field}",
                            issues,
                        )
            elif not any(value in states for states in screen_states.values()):
                append_missing_reference(
                    "state", value, f"$.mutations[{index}].{state_field}", issues
                )


def _validate_permissions(
    contract: dict[str, Any],
    registries: dict[str, Any],
    transition_triggers: set[str],
    issues: list[dict[str, Any]],
) -> None:
    for index, permission in enumerate(record_items(contract, "permissions")):
        if permission.get("actor") not in registries["actors"]:
            append_missing_reference(
                "actor", permission.get("actor"), f"$.permissions[{index}].actor", issues
            )
        if permission.get("action") not in registries["actions"]:
            append_missing_reference(
                "action", permission.get("action"), f"$.permissions[{index}].action", issues
            )
        if permission.get("entity") not in registries["entities"]:
            append_missing_reference(
                "entity", permission.get("entity"), f"$.permissions[{index}].entity", issues
            )


def _validate_actions(
    contract: dict[str, Any],
    registries: dict[str, Any],
    transition_triggers: set[str],
    issues: list[dict[str, Any]],
) -> None:
    for index, action in enumerate(record_items(contract, "actions")):
        path = f"$.actions[{index}]"
        node = registries["nodes"].get(action.get("node"))
        if node is None:
            append_missing_reference("node", action.get("node"), f"{path}.node", issues)
        elif node.get("role") not in INTERACTIVE_ROLES:
            issues.append(
                contract_issue(
                    "error",
                    "contract.reference.non_interactive_action",
                    f"{path}.node",
                    "action node must be interactive",
                )
            )
        for field, registry_name in (
            ("guard", "guards"),
            ("permission", "permissions"),
            ("mutation", "mutations"),
            ("success_transition", "transitions"),
            ("error_transition", "transitions"),
        ):
            value = action.get(field)
            if value and value not in registries[registry_name]:
                append_missing_reference(registry_name[:-1], value, f"{path}.{field}", issues)
        if node is not None:
            issues.extend(action_binding_issues(action, node, registries["screens"], path))
            issues.extend(
                local_submit_transition_issues(action, node, registries["transitions"], path)
            )


def _validate_nodes(
    contract: dict[str, Any],
    registries: dict[str, Any],
    transition_triggers: set[str],
    issues: list[dict[str, Any]],
) -> None:
    for index, node in enumerate(record_items(contract, "nodes")):
        path = f"$.nodes[{index}]"
        if node.get("screen_id") not in registries["screens"]:
            append_missing_reference("screen", node.get("screen_id"), f"{path}.screen_id", issues)
        if binding := node.get("binding"):
            if not isinstance(binding, str) or not BINDING_RE.match(binding):
                issues.append(
                    contract_issue(
                        "error",
                        "contract.reference.invalid_binding",
                        f"{path}.binding",
                        "binding must use entity.field",
                    )
                )
            elif binding not in registries["fields"]:
                append_missing_reference("binding_field", binding, f"{path}.binding", issues)
        if (entity := node.get("entity")) and entity not in registries["entities"]:
            append_missing_reference("entity", entity, f"{path}.entity", issues)
        if action := node.get("action"):
            if action not in registries["actions"]:
                append_missing_reference("action", action, f"{path}.action", issues)
        elif node.get("role") in INTERACTIVE_ROLES and node.get("id") not in transition_triggers:
            issues.append(
                contract_issue(
                    "error",
                    "contract.reference.interactive_action_required",
                    f"{path}.action",
                    "interactive node requires action or transition trigger",
                )
            )
        if (
            node.get("role") in VISUALLY_INTERACTIVE_ROLES
            and interactive_binding_kind(node, transition_triggers) is None
        ):
            issues.append(
                contract_issue(
                    "error",
                    "contract.interactive_unbound",
                    f"{path}.action",
                    "visually interactive node requires an action or transition trigger",
                )
            )
        for child_id in node.get("children", []) or []:
            if child_id not in registries["nodes"]:
                append_missing_reference("node", child_id, f"{path}.children", issues)


def _validate_screens(
    contract: dict[str, Any],
    registries: dict[str, Any],
    transition_triggers: set[str],
    issues: list[dict[str, Any]],
) -> None:
    for index, screen in enumerate(record_items(contract, "screens")):
        if screen.get("flow_id") not in registries["flows"]:
            append_missing_reference(
                "flow", screen.get("flow_id"), f"$.screens[{index}].flow_id", issues
            )
        if screen.get("root_node") not in registries["nodes"]:
            append_missing_reference(
                "node", screen.get("root_node"), f"$.screens[{index}].root_node", issues
            )


def _duplicate_id_issues(contract: dict[str, Any], issues: list[dict[str, Any]]) -> None:
    for collection in (
        "actors",
        "entities",
        "screens",
        "nodes",
        "guards",
        "permissions",
        "mutations",
        "actions",
        "flows",
        "transitions",
    ):
        seen: dict[str, int] = {}
        for index, item in enumerate(record_items(contract, collection)):
            item_id = item.get("id")
            if isinstance(item_id, str) and item_id in seen:
                issues.append(
                    contract_issue(
                        "error",
                        f"contract.reference.duplicate_{collection[:-1]}_id",
                        f"$.{collection}[{index}].id",
                        f"duplicate id: {item_id}",
                    )
                )
            if isinstance(item_id, str):
                seen[item_id] = index
    for key in ("semantic_id", "test_id"):
        seen_values: set[str] = set()
        for index, node in enumerate(record_items(contract, "nodes")):
            value = node.get(key)
            if not isinstance(value, str):
                continue
            if value in seen_values:
                issues.append(
                    contract_issue(
                        "error",
                        f"contract.reference.duplicate_{key}",
                        f"$.nodes[{index}].{key}",
                        f"duplicate {key}: {value}",
                    )
                )
            seen_values.add(value)


def _unused_reference_issues(contract: dict[str, Any], issues: list[dict[str, Any]]) -> None:
    used_actions = {
        str(node["action"])
        for node in record_items(contract, "nodes")
        if isinstance(node.get("action"), str)
    }
    used_actions.update(
        str(t["action"])
        for t in record_items(contract, "transitions")
        if isinstance(t.get("action"), str)
    )
    used_guards = {
        str(a["guard"])
        for a in record_items(contract, "actions")
        if isinstance(a.get("guard"), str)
    }
    used_guards.update(
        str(t["guard"])
        for t in record_items(contract, "transitions")
        if isinstance(t.get("guard"), str)
    )
    used_mutations = {
        str(a["mutation"])
        for a in record_items(contract, "actions")
        if isinstance(a.get("mutation"), str)
    }
    for collection, used, code in (
        ("actions", used_actions, "contract.reference.unused_action"),
        ("guards", used_guards, "contract.reference.unused_guard"),
        ("mutations", used_mutations, "contract.reference.unused_mutation"),
    ):
        for index, item in enumerate(record_items(contract, collection)):
            if item["id"] not in used and item.get("unused_allowed") is not True:
                issues.append(
                    contract_issue(
                        "error",
                        code,
                        f"$.{collection}[{index}].id",
                        f"declared {collection[:-1]} is unused: {item['id']}",
                    )
                )
