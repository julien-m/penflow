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
    "**Review inputs:**",
    "**Static command:**",
    "**Static directory:**",
    "**Static inputs:**",
)
_HEADING = re.compile(r"^#{1,6}\s+(.*)$")
_CRITERION = re.compile(r"^(AC-[0-9]{3})\b")
_REPRESENTATION_KEYS = ("states", "repeat_model")
_EVIDENCE = re.compile(r"^\*\*Evidence:\*\*\s*([a-z-]+)\s*$")
# An explicitly declared level that no technical change may move (LiveSpec floors).
_FIXED_LEVELS = ("execution", "native")
# LiveSpec reads an acceptance criterion without an Evidence line as an execution one.
_IMPLICIT_LEVEL = "execution"
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


def evidence_level(lines: tuple[str, ...]) -> tuple[str, bool]:
    """The evidence level of one criterion and whether it is explicitly declared."""
    for line in lines:
        match = _EVIDENCE.match(line)
        if match:
            return match.group(1), True
    return _IMPLICIT_LEVEL, False


_LEVELS = ("static", "unit", "integration", "mocked-web", "native", "execution", "review")
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_CRITERIA = re.compile(r"\b(?:acs?|acceptance criteri(?:on|a)|criteri(?:on|a))\b")
_ID_OR_RANGE = re.compile(r"AC-([0-9]{3})(?:\s*(?:\u2013|\u2014|-|to)\s*AC-([0-9]{3}))?")


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def level_table(text: str) -> dict[str, set[str]]:
    """The evidence levels each criterion receives from normative level tables.

    A level table is a Markdown table outside fences and HTML comments whose header has
    a cell naming the level and a cell naming the criteria. Each row reads the first word
    of its level cell (one of ``_LEVELS``) and every ``AC-NNN`` or ``AC-NNN–AC-MMM`` range
    of its criteria cell; a parenthetical qualifier keeps the criterion.
    """
    found: dict[str, set[str]] = {}
    lines = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL).splitlines()
    fence = False
    columns: tuple[int, int] | None = None
    for index, line in enumerate(lines):
        if _FENCE.match(line):
            fence, columns = not fence, None
            continue
        if fence or not line.strip().startswith("|"):
            columns = None
            continue
        cells = _cells(line)
        if columns is None:
            header = [cell.casefold() for cell in cells]
            separator = index + 1 < len(lines) and set(
                lines[index + 1].replace("|", "").strip()
            ) <= set("-: ")
            level = next((i for i, cell in enumerate(header) if "level" in cell), None)
            criteria = next((i for i, cell in enumerate(header) if _CRITERIA.search(cell)), None)
            if separator and level is not None and criteria is not None and level != criteria:
                columns = (level, criteria)
            continue
        if set(line.replace("|", "").strip()) <= set("-: ") or max(columns) >= len(cells):
            continue
        words = cells[columns[0]].split()
        name = words[0].casefold() if words else ""
        if name not in _LEVELS:
            continue
        for start, end in _ID_OR_RANGE.findall(cells[columns[1]]):
            for number in range(int(start), int(end or start) + 1):
                found.setdefault(f"AC-{number:03d}", set()).add(name)
    return found


def verify_source_change(before: bytes, after: bytes, declared: list[dict[str, Any]]) -> None:
    """Refuse unless only the declared criteria changed their declarations, to a level the
    approved document already grants: the level table's only level for that criterion,
    or, without a table entry, a move that keeps an explicit floor (execution and native
    never move, nothing becomes review). Without any approved level, nothing is guessed.
    ``declared`` names each criterion with its levels before/after."""
    old_source = before.decode("utf-8")
    old_text, old = evidence_declarations(old_source)
    new_text, new = evidence_declarations(after.decode("utf-8"))
    if semantic_text_sha256(old_text) != semantic_text_sha256(new_text):
        raise VerificationInputError("continuity.source.meaning_changed")
    changed = sorted(key for key in old.keys() | new.keys() if old.get(key) != new.get(key))
    if changed != sorted(item["requirement"] for item in declared):
        raise VerificationInputError("continuity.source.undeclared_evidence_change")
    approved = level_table(old_text)
    for item in declared:
        (level, explicit), (later, _) = (
            evidence_level(old.get(item["requirement"], ())),
            evidence_level(new.get(item["requirement"], ())),
        )
        if [item["before_level"], item["after_level"]] != [level, later]:
            raise VerificationInputError("continuity.source.declared_level_mismatch")
        table = approved.get(item["requirement"])
        # Every approved floor holds: the level table's level and an explicit inline one.
        if (table is not None and table != {later}) or (table is None and not explicit):
            raise VerificationInputError("continuity.source.level_not_approved")
        if (explicit and level in _FIXED_LEVELS and later != level) or (
            later == "review" and level != "review"
        ):
            raise VerificationInputError("continuity.source.evidence_weakened")


def functional_contract(
    contract: dict[str, Any], added: set[tuple[str, str]], moved: set[str]
) -> Any:
    """The contract without the representation keys a revision ADDED to a node, the entity
    fields its new repeat models introduced, and the digests of the source references whose
    continuity is proved separately. ``added`` lists ``(node id, key)`` pairs, or
    ``(entity id, field id)`` pairs prefixed by ``"field:"`` for introduced fields."""
    view = copy.deepcopy(contract)
    for ref in view.get("requirements", {}).get("source_refs", []):
        if ref.get("path") in moved:
            ref["sha256"] = None
    for node in view.get("nodes", []):
        for key in _REPRESENTATION_KEYS:
            if (str(node.get("id")), key) in added:
                node.pop(key, None)
    for entity in view.get("entities", []):
        entity["fields"] = [
            field
            for field in entity["fields"]
            if (f"field:{entity['id']}", str(field["id"])) not in added
        ]
    return view


def verify_contract_change(
    before: dict[str, Any], after: dict[str, Any], moved: dict[str, tuple[str, str]]
) -> None:
    """Refuse unless the revision only ADDS state scopes and repeat models to nodes that had
    none, the entity fields those new repeat models name, and the source digests moved by a
    proved source change (``path: (old, new)``). An existing scope or model, a binding, an
    order, an action, a guard, a transition or an expectation never changes this way."""
    if any(item["severity"] == "error" for item in validate_flow_contract_v2(after)):
        raise VerificationInputError("continuity.contract.invalid")
    for contract, side in ((before, 0), (after, 1)):
        refs = {
            ref.get("path"): ref.get("sha256")
            for ref in contract.get("requirements", {}).get("source_refs", [])
        }
        if any(refs.get(path) != digests[side] for path, digests in moved.items()):
            raise VerificationInputError("continuity.contract.source_ref_mismatch")
    old_nodes = {str(node.get("id")): node for node in before.get("nodes", [])}
    added = {
        (str(node.get("id")), key)
        for node in after.get("nodes", [])
        for key in _REPRESENTATION_KEYS
        if key in node and key not in old_nodes.get(str(node.get("id")), {key: None})
    }
    new_models = [
        node["repeat_model"]
        for node in after.get("nodes", [])
        if (str(node.get("id")), "repeat_model") in added and isinstance(node["repeat_model"], dict)
    ]
    known = {(e["id"], f["id"]) for e in before.get("entities", []) for f in e["fields"]}
    added |= {(f"field:{owner}", name) for owner, name in _repeat_fields(new_models) - known}
    if canonical_bytes(functional_contract(before, set(), set(moved))) != canonical_bytes(
        functional_contract(after, added, set(moved))
    ):
        raise VerificationInputError("continuity.contract.functional_change")


def _repeat_fields(models: list[dict[str, Any]]) -> set[tuple[str, str]]:
    """The entity fields that repeat models name: their collection and item key."""
    fields: set[tuple[str, str]] = set()
    for model in models:
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
