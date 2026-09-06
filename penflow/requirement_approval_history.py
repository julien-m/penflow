"""Read-only independent verification of the cumulative LiveSpec approval chain."""

from __future__ import annotations

from typing import Any

from .verification_applicability import read_policy_source, validate_plan_policy
from .verification_files import InputReader, VerificationInputError
from .verification_json import canonical_bytes, digest
from .requirement_projection import project_requirements


def validate_history(reader: InputReader, baseline: dict[str, Any]) -> dict[str, Any]:
    """Authenticate review bytes, immutable snapshots and every cumulative predecessor."""
    current = baseline
    latest: dict[str, Any] | None = None
    seen: set[str] = set()
    while True:
        snapshot, approval = _approval(reader, current)
        if latest is None:
            latest = snapshot
        previous = current["previous"]
        prior = None
        if previous is not None:
            if previous["sha256"] in seen:
                raise VerificationInputError("approval.history.cycle")
            seen.add(previous["sha256"])
            prior = reader.object(
                reader.reference(previous, archive="baseline"), "requirements-baseline"
            )
        _selection(snapshot, prior)
        expected_changes = source_changes(
            prior, current["sources"], current["projection"], current["contract"]["sha256"]
        )
        if approval["changes"] != expected_changes:
            raise VerificationInputError("approval.delta.mismatch")
        if prior is None:
            break
        current = prior
    assert latest is not None
    return latest


def _approval(
    reader: InputReader, baseline: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    if len(baseline["approval_receipts"]) != 1:
        raise VerificationInputError("approval.receipt.cardinality")
    approval = reader.object(
        reader.reference(baseline["approval_receipts"][0], archive="approval"), "review-approval"
    )
    review = approval["review"]
    output = reader.object(reader.reference(review["output"], archive="review-output"))
    if canonical_bytes(output) != canonical_bytes(
        {key: value for key, value in review.items() if key != "output"}
    ):
        raise VerificationInputError("approval.review.output_mismatch")
    if (
        review["verdict"] != "PASS"
        or review["blocking_count"] != 0
        or any(row["severity"] == "BLOCKING" for row in review["findings"])
    ):
        raise VerificationInputError("approval.review.not_pass")
    if approval["snapshot"]["sha256"] != review["input_sha256"]:
        raise VerificationInputError("approval.review.input_mismatch")
    snapshot = reader.object(
        reader.reference(approval["snapshot"], archive="snapshot"), "review-snapshot"
    )
    _envelope_identity(baseline, approval, snapshot)
    for record in [*baseline["sources"], *approval["inputs"]["plans"]]:
        if (
            digest(reader.reference(record["reviewed_snapshot"], archive="source"))
            != record["sha256"]
        ):
            raise VerificationInputError("approval.source.raw_mismatch")
    raw = reader.reference(approval["inputs"]["contract"], archive="contract")
    _historical_projection(reader, snapshot, raw)
    return snapshot, approval


def _historical_projection(reader: InputReader, snapshot: dict[str, Any], raw: bytes) -> None:
    expected_scope = {"project_root": str(reader.root), "workspace": str(reader.path("penflow"))}
    if snapshot["scope"] != expected_scope:
        raise VerificationInputError("approval.history.foreign_scope")
    policy_ref = snapshot["inputs"].get("verification_policy")
    if policy_ref is not None:
        source = read_policy_source(reader, policy_ref)
        validate_plan_policy(reader, snapshot, source)
        if source["decisions"] != reader.object(raw).get("verification_policy"):
            raise VerificationInputError("approval.history.policy_changed")
    projection = project_requirements(reader, snapshot, reader.object(raw))
    if snapshot["projection"] != projection or snapshot["inputs"]["projection_sha256"] != digest(
        canonical_bytes(projection)
    ):
        raise VerificationInputError("approval.history.projection_changed")


def _envelope_identity(
    baseline: dict[str, Any], approval: dict[str, Any], snapshot: dict[str, Any]
) -> None:
    expected_contract = (
        snapshot["inputs"]["contract"]
        if baseline["disposition"] == "retired"
        else {
            "path": "penflow/flow-ui-contract/contract.json",
            "sha256": snapshot["inputs"]["contract"]["sha256"],
        }
    )
    if (
        baseline["contract"] != expected_contract
        or any(
            baseline[key] != approval[key]
            for key in ("disposition", "scope", "selection", "retired_features")
        )
        or approval["feature"] not in baseline["selection"]
        or approval["inputs"]["sources"] != baseline["sources"]
        or approval["prior_receipt"] != baseline["previous"]
        or snapshot["projection"] != baseline["projection"]
        or any(
            approval[key] != snapshot[key]
            for key in (
                "scope",
                "selection",
                "feature",
                "inputs",
                "prior_receipt",
                "changes",
                "disposition",
                "retired_features",
            )
        )
    ):
        raise VerificationInputError("approval.envelope.identity_mismatch")


def _selection(snapshot: dict[str, Any], prior: dict[str, Any] | None) -> None:
    selected, retired, feature = (
        snapshot["selection"],
        snapshot["retired_features"],
        snapshot["feature"],
    )
    expected = sorted(set(prior["selection"] if prior else []) | {feature})
    old_retired = set(prior["retired_features"] if prior else [])
    if (
        selected != expected
        or retired != sorted(set(retired))
        or not set(retired) <= set(selected)
        or set(retired) - {feature} != old_retired - {feature}
        or (feature in retired and (prior is None or feature not in prior["selection"]))
        or snapshot["disposition"] != ("active" if set(selected) - set(retired) else "retired")
        or snapshot["inputs"]["selection_sha256"] != digest(canonical_bytes(selected))
    ):
        raise VerificationInputError("approval.selection.mismatch")


def source_changes(
    prior: dict[str, Any] | None,
    sources: list[dict[str, Any]],
    projection: dict[str, Any],
    contract_sha: str,
) -> list[dict[str, Any]]:
    """Recompute the exact reviewed source and predicate delta from immutable predecessors."""
    if prior is None:
        return []
    old_sources = {row["path"]: row for row in prior["sources"]}
    current = {row["path"]: row for row in sources}
    old_ids = {row["id"] for row in prior["projection"]["requirements"]}
    ids = {row["id"] for row in projection["requirements"]}
    old_bindings = {
        f"{row['requirement_id']}:{row['obligation_id']}": row
        for row in prior["projection"]["bindings"]
    }
    new_bindings = {
        f"{row['requirement_id']}:{row['obligation_id']}": row for row in projection["bindings"]
    }
    changed = sorted(
        key
        for key in old_bindings.keys() | new_bindings.keys()
        if old_bindings.get(key) != new_bindings.get(key)
    )
    result = []
    for path in sorted(old_sources.keys() | current.keys()):
        before, after = old_sources.get(path), current.get(path)
        if before != after or changed or prior["contract"]["sha256"] != contract_sha:
            result.append(
                {
                    "source_path": path,
                    "old_sha256": before["sha256"] if before else digest(b""),
                    "new_sha256": after["sha256"] if after else digest(b""),
                    "removed_requirement_ids": sorted(old_ids - ids),
                    "changed_binding_ids": changed,
                }
            )
    return result
