"""Source-defined Brainstorm flow/surface/state/return requirement identities."""

from __future__ import annotations

from typing import Any

from .verification_files import VerificationInputError
from .verification_json import canonical_bytes, digest

RETURN_SENTINELS = {"exit", "back", "dismiss", "close"}


def product_requirements(product: dict[str, Any]) -> list[dict[str, str]]:
    """Recompute the frozen denominator, excluding only explicitly technical non-screens."""
    _validate_product(product)
    rows: dict[str, dict[str, str]] = {}

    def add(identifier: str, pointer: str, value: Any) -> None:
        if identifier in rows:
            raise VerificationInputError("product.requirement.duplicate")
        rows[identifier] = {
            "id": identifier,
            "source_pointer": "product-contract.json#" + pointer,
            "text_sha256": digest(canonical_bytes(value)),
        }

    for index, flow in enumerate(product["flows"]):
        add(f"brainstorm:flow:{flow['id']}", f"/flows/{index}", flow)
        for return_index, target in enumerate(flow.get("return_paths") or []):
            add(
                f"brainstorm:return:flow:{flow['id']}:{target}",
                f"/flows/{index}/return_paths/{return_index}",
                target,
            )
    for index, surface in enumerate(product["surfaces"]):
        if not product_screen(surface):
            continue
        add(f"brainstorm:surface:{surface['id']}", f"/surfaces/{index}", surface)
        for state_index, state in enumerate(surface["states"]):
            add(
                f"brainstorm:state:{surface['id']}:{state['id']}",
                f"/surfaces/{index}/states/{state_index}",
                state,
            )
        add(
            f"brainstorm:return:surface:{surface['id']}:{surface['return_path']}",
            f"/surfaces/{index}/return_path",
            surface["return_path"],
        )
    return [rows[key] for key in sorted(rows)]


def product_screen(surface: dict[str, Any]) -> bool:
    """Match the upstream rule for product screens and user-facing technical routes."""
    return surface.get("kind") == "screen" or (
        surface.get("kind") == "technical" and surface.get("user_facing") is True
    )


def _validate_product(product: dict[str, Any]) -> None:
    if (
        product.get("kind") != "product-contract"
        or type(product.get("version")) is not int
        or product["version"] != 1
        or not _text(product.get("product"))
    ):
        raise VerificationInputError("product.contract.identity")
    flows, surfaces = _records(product.get("flows")), _records(product.get("surfaces"))
    product_ids = {item["id"] for item in surfaces.values() if product_screen(item)}
    for flow in flows.values():
        if flow.get("entry_surface") not in product_ids:
            raise VerificationInputError("product.flow.entry")
        returns = flow.get("return_paths", [])
        if not isinstance(returns, list) or any(
            not isinstance(target, str) or target not in surfaces.keys() | RETURN_SENTINELS
            for target in returns
        ):
            raise VerificationInputError("product.flow.return")
    for surface in surfaces.values():
        if (
            surface.get("kind") not in {"screen", "technical"}
            or surface.get("flow_id") not in flows
        ):
            raise VerificationInputError("product.surface.identity")
        if product_screen(surface):
            _validate_screen(surface, set(surfaces))


def _records(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise VerificationInputError("product.records.nonempty")
    result = {}
    for item in value:
        if not isinstance(item, dict) or not _text(item.get("id")) or item["id"] in result:
            raise VerificationInputError("product.record.identity")
        result[item["id"]] = item
    return result


def _validate_screen(surface: dict[str, Any], surface_ids: set[str]) -> None:
    if surface.get("user_facing") is not True or any(
        not _text(surface.get(key))
        for key in ("role", "surface", "product_justification", "return_path")
    ):
        raise VerificationInputError("product.screen.shape")
    if surface["return_path"] not in surface_ids | RETURN_SENTINELS:
        raise VerificationInputError("product.screen.return")
    states = _records(surface.get("states"))
    references = surface.get("references")
    if not isinstance(references, list) or any(not isinstance(item, dict) for item in references):
        raise VerificationInputError("product.references.shape")
    for state in states:
        matching = [item for item in references if item.get("state") == state]
        if any(
            not _text(item.get("source")) or not _text(item.get("design_intent"))
            for item in matching
        ):
            raise VerificationInputError("product.references.identity")
        if (
            len({item["source"] for item in matching}) < 2
            or len({item["design_intent"] for item in matching}) != 1
        ):
            raise VerificationInputError("product.references.homology")
        if any(item.get(key) != surface[key] for item in matching for key in ("surface", "role")):
            raise VerificationInputError("product.references.surface_mismatch")


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())
