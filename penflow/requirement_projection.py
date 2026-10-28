"""Project authenticated source definitions onto explicit canonical obligations."""

from __future__ import annotations

from typing import Any

from .verification_authority import inherited_projection
from .requirement_markdown import (
    RequirementDefinition,
    RequirementSourceError,
    extract_requirement_definitions_text,
)
from .verification_files import InputReader, VerificationInputError


def project_requirements(
    reader: InputReader, snapshot: dict[str, Any], contract: dict[str, Any]
) -> dict[str, Any]:
    active = [name for name in snapshot["selection"] if name not in snapshot["retired_features"]]
    if not active:
        return {
            "source_kind": "livespec-fr-ac-v1",
            "sources": [],
            "requirements": [],
            "bindings": [],
            "uncovered": [],
        }
    records = {record["path"]: record for record in snapshot["inputs"]["sources"]}
    requirements = []
    refs = []
    for slug in active:
        record = records[f".specs/features/{slug}/spec.md"]
        refs.append({"path": record["path"], "sha256": record["sha256"]})
        raw = reader.reference(record["reviewed_snapshot"], archive="source")
        for definition in _source_definitions(raw.decode("utf-8"), slug, snapshot):
            requirements.append(
                {
                    "id": definition.id,
                    "source_pointer": definition.source_pointer,
                    "text_sha256": definition.text_sha256,
                }
            )
    imported = None
    policy_ref = snapshot["inputs"].get("verification_policy")
    if policy_ref is not None:
        policy = reader.object(reader.reference(policy_ref), "verification-policy-source")
        if policy["inherited_authority"] is not None:
            imported = inherited_projection(reader, policy["inherited_authority"], contract)
            requirements.extend(imported["requirements"])
            refs.extend(imported["sources"])
    declared = contract.get("requirements", {})
    if declared.get("source_kind") != "livespec-fr-ac-v1" or declared.get("source_refs") != refs:
        raise VerificationInputError("requirements.selection_mismatch")
    outcomes = {item["obligation_id"]: item for item in contract.get("outcome_expectations", [])}
    if len(outcomes) != len(contract.get("outcome_expectations", [])):
        raise VerificationInputError("requirements.duplicate_outcome")
    ids = {item["id"] for item in requirements}
    _system_sources(contract, requirements)
    bindings = []
    seen: set[tuple[str, str]] = set()
    for binding in declared.get("bindings", []):
        pair = binding["requirement_id"], binding["obligation_id"]
        if pair in seen or pair[0] not in ids or pair[1] not in outcomes:
            raise VerificationInputError("requirements.binding.invalid")
        seen.add(pair)
        expected = outcomes[pair[1]]
        bindings.append({**binding, "category": expected["category"], "expected": expected})
    return {
        "source_kind": "livespec-fr-ac-v1",
        "sources": refs,
        "requirements": requirements,
        "bindings": bindings,
        "uncovered": sorted(ids - {item["requirement_id"] for item in bindings}),
    }


def _source_definitions(
    source: str, slug: str, snapshot: dict[str, Any]
) -> list[RequirementDefinition]:
    definitions = extract_requirement_definitions_text(source, slug)
    expected = [
        row
        for row in snapshot["projection"]["requirements"]
        if row["id"].startswith(f"livespec:{slug}:")
    ]
    current = [
        {"id": item.id, "source_pointer": item.source_pointer, "text_sha256": item.text_sha256}
        for item in definitions
    ]
    if current == expected:
        return definitions
    # Recompute both supported historical grammars from authenticated bytes.
    # Select the old grammar only on an exact match of the complete source set;
    # no expected pointer, hash or requirement is copied into computed results.
    try:
        historical = extract_requirement_definitions_text(source, slug, legacy_tables=True)
    except RequirementSourceError:
        # The caller still compares the complete computed projection and rejects
        # mismatches; invalid legacy syntax cannot authorize expected values.
        return definitions
    rows = [
        {"id": item.id, "source_pointer": item.source_pointer, "text_sha256": item.text_sha256}
        for item in historical
    ]
    return historical if rows == expected else definitions


def _system_sources(contract: dict[str, Any], requirements: list[dict[str, Any]]) -> None:
    known = {item["id"]: item for item in requirements}
    outcomes = {item["obligation_id"]: item for item in contract.get("outcome_expectations", [])}
    bindings = contract["requirements"]["bindings"]
    for index, record in enumerate(contract.get("system_returns", [])):
        source = record["source"]
        expected = known.get(source["requirement_id"])
        if expected != {
            "id": source["requirement_id"],
            "source_pointer": source["source_pointer"],
            "text_sha256": source["text_sha256"],
        }:
            raise VerificationInputError("requirements.system_return.source")
        if not any(
            binding["requirement_id"] == source["requirement_id"]
            and outcomes.get(binding["obligation_id"], {}).get("source_pointer")
            == f"/system_returns/{index}"
            for binding in bindings
        ):
            raise VerificationInputError("requirements.system_return.binding")
