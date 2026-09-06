"""Distinguish local editing, navigation and strict historical request actions."""

from typing import Any

from .contract_records import contract_issue


def action_mode(action: dict[str, Any]) -> str:
    """Classify source semantics; existing mutation-bearing actions stay requests."""
    if "mutation" in action:
        return "request"
    if action.get("kind") == "state_change" and action.get("event") == "change":
        return "local"
    return "navigation" if action.get("kind") == "navigation" else "request"


def action_binding_issues(
    action: dict[str, Any], node: dict[str, Any], screens: dict[str, Any], path: str
) -> list[dict[str, Any]]:
    """Validate local field identity and navigation destinations against their real records."""
    mode = action_mode(action)
    if mode == "local":
        reference = action["binding_ref"]
        binding = reference["entity"] + "." + reference["field"]
        if node.get("binding") != binding or node.get("role") not in {"input", "select", "toggle"}:
            return [
                contract_issue(
                    "error",
                    "contract.action.local_binding",
                    path,
                    "local edit must bind its actual input field",
                )
            ]
    if mode == "navigation":
        destination = action["destination"]
        screen = screens.get(destination["screen"])
        if screen is None or destination["state"] not in {
            state["id"] for state in screen["states"]
        }:
            return [
                contract_issue(
                    "error",
                    "contract.action.destination",
                    path,
                    "navigation must target an existing screen/state",
                )
            ]
    return []
