# @spec(FR-002)
# @spec(FR-003)
"""Strict v2 JSON flow contract loading and validation."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .schema_cache import load_schema

ID_RE = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$")
BINDING_RE = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
INTERACTIVE_ROLES = {"button", "link", "input", "select", "toggle", "form", "component"}
HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}
SCHEMA_PATH = Path(__file__).parent / "schemas" / "flow-contract-v2.schema.json"


class FlowContractValidationError(ValueError):
    """Raised when a strict v2 flow contract fails validation."""


def load_flow_contract_v2(path: str | Path) -> dict[str, Any]:
    """Load a v2 `flow-ui-contract/contract.json` document."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


# @spec FR-001: Strict schema, FR-003: References — .specs/features/045-penflow-json-only-strict-contract-v2/spec.md#fr-001
def validate_flow_contract_v2(contract: Any) -> list[dict[str, Any]]:
    """Validate a strict v2 contract with closed schema and referential checks."""
    issues: list[dict[str, Any]] = []
    if not isinstance(contract, dict):
        return [_issue("error", "contract.schema.type", "$", "contract must be object")]
    _validate_schema(contract, issues)
    if not _has_errors(issues):
        _validate_references(contract, issues)
    return sorted(issues, key=lambda issue: (issue["path"], issue["code"], issue["message"]))


def contract_registries(contract: dict[str, Any]) -> dict[str, Any]:
    """Return id registries used by downstream artifact validators."""
    nodes = _by_id(contract, "nodes")
    return {
        "actors": _by_id(contract, "actors"),
        "entities": _by_id(contract, "entities"),
        "screens": _by_id(contract, "screens"),
        "nodes": nodes,
        "guards": _by_id(contract, "guards"),
        "permissions": _by_id(contract, "permissions"),
        "mutations": _by_id(contract, "mutations"),
        "actions": _by_id(contract, "actions"),
        "flows": _by_id(contract, "flows"),
        "transitions": _by_id(contract, "transitions"),
        "semantic_ids": {
            str(node["semantic_id"]): node
            for node in nodes.values()
            if isinstance(node.get("semantic_id"), str)
        },
        "test_ids": {
            str(node["test_id"]): node
            for node in nodes.values()
            if isinstance(node.get("test_id"), str)
        },
        "fields": {
            f"{entity['id']}.{field['id']}"
            for entity in _items(contract, "entities")
            for field in entity.get("fields", []) or []
            if isinstance(field, dict) and isinstance(field.get("id"), str)
        },
    }


def _validate_schema(contract: dict[str, Any], issues: list[dict[str, Any]]) -> None:
    schema = load_schema(SCHEMA_PATH.name)
    _validate_schema_subset(contract, schema, "$", schema.get("$defs", {}), issues)


def _validate_references(contract: dict[str, Any], issues: list[dict[str, Any]]) -> None:
    registries = contract_registries(contract)
    _duplicate_id_issues(contract, issues)
    if contract.get("needs_clarification"):
        issues.append(
            _issue(
                "error",
                "contract.clarification.unresolved",
                "$.needs_clarification",
                "clarification items must be resolved before strict validation",
            )
        )
    for index, screen in enumerate(_items(contract, "screens")):
        if screen.get("flow_id") not in registries["flows"]:
            _missing("flow", screen.get("flow_id"), f"$.screens[{index}].flow_id", issues)
        if screen.get("root_node") not in registries["nodes"]:
            _missing("node", screen.get("root_node"), f"$.screens[{index}].root_node", issues)
    for index, node in enumerate(_items(contract, "nodes")):
        path = f"$.nodes[{index}]"
        if node.get("screen_id") not in registries["screens"]:
            _missing("screen", node.get("screen_id"), f"{path}.screen_id", issues)
        if binding := node.get("binding"):
            if not isinstance(binding, str) or not BINDING_RE.match(binding):
                issues.append(
                    _issue(
                        "error",
                        "contract.reference.invalid_binding",
                        f"{path}.binding",
                        "binding must use entity.field",
                    )
                )
            elif binding not in registries["fields"]:
                _missing("binding_field", binding, f"{path}.binding", issues)
        if entity := node.get("entity"):
            if entity not in registries["entities"]:
                _missing("entity", entity, f"{path}.entity", issues)
        if action := node.get("action"):
            if action not in registries["actions"]:
                _missing("action", action, f"{path}.action", issues)
        elif node.get("role") in INTERACTIVE_ROLES:
            issues.append(
                _issue(
                    "error",
                    "contract.reference.interactive_action_required",
                    f"{path}.action",
                    "interactive node requires action",
                )
            )
        for child_id in node.get("children", []) or []:
            if child_id not in registries["nodes"]:
                _missing("node", child_id, f"{path}.children", issues)
    for index, action in enumerate(_items(contract, "actions")):
        path = f"$.actions[{index}]"
        node = registries["nodes"].get(action.get("node"))
        if node is None:
            _missing("node", action.get("node"), f"{path}.node", issues)
        elif node.get("role") not in INTERACTIVE_ROLES:
            issues.append(
                _issue(
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
                _missing(registry_name[:-1], value, f"{path}.{field}", issues)
    for index, permission in enumerate(_items(contract, "permissions")):
        if permission.get("actor") not in registries["actors"]:
            _missing("actor", permission.get("actor"), f"$.permissions[{index}].actor", issues)
        if permission.get("action") not in registries["actions"]:
            _missing("action", permission.get("action"), f"$.permissions[{index}].action", issues)
        if permission.get("entity") not in registries["entities"]:
            _missing("entity", permission.get("entity"), f"$.permissions[{index}].entity", issues)
    screen_states = _screen_states(contract)
    action_screens = {
        str(action["id"]): str(node["screen_id"])
        for action in _items(contract, "actions")
        if isinstance(action.get("id"), str)
        for node in [registries["nodes"].get(action.get("node"))]
        if isinstance(node, dict) and isinstance(node.get("screen_id"), str)
    }
    for index, mutation in enumerate(_items(contract, "mutations")):
        if mutation.get("entity") not in registries["entities"]:
            _missing("entity", mutation.get("entity"), f"$.mutations[{index}].entity", issues)
        mutation_actions = [
            str(action["id"])
            for action in _items(contract, "actions")
            if action.get("mutation") == mutation.get("id") and isinstance(action.get("id"), str)
        ]
        for state_field in ("success_state", "error_state"):
            value = mutation.get(state_field)
            if mutation_actions:
                for action_id in mutation_actions:
                    screen_id = action_screens.get(action_id)
                    if screen_id and value not in screen_states.get(screen_id, set()):
                        _missing(
                            "state",
                            value,
                            f"$.mutations[{index}].{state_field}",
                            issues,
                        )
            elif not any(value in states for states in screen_states.values()):
                _missing("state", value, f"$.mutations[{index}].{state_field}", issues)
    for index, transition in enumerate(_items(contract, "transitions")):
        path = f"$.transitions[{index}]"
        if transition.get("flow") not in registries["flows"]:
            _missing("flow", transition.get("flow"), f"{path}.flow", issues)
        for field in ("from_screen", "to_screen"):
            if transition.get(field) not in registries["screens"]:
                _missing("screen", transition.get(field), f"{path}.{field}", issues)
        for field in ("from_state", "to_state"):
            screen_field = "from_screen" if field == "from_state" else "to_screen"
            screen_id = transition.get(screen_field)
            states = screen_states.get(str(screen_id), set())
            if transition.get(field) not in states:
                _missing("state", transition.get(field), f"{path}.{field}", issues)
        if transition.get("action") and transition.get("action") not in registries["actions"]:
            _missing("action", transition.get("action"), f"{path}.action", issues)
        trigger = transition.get("trigger")
        if trigger not in registries["actions"]:
            trigger_node = registries["nodes"].get(trigger)
            if trigger_node is None:
                _missing("trigger", trigger, f"{path}.trigger", issues)
            elif trigger_node.get("role") not in INTERACTIVE_ROLES:
                issues.append(
                    _issue(
                        "error",
                        "contract.reference.non_interactive_trigger",
                        f"{path}.trigger",
                        "transition trigger node must be interactive",
                    )
                )
    _unused_reference_issues(contract, issues)


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
        for index, item in enumerate(_items(contract, collection)):
            item_id = item.get("id")
            if isinstance(item_id, str) and item_id in seen:
                issues.append(
                    _issue(
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
        for index, node in enumerate(_items(contract, "nodes")):
            value = node.get(key)
            if not isinstance(value, str):
                continue
            if value in seen_values:
                issues.append(
                    _issue(
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
        for node in _items(contract, "nodes")
        if isinstance(node.get("action"), str)
    }
    used_actions.update(
        str(t["action"])
        for t in _items(contract, "transitions")
        if isinstance(t.get("action"), str)
    )
    used_guards = {
        str(a["guard"]) for a in _items(contract, "actions") if isinstance(a.get("guard"), str)
    }
    used_guards.update(
        str(t["guard"]) for t in _items(contract, "transitions") if isinstance(t.get("guard"), str)
    )
    used_mutations = {
        str(a["mutation"])
        for a in _items(contract, "actions")
        if isinstance(a.get("mutation"), str)
    }
    for collection, used, code in (
        ("actions", used_actions, "contract.reference.unused_action"),
        ("guards", used_guards, "contract.reference.unused_guard"),
        ("mutations", used_mutations, "contract.reference.unused_mutation"),
    ):
        for index, item in enumerate(_items(contract, collection)):
            if item["id"] not in used and item.get("unused_allowed") is not True:
                issues.append(
                    _issue(
                        "error",
                        code,
                        f"$.{collection}[{index}].id",
                        f"declared {collection[:-1]} is unused: {item['id']}",
                    )
                )


def _validate_object_id(item: dict[str, Any], path: str, issues: list[dict[str, Any]]) -> None:
    if not isinstance(item, dict):
        issues.append(_issue("error", "contract.schema.type", path, "item must be object"))
        return
    item_id = item.get("id")
    if not isinstance(item_id, str):
        issues.append(_issue("error", "contract.schema.required", f"{path}.id", "id is required"))
    elif not ID_RE.match(item_id):
        issues.append(
            _issue(
                "error",
                "contract.schema.id_format",
                f"{path}.id",
                "id must be lowercase identifier",
            )
        )


def _items(contract: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = contract.get(key)
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _by_id(contract: dict[str, Any], key: str) -> dict[str, dict[str, Any]]:
    return {
        str(item["id"]): item for item in _items(contract, key) if isinstance(item.get("id"), str)
    }


def _screen_states(contract: dict[str, Any]) -> dict[str, set[str]]:
    return {
        str(screen["id"]): {
            str(state["id"])
            for state in screen.get("states", []) or []
            if isinstance(state, dict) and isinstance(state.get("id"), str)
        }
        for screen in _items(contract, "screens")
        if isinstance(screen.get("id"), str)
    }


def _validate_schema_subset(
    value: Any,
    schema: dict[str, Any],
    path: str,
    defs: dict[str, Any],
    issues: list[dict[str, Any]],
) -> None:
    if "$ref" in schema:
        ref = schema["$ref"]
        if isinstance(ref, str) and ref.startswith("#/$defs/"):
            target = defs.get(ref.rsplit("/", 1)[-1])
            if isinstance(target, dict):
                _validate_schema_subset(value, target, path, defs, issues)
                return
        issues.append(
            _issue("error", "contract.schema.unsupported_ref", path, f"unsupported ref: {ref}")
        )
        return
    expected_type = schema.get("type")
    if expected_type and not _matches_json_type(value, expected_type):
        issues.append(_issue("error", "contract.schema.type", path, f"expected {expected_type}"))
        return
    if "const" in schema and value != schema["const"]:
        issues.append(
            _issue("error", "contract.schema.const", path, f"expected {schema['const']!r}")
        )
    if "enum" in schema and value not in schema["enum"]:
        issues.append(
            _issue("error", "contract.schema.enum", path, f"expected one of {schema['enum']}")
        )
    if isinstance(value, str) and isinstance(schema.get("pattern"), str):
        if re.fullmatch(str(schema["pattern"]), value) is None:
            issues.append(
                _issue("error", "contract.schema.pattern", path, "value does not match pattern")
            )
    if isinstance(value, dict):
        required = schema.get("required", []) if isinstance(schema.get("required"), list) else []
        for key in required:
            if isinstance(key, str) and key not in value:
                issues.append(
                    _issue(
                        "error", "contract.schema.required", f"{path}.{key}", f"{key} is required"
                    )
                )
        properties = (
            schema.get("properties", {}) if isinstance(schema.get("properties"), dict) else {}
        )
        if schema.get("additionalProperties") is False:
            for key in sorted(set(value) - set(properties)):
                issues.append(
                    _issue(
                        "error",
                        "contract.schema.additional_property",
                        f"{path}.{key}",
                        "unknown property",
                    )
                )
        for key, child_schema in properties.items():
            if key in value and isinstance(child_schema, dict):
                _validate_schema_subset(value[key], child_schema, f"{path}.{key}", defs, issues)
    elif isinstance(value, list) and isinstance(schema.get("items"), dict):
        for index, item in enumerate(value):
            _validate_schema_subset(item, schema["items"], f"{path}[{index}]", defs, issues)


def _matches_json_type(value: Any, expected: str) -> bool:
    return {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
        "null": value is None,
    }.get(expected, True)


def _missing(kind: str, value: Any, path: str, issues: list[dict[str, Any]]) -> None:
    issues.append(
        _issue("error", f"contract.reference.missing_{kind}", path, f"missing {kind}: {value}")
    )


def _has_errors(issues: list[dict[str, Any]]) -> bool:
    return any(issue["severity"] == "error" for issue in issues)


def _issue(severity: str, code: str, path: str, message: str) -> dict[str, str]:
    return {"severity": severity, "code": code, "path": path, "message": message}
