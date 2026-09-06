"""Workflow authority is independent of optional evidence and C20 declarations."""

from pathlib import Path

import pytest

from penflow.verification_applicability import workflow_decisions
from penflow.verification_files import VerificationInputError


POLICY = {
    "version": 1,
    "generated_docs": "not_applicable",
    "native_geometry": "required",
    "homologous_references": "not_applicable",
    "native_export": "not_applicable",
}


def test_policy_is_derived_from_the_selected_real_workflow_mode() -> None:
    import yaml

    raw = (
        "---\n"
        + yaml.safe_dump({"penflow_verification_policy": {"livespec": POLICY}})
        + "---\n# Workflow\n"
    )
    assert workflow_decisions(raw, inherited=False) == POLICY
    with pytest.raises(VerificationInputError):
        workflow_decisions(raw, inherited=True)


@pytest.mark.parametrize(
    "raw",
    [
        "# no structured policy",
        "---\npenflow_verification_policy: false\n---\n",
        "---\npenflow_verification_policy:\n  arbitrary: {}\n---\n",
    ],
)
def test_absent_or_unknown_workflow_decisions_never_mean_not_applicable(raw: str) -> None:
    with pytest.raises(VerificationInputError):
        workflow_decisions(raw, inherited=False)


def test_broken_baseline_is_present_authority_without_fallback(tmp_path: Path) -> None:
    from penflow.verification_files import InputReader
    from penflow.verification_snapshot import load_source_snapshot

    (tmp_path / ".specs").mkdir()
    (tmp_path / ".specs/penflow-requirements.json").symlink_to(tmp_path / "missing")
    (tmp_path / "penflow").mkdir()
    with pytest.raises((OSError, VerificationInputError)) as caught:
        load_source_snapshot(InputReader(tmp_path), tmp_path / "penflow")
    assert "ambiguous_or_missing_authority" not in str(caught.value)


def test_inherited_business_predicate_does_not_equate_boolean_and_number():
    from penflow.verification_authority import _preserved_expectations

    expected = {
        "obligation_id": "storage",
        "category": "persistence",
        "assertions": [{"operator": "equals", "pointer": "/after/value", "expected": 1}],
    }
    original = {
        "outcome_expectations": [expected],
        "requirements": {
            "bindings": [{"requirement_id": "product:state", "obligation_id": "storage"}]
        },
    }
    projection = {
        "bindings": [
            {
                "requirement_id": "product:state",
                "expected": {
                    **expected,
                    "assertions": [
                        {"operator": "equals", "pointer": "/after/value", "expected": True}
                    ],
                },
            }
        ]
    }
    with pytest.raises(VerificationInputError):
        _preserved_expectations(original, projection)


def test_duplicate_workflow_policy_keys_cannot_override_required_duties():
    import yaml

    raw = "---\n" + yaml.safe_dump({"penflow_verification_policy": {"livespec": POLICY}}) + "---\n"
    raw = raw.replace(
        "    generated_docs: not_applicable",
        "    generated_docs: required\n    generated_docs: not_applicable",
    )
    with pytest.raises(VerificationInputError):
        workflow_decisions(raw, inherited=False)
