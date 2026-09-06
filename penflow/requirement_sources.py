# @spec FR-007: Derive requirement-to-contract-to-outcome coverage from revision-bound canonical sources without a manual registry. — .specs/features/077-complete-verification-workflow/spec.md#fr-007
"""Recompute selected LiveSpec requirements from authenticated source snapshots."""

from __future__ import annotations

from typing import Any

from .requirement_approval_history import validate_history
from .requirement_projection import project_requirements
from .flow_contract import validate_flow_contract_v2
from .requirement_markdown import SLUG_REGEX, semantic_text_sha256
from .verification_files import InputReader, VerificationInputError
from .verification_json import canonical_bytes, digest


# @spec FR-007: source-derived approved denominator — .specs/features/077-complete-verification-workflow/spec.md#fr-007
def load_livespec_requirements(reader: InputReader) -> dict[str, Any]:
    """Load cumulative caller authority; a report cannot select or narrow its features."""
    baseline = reader.object(
        reader.read(".specs/penflow-requirements.json"), "requirements-baseline"
    )
    expected_scope = {"project_root": str(reader.root), "workspace": str(reader.path("penflow"))}
    if baseline["scope"] != expected_scope or baseline["disposition"] != "active":
        raise VerificationInputError("requirements.scope_or_disposition")
    snapshot = validate_history(reader, baseline)
    _current_sources(reader, snapshot)
    contract_raw = reader.reference(baseline["contract"])
    if contract_raw != reader.reference(snapshot["inputs"]["contract"], archive="contract"):
        raise VerificationInputError("requirements.contract_changed")
    contract = reader.object(contract_raw)
    if any(item["severity"] == "error" for item in validate_flow_contract_v2(contract)):
        raise VerificationInputError("requirements.contract.invalid")
    projection = project_requirements(reader, snapshot, contract)
    if (
        projection != baseline["projection"]
        or digest(canonical_bytes(projection)) != snapshot["inputs"]["projection_sha256"]
    ):
        raise VerificationInputError("requirements.projection_changed")
    if projection["uncovered"]:
        raise VerificationInputError("requirements.uncovered")
    return {
        "baseline": baseline,
        "snapshot": snapshot,
        "projection": projection,
        "contract": contract,
    }


def _current_sources(reader: InputReader, snapshot: dict[str, Any]) -> None:
    selection = snapshot["selection"]
    if any(not SLUG_REGEX.fullmatch(name) for name in selection):
        raise VerificationInputError("requirements.feature.invalid")
    for collection, filename in (("sources", "spec.md"), ("plans", "plan.md")):
        records = snapshot["inputs"][collection]
        if [record["path"] for record in records] != [
            f".specs/features/{name}/{filename}" for name in selection
        ]:
            raise VerificationInputError("requirements.source.membership")
        for record in records:
            current = reader.read(record["path"])
            archived = reader.reference(record["reviewed_snapshot"], archive="source")
            for raw in (current, archived):
                if semantic_text_sha256(raw.decode("utf-8")) != record["semantic_sha256"]:
                    raise VerificationInputError("requirements.source.semantic_changed")
