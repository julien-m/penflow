"""Validate frozen product relations through existing explicit C51 bindings."""

from __future__ import annotations

from typing import Any

from .product_projection import RETURN_SENTINELS, product_screen
from .verification_assertions import resolve_pointer
from .verification_files import VerificationInputError


def validate_product_mapping(
    product: dict[str, Any], contract: dict[str, Any], projection: dict[str, Any]
) -> None:
    """Allow aliases while rejecting weak all-requirements-to-one-root substitutions."""
    bindings: dict[str, list[dict[str, Any]]] = {}
    for binding in projection["bindings"]:
        bindings.setdefault(binding["requirement_id"], []).append(binding["expected"])
    screens = {screen["id"]: screen for screen in contract["screens"]}
    surfaces = {}
    flows = {}
    for surface in product["surfaces"]:
        if not product_screen(surface):
            continue
        expected = _surface_binding(contract, bindings, f"brainstorm:surface:{surface['id']}")
        target = _root_screen(contract, expected["source_pointer"])
        if surface["surface"] != target.get("surface"):
            raise VerificationInputError("product.mapping.surface_kind")
        surfaces[surface["id"]] = target["id"]
        state_targets = []
        for state in surface["states"]:
            mapped = _one(bindings, f"brainstorm:state:{surface['id']}:{state['id']}")
            pointer = mapped["source_pointer"]
            parts = pointer.split("/")
            if (
                len(parts) != 5
                or parts[1] != "screens"
                or parts[3] != "states"
                or resolve_pointer(contract, "/" + "/".join(parts[1:3])) != target
            ):
                raise VerificationInputError("product.mapping.state_owner")
            item = resolve_pointer(contract, pointer)
            if not isinstance(item, dict):
                raise VerificationInputError("product.mapping.state_missing")
            state_targets.append(item["id"])
        _injective(state_targets, "states")
    _injective(list(surfaces.values()), "surfaces")
    for flow in product["flows"]:
        owners = set()
        for expected in bindings.get(f"brainstorm:flow:{flow['id']}", []):
            owners.add(_root_screen(contract, expected["source_pointer"])["flow_id"])
        if len(owners) != 1:
            raise VerificationInputError("product.mapping.flow_ambiguous")
        target_flow = next(item for item in contract["flows"] if item["id"] in owners)
        if target_flow["entry_screen"] != surfaces[flow["entry_surface"]]:
            raise VerificationInputError("product.mapping.entry")
        flows[flow["id"]] = target_flow["id"]
    _injective(list(flows.values()), "flows")
    for surface in product["surfaces"]:
        if (
            product_screen(surface)
            and screens[surfaces[surface["id"]]]["flow_id"] != flows[surface["flow_id"]]
        ):
            raise VerificationInputError("product.mapping.surface_flow")
    _returns(product, contract, projection, bindings, surfaces, flows)


def _one(bindings: dict[str, list[dict[str, Any]]], identifier: str) -> dict[str, Any]:
    items = bindings.get(identifier, [])
    unique = {item["source_pointer"] for item in items}
    if len(unique) != 1:
        raise VerificationInputError(f"product.mapping.ambiguous: {identifier}")
    return items[0]


def _surface_binding(
    contract: dict[str, Any], bindings: dict[str, list[dict[str, Any]]], identifier: str
) -> dict[str, Any]:
    roots = {screen["root_node"] for screen in contract["screens"]}
    matches = []
    for expected in bindings.get(identifier, []):
        record = resolve_pointer(contract, expected["source_pointer"])
        if (
            isinstance(record, dict)
            and record.get("id") in roots
            and expected["source_pointer"].startswith("/nodes/")
        ):
            matches.append(expected)
    pointers = {expected["source_pointer"] for expected in matches}
    if len(pointers) != 1:
        raise VerificationInputError("product.mapping.surface_root_ambiguous")
    return matches[0]


def _root_screen(contract: dict[str, Any], pointer: str) -> dict[str, Any]:
    node = resolve_pointer(contract, pointer)
    if not pointer.startswith("/nodes/") or not isinstance(node, dict):
        raise VerificationInputError("product.mapping.surface_not_root")
    screen = next(
        (item for item in contract["screens"] if item["root_node"] == node.get("id")), None
    )
    if screen is None:
        raise VerificationInputError("product.mapping.surface_not_root")
    return screen


def _injective(values: list[str], category: str) -> None:
    if len(values) != len(set(values)):
        raise VerificationInputError(f"product.mapping.collapsed_{category}")


def _returns(
    product: dict[str, Any],
    contract: dict[str, Any],
    projection: dict[str, Any],
    bindings: dict[str, list[dict[str, Any]]],
    surfaces: dict[str, str],
    flows: dict[str, str],
) -> None:
    rows = {row["id"]: row for row in projection["requirements"]}
    duties: list[tuple[str, str, str | None, str | None]] = [
        (
            f"brainstorm:return:surface:{item['id']}:{item['return_path']}",
            item["return_path"],
            surfaces[item["id"]],
            None,
        )
        for item in product["surfaces"]
        if product_screen(item)
    ]
    duties.extend(
        (f"brainstorm:return:flow:{flow['id']}:{target}", target, None, flows[flow["id"]])
        for flow in product["flows"]
        for target in flow.get("return_paths", [])
    )
    screens = {item["id"]: item for item in contract["screens"]}
    for identifier, target, screen_id, flow_id in duties:
        expected = _one(bindings, identifier)
        pointer = expected["source_pointer"]
        record = resolve_pointer(contract, pointer)
        if not isinstance(record, dict):
            raise VerificationInputError("product.mapping.return_missing")
        if target in RETURN_SENTINELS:
            _system_return(record, pointer, rows[identifier], target)
            owner = record["screen_id"]
        else:
            if not pointer.startswith("/transitions/") or record.get("to_screen") != surfaces.get(
                target
            ):
                raise VerificationInputError("product.mapping.return_destination")
            owner = record["from_screen"]
        if (screen_id is not None and owner != screen_id) or (
            flow_id is not None and screens[owner]["flow_id"] != flow_id
        ):
            raise VerificationInputError("product.mapping.return_owner")


def _system_return(
    record: dict[str, Any], pointer: str, requirement: dict[str, Any], event: str
) -> None:
    expected_source = {
        "requirement_id": requirement["id"],
        "source_pointer": requirement["source_pointer"],
        "text_sha256": requirement["text_sha256"],
    }
    if (
        not pointer.startswith("/system_returns/")
        or record.get("event") != event
        or record.get("source") != expected_source
    ):
        raise VerificationInputError("product.mapping.system_return_source")
