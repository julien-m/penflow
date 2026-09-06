"""Linear containment checks before canonical contract traversal."""

from __future__ import annotations

from collections import Counter
from typing import Any


# @spec FR-004: Closed containment graph — .specs/features/077-complete-verification-workflow/spec.md#fr-004
def validate_containment(contract: dict[str, Any]) -> list[dict[str, Any]]:
    """Check ownership, parent cardinality, cycles and reachability in O(V+E)."""
    nodes = {node["id"]: node for node in contract["nodes"]}
    roots = {screen["root_node"]: screen["id"] for screen in contract["screens"]}
    issues: list[dict[str, Any]] = []
    parents: Counter[str] = Counter()
    for index, node in enumerate(contract["nodes"]):
        path = f"$.nodes[{index}]"
        for child in node.get("children", []):
            parents[child] += 1
            if child in nodes and nodes[child]["screen_id"] != node["screen_id"]:
                issues.append(_issue("ownership", path, f"child {child} belongs to another screen"))
        if node["id"] in roots and node["screen_id"] != roots[node["id"]]:
            issues.append(_issue("root_owner", path, "screen root belongs to another screen"))
    for node_id in nodes:
        expected = 0 if node_id in roots else 1
        if parents[node_id] != expected:
            issues.append(
                _issue(
                    "parent_cardinality",
                    "$.nodes",
                    f"{node_id}: expected {expected} parents, got {parents[node_id]}",
                )
            )
    issues.extend(_cycles(nodes))
    reached: set[str] = set()
    pending = list(roots)
    while pending:
        node_id = pending.pop()
        if node_id in reached or node_id not in nodes:
            continue
        reached.add(node_id)
        pending.extend(nodes[node_id].get("children", []))
    for node_id in sorted(nodes.keys() - reached):
        issues.append(
            _issue("unreachable", "$.nodes", f"{node_id} is unreachable from its screen root")
        )
    return issues


def _cycles(nodes: dict[str, Any]) -> list[dict[str, Any]]:
    colors: dict[str, int] = {}
    issues: list[dict[str, Any]] = []
    # Explicit enter/leave stack detects back edges without recursive Python calls.
    for start in nodes:
        if colors.get(start):
            continue
        stack = [(start, False)]
        while stack:
            node_id, leaving = stack.pop()
            if node_id not in nodes:
                continue
            if leaving:
                colors[node_id] = 2
            elif colors.get(node_id) == 1:
                issues.append(_issue("cycle", "$.nodes", f"containment cycle at {node_id}"))
            elif not colors.get(node_id):
                colors[node_id] = 1
                stack.append((node_id, True))
                stack.extend(
                    (child, False) for child in reversed(nodes[node_id].get("children", []))
                )
    return issues


def _issue(code: str, path: str, message: str) -> dict[str, Any]:
    return {"severity": "error", "code": f"contract.graph.{code}", "path": path, "message": message}
