"""Expected-value predicates and typed outcome evidence, including omission attacks."""

import json
from pathlib import Path

import pytest

from penflow.requirement_sources import load_livespec_requirements
from penflow.schema_cache import load_schema
from penflow.verification import (
    evaluate_verification,
    produce_verification_report,
    validate_verification_report,
)
from penflow.verification_assertions import evaluate_assertion, wildcard_matches
from penflow.verification_files import InputReader
from penflow.verification_json import canonical_bytes, digest
from penflow.verification_obligations import derive_obligations
from penflow.verification_policy import GATE_IDS
from penflow.verification_schema import schema_issues
from penflow.verification_snapshot import load_source_snapshot
from tests.c51_design_workspace import (
    DesignProject,
    build_design_project,
    default_delegations,
    design_contract,
    review_request,
    uncertified,
)
from tests.c51_review_chain import SOURCE_KIND
from tests.contract_factory import valid_contract


def _assertion(operator: str, pointer: str, expected=None) -> dict:
    return {"operator": operator, "pointer": pointer, "expected": expected, "capability": "storage"}


@pytest.mark.parametrize("value", [None, False, 0, "", [], {}])
def test_existing_json_values_are_not_missing(value) -> None:
    observed = {"after": {"value": value}, "capability": "storage"}
    assert evaluate_assertion(_assertion("exists", "/after/value"), observed)
    assert not evaluate_assertion(_assertion("absent", "/after/value"), observed)
    assert not evaluate_assertion(_assertion("exists", "/after/missing"), observed)
    assert evaluate_assertion(_assertion("absent", "/after/missing"), observed)


def test_unchanged_requires_two_present_values() -> None:
    assert evaluate_assertion(
        _assertion("unchanged", "/value"),
        {"capability": "storage", "before": {"value": None}, "after": {"value": None}},
    )
    assert not evaluate_assertion(
        _assertion("unchanged", "/value"), {"capability": "storage", "before": {}, "after": {}}
    )


@pytest.mark.parametrize(
    "pattern, value, expected",
    [
        ("saved *", "saved document", True),
        ("a?c", "abc", True),
        ("a?c", "ac", False),
        ("a*c", "abbbc", True),
    ],
)
def test_restricted_matcher_has_deterministic_full_string_semantics(
    pattern, value, expected
) -> None:
    assert wildcard_matches(pattern, value) == expected


@pytest.mark.parametrize("pattern", ["(a+)+", "[abc]", "a|b", r"\1", "a" * 129])
def test_regex_and_overlong_patterns_are_rejected(pattern) -> None:
    with pytest.raises(ValueError):
        wildcard_matches(pattern, "a")


def test_boolean_cannot_masquerade_as_numeric_expected_result() -> None:
    assert not evaluate_assertion(
        _assertion("equals", "/after/value", 1), {"capability": "storage", "after": {"value": True}}
    )


@pytest.mark.parametrize(
    "expected, actual",
    [(1, 1.0), (0, -0.0), (10**400, 10**400), ({"a": [1, 0]}, {"a": [1.0, -0.0]})],
)
def test_json_numbers_compare_by_value(expected, actual) -> None:
    assert evaluate_assertion(
        _assertion("equals", "/after/value", expected),
        {"capability": "storage", "after": {"value": actual}},
    )


@pytest.mark.parametrize(
    "payload", ['{"v":1e400}', '{"v":-1e400}', '{"v":NaN}', '{"v":Infinity}', '{"v":1,"v":2}']
)
def test_strict_json_rejects_nonfinite_and_ambiguous_values(payload: str) -> None:
    from penflow.verification_json import decode_json

    with pytest.raises(ValueError):
        decode_json(payload)


def test_strict_json_preserves_business_sentinel_values() -> None:
    from penflow.verification_json import decode_json

    assert decode_json('{"null":null,"false":false,"zero":0}') == {
        "null": None,
        "false": False,
        "zero": 0,
    }


def test_source_records_determine_denominator_without_observations() -> None:
    contract = valid_contract()
    slots = derive_obligations(contract)
    assert {slot.category for slot in slots} == {
        "structure",
        "action",
        "permission",
        "validation",
        "transition",
        "effect",
        "result",
    }
    assert len({slot.id for slot in slots}) == len(slots)
    for transition in contract["transitions"]:
        for field in ("causal", "kind", "label"):
            transition.pop(field)
    assert derive_obligations(contract) == slots


def test_invalid_contract_cannot_supply_a_reduced_denominator() -> None:
    contract = valid_contract()
    contract["nodes"] = []
    with pytest.raises(ValueError, match="invalid C20"):
        derive_obligations(contract)


def _failures(report: dict) -> list[tuple[str, str, list[str]]]:
    """Name every non-passing required gate so a fixture defect is diagnosed, not hidden."""
    return [
        (gate["id"], gate["status"], [item["message"] for item in gate["issues"]])
        for gate in report["gates"]
        if gate["required"] and gate["status"] != "PASS"
    ] + [("issue", item["code"], [item["message"]]) for item in report["issues"]]


def _derived_requirements(workspace: Path) -> list[dict]:
    """Read the contract requirements copied into the semantic tree and into the code IR."""
    tree = json.loads((workspace / "semantic-ui-tree.json").read_text(encoding="utf-8"))
    code_ir = json.loads((workspace / "code-ir.json").read_text(encoding="utf-8"))
    return [tree["requirements"], code_ir["contract"]["requirements"]]


# @spec AC-003: No-delegation artifacts keep exact bytes — .specs/features/082-reviewed-requirement-delegation-to-upstream-acceptance/spec.md#ac-003
def test_no_delegation_design_pass(tmp_path: Path, governed_consumer_project) -> None:
    project = build_design_project(tmp_path / "consumer", governed_consumer_project)
    report = produce_verification_report(
        project.workspace, project_root=project.root, profile="design"
    )
    assert report["status"] == "PASS", _failures(report)

    projection = load_livespec_requirements(InputReader(project.root))["projection"]
    assert set(projection) == {"source_kind", "sources", "requirements", "bindings", "uncovered"}
    assert canonical_bytes(projection) == canonical_bytes(project.link.projection)
    assert (
        digest(canonical_bytes(projection)) == project.link.snapshot["inputs"]["projection_sha256"]
    )
    report_schema = load_schema("c51-contracts.schema.json")["$defs"]["report"]
    assert set(report) == set(report_schema["required"])
    validation = validate_verification_report(
        project.workspace / "run-report.json", project_root=project.root, required_profile="design"
    )
    assert validation["status"] == "PASS", validation["issues"]
    assert _derived_requirements(project.workspace) == [project.link.contract["requirements"]] * 2
    retired = {
        **{key: [] for key in ("sources", "requirements", "bindings", "uncovered")},
        "source_kind": SOURCE_KIND,
        "delegated": default_delegations(),
    }
    assert schema_issues(retired, "retired-projection")


def _delegated_project(root: Path, govern) -> DesignProject:
    """Build the design fixture whose reviewed contract delegates two requirements."""
    return build_design_project(root, govern, review_request(delegations=default_delegations()))


# @spec AC-009: Report lists delegated as not certified — .specs/features/082-reviewed-requirement-delegation-to-upstream-acceptance/spec.md#ac-009
def test_design_pass_lists_delegated_requirements_uncertified(
    tmp_path: Path, governed_consumer_project
) -> None:
    project = _delegated_project(tmp_path / "consumer", governed_consumer_project)
    report = produce_verification_report(
        project.workspace, project_root=project.root, profile="design"
    )
    assert report["status"] == "PASS", _failures(report)

    declared = project.link.contract["requirements"]["delegations"]
    assert report["delegated_requirements"] == uncertified(declared)
    structure = [
        slot for slot in derive_obligations(project.link.contract) if slot.category == "structure"
    ]
    counts = report["obligations"]
    assert (counts["required"], counts["verified"], counts["missing"]) == (
        len(structure),
        len(structure),
        0,
    )
    delegated = {row["requirement_id"] for row in declared}
    assert all(delegated.isdisjoint(item["requirement_ids"]) for item in counts["items"])
    assert schema_issues(report, "report") == []
    records = {key: value for key, value in project.link.contract.items() if key != "requirements"}
    assert records == design_contract()
    assert [value["delegations"] for value in _derived_requirements(project.workspace)] == [
        declared
    ] * 2
    implementation = evaluate_verification(
        InputReader(project.root), project.workspace, "implementation", None, produce=False
    )
    assert implementation["delegated_requirements"] == uncertified(declared)


def _gate_rows(report: dict) -> list[tuple[str, bool, bool, str]]:
    return [
        (gate["id"], gate["applicable"], gate["required"], gate["status"])
        for gate in report["gates"]
    ]


def _profile_reports(project: DesignProject) -> dict[str, dict]:
    """Produce the design report, then evaluate both profiles against the stored projections."""
    produced = produce_verification_report(
        project.workspace, project_root=project.root, profile="design"
    )
    assert produced["status"] == "PASS", _failures(produced)
    return {
        profile: evaluate_verification(
            InputReader(project.root), project.workspace, profile, None, produce=False
        )
        for profile in ("design", "implementation")
    }


# @spec AC-011: Delegation changes no gate or capability — .specs/features/082-reviewed-requirement-delegation-to-upstream-acceptance/spec.md#ac-011
def test_delegation_changes_no_gate_policy_or_capability(
    tmp_path: Path, governed_consumer_project
) -> None:
    delegated = _delegated_project(tmp_path / "delegated", governed_consumer_project)
    twin = build_design_project(tmp_path / "twin", governed_consumer_project)
    with_delegation, without = _profile_reports(delegated), _profile_reports(twin)

    for profile in ("design", "implementation"):
        rows = _gate_rows(with_delegation[profile])
        assert rows == _gate_rows(without[profile])
        assert [row[0] for row in rows] == list(GATE_IDS)
    policies = [
        load_source_snapshot(InputReader(project.root), project.workspace).policy
        for project in (delegated, twin)
    ]
    assert policies == [design_contract()["verification_policy"]] * 2
    definitions = load_schema("c51-contracts.schema.json")["$defs"]
    assert [
        sorted(definitions[name]["properties"]["capability"]["enum"])
        for name in ("assertion", "observation")
    ] == [["network", "storage", "ui"]] * 2
