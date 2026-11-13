"""Resolve actor grants for one source permission's action and entity."""

from typing import Any


# C20 is a validated JSON mapping; records retain the schema's heterogeneous values.
def authorized_permission_actors(
    contract: dict[str, Any], action: dict[str, Any], permission: dict[str, Any]
) -> set[str]:
    """Return grants bound to this action and exact source entity.

    The action's explicit permission pointer and each permission's action reference
    are both existing C20 bindings. A grant for another entity confers no authority.
    """
    return {
        record["actor"]
        for record in contract["permissions"]
        if record["entity"] == permission["entity"]
        and (record["action"] == action["id"] or record["id"] == action.get("permission"))
    }
