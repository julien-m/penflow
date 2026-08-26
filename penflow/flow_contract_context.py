"""Feature-076 semantic ownership and behavior reference validation."""

from __future__ import annotations

from typing import Any

INTERACTIVE_ROLES = {"button", "link", "input", "select", "toggle", "form", "component"}


# @spec FR-007: Fail-closed references — .specs/features/076-exhaustive-bidirectional-semantic-context/spec.md#fr-007
def semantic_context_reference_issues(
    contract: dict[str, Any],
    registries: dict[str, Any],
    screen_states: dict[str, set[str]],
) -> list[dict[str, Any]]:
    """Return stable issues for feature-076 cross references."""
    issues: list[dict[str, Any]] = []
    for index, node in enumerate(_items(contract, "nodes")):
        _validate_node(node, index, registries, issues)
    for index, action in enumerate(_items(contract, "actions")):
        _validate_action(action, index, registries, screen_states, issues)
    for index, relation in enumerate(_items(contract, "relations")):
        _validate_relation(relation, index, registries, issues)
    _validate_static_screens(contract, issues)
    return issues


def _validate_node(
    node: dict[str, Any],
    index: int,
    registries: dict[str, Any],
    issues: list[dict[str, Any]],
) -> None:
    path = f"$.nodes[{index}]"
    owner = node.get("owner")
    if isinstance(owner, dict) and owner.get("scope") == "screen":
        if owner.get("screen") not in registries["screens"]:
            _missing("screen", owner.get("screen"), f"{path}.owner.screen", issues)
    parent = node.get("parent")
    if parent and parent not in registries["nodes"]:
        _missing("node", parent, f"{path}.parent", issues)
    repeat = node.get("repeat_model")
    if node.get("role") in {"list", "list_item"} and not isinstance(repeat, dict):
        issues.append(
            _issue(
                "list.model_incomplete",
                f"{path}.repeat_model",
                "semantic list requires repeat model",
            )
        )
    if isinstance(repeat, dict):
        _validate_repeat(repeat, path, registries, issues)


def _validate_repeat(
    repeat: dict[str, Any],
    path: str,
    registries: dict[str, Any],
    issues: list[dict[str, Any]],
) -> None:
    if repeat.get("collection") not in registries["fields"]:
        issues.append(
            _issue(
                "binding.field_missing",
                f"{path}.repeat_model.collection",
                "collection field is missing",
            )
        )
    entity = registries["entities"].get(repeat.get("item_model"))
    field_ids = (
        {field.get("id") for field in entity.get("fields", []) if isinstance(field, dict)}
        if isinstance(entity, dict)
        else set()
    )
    if entity is None or repeat.get("item_key") not in field_ids:
        issues.append(
            _issue("list.model_incomplete", f"{path}.repeat_model", "item model or key is missing")
        )


def _validate_action(
    action: dict[str, Any],
    index: int,
    registries: dict[str, Any],
    screen_states: dict[str, set[str]],
    issues: list[dict[str, Any]],
) -> None:
    path = f"$.actions[{index}]"
    destination = action.get("destination")
    if isinstance(destination, dict):
        screen = destination.get("screen")
        state = destination.get("state")
        if screen not in registries["screens"] or state not in screen_states.get(
            str(screen), set()
        ):
            issues.append(
                _issue(
                    "destination.reference_missing",
                    f"{path}.destination",
                    "destination screen or state is missing",
                )
            )
    binding = action.get("binding_ref")
    if isinstance(binding, dict):
        field = f"{binding.get('entity')}.{binding.get('field')}"
        if field not in registries["fields"]:
            issues.append(
                _issue("binding.field_missing", f"{path}.binding_ref", "binding field is missing")
            )


def _validate_relation(
    relation: dict[str, Any],
    index: int,
    registries: dict[str, Any],
    issues: list[dict[str, Any]],
) -> None:
    for field in ("source", "target"):
        value = relation.get(field)
        if value not in registries["semantic_ids"]:
            _missing("semantic_node", value, f"$.relations[{index}].{field}", issues)


# @spec FR-006: Complete behavior graph — .specs/features/076-exhaustive-bidirectional-semantic-context/spec.md#fr-006
def _validate_static_screens(contract: dict[str, Any], issues: list[dict[str, Any]]) -> None:
    static_screens = {
        screen.get("id") for screen in _items(contract, "screens") if screen.get("static") is True
    }
    for index, node in enumerate(_items(contract, "nodes")):
        interactive = node.get("role") in INTERACTIVE_ROLES or isinstance(node.get("action"), str)
        if node.get("screen_id") in static_screens and interactive:
            issues.append(
                _issue(
                    "screen.static_interactive",
                    f"$.nodes[{index}]",
                    "static screen contains interactive semantic node",
                )
            )


def _items(contract: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = contract.get(key, [])
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _missing(kind: str, value: Any, path: str, issues: list[dict[str, Any]]) -> None:
    issues.append(_issue(f"contract.reference.missing_{kind}", path, f"missing {kind}: {value}"))


def _issue(code: str, path: str, message: str) -> dict[str, str]:
    return {"severity": "error", "code": code, "path": path, "message": message}
