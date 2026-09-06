"""Expected-value predicates and typed outcome evidence, including omission attacks."""

import pytest

from penflow.verification_assertions import evaluate_assertion, wildcard_matches
from penflow.verification_obligations import derive_obligations
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
