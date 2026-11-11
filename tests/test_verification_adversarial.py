# @spec AC-009: Given wrong screen identity, duplicate semantic instance, missing required text/visual/layout observation or extra interactive control, when compared, then it fails regardless of aggregate score. — .specs/features/077-complete-verification-workflow/spec.md#ac-009
# @spec AC-008: Given a same-ID role/action/binding/permission/state difference between contract and Pencil/IR, when bidirectional validation runs, then it fails even if all IDs exist globally. — .specs/features/077-complete-verification-workflow/spec.md#ac-008
# @spec AC-007: Given exact declared reusable instances, repeated keys, inherited/decorative classification and legitimate business loops, when validated under their explicit models, then valid cases pass; duplicate instance keys fail. — .specs/features/077-complete-verification-workflow/spec.md#ac-007
# @spec AC-006: Given a UI graph cycle, detached active node, invalid ownership/reference or ambiguous parent/instance, when schema/graph validation runs, then a deterministic coded finding replaces recursion failure or lossy export. — .specs/features/077-complete-verification-workflow/spec.md#ac-006
# @spec AC-004: Given empty/missing expected screens or invalid contract cardinality, when export/compare/closure runs, then it fails before publishing successful partial artifacts or similarity success. — .specs/features/077-complete-verification-workflow/spec.md#ac-004
"""C51 rejection cases exercise real validators, never replace the rule under test."""

import json
from collections.abc import Callable
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

from penflow.compare import compare_trees
from penflow.flow_contract import validate_flow_contract_v2
from penflow.product_sources import load_brainstorm_requirements
from penflow.requirement_projection import project_requirements
from penflow.semantic import semantic_tree_from_contract
from penflow.semantic_context_coverage import audit_semantic_context
from penflow.verification import evaluate_verification
from penflow.verification_authority import inherited_projection
from penflow.verification_files import InputReader, VerificationInputError
from penflow.verification_json import canonical_bytes, digest
from tests.c51_design_workspace import (
    BOUND,
    DELEGABLE,
    default_delegations,
    invalid_delegation_request,
    retired_feature_delegation_request,
    review_request,
    unknown_delegation_request,
)
from tests.c51_review_chain import (
    CONTRACT_PATH,
    POLICY_SOURCE_PATH,
    SPEC_TEXT,
    ChainOverrides,
    InheritedAuthority,
    ReviewRequest,
    delegation,
    encode,
    write_inherited_authority,
    write_review_link,
)
from tests.contract_factory import valid_contract
from tests.test_product_sources_adversarial import CONTRACT as BRAINSTORM_CONTRACT
from tests.test_product_sources_adversarial import FIXTURE as BRAINSTORM_FIXTURE
from tests.test_product_sources_adversarial import WORKSPACE as BRAINSTORM_WORKSPACE
from tests.test_product_sources_adversarial import _copy_consumer
from tests.test_semantic_context_coverage import _contract, _pen


def _tree() -> dict:
    return {
        "version": 1,
        "screens": [
            {
                "screen_id": "checkout",
                "root": {
                    "id": "checkout",
                    "semantic_id": "checkout",
                    "role": "screen",
                    "bbox": {"x": 0, "y": 0, "width": 100, "height": 100},
                    "children": [
                        {
                            "id": "pay",
                            "semantic_id": "checkout.pay",
                            "role": "button",
                            "bbox": {"x": 8, "y": 8, "width": 80, "height": 44},
                            "text": "Pay",
                            "visual": {"fill": "#ffffff", "fontSize": 16},
                        }
                    ],
                },
            }
        ],
    }


@pytest.mark.parametrize("defect", ["cycle", "detached", "multi_parent"])
def test_contract_containment_defects_block_before_export(defect: str) -> None:
    contract = valid_contract()
    if defect == "cycle":
        contract["nodes"][1]["children"] = ["checkout.root"]
    elif defect == "detached":
        contract["nodes"][0]["children"].remove("checkout.title")
    else:
        contract["nodes"][2]["children"] = ["checkout.title"]
    assert any(i["code"].startswith("contract.graph.") for i in validate_flow_contract_v2(contract))
    with pytest.raises(ValueError, match="contract validation failed"):
        semantic_tree_from_contract(contract)


@pytest.mark.parametrize(
    "defect",
    [
        "text",
        "visual",
        "screen",
        "extra",
        "empty",
        "missing_screens",
        "role",
        "version",
        "duplicate_screen",
        "duplicate_node",
        "bbox",
    ],
)
def test_comparison_cannot_accept_missing_or_malformed_observation(defect: str) -> None:
    expected = _tree()
    actual = deepcopy(expected)
    node = actual["screens"][0]["root"]["children"][0]
    if defect == "text":
        del node["text"]
    elif defect == "visual":
        del node["visual"]["fill"]
    elif defect == "screen":
        actual["screens"][0]["screen_id"] = "foreign"
    elif defect == "extra":
        extra = deepcopy(node)
        extra.update(id="ghost", semantic_id="ghost")
        actual["screens"][0]["root"]["children"].append(extra)
    elif defect == "empty":
        expected["screens"] = []
    elif defect == "missing_screens":
        del expected["screens"]
    elif defect == "role":
        node["role"] = ""
    elif defect == "version":
        actual["version"] = 999
    elif defect == "duplicate_screen":
        actual["screens"].append(deepcopy(actual["screens"][0]))
    elif defect == "duplicate_node":
        actual["screens"][0]["root"]["children"].append(deepcopy(node))
    elif defect == "bbox":
        node["bbox"]["width"] = "invalid"
    report = compare_trees(expected, actual)
    assert report["status"] == "FAIL"
    assert report["issues"]


def test_context_role_substitution_is_not_equivalent() -> None:
    pencil = _pen()
    pencil["children"][0]["children"][1]["context"]["role"] = "text"
    report = audit_semantic_context(
        _contract(), pencil, contract_path="contract.json", pen_path="ui.pen"
    )
    assert report["status"] != "PASS"
    assert any(i["code"] == "pencil.role_mismatch" for i in report["buckets"]["reference_invalid"])


def test_equal_independent_observations_and_business_state_loops_remain_valid() -> None:
    assert compare_trees(_tree(), deepcopy(_tree()))["status"] == "PASS"
    assert validate_flow_contract_v2(valid_contract()) == []


@pytest.mark.parametrize("value", [None, "", False, 0, [], {}])
def test_observed_visual_value_cannot_hide_behind_falsey_value(value: object) -> None:
    expected = _tree()
    actual = deepcopy(expected)
    actual["screens"][0]["root"]["children"][0]["visual"]["fill"] = value
    assert compare_trees(expected, actual)["status"] == "FAIL"


@pytest.mark.parametrize("value", ["nope", float("nan"), float("inf"), -1, True])
def test_invalid_tolerance_cannot_disable_measurement(value: object) -> None:
    expected = _tree()
    expected["screens"][0]["root"]["context"] = {"tolerance": {"bbox_px": value}}
    assert compare_trees(expected, _tree())["status"] == "FAIL"


@pytest.mark.parametrize(
    "key, before, after", [("strokeThickness", 1, 100), ("textAlign", "left", "right")]
)
def test_native_visual_properties_are_compared(key: str, before: object, after: object) -> None:
    expected = _tree()
    actual = deepcopy(expected)
    expected["screens"][0]["root"]["visual"] = {key: before}
    actual["screens"][0]["root"]["visual"] = {key: after}
    report = compare_trees(expected, actual)
    assert report["status"] == "FAIL"
    assert any(issue["code"] == f"node.visual.{key}" for issue in report["issues"])


@pytest.mark.parametrize("field", ["binding", "entity", "permission"])
def test_context_business_slot_is_checked_on_its_own_identity(field: str) -> None:
    pencil = _pen()
    pay = pencil["children"][0]["children"][1]["context"]
    pay.update(binding="checkout.payment_method", entity="checkout", permission="buyer_can_pay")
    pay[field] = "checkout.title" if field == "binding" else "foreign"
    report = audit_semantic_context(
        _contract(), pencil, contract_path="contract.json", pen_path="ui.pen"
    )
    assert report["status"] != "PASS"
    assert any(
        i["code"] == f"pencil.{field}_mismatch" for i in report["buckets"]["reference_invalid"]
    )


@pytest.mark.parametrize(
    "field, value", [("bbox", -1), ("viewport", -1), ("viewport", float("nan"))]
)
def test_dimensions_are_finite_and_nonnegative(field: str, value: float) -> None:
    actual = _tree()
    screen = actual["screens"][0]
    target = (
        screen["root"]["bbox"]
        if field == "bbox"
        else screen.setdefault("viewport", {"width": 100, "height": 100})
    )
    target["width"] = value
    assert compare_trees(_tree(), actual)["status"] == "FAIL"


def test_negative_position_and_zero_hidden_dimensions_remain_valid() -> None:
    expected = _tree()
    expected["screens"][0]["root"]["bbox"].update(x=-10, width=0, height=0)
    expected["screens"][0]["root"]["visual"] = {"cornerRadius": 0}
    assert compare_trees(expected, deepcopy(expected))["status"] == "PASS"


def test_native_stroke_object_and_adapter_thickness_have_same_meaning() -> None:
    expected = _tree()
    actual = deepcopy(expected)
    expected["screens"][0]["root"]["visual"] = {"stroke": {"fill": "#123456", "thickness": 1}}
    actual["screens"][0]["root"]["visual"] = {"stroke": "#123456", "strokeThickness": 1}
    assert compare_trees(expected, deepcopy(expected))["status"] == "PASS"
    assert compare_trees(expected, actual)["status"] == "PASS"
    actual["screens"][0]["root"]["visual"]["strokeThickness"] = 100
    assert compare_trees(expected, actual)["status"] == "FAIL"


def test_canonical_business_context_survives_draft_and_code_ir(tmp_path) -> None:
    import json
    from penflow.context import Context
    from penflow.contracts import code_ir_from_pen
    from penflow.semantic_draft import pen_draft_from_semantic_tree

    contract = _contract()
    tree = semantic_tree_from_contract(contract)
    draft = pen_draft_from_semantic_tree(tree)
    pay = draft["children"][0]["children"][1]
    context = Context.from_raw(pay["context"])
    assert (context.binding, context.entity, context.permission) == (
        "checkout.payment_method",
        "checkout",
        "buyer_can_pay",
    )
    path = tmp_path / "ui.pen"
    path.write_text(json.dumps(draft))
    ir = code_ir_from_pen(path, contract=contract)
    ir_pay = ir["screens"][0]["root"]["children"][1]
    assert ir_pay["permission"] == "buyer_can_pay"
    assert ir_pay["binding"] == "checkout.payment_method"


def test_inferred_binding_entity_cannot_be_replaced_by_another_known_entity() -> None:
    contract = _contract()
    contract["entities"].append({"id": "foreign", "fields": []})
    pencil = _pen()
    pencil["children"][0]["children"][0]["context"]["entity"] = "foreign"
    report = audit_semantic_context(
        contract, pencil, contract_path="contract.json", pen_path="ui.pen"
    )
    assert report["status"] != "PASS"
    assert any(
        item["code"] == "pencil.entity_mismatch" for item in report["buckets"]["reference_invalid"]
    )


def test_required_pencil_copy_must_be_observed() -> None:
    pencil = _pen()
    del pencil["children"][0]["children"][0]["content"]
    report = audit_semantic_context(
        _contract(), pencil, contract_path="contract.json", pen_path="ui.pen"
    )
    assert report["status"] != "PASS"
    assert any(
        item["code"] == "pencil.copy_mismatch" for item in report["buckets"]["reference_invalid"]
    )


def _upstream_gate(
    root: Path, workspace: str | Path = "penflow"
) -> tuple[str, list[tuple[str, str]], str]:
    """Evaluate the design profile without writing, and describe its upstream gate.

    Returns the gate status, its issue codes and messages, and the report status.
    """
    report = evaluate_verification(
        InputReader(root), root / workspace, "design", None, produce=False
    )
    gate = next(row for row in report["gates"] if row["id"] == "upstream-requirements")
    return (
        gate["status"],
        [(row["code"], row["message"]) for row in gate["issues"]],
        report["status"],
    )


def _blocked(message: str) -> tuple[str, list[tuple[str, str]], str]:
    """Describe an upstream gate blocked by one source diagnostic, with no PASS."""
    return "BLOCKED", [("verification.source.invalid", message)], "FAIL"


def _rewrite_contract(root: Path, edit) -> None:
    """Edit the current contract after its review, leaving the review chain untouched."""
    path = root / CONTRACT_PATH
    contract = json.loads(path.read_text(encoding="utf-8"))
    edit(contract["requirements"])
    path.write_bytes(encode(contract))


def test_edited_contract_blocks_upstream_requirements(tmp_path: Path) -> None:
    write_review_link(tmp_path, review_request())
    _rewrite_contract(tmp_path, lambda requirements: requirements["bindings"].pop())

    assert _upstream_gate(tmp_path) == _blocked(f"input.stale: {CONTRACT_PATH}")


RATIONALE = "Owned by the upstream acceptance."
FR_WITHOUT_AC = SPEC_TEXT.replace(
    "## Acceptance Criteria", "- **FR-003**: Keep an export log.\n## Acceptance Criteria"
)
# Cases (a) to (e) of AC-005; a callable builds the predecessors its case needs.
INVALID_DELEGATION_CASES: dict[str, ReviewRequest | Callable[[Path], ReviewRequest]] = {
    "unknown id": unknown_delegation_request(),
    "retired feature id": retired_feature_delegation_request,
    "duplicate id": invalid_delegation_request([*default_delegations(), default_delegations()[1]]),
    "also bound": invalid_delegation_request(default_delegations()[1:], bound=BOUND + DELEGABLE),
    "FR without AC reference": invalid_delegation_request(
        [*default_delegations(), delegation("FR-003", RATIONALE)], spec=FR_WITHOUT_AC
    ),
    "empty array": invalid_delegation_request([]),
    "not an array": invalid_delegation_request(default_delegations()[0]),
    "additional key": invalid_delegation_request(
        [{**default_delegations()[0], "certified": False}, default_delegations()[1]]
    ),
}


# @spec AC-005: Invalid delegations fail projection — .specs/features/082-reviewed-requirement-delegation-to-upstream-acceptance/spec.md#ac-005
def test_invalid_delegation_blocks_upstream_requirements(tmp_path: Path) -> None:
    observed = {}
    for label, case in INVALID_DELEGATION_CASES.items():
        root = tmp_path / label.replace(" ", "-")
        write_review_link(root, case(root) if callable(case) else case)
        observed[label] = _upstream_gate(root)
    assert observed == dict.fromkeys(
        INVALID_DELEGATION_CASES, _blocked("requirements.delegation.invalid")
    )


def _brainstorm_outcomes(tmp_path: Path) -> dict:
    """Load Brainstorm workspaces whose contract carries a valid or malformed delegations key."""
    observed: dict[str, object] = {}
    for label, malformed in (("brainstorm valid", False), ("brainstorm malformed", True)):
        consumer = _copy_consumer(BRAINSTORM_FIXTURE, tmp_path / label.replace(" ", "-"))
        contract = json.loads((consumer / BRAINSTORM_CONTRACT).read_text(encoding="utf-8"))
        bound = contract["requirements"]["bindings"][0]["requirement_id"]
        contract["requirements"]["delegations"] = (
            [] if malformed else [{**delegation("AC-001", RATIONALE), "requirement_id": bound}]
        )
        (consumer / BRAINSTORM_CONTRACT).write_bytes(encode(contract))
        observed[label] = _upstream_gate(consumer, BRAINSTORM_WORKSPACE)
    untouched = _copy_consumer(BRAINSTORM_FIXTURE, tmp_path / "brainstorm-untouched")
    loaded = load_brainstorm_requirements(InputReader(untouched), untouched / BRAINSTORM_WORKSPACE)
    observed["brainstorm projection keys"] = "delegated" in loaded["projection"]
    return observed


def _projected(inherited: InheritedAuthority, requirements: dict) -> dict | str:
    """Project a LiveSpec contract that inherits the Brainstorm authority, or return the code."""
    contract = {**inherited.contract, "requirements": requirements}
    try:
        return project_requirements(InputReader(inherited.root), inherited.snapshot, contract)
    except VerificationInputError as error:
        return str(error)


def _inherited_outcomes(tmp_path: Path) -> dict:
    """Delegate an unbound and a bound inherited duty, then two native requirements."""
    inherited = write_inherited_authority(tmp_path / "inherited", BRAINSTORM_FIXTURE)
    declared = inherited.contract["requirements"]
    duty = inherited.inherited_ids[0]
    record = {**delegation("AC-001", RATIONALE), "requirement_id": duty}
    unbound = [row for row in declared["bindings"] if row["requirement_id"] != duty]
    native = _projected(inherited, {**declared, "delegations": default_delegations()})
    reference = json.loads((inherited.root / POLICY_SOURCE_PATH).read_text(encoding="utf-8"))
    imported = inherited_projection(
        InputReader(inherited.root), reference["inherited_authority"], inherited.contract
    )
    refused = {
        "inherited unbound": {**declared, "bindings": unbound, "delegations": [record]},
        "inherited bound": {**declared, "delegations": [record]},
    }
    return {
        **{
            label: outcome
            if isinstance(outcome := _projected(inherited, value), str)
            else "projected"
            for label, value in refused.items()
        },
        "native delegated": native.get("delegated") if isinstance(native, dict) else native,
        "native uncovered": native["uncovered"] if isinstance(native, dict) else native,
        "inherited projection keys": "delegated" in imported,
    }


# @spec AC-006: Brainstorm and inherited duties stay bound — .specs/features/082-reviewed-requirement-delegation-to-upstream-acceptance/spec.md#ac-006
def test_brainstorm_and_inherited_duties_cannot_be_delegated(tmp_path: Path) -> None:
    observed = {**_brainstorm_outcomes(tmp_path), **_inherited_outcomes(tmp_path)}
    forbidden = _blocked("product.delegation.forbidden")
    assert observed == {
        "brainstorm valid": forbidden,
        "brainstorm malformed": forbidden,
        "brainstorm projection keys": False,
        "inherited unbound": "authority.import.requirements_uncovered",
        "inherited bound": "requirements.delegation.invalid",
        "native delegated": sorted(default_delegations(), key=lambda row: row["requirement_id"]),
        "native uncovered": [],
        "inherited projection keys": False,
    }


def _reworded(projection: dict) -> dict:
    """Return the projection with the rationale of its first delegated record changed."""
    first, *others = projection["delegated"]
    return {**projection, "delegated": [{**first, "rationale": "Reworded."}, *others]}


def _stale_contract_cases() -> dict:
    """Edit the current contract after review: one record added, removed or reworded."""
    extra = delegation("AC-002", RATIONALE)
    return {
        "delegation added": (None, lambda rows: rows.update(delegations=[extra])),
        "delegation removed": (default_delegations(), lambda rows: rows["delegations"].pop()),
        "delegation edited": (
            default_delegations(),
            lambda rows: rows["delegations"][0].update(rationale="Reworded."),
        ),
    }


def _weakened_chain_cases(reference: dict) -> dict:
    """Deviate one stored projection fact from the reviewed contract of a delegated chain."""
    return {
        "baseline projection edited": (
            ChainOverrides(baseline_projection=_reworded),
            "approval.envelope.identity_mismatch",
        ),
        "snapshot projection differs": (
            ChainOverrides(reviewed_projection=_reworded),
            "approval.history.projection_changed",
        ),
        "projection digest differs": (
            ChainOverrides(projection_sha256=digest(canonical_bytes(_reworded(reference)))),
            "approval.history.projection_changed",
        ),
    }


# @spec AC-007: Unreviewed delegation changes fail closed — .specs/features/082-reviewed-requirement-delegation-to-upstream-acceptance/spec.md#ac-007
def test_unreviewed_delegation_change_blocks_upstream_requirements(tmp_path: Path) -> None:
    observed = {}
    expected = {}
    for label, (delegations, edit) in _stale_contract_cases().items():
        root = tmp_path / label.replace(" ", "-")
        write_review_link(root, review_request(delegations=delegations))
        _rewrite_contract(root, edit)
        observed[label] = _upstream_gate(root)
        expected[label] = _blocked(f"input.stale: {CONTRACT_PATH}")
    reviewed = review_request(delegations=default_delegations())
    reference = write_review_link(tmp_path / "reference", reviewed).projection
    for label, (overrides, code) in _weakened_chain_cases(reference).items():
        root = tmp_path / label.replace(" ", "-")
        write_review_link(root, replace(reviewed, overrides=overrides))
        observed[label] = _upstream_gate(root)
        expected[label] = _blocked(code)
    assert observed == expected
