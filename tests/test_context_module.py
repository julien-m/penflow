"""Feature 054 — direct unit coverage for `penflow/context.py`.

Invariant protected: the Pencil context grammar is a closed contract —
`key=value; key=value` strings parse deterministically, formatting is the
sorted inverse, unknown keys are quarantined in `extra`, and every
`validate_context` rule (semantic_id format, button intent, list repeat,
binding syntax, platform coupling) has a stable code and severity.
"""

from __future__ import annotations

from penflow.context import (
    Context,
    ContextIssue,
    format_context_string,
    infer_role,
    parse_context_string,
    validate_context,
)


def codes(issues: list[ContextIssue]) -> list[str]:
    return [issue.code for issue in issues]


# --- parse_context_string -------------------------------------------------


def test_parse_context_string_splits_key_values_and_flags() -> None:
    parsed = parse_context_string("semantic_id=checkout.pay; role=button; mask")
    assert parsed == {"semantic_id": "checkout.pay", "role": "button", "mask": True}


def test_parse_context_string_accepts_newline_separators_and_whitespace() -> None:
    parsed = parse_context_string("  role = button \n intent= submit_payment ;; ")
    assert parsed == {"role": "button", "intent": "submit_payment"}


def test_parse_context_string_keeps_equals_in_value() -> None:
    assert parse_context_string("binding=a.b=c") == {"binding": "a.b=c"}


def test_parse_context_string_empty_string_yields_empty_dict() -> None:
    assert parse_context_string("") == {}


# --- format_context_string ------------------------------------------------


def test_format_context_string_sorts_keys_and_renders_flags() -> None:
    formatted = format_context_string(
        {"role": "button", "mask": True, "mask_text": False, "intent": "submit"}
    )
    assert formatted == "intent=submit; mask; mask_text=false; role=button"


def test_format_context_string_flattens_nested_dicts() -> None:
    formatted = format_context_string({"tolerance": {"bbox_px": 8, "spacing_px": 2}})
    assert formatted == "tolerance.bbox_px=8; tolerance.spacing_px=2"


def test_format_context_string_skips_none_and_empty_values() -> None:
    assert format_context_string({"role": None, "intent": "", "entity": "order"}) == "entity=order"


def test_parse_format_round_trip() -> None:
    original = "intent=submit_payment; role=button; semantic_id=checkout.pay"
    assert format_context_string(parse_context_string(original)) == original


# --- Context.from_raw / to_dict --------------------------------------------


def test_from_raw_none_returns_empty_context() -> None:
    context = Context.from_raw(None)
    assert context.to_dict() == {}


def test_from_raw_parses_string_shorthand() -> None:
    context = Context.from_raw("semantic_id=checkout.pay; role=button; intent=submit_payment")
    assert context.semantic_id == "checkout.pay"
    assert context.role == "button"
    assert context.intent == "submit_payment"


def test_from_raw_non_dict_payload_is_quarantined_in_extra() -> None:
    context = Context.from_raw([1, 2, 3])
    assert context.extra == {"_invalid_raw": [1, 2, 3]}
    assert context.semantic_id is None


def test_from_raw_unknown_keys_go_to_extra() -> None:
    context = Context.from_raw({"role": "text", "swift_view": "TitleView"})
    assert context.role == "text"
    assert context.extra == {"swift_view": "TitleView"}


def test_from_raw_invalid_tolerance_is_quarantined() -> None:
    context = Context.from_raw({"tolerance": "loose"})
    assert context.tolerance == {}
    assert context.extra == {"_invalid_tolerance": "loose"}


def test_to_dict_emits_sorted_known_keys_and_tolerance() -> None:
    context = Context.from_raw(
        {"semantic_id": "checkout.pay", "role": "button", "tolerance": {"bbox_px": 8}}
    )
    assert context.to_dict() == {
        "role": "button",
        "semantic_id": "checkout.pay",
        "tolerance": {"bbox_px": 8},
    }


# --- infer_role -------------------------------------------------------------


def test_infer_role_prefers_context_role_over_type_alias() -> None:
    assert infer_role("frame", Context(role="button")) == "button"


def test_infer_role_aliases_pencil_types() -> None:
    assert infer_role("frame", Context()) == "container"
    assert infer_role("icon_font", Context()) == "icon"
    assert infer_role("rectangle", Context()) == "shape"
    assert infer_role("ref", Context()) == "component"
    assert infer_role("mystery", Context()) == "mystery"


# --- validate_context -------------------------------------------------------


def test_valid_button_context_has_no_issues() -> None:
    context = Context.from_raw(
        {"semantic_id": "checkout.pay", "role": "button", "intent": "submit_payment"}
    )
    assert validate_context("pay", "frame", context) == []


def test_extra_keys_produce_warning() -> None:
    context = Context.from_raw({"role": "text", "unknown_a": 1, "unknown_b": 2})
    [issue] = validate_context("n", "text", context)
    assert issue.code == "context.extra_keys"
    assert issue.severity == "warning"
    assert "unknown_a, unknown_b" in issue.message


def test_semantic_id_format_is_enforced() -> None:
    context = Context.from_raw({"semantic_id": "Checkout.Pay", "role": "text"})
    assert "context.semantic_id_format" in codes(validate_context("n", "text", context))
    valid = Context.from_raw({"semantic_id": "checkout.pay-now_v2", "role": "text"})
    assert validate_context("n", "text", valid) == []


def test_button_requires_intent() -> None:
    context = Context.from_raw({"semantic_id": "checkout.pay", "role": "button"})
    [issue] = validate_context("pay", "frame", context)
    assert issue.code == "context.button_intent_missing"
    assert issue.severity == "error"


def test_list_roles_require_repeat() -> None:
    for role in ("list", "list_item"):
        context = Context.from_raw({"semantic_id": "orders", "role": role})
        assert "context.list_repeat_missing" in codes(validate_context("n", "frame", context))
    with_repeat = Context.from_raw({"semantic_id": "orders", "role": "list", "repeat": "order"})
    assert validate_context("n", "frame", with_repeat) == []


def test_binding_must_use_entity_field_syntax() -> None:
    bad = Context.from_raw({"semantic_id": "total", "role": "text", "binding": "totalAmount"})
    assert "context.binding_format" in codes(validate_context("n", "text", bad))
    good = Context.from_raw({"semantic_id": "total", "role": "text", "binding": "order.total"})
    assert validate_context("n", "text", good) == []


def test_platform_words_are_rejected_in_context_values() -> None:
    context = Context.from_raw({"semantic_id": "title", "role": "text", "variant": "SwiftUI-bold"})
    [issue] = validate_context("n", "text", context)
    assert issue.code == "context.platform_coupling"
    assert "swiftui" in issue.message
