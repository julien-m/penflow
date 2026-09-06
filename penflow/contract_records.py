"""Canonical contract record access and structured issue construction."""

from __future__ import annotations
from typing import Any


def record_items(contract: dict[str, Any], key: str) -> list[dict[str, Any]]:
    """Select object records without copying or mutating their contents.

    Args:
        contract: Contract containing named collections.
        key: Collection to read; absent or non-list collections yield no records.

    Returns:
        A new list retaining only dictionary entries from the collection.
    """
    value = contract.get(key)
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def records_by_id(contract: dict[str, Any], key: str) -> dict[str, dict[str, Any]]:
    """Index a collection by its string record identifiers.

    Args:
        contract: Contract containing named collections.
        key: Collection to index.

    Returns:
        Original records keyed by ID; later duplicates replace earlier entries.
    """
    return {
        str(item["id"]): item
        for item in record_items(contract, key)
        if isinstance(item.get("id"), str)
    }


def screen_state_ids(contract: dict[str, Any]) -> dict[str, set[str]]:
    """Collect declared state identifiers for each identified screen.

    Args:
        contract: Contract containing screens and their state records.

    Returns:
        Screen IDs mapped to sets of string state IDs, without modifying records.
    """
    return {
        str(screen["id"]): {
            str(state["id"])
            for state in screen.get("states", []) or []
            if isinstance(state, dict) and isinstance(state.get("id"), str)
        }
        for screen in record_items(contract, "screens")
        if isinstance(screen.get("id"), str)
    }


def append_missing_reference(
    kind: str, value: Any, path: str, issues: list[dict[str, Any]]
) -> None:
    """Append a missing-reference error to the caller's issue accumulator.

    Args:
        kind: Referenced record category used in the diagnostic code.
        value: Missing identifier included in the message.
        path: Contract location of the unresolved reference.
        issues: Mutable accumulator receiving one structured error.
    """
    issues.append(
        contract_issue(
            "error", f"contract.reference.missing_{kind}", path, f"missing {kind}: {value}"
        )
    )


def has_errors(issues: list[dict[str, Any]]) -> bool:
    """Check whether accumulated contract findings contain an error.

    Args:
        issues: Structured findings with severity fields.

    Returns:
        True when at least one finding has error severity.
    """
    return any(issue["severity"] == "error" for issue in issues)


def contract_issue(severity: str, code: str, path: str, message: str) -> dict[str, str]:
    """Build a contract diagnostic without changing caller data.

    Args:
        severity: Diagnostic severity.
        code: Stable machine-readable diagnostic identifier.
        path: Location of the invalid contract value.
        message: Human-readable explanation.

    Returns:
        A new structured issue containing the four supplied fields.
    """
    return {"severity": severity, "code": code, "path": path, "message": message}


def interactive_binding_kind(node: dict[str, Any], transition_triggers: set[str]) -> str | None:
    """Resolve an interactive node's binding, preferring its explicit action.

    Args:
        node: Contract node with an optional action and identifier.
        transition_triggers: Node identifiers referenced as transition triggers.

    Returns:
        Action or transition binding kind, or None when neither is declared.
    """
    if isinstance(node.get("action"), str) and node["action"]:
        return "action"
    if isinstance(node.get("id"), str) and node["id"] in transition_triggers:
        return "transition"
    return None
