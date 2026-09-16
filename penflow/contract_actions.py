"""Distinguish local editing, navigation and strict historical request actions."""

from typing import Any

from .contract_records import contract_issue


# @spec FR-002: local submit classification — .specs/features/045-penflow-json-only-strict-contract-v2/spec.md#fr-002
def action_mode(action: dict[str, Any]) -> str:
    """Classify source semantics, preserving mutation-bearing request duties.

    Args:
        action: JSON action validated against the closed C20 schema.

    Returns:
        One of ``request``, ``local``, ``local_submit`` or ``navigation``.
    """
    if "mutation" in action:
        return "request"
    if action.get("kind") == "state_change" and action.get("event") == "change":
        return "local"
    # Mutation-bearing submits remain requests; only mutation-free submits use local transitions.
    if action.get("kind") == "state_change" and action.get("event") == "submit":
        return "local_submit"
    return "navigation" if action.get("kind") == "navigation" else "request"


def action_binding_issues(
    action: dict[str, Any], node: dict[str, Any], screens: dict[str, Any], path: str
) -> list[dict[str, Any]]:
    """Validate local field identity and navigation destinations against their real records."""
    mode = action_mode(action)
    # A local submit belongs to the control or form that initiates submission.
    if mode == "local_submit" and node.get("role") not in {"button", "form"}:
        return [
            contract_issue(
                "error",
                "contract.action.local_submit_node",
                path,
                "local submit must belong to a button or form",
            )
        ]
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


# @spec FR-003: local submit transition — .specs/features/045-penflow-json-only-strict-contract-v2/spec.md
# Any preserves the shared schema-validated JSON boundary, including optional extension payloads;
# this validator reads known fields without coercing or reconstructing the canonical records.
def local_submit_transition_issues(
    action: dict[str, Any], node: dict[str, Any], transitions: dict[str, Any], path: str
) -> list[dict[str, Any]]:
    """Require the local submit's declared transition to change its own screen state.

    Args:
        action: Schema-validated C20 action record.
        node: Existing node that owns this action.
        transitions: Transition registry keyed by canonical transition ID.
        path: Source JSON path used in deterministic diagnostics.

    Returns:
        Contract issues for incoherent ownership or state changes; missing IDs are
        reported separately by the shared reference validator.
    """
    if action_mode(action) != "local_submit":
        return []
    transition = transitions.get(action["success_transition"])
    if transition is None:
        return []  # The shared reference validator reports absent transition IDs.
    if (
        transition.get("action") != action["id"]
        or transition.get("trigger") not in {action["id"], node["id"]}
        or transition.get("from_screen") != node["screen_id"]
        or transition.get("to_screen") != node["screen_id"]
        or transition.get("from_state") == transition.get("to_state")
    ):
        return [
            contract_issue(
                "error",
                "contract.action.local_submit_transition",
                path,
                "local submit must change its own screen state through its action",
            )
        ]
    return []
