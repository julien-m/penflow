"""Carry the contract's state and collection constraints into the expected tree (C51).

The expected tree comes from the design board, which shows every state at once and one
template per collection. The contract decides which state a node exists in and which
node is a collection template; only those declared facts are copied, by semantic id.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


def apply_contract_constraints(expected: dict[str, Any], contract: dict[str, Any]) -> None:
    """Annotate ``expected`` in place with the contract's screen states and node constraints.

    Each expected screen receives the ids of its contract screen's ``states``. Each node
    whose semantic id is a contract node receives that node's non-empty ``states`` and
    its ``repeat_model``; nothing is added for a node the contract leaves unconstrained.
    """
    screens = {screen["id"]: screen for screen in contract.get("screens", [])}
    nodes = {node["semantic_id"]: node for node in contract.get("nodes", [])}
    for screen in expected.get("screens", []):
        source = screens.get(screen.get("screen_id"))
        if source is not None:
            screen["states"] = [state["id"] for state in source.get("states", [])]
        pending = [screen["root"]]
        while pending:
            node = pending.pop()
            declared = nodes.get(node.get("semantic_id"))
            if declared is not None:
                if declared.get("states"):
                    node["states"] = list(declared["states"])
                if isinstance(declared.get("repeat_model"), dict):
                    node["repeat_model"] = deepcopy(declared["repeat_model"])
            pending.extend(node.get("children", []) or [])
