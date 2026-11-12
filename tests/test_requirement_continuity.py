"""A LiveSpec technical continuity revision republishes the baseline without a new review.

Observed on a real consumer: LiveSpec delivery continuity accepted six evidence
declaration lines under two acceptance criteria and a contract revision that only adds
state scopes and a collection model, but the Penflow baseline bound the exact reviewed
bytes and refused both. Penflow now consumes a continuity revision and re-proves each
change itself; a change of meaning keeps the refusal.
"""

from __future__ import annotations

import copy
import json
from dataclasses import replace
from pathlib import Path

import pytest

from penflow.requirement_continuity import evidence_declarations
from penflow.requirement_sources import load_livespec_requirements
from penflow.verification_files import InputReader, VerificationInputError
from penflow.verification_json import canonical_bytes, digest
from tests.c51_continuity_support import SPEC_WITH_SECTIONS, with_static, write_continuity
from tests.c51_design_workspace import review_request
from tests.c51_review_chain import (
    BASELINE_PATH,
    FeatureSource,
    ReviewLink,
    encode,
    write_file,
    write_review_link,
)


def _approved(root: Path) -> ReviewLink:
    request = review_request()
    return write_review_link(
        root, replace(request, features=(FeatureSource(spec=SPEC_WITH_SECTIONS),))
    )


def _loaded(root: Path) -> dict | str:
    try:
        return load_livespec_requirements(InputReader(root))
    except VerificationInputError as error:
        return str(error)


def _states(contract: dict) -> dict:
    revised = copy.deepcopy(contract)
    node = next(row for row in revised["nodes"] if row["id"] == "checkout.pay")
    node["states"] = ["default", "error"]
    return revised


def test_the_static_evidence_lines_need_the_revision(tmp_path: Path) -> None:
    link = _approved(tmp_path)
    assert isinstance(_loaded(tmp_path), dict)
    spec = tmp_path / ".specs/features/001-checkout/spec.md"
    spec.write_text(with_static(SPEC_WITH_SECTIONS, "AC-002"))
    # Without a revision the evidence lines are a change of the reviewed source.
    assert _loaded(tmp_path) == "requirements.source.semantic_changed"
    write_continuity(link, spec=with_static(SPEC_WITH_SECTIONS, "AC-002"), declared=("AC-002",))
    loaded = _loaded(tmp_path)
    assert isinstance(loaded, dict), loaded
    expected = copy.deepcopy(link.projection)
    for ref in expected["sources"]:
        ref["sha256"] = loaded["baseline"]["sources"][0]["sha256"]
    assert canonical_bytes(loaded["projection"]) == canonical_bytes(expected)
    assert [row["id"] for row in loaded["projection"]["requirements"]] == [
        row["id"] for row in link.projection["requirements"]
    ]


def test_a_representation_only_contract_revision_is_consumed(tmp_path: Path) -> None:
    link = _approved(tmp_path)
    revised = _states(link.contract)
    write_continuity(
        link,
        spec=with_static(SPEC_WITH_SECTIONS, "AC-002"),
        contract=revised,
        declared=("AC-002",),
    )
    loaded = _loaded(tmp_path)
    assert isinstance(loaded, dict), loaded
    assert loaded["contract"]["nodes"] == revised["nodes"]


@pytest.mark.parametrize(
    ("case", "expected"),
    [
        ("criterion-text", "continuity.source.meaning_changed"),
        ("undeclared-criterion", "continuity.source.undeclared_evidence_change"),
        ("contract-copy", "continuity.contract.functional_change"),
        ("contract-field", "continuity.contract.functional_change"),
        ("tampered-receipt", "input.stale: .specs/penflow-approvals/continuity-"),
        ("edited-projection", "continuity.envelope.mismatch"),
        ("altered-record", "input.stale: .specs/penflow-approvals/continuity-record-"),
    ],
)
def test_a_change_of_meaning_or_a_broken_link_stays_refused(
    tmp_path: Path, case: str, expected: str
) -> None:
    link = _approved(tmp_path)
    spec = with_static(SPEC_WITH_SECTIONS, "AC-002")
    contract = None
    declared = ("AC-002",)
    if case == "criterion-text":
        spec = spec.replace("accepted upstream", "accepted downstream")
    elif case == "undeclared-criterion":
        spec = with_static(spec, "AC-001")
    elif case == "contract-copy":
        contract = _states(link.contract)
        next(row for row in contract["nodes"] if row["id"] == "checkout.pay")["text"] = "Pay now"
    elif case == "contract-field":
        contract = copy.deepcopy(link.contract)
        contract["entities"][0]["fields"].append({"id": "coupon", "type": "string"})
    baseline = write_continuity(link, spec=spec, contract=contract, declared=declared)
    if case == "tampered-receipt":
        receipt = tmp_path / baseline["continuity"]["path"]
        receipt.write_text(receipt.read_text().replace('"feature"', '"feature" '))
    elif case == "altered-record":
        record = tmp_path / receipt_record(tmp_path, baseline)
        record.write_text(record.read_text() + " ")
    elif case == "edited-projection":
        # A revision must carry the approved envelope: a different projection is a review.
        baseline["projection"] = {**baseline["projection"], "uncovered": ["x"]}
        write_file(tmp_path, BASELINE_PATH, encode(baseline))
    outcome = _loaded(tmp_path)
    assert isinstance(outcome, str) and outcome.startswith(expected), outcome


def test_a_baseline_without_continuity_is_read_as_before(tmp_path: Path) -> None:
    link = _approved(tmp_path)
    assert "continuity" not in link.baseline
    assert isinstance(_loaded(tmp_path), dict)


def test_evidence_lines_outside_a_criterion_section_are_meaning() -> None:
    text = "## Notes\n\n**Evidence:** static\n\n### AC-001\n\n**Evidence:** static\n"
    kept, found = evidence_declarations(text)
    assert found == {"AC-001": ("**Evidence:** static",)}
    assert "## Notes\n\n**Evidence:** static" in kept


def receipt_record(root: Path, baseline: dict) -> str:
    receipt = json.loads((root / baseline["continuity"]["path"]).read_text())
    return receipt["livespec_record"]["path"]


def test_a_repeat_model_and_its_collection_fields_are_representation(tmp_path: Path) -> None:
    link = _approved(tmp_path)
    revised = copy.deepcopy(link.contract)
    revised["entities"][0]["fields"] += [
        {"id": "lines", "type": "string"},
        {"id": "id", "type": "string"},
    ]
    node = next(row for row in revised["nodes"] if row["id"] == "checkout.title")
    node["repeat_model"] = {
        "collection": "checkout.lines",
        "item_model": "checkout",
        "item_key": "id",
        "instance_id_template": "line-{checkout.id}",
    }
    write_continuity(link, contract=revised)
    loaded = _loaded(tmp_path)
    assert isinstance(loaded, dict), loaded


def test_a_second_revision_continues_the_first(tmp_path: Path) -> None:
    link = _approved(tmp_path)
    first = write_continuity(
        link, spec=with_static(SPEC_WITH_SECTIONS, "AC-002"), declared=("AC-002",)
    )
    raw = (tmp_path / BASELINE_PATH).read_bytes()
    archived = write_file(tmp_path, f".specs/penflow-approvals/baseline-{digest(raw)}.json", raw)
    contract = json.loads((tmp_path / "penflow/flow-ui-contract/contract.json").read_text())
    second_link = replace(link, baseline=first, baseline_ref=archived, contract=contract)
    write_continuity(
        second_link,
        spec=with_static(with_static(SPEC_WITH_SECTIONS, "AC-002"), "AC-001"),
        declared=("AC-001",),
    )
    loaded = _loaded(tmp_path)
    assert isinstance(loaded, dict), loaded
