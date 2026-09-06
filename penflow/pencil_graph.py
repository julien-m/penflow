# @spec FR-004: Enforce complete JSON Schema and UI graph closure with cycle-safe lossless export. — .specs/features/077-complete-verification-workflow/spec.md#fr-004
# @spec FR-002: Complete Pencil graph inventory — .specs/features/076-exhaustive-bidirectional-semantic-context/spec.md#fr-002
"""Cycle-safe inventory of every active id-bearing Pencil record."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .context import Context

DEFAULT_MAX_NODES = 100_000
STRUCTURAL_KEYS = ("children", "components", "shared_components", "definitions", "instances")
KNOWN_NODE_TYPES = {
    "component",
    "ellipse",
    "frame",
    "group",
    "icon",
    "icon_font",
    "image",
    "line",
    "path",
    "rectangle",
    "ref",
    "shape",
    "text",
    "vector",
}


@dataclass(frozen=True, slots=True)
class PencilGraphFinding:
    """One deterministic structural inventory finding."""

    code: str
    node_id: str | None
    node_path: str
    message: str


@dataclass(frozen=True, slots=True)
class PencilGraphNode:
    """One active authored Pencil node with its physical ownership."""

    node_id: str
    node_path: str
    node: dict[str, Any]
    parent_id: str | None
    screen_id: str | None
    owner_domain: str


@dataclass(frozen=True, slots=True)
class PencilGraphInventory:
    """Complete graph inventory and coded structural findings."""

    nodes: tuple[PencilGraphNode, ...]
    findings: tuple[PencilGraphFinding, ...]
    out_of_scope_metadata: int


@dataclass(slots=True)
class _WalkState:
    nodes: list[PencilGraphNode]
    findings: list[PencilGraphFinding]
    seen_objects: set[int]
    max_nodes: int
    out_of_scope_metadata: int = 0
    limit_reached: bool = False


def inventory_pencil_graph(
    document: dict[str, Any], *, max_nodes: int = DEFAULT_MAX_NODES
) -> PencilGraphInventory:
    # @spec(FR-002)
    """Inventory active id-bearing records without interpreting appearance."""
    if max_nodes < 1:
        raise ValueError("max_nodes must be positive")
    state = _WalkState([], [], set(), max_nodes)
    _walk_value(document, "$", None, None, "document", state)
    return PencilGraphInventory(
        nodes=tuple(state.nodes),
        findings=tuple(state.findings),
        out_of_scope_metadata=state.out_of_scope_metadata,
    )


def _walk_value(
    value: object,
    path: str,
    parent_id: str | None,
    screen_id: str | None,
    owner_domain: str,
    state: _WalkState,
) -> None:
    if isinstance(value, dict):
        _walk_object(value, path, parent_id, screen_id, owner_domain, state)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _walk_value(item, f"{path}[{index}]", parent_id, screen_id, owner_domain, state)


def _walk_object(
    node: dict[str, Any],
    path: str,
    parent_id: str | None,
    screen_id: str | None,
    owner_domain: str,
    state: _WalkState,
) -> None:
    identity = id(node)
    if identity in state.seen_objects:
        _finding(state, "pencil.graph_cycle", _node_id(node), path, "cyclic object reference")
        return
    state.seen_objects.add(identity)
    if _is_tombstone(node):
        state.out_of_scope_metadata += 1
        return
    next_parent, next_screen, next_domain = _record_node(
        node, path, parent_id, screen_id, owner_domain, state
    )
    for key, child in node.items():
        child_domain = (
            "shared_component"
            if key in {"components", "shared_components", "definitions"}
            else next_domain
        )
        if key in STRUCTURAL_KEYS or isinstance(child, (dict, list)):
            _walk_value(child, f"{path}.{key}", next_parent, next_screen, child_domain, state)


def _record_node(
    node: dict[str, Any],
    path: str,
    parent_id: str | None,
    screen_id: str | None,
    owner_domain: str,
    state: _WalkState,
) -> tuple[str | None, str | None, str]:
    node_id = _node_id(node)
    if node_id is None:
        return parent_id, screen_id, owner_domain
    if len(state.nodes) >= state.max_nodes:
        if not state.limit_reached:
            _finding(
                state, "pencil.graph_node_limit", node_id, path, "authored node bound exceeded"
            )
            state.limit_reached = True
        return parent_id, screen_id, owner_domain
    context = Context.from_raw(node.get("context"))
    is_screen = context.role == "screen"
    resolved_screen = context.semantic_id if is_screen else screen_id
    resolved_domain = "screen" if is_screen else owner_domain
    state.nodes.append(
        PencilGraphNode(node_id, path, node, parent_id, resolved_screen, resolved_domain)
    )
    _record_structure_findings(node, node_id, path, resolved_screen, resolved_domain, state)
    return node_id, resolved_screen, resolved_domain


def _record_structure_findings(
    node: dict[str, Any],
    node_id: str,
    path: str,
    screen_id: str | None,
    owner_domain: str,
    state: _WalkState,
) -> None:
    if screen_id is None and owner_domain != "shared_component":
        _finding(
            state, "pencil.node_outside_screen", node_id, path, "node has no screen or shared owner"
        )
    node_type = node.get("type")
    if isinstance(node_type, str) and node_type not in KNOWN_NODE_TYPES:
        _finding(
            state, "pencil.node_type_unknown", node_id, path, f"unsupported node type: {node_type}"
        )


def _finding(state: _WalkState, code: str, node_id: str | None, path: str, message: str) -> None:
    state.findings.append(PencilGraphFinding(code, node_id, path, message))


def _node_id(node: dict[str, Any]) -> str | None:
    value = node.get("id")
    return str(value) if isinstance(value, (str, int)) and str(value) else None


def _is_tombstone(node: dict[str, Any]) -> bool:
    return node.get("deleted") is True or node.get("tombstone") is True
