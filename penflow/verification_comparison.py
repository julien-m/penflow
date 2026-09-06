# @spec FR-006: Verify required runtime properties, screen and instance identity, unexpected interaction absence and declared normalization/capability rules. — .specs/features/077-complete-verification-workflow/spec.md#fr-006
"""Compare required source identities while preserving declared decorative layout wrappers."""

from copy import deepcopy
from typing import Any

from .compare import compare_trees
from .tree import flatten_nodes
from .verification_styles import normalize_observed_styles

LAYOUT_WRAPPERS = {"container", "group"}
# Projection discards a node's observations: only classification/ownership metadata
# and a matching role can prove inertness. Any other explicit field must survive.
INERT_CONTEXT_KEYS = {
    "classification",
    "role",
    "inherits_from",
    "relation",
    "decorative_owner",
    "decorative_reason",
}


def compare_required_trees(
    contract: dict[str, Any], expected: dict[str, Any], actual: dict[str, Any]
) -> list[dict[str, Any]]:
    """Keep all source nodes and every extra runtime control in the comparison.

    Strict semantic coverage has already classified every Pencil wrapper. Removing
    its nonsemantic layout containers preserves nearest semantic ancestry; masks
    and user tolerances cannot remove a source identity from this comparison.
    """
    required = {node["semantic_id"] for node in contract["nodes"]}
    projected = []
    for tree, runtime in ((expected, False), (actual, True)):
        result = deepcopy(tree)
        for screen in result["screens"]:
            roots = _retained_nodes(
                screen["root"],
                required,
                runtime,
                {node["semantic_id"]: node.get("text") for node in contract["nodes"]},
            )
            screen["root"] = roots[0] if len(roots) == 1 else screen["root"]
        normalize_observed_styles(result)
        projected.append(result)
    findings = compare_trees(projected[0], projected[1], mandatory=True)["issues"]
    for screen in projected[1]["screens"]:
        for node in flatten_nodes(screen["root"]):
            if (node.get("semantic_id") or node["id"]) not in required:
                findings.append(
                    {
                        "severity": "error",
                        "code": "node.unexpected",
                        "semantic_id": node.get("semantic_id") or node["id"],
                        "message": "runtime node is not a declared source node or a recognized noninteractive layout wrapper",
                    }
                )
    return findings


def _retained_nodes(
    root: dict[str, Any], required: set[str], runtime: bool, copy: dict[str, Any]
) -> list[dict[str, Any]]:
    built: dict[int, list[dict[str, Any]]] = {}
    pending = [(root, False, None)]
    while pending:
        node, visited, owner = pending.pop()
        if not visited:
            pending.append((node, True, owner))
            child_owner = node.get("semantic_id") if node.get("semantic_id") in required else owner
            pending.extend(
                (child, False, child_owner) for child in reversed(node.get("children", []))
            )
            continue
        children = [value for child in node.get("children", []) for value in built[id(child)]]
        if node.get("semantic_id") in required or (
            runtime and not _runtime_wrapper(node, owner, copy)
        ):
            kept = {key: value for key, value in node.items() if key != "children"}
            kept["children"] = children
            built[id(node)] = [kept]
        else:
            built[id(node)] = children
    return built[id(root)]


def _runtime_wrapper(node: dict[str, Any], owner: str | None, copy: dict[str, Any]) -> bool:
    if not _inert_context(node, owner):
        return False
    context = node.get("context", {})
    if node.get("role") == "text":
        return bool(
            owner
            and isinstance(copy.get(owner), str)
            and context.get("classification") == "inherited"
            and context.get("inherits_from") == owner
            and context.get("relation") == "content"
            and node.get("text") == copy[owner]
        )
    return node.get("role") in LAYOUT_WRAPPERS and (
        not node.get("semantic_id") or context.get("classification") in {"decorative", "inherited"}
    )


def _inert_context(node: dict[str, Any], owner: str | None) -> bool:
    """Require absent behavior and consistent ownership before losing observations."""
    context = node.get("context", {})
    if not isinstance(context, dict) or context.keys() - INERT_CONTEXT_KEYS:
        return False
    if "role" in context and context["role"] != node.get("role"):
        return False
    identity = node.get("semantic_id")
    if identity is not None and not (isinstance(identity, str) and identity.strip()):
        return False
    classification = context.get("classification")
    if "classification" not in context:
        return not (context.keys() - {"role"}) and identity is None
    if classification == "inherited":
        owner_key, detail_key = "inherits_from", "relation"
        conflicting_keys = {"decorative_owner", "decorative_reason"}
    elif classification == "decorative":
        # C12 permits null semantic IDs and unowned, unannotated layout containers;
        # an explicit owner claim must still be complete and consistent below.
        if identity is None and not (context.keys() - {"classification", "role"}):
            return True
        owner_key, detail_key = "decorative_owner", "decorative_reason"
        conflicting_keys = {"inherits_from", "relation"}
    else:
        return False
    detail = context.get(detail_key)
    return bool(
        owner
        and context.get(owner_key) == owner
        and isinstance(detail, str)
        and detail.strip()
        and not conflicting_keys.intersection(context)
    )
