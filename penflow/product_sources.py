"""Read one caller-selected Brainstorm workspace and its frozen source authority."""

from pathlib import Path
from typing import Any

from .flow_contract import validate_flow_contract_v2
from .product_freeze import load_frozen_product
from .product_mapping import validate_product_mapping
from .product_projection import product_requirements
from .verification_files import InputReader, VerificationInputError


def load_brainstorm_requirements(reader: InputReader, workspace: Path) -> dict[str, Any]:
    """Require every frozen source definition and its semantically corresponding C20 record."""
    product, sources = load_frozen_product(reader, workspace)
    requirements = product_requirements(product)
    contract = reader.object(reader.read(workspace / "flow-ui-contract/contract.json"))
    if any(item["severity"] == "error" for item in validate_flow_contract_v2(contract)):
        raise VerificationInputError("product.c20.invalid")
    declared = contract.get("requirements", {})
    if (
        declared.get("source_kind") != "brainstorm-product-v1"
        or declared.get("source_refs") != sources
    ):
        raise VerificationInputError("product.sources.changed")
    outcomes = {item["obligation_id"]: item for item in contract.get("outcome_expectations", [])}
    if len(outcomes) != len(contract.get("outcome_expectations", [])):
        raise VerificationInputError("product.outcome.duplicate")
    known = {item["id"] for item in requirements}
    bindings = []
    seen = set()
    for binding in declared["bindings"]:
        pair = binding["requirement_id"], binding["obligation_id"]
        if pair in seen or pair[0] not in known or pair[1] not in outcomes:
            raise VerificationInputError("product.binding.unknown_or_duplicate")
        seen.add(pair)
        expected = outcomes[pair[1]]
        bindings.append({**binding, "category": expected["category"], "expected": expected})
    projection = {
        "source_kind": "brainstorm-product-v1",
        "sources": sources,
        "requirements": requirements,
        "bindings": sorted(
            bindings, key=lambda item: (item["requirement_id"], item["obligation_id"])
        ),
        "uncovered": sorted(known - {item["requirement_id"] for item in bindings}),
    }
    if projection["uncovered"]:
        raise VerificationInputError("product.requirements.uncovered")
    validate_product_mapping(product, contract, projection)
    return {"projection": projection, "contract": contract, "product": product}
