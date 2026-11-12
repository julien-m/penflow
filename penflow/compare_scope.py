"""State scope and collection instances of the expected/actual node join (C51).

Two contract facts, carried by the expected tree, decide which expected node an actual
node answers:

- ``states``: the contract states in which a node exists. A board documents several
  mutually exclusive states; an actual capture witnesses one of them, so only the nodes
  of that state are required in it, and a node of another state is refused there.
  A node without ``states`` exists in every state of its screen (within its ancestors').
- ``repeat_model``: a collection template. Its runtime instances
  (``semantic_id::instance_id``) must match ``instance_id_template`` exactly, and the
  repeated descendants of an instance carry the same instance id.

Nothing is inferred: without ``states`` every node is required in the single capture,
and without ``repeat_model`` an instance key matches nothing, as before.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

INTERACTIVE_ROLES = frozenset({"button", "link", "input", "select", "toggle", "form", "component"})
# A template placeholder value: one non-empty token without separators of the key.
_PLACEHOLDER_VALUE = r"[A-Za-z0-9][A-Za-z0-9_.-]*"
_PLACEHOLDER = re.compile(r"\{[^{}\s]+\}")


@dataclass
class Join:
    """The pairs of one capture, with the issues and counts of the join itself."""

    pairs: list[tuple[dict[str, Any], dict[str, Any]]] = field(default_factory=list)
    issues: list[dict[str, Any]] = field(default_factory=list)
    checks: int = 0
    failed: int = 0


def template_pattern(template: str) -> re.Pattern[str]:
    """The exact pattern of ``instance_id_template``: literals, then one token per placeholder."""
    parts = _PLACEHOLDER.split(template)
    return re.compile(_PLACEHOLDER_VALUE.join(re.escape(part) for part in parts))


def base_identity(node: dict[str, Any]) -> str:
    """The semantic identity of a node without its instance."""
    return str(node.get("semantic_id") or node.get("id"))


def effective_states(nodes: list[dict[str, Any]]) -> dict[str, frozenset[str] | None]:
    """Each expected node's states, narrowed by its ancestors' (None: every state)."""
    result: dict[str, frozenset[str] | None] = {}
    for node in nodes:  # flatten_nodes is preorder: a parent precedes its children.
        own = node.get("states")
        inherited = result.get(str(node.get("_parent_key"))) if node.get("_parent_key") else None
        states = frozenset(own) if isinstance(own, list) else None
        if inherited is not None:
            states = inherited if states is None else states & inherited
        result[str(node["_semantic_key"])] = states
    return result


def governing_repeats(nodes: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """For each repeated expected node, the template node whose repeat_model governs it."""
    result: dict[str, dict[str, Any]] = {}
    for node in nodes:
        key = str(node["_semantic_key"])
        if isinstance(node.get("repeat_model"), dict):
            result[key] = node
        elif node.get("_parent_key") and str(node["_parent_key"]) in result:
            result[key] = result[str(node["_parent_key"])]
    return result


def declared_states(nodes: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Every state some expected node is scoped to, with the nodes scoped to it."""
    found: dict[str, list[str]] = {}
    for key, states in effective_states(nodes).items():
        for state in sorted(states or ()):
            found.setdefault(state, []).append(key)
    return found


def witnessed(actual: dict[str, Any], capture: dict[str, Any]) -> bool:
    """Whether ``observed_states`` names this capture's screen, state and scenario."""
    return any(
        isinstance(entry, dict)
        and entry.get("screen_id") == capture.get("screen_id")
        and entry.get("state") == capture.get("state")
        and entry.get("scenario_id") == capture.get("scenario_id")
        for entry in actual.get("observed_states", []) or []
    )


def join_nodes(
    expected_nodes: list[dict[str, Any]],
    actual_nodes: list[dict[str, Any]],
    state: str | None,
    masked: Callable[[dict[str, Any]], bool] = lambda node: False,
) -> Join:
    """Pair the expected nodes applicable in ``state`` with the actual capture's nodes.

    ``state`` None is the strict single capture: every expected node is applicable. A
    ``masked`` expected node is neither required nor compared, and its actual
    counterpart is not unexpected.
    """
    join = Join()
    scope = effective_states(expected_nodes)
    repeats = governing_repeats(expected_nodes)
    actual_keys = {str(node["_semantic_key"]): node for node in actual_nodes}
    consumed: set[str] = set()
    applicable_ids: set[str] = set()
    applicable_keys: set[str] = set()
    excluded_ids: set[str] = set()
    applicable = [
        node
        for node in expected_nodes
        if state is None
        or scope.get(str(node["_semantic_key"])) is None
        or state in (scope.get(str(node["_semantic_key"])) or ())
    ]
    applicable_set = {id(node) for node in applicable}
    positions = _state_positions(applicable) if state is not None else {}
    for node in expected_nodes:
        key = str(node["_semantic_key"])
        if id(node) not in applicable_set:
            excluded_ids.add(base_identity(node))
            continue
        applicable_ids.add(base_identity(node))
        applicable_keys.add(key)
        if key in positions:
            node = {**node, "_order": positions[key]}
        if masked(node):
            continue
        governing = repeats.get(key)
        if governing is None:
            join.checks += 1
            actual = actual_keys.get(key)
            if actual is None:
                join.failed += 1
                join.issues.append(_missing(key, state))
            else:
                consumed.add(key)
                join.pairs.append((node, actual))
            continue
        _join_instances(join, node, governing, actual_nodes, actual_keys, consumed, state)
    for key, actual in actual_keys.items():
        if key in consumed or key in applicable_keys:
            continue
        identity = base_identity(actual)
        if state is not None and identity in excluded_ids and identity not in applicable_ids:
            join.issues.append(
                _issue(
                    "node.state_unexpected",
                    key,
                    f"node of another contract state is present in state {state}",
                )
            )
        elif actual.get("role") in INTERACTIVE_ROLES:
            join.issues.append(
                _issue("node.unexpected_interactive", key, "unexpected interactive control")
            )
    return join


def _state_positions(applicable: list[dict[str, Any]]) -> dict[str, int]:
    """Sibling positions among the nodes of one state: the others are not rendered in it."""
    counters: dict[str | None, int] = {}
    positions: dict[str, int] = {}
    for node in sorted(applicable, key=lambda item: int(item.get("_order", 0))):
        parent = node.get("_parent_key")
        positions[str(node["_semantic_key"])] = counters.get(parent, 0)
        counters[parent] = counters.get(parent, 0) + 1
    return positions


def _join_instances(
    join: Join,
    node: dict[str, Any],
    governing: dict[str, Any],
    actual_nodes: list[dict[str, Any]],
    actual_keys: dict[str, dict[str, Any]],
    consumed: set[str],
    state: str | None,
) -> None:
    """Pair a repeated expected node with every conforming actual instance of it."""
    identity = base_identity(node)
    owner = base_identity(governing)
    pattern = template_pattern(governing["repeat_model"]["instance_id_template"])
    matched = 0
    for actual in actual_nodes:
        instance = actual.get("instance_id")
        if base_identity(actual) != identity or not instance:
            continue
        key = str(actual["_semantic_key"])
        consumed.add(key)
        if not pattern.fullmatch(str(instance)):
            join.issues.append(
                _issue(
                    "node.instance_unexpected",
                    key,
                    "instance does not match the repeat model instance_id_template",
                )
            )
            continue
        if identity != owner and f"{owner}::{instance}" not in actual_keys:
            join.issues.append(
                _issue("node.instance_mismatch", key, f"no {owner} instance {instance} owns it")
            )
            continue
        matched += 1
        join.checks += 1
        join.pairs.append((_instance_view(node, governing, actual), actual))
    if matched == 0:
        join.checks += 1
        join.failed += 1
        join.issues.append(_missing(str(node["_semantic_key"]), state))


def _instance_view(
    node: dict[str, Any], governing: dict[str, Any], actual: dict[str, Any]
) -> dict[str, Any]:
    """The template node as this instance: its key, parent instance and, for the owner, order.

    The position of a collection item among its siblings depends on the collection size,
    so the template owner's order is the instance's; its descendants keep theirs.
    """
    view = dict(node)
    instance = actual["instance_id"]
    view["_semantic_key"] = actual["_semantic_key"]
    if node["_semantic_key"] == governing["_semantic_key"]:
        view["_order"] = actual.get("_order", node.get("_order"))
    elif node.get("_parent_key"):
        parent = str(node["_parent_key"])
        view["_parent_key"] = f"{parent}::{instance}"
    return view


def _missing(key: str, state: str | None) -> dict[str, Any]:
    where = f" in state {state}" if state is not None else ""
    return _issue("node.missing", key, f"node missing in actual tree{where}")


def _issue(code: str, semantic_id: str, message: str) -> dict[str, Any]:
    return {"severity": "error", "code": code, "semantic_id": semantic_id, "message": message}
