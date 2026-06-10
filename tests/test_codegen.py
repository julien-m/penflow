# @spec(FR-005)
"""Feature 054 — direct unit coverage for `penflow/codegen.py`.

Invariant protected: the three generators (SwiftUI, React, Dioxus) are pure
deterministic functions of the IR — same IR, same source text — and they
accept both supported IR shapes (legacy feature-018 `screen`+`components` and
contextualized feature-036 `screens[]`) with identical generator output.
"""

from __future__ import annotations

from typing import Any

import pytest

from penflow.codegen import react, rust_dioxus, swiftui


def legacy_ir(**overrides: Any) -> dict[str, Any]:
    ir: dict[str, Any] = {
        "screen": "checkout",
        "components": [
            {"id": "checkout.title", "role": "text", "text": "Checkout"},
            {
                "id": "checkout.pay",
                "role": "button",
                "text": "Pay now",
                "intent": "submit_payment",
                "test_id": "checkout-pay-now",
            },
        ],
    }
    ir.update(overrides)
    return ir


def contextualized_ir() -> dict[str, Any]:
    return {
        "flow": {"id": "checkout"},
        "screens": [
            {
                "id": "checkout",
                "root": {
                    "id": "checkout",
                    "role": "screen",
                    "children": [
                        {"id": "checkout.title", "role": "text", "text": "Checkout"},
                        {
                            "id": "checkout.pay",
                            "role": "button",
                            "text": "Pay now",
                            "intent": "submit_payment",
                            "test_id": "checkout-pay-now",
                        },
                    ],
                },
            }
        ],
    }


@pytest.mark.parametrize("generator", [swiftui, react, rust_dioxus])
def test_generators_are_deterministic_across_reruns(generator: Any) -> None:
    assert generator(legacy_ir()) == generator(legacy_ir())


@pytest.mark.parametrize("generator", [swiftui, react, rust_dioxus])
def test_both_ir_shapes_produce_identical_component_output(generator: Any) -> None:
    assert generator(legacy_ir()) == generator(contextualized_ir())


def test_swiftui_emits_view_struct_with_button_and_text() -> None:
    source = swiftui(legacy_ir())
    assert "struct CheckoutView: View {" in source
    assert 'Text("Checkout")' in source
    assert 'Button("Pay now") {' in source
    assert "// intent: submit_payment" in source
    assert '.accessibilityIdentifier("checkout-pay-now")' in source


def test_react_emits_function_with_penflow_ids_and_testid() -> None:
    source = react(legacy_ir())
    assert "export function Checkout() {" in source
    assert '<main data-penflow-id="checkout">' in source
    assert '<span data-penflow-id="checkout.title">Checkout</span>' in source
    assert 'data-testid="checkout-pay-now"' in source
    assert '<button data-penflow-id="checkout.pay"' in source


def test_rust_dioxus_emits_component_with_penflow_ids() -> None:
    source = rust_dioxus(legacy_ir())
    assert "pub fn Checkout() -> Element {" in source
    assert '"data-penflow-id": "checkout"' in source
    assert 'span { "data-penflow-id": "checkout.title", "Checkout" }' in source
    assert '"data-testid": "checkout-pay-now"' in source


def test_button_without_test_id_omits_test_attribute() -> None:
    ir = legacy_ir(components=[{"id": "go", "role": "button", "text": "Go"}])
    assert "data-testid" not in react(ir)
    assert "accessibilityIdentifier" not in swiftui(ir)
    assert "data-testid" not in rust_dioxus(ir)


def test_button_label_children_render_as_spans() -> None:
    ir = legacy_ir(
        components=[
            {
                "id": "checkout.pay",
                "role": "button",
                "text": "Pay now",
                "children": [{"id": "checkout.pay.label", "role": "text", "text": "Pay now"}],
            }
        ]
    )
    react_source = react(ir)
    assert '<span data-penflow-id="checkout.pay.label">Pay now</span>' in react_source
    rust_source = rust_dioxus(ir)
    assert 'span { "data-penflow-id": "checkout.pay.label", "Pay now" }' in rust_source


def test_quotes_and_backslashes_are_escaped() -> None:
    ir = legacy_ir(components=[{"id": "msg", "role": "text", "text": 'say "hi" \\ bye'}])
    assert 'Text("say \\"hi\\" \\\\ bye")' in swiftui(ir)
    # React inserts the raw text into JSX children (no quoting context),
    # while attribute-position values go through _escape.
    button_ir = legacy_ir(
        components=[{"id": "b", "role": "button", "text": "ok", "test_id": 'a"b'}]
    )
    assert 'data-testid="a\\"b"' in react(button_ir)


def test_non_text_button_components_are_filtered_out() -> None:
    ir = legacy_ir(
        components=[
            {"id": "wrap", "role": "container"},
            "garbage",
            {"id": "checkout.title", "role": "text", "text": "Checkout"},
        ]
    )
    source = react(ir)
    assert "wrap" not in source
    assert "checkout.title" in source


def test_contextualized_ir_button_subtree_is_not_descended() -> None:
    """Button children stay part of the button component, never siblings."""
    source = react(contextualized_ir())
    assert source.count("<button") == 1
    assert source.count("checkout.pay") == 1


def test_pascal_falls_back_to_screen_for_empty_ids() -> None:
    assert "struct ScreenView: View {" in swiftui({"screen": "---", "components": []})
    assert "export function Screen() {" in react({"screen": "", "components": []})


def test_contextualized_ir_without_screens_uses_flow_id_and_global_components() -> None:
    ir = {
        "flow": {"id": "checkout"},
        "screens": [],
        "components": [{"id": "t", "role": "text", "text": "T"}],
    }
    source = react(ir)
    assert '<main data-penflow-id="checkout">' in source
    assert '<span data-penflow-id="t">T</span>' in source
