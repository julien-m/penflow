"""One canonical projection of explicit and inferred node business semantics."""

from __future__ import annotations

from typing import Any


# @spec FR-005: Same-identity semantic projection — .specs/features/077-complete-verification-workflow/spec.md#fr-005
def canonical_node_slots(node: dict[str, Any], actions: dict[str, Any]) -> dict[str, Any]:
    """Resolve business slots once; absence remains distinct from a different value.

    Args:
        node: Schema-validated canonical node.
        actions: Canonical action registry indexed by ID.

    Returns:
        Complete expected slots, including absent values for reverse reconciliation.
        Binding implies its entity unless an explicit matching entity is supplied.
    """
    binding = node.get("binding")
    action_id = node.get("action")
    action = actions.get(action_id, {}) if isinstance(action_id, str) else {}
    entity = node.get("entity")
    if not entity and binding:
        entity = str(binding).split(".", 1)[0]
    return {
        "role": node.get("role"),
        "action": node.get("action"),
        "binding": binding,
        "entity": entity,
        "permission": action.get("permission"),
        "text": node.get("text"),
    }
