"""Technical continuity revisions of the LiveSpec requirement baseline.

LiveSpec accepts some technical changes of reviewed sources without a new review (its
delivery continuity), for example the evidence declarations of an acceptance criterion.
It then republishes the baseline as a continuity revision: the same approval, scope,
selection and projection, a ``previous`` link to the archived predecessor and an archived
``requirements-continuity`` receipt naming each changed source and contract.

Penflow trusts no verdict of that receipt. It authenticates every archived byte and
re-proves each change itself:

- a source keeps its meaning once the evidence declarations of its acceptance criteria are
  removed, and exactly the declared criteria changed their declarations;
- a contract keeps every functional field once the representation-only keys (node
  ``states`` and ``repeat_model``, and the entity fields a repeat model introduces) are
  removed, and still validates;
- the recomputed projection equals the approved one (checked by the caller).
"""

from __future__ import annotations

import copy
import re
from typing import Any

from .flow_contract import validate_flow_contract_v2
from .requirement_markdown import semantic_text_sha256
from .verification_files import InputReader, VerificationInputError
from .verification_json import canonical_bytes, digest

CONTRACT_PATH = "penflow/flow-ui-contract/contract.json"
# LiveSpec spec-system evidence declaration lines of an acceptance criterion.
EVIDENCE_PREFIXES = (
    "**Evidence:**",
    "**Static command:**",
    "**Static directory:**",
    "**Static inputs:**",
)
_HEADING = re.compile(r"^#{1,6}\s+(.*)$")
_CRITERION = re.compile(r"^(AC-[0-9]{3})\b")
_REPRESENTATION_KEYS = ("states", "repeat_model")
# Keys of a baseline that a continuity revision must carry over unchanged.
_CARRIED = ("scope", "selection", "disposition", "retired_features", "approval_receipts")


def evidence_declarations(text: str) -> tuple[str, dict[str, tuple[str, ...]]]:
    """Split the evidence declaration lines of each ``AC-NNN`` section from the rest."""
    kept: list[str] = []
    found: dict[str, list[str]] = {}
    criterion: str | None = None
    for line in text.splitlines(keepends=True):
        heading = _HEADING.match(line.strip())
        if heading:
            match = _CRITERION.match(heading.group(1))
            criterion = match.group(1) if match else None
        elif criterion and line.strip().startswith(EVIDENCE_PREFIXES):
            found.setdefault(criterion, []).append(line.strip())
            continue
        kept.append(line)
    return "".join(kept), {key: tuple(value) for key, value in found.items()}


def verify_source_change(before: bytes, after: bytes, declared: list[str]) -> None:
    """Refuse unless only the declared criteria's evidence declarations differ."""
    old_text, old = evidence_declarations(before.decode("utf-8"))
    new_text, new = evidence_declarations(after.decode("utf-8"))
    if semantic_text_sha256(old_text) != semantic_text_sha256(new_text):
        raise VerificationInputError("continuity.source.meaning_changed")
    changed = sorted(key for key in old.keys() | new.keys() if old.get(key) != new.get(key))
    if changed != sorted(declared):
        raise VerificationInputError("continuity.source.undeclared_evidence_change")


def functional_contract(
    contract: dict[str, Any], introduced: set[tuple[str, str]], moved: set[str]
) -> Any:
    """The contract without its representation-only keys, introduced entity fields and the
    digests of the source references whose continuity is proved separately."""
    view = copy.deepcopy(contract)
    for ref in view.get("requirements", {}).get("source_refs", []):
        if ref.get("path") in moved:
            ref["sha256"] = None
    for node in view.get("nodes", []):
        for key in _REPRESENTATION_KEYS:
            node.pop(key, None)
    for entity in view.get("entities", []):
        entity["fields"] = [
            field for field in entity["fields"] if (entity["id"], field["id"]) not in introduced
        ]
    return view


def verify_contract_change(
    before: dict[str, Any], after: dict[str, Any], moved: dict[str, tuple[str, str]]
) -> None:
    """Refuse unless the contracts differ only in their representation and in the digests
    of the source references moved by a proved source change (``path: (old, new)``)."""
    if any(item["severity"] == "error" for item in validate_flow_contract_v2(after)):
        raise VerificationInputError("continuity.contract.invalid")
    for contract, side in ((before, 0), (after, 1)):
        refs = {
            ref.get("path"): ref.get("sha256")
            for ref in contract.get("requirements", {}).get("source_refs", [])
        }
        if any(refs.get(path) != digests[side] for path, digests in moved.items()):
            raise VerificationInputError("continuity.contract.source_ref_mismatch")
    known = {
        (entity["id"], field["id"])
        for entity in before.get("entities", [])
        for field in entity["fields"]
    }
    introduced = _repeat_fields(after) - known
    if canonical_bytes(functional_contract(before, set(), set(moved))) != canonical_bytes(
        functional_contract(after, introduced, set(moved))
    ):
        raise VerificationInputError("continuity.contract.functional_change")


def _repeat_fields(contract: dict[str, Any]) -> set[tuple[str, str]]:
    """The entity fields that repeat models name: their collection and item key."""
    fields: set[tuple[str, str]] = set()
    for node in contract.get("nodes", []):
        model = node.get("repeat_model")
        if not isinstance(model, dict):
            continue
        owner, _, collection = str(model.get("collection", "")).partition(".")
        if owner and collection:
            fields.add((owner, collection))
        fields.add((str(model.get("item_model")), str(model.get("item_key"))))
    return fields


def resolve_continuity(
    reader: InputReader, baseline: dict[str, Any], depth: int = 0
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Return the approved baseline under continuity revisions and the effective inputs.

    The effective inputs are None for an approved baseline. Every link is verified once,
    oldest first; the approved baseline itself is verified by ``validate_history``.
    """
    if "continuity" not in baseline:
        return baseline, None
    if depth > 64:
        raise VerificationInputError("continuity.history.cycle")
    if baseline["previous"] is None:
        raise VerificationInputError("continuity.previous.missing")
    prior = reader.object(
        reader.reference(baseline["previous"], archive="baseline"), "requirements-baseline"
    )
    approved, prior_inputs = resolve_continuity(reader, prior, depth + 1)
    inputs = prior_inputs if prior_inputs is not None else approved_inputs(reader, approved)
    return approved, _verify_link(reader, baseline, prior, inputs)


def approved_inputs(reader: InputReader, baseline: dict[str, Any]) -> dict[str, Any]:
    """The inputs of the approval snapshot an approved baseline publishes."""
    approval = reader.object(
        reader.reference(baseline["approval_receipts"][0], archive="approval"), "review-approval"
    )
    snapshot = reader.object(
        reader.reference(approval["snapshot"], archive="snapshot"), "review-snapshot"
    )
    return snapshot["inputs"]


def _verify_link(
    reader: InputReader,
    baseline: dict[str, Any],
    prior: dict[str, Any],
    inputs: dict[str, Any],
) -> dict[str, Any]:
    receipt = reader.object(
        reader.reference(baseline["continuity"], archive="continuity"), "requirements-continuity"
    )
    reader.reference(receipt["livespec_record"], archive="continuity-record")
    if (
        receipt["previous"] != baseline["previous"]
        or receipt["scope"] != baseline["scope"]
        or receipt["feature"] not in baseline["selection"]
        or any(baseline[key] != prior[key] for key in _CARRIED)
    ):
        raise VerificationInputError("continuity.envelope.mismatch")
    effective = copy.deepcopy(inputs)
    if not receipt["changes"] and receipt["contract"] is None:
        raise VerificationInputError("continuity.changes.empty")
    for change in receipt["changes"]:
        _apply_source_change(reader, effective, change)
    moved = {
        change["path"]: (change["before"]["sha256"], change["after"]["sha256"])
        for change in receipt["changes"]
        if change["collection"] == "sources"
    }
    effective["contract"] = _contract_link(reader, receipt["contract"], inputs["contract"], moved)
    expected_contract = {"path": CONTRACT_PATH, "sha256": effective["contract"]["sha256"]}
    if (
        baseline["sources"] != effective["sources"]
        or baseline["contract"] != expected_contract
        or baseline["projection"] != _moved_projection(prior["projection"], moved)
    ):
        raise VerificationInputError("continuity.envelope.mismatch")
    effective["projection_sha256"] = digest(canonical_bytes(baseline["projection"]))
    return effective


def _moved_projection(projection: dict[str, Any], moved: dict[str, tuple[str, str]]) -> Any:
    """The approved projection with only the source digests a proved change moved."""
    result = copy.deepcopy(projection)
    for ref in result.get("sources", []):
        if ref["path"] in moved and ref["sha256"] == moved[ref["path"]][0]:
            ref["sha256"] = moved[ref["path"]][1]
    return result


def _apply_source_change(
    reader: InputReader, effective: dict[str, Any], change: dict[str, Any]
) -> None:
    records = effective[change["collection"]]
    index = next((i for i, row in enumerate(records) if row["path"] == change["path"]), None)
    if index is None or records[index] != change["before"]:
        raise VerificationInputError("continuity.source.before_mismatch")
    after = change["after"]
    if after["path"] != change["path"]:
        raise VerificationInputError("continuity.source.path_mismatch")
    before_raw = reader.reference(change["before"]["reviewed_snapshot"], archive="source")
    after_raw = reader.reference(after["reviewed_snapshot"], archive="source")
    if (
        digest(after_raw) != after["sha256"]
        or semantic_text_sha256(after_raw.decode("utf-8")) != after["semantic_sha256"]
    ):
        raise VerificationInputError("continuity.source.after_mismatch")
    verify_source_change(before_raw, after_raw, change["evidence_changes"])
    records[index] = after


def _contract_link(
    reader: InputReader,
    link: dict[str, Any] | None,
    current: dict[str, Any],
    moved: dict[str, tuple[str, str]],
) -> dict[str, Any]:
    if link is None:
        if moved:  # The contract names the reviewed source digests: it must follow them.
            raise VerificationInputError("continuity.contract.missing")
        return current
    if link["before"]["sha256"] != current["sha256"]:
        raise VerificationInputError("continuity.contract.before_mismatch")
    before = reader.object(reader.reference(link["before"], archive="contract"))
    after = reader.object(reader.reference(link["after"], archive="contract"))
    verify_contract_change(before, after, moved)
    return link["after"]
