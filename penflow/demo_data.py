# @spec(FR-011)
"""Package-owned synthetic checkout inputs; each generation receives fresh data."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

FLOW_CONTRACT = {
    "version": 2,
    "kind": "penflow-flow-contract",
    "contract_id": "checkout-contract",
    "actors": [{"id": "buyer", "name": "Buyer"}],
    "entities": [
        {
            "id": "checkout",
            "fields": [
                {"id": "order_summary", "type": "string"},
                {"id": "selected_payment_method", "type": "string"},
            ],
        }
    ],
    "screens": [
        {
            "id": "checkout",
            "flow_id": "checkout",
            "title": "Checkout",
            "surface": "web",
            "viewport": {"width": 390, "height": 844},
            "states": [{"id": "default"}, {"id": "submitting"}, {"id": "error"}],
            "root_node": "checkout.root",
        }
    ],
    "nodes": [
        {
            "id": "checkout.root",
            "screen_id": "checkout",
            "semantic_id": "checkout",
            "test_id": "checkout-screen",
            "role": "screen",
            "children": [
                "checkout.order_summary",
                "checkout.selected_payment_method",
                "checkout.pay_now",
            ],
        },
        {
            "id": "checkout.order_summary",
            "screen_id": "checkout",
            "semantic_id": "checkout.order-summary",
            "test_id": "checkout-order-summary",
            "role": "text",
            "text": "Order summary",
            "binding": "checkout.order_summary",
        },
        {
            "id": "checkout.selected_payment_method",
            "screen_id": "checkout",
            "semantic_id": "checkout.selected-payment-method",
            "test_id": "checkout-selected-payment-method",
            "role": "text",
            "text": "Selected payment method",
            "binding": "checkout.selected_payment_method",
        },
        {
            "id": "checkout.pay_now",
            "screen_id": "checkout",
            "semantic_id": "checkout.pay-now",
            "test_id": "checkout-pay-now",
            "role": "button",
            "text": "Pay now",
            "binding": "checkout.selected_payment_method",
            "entity": "checkout",
            "action": "submit_payment",
        },
    ],
    "guards": [{"id": "payment_ready"}],
    "permissions": [
        {"id": "buyer_can_pay", "actor": "buyer", "action": "submit_payment", "entity": "checkout"}
    ],
    "mutations": [
        {
            "id": "create_payment",
            "method": "POST",
            "endpoint": "/payments",
            "entity": "checkout",
            "request": {},
            "response": {},
            "success_state": "submitting",
            "error_state": "error",
        }
    ],
    "actions": [
        {
            "id": "submit_payment",
            "node": "checkout.pay_now",
            "trigger": "click",
            "guard": "payment_ready",
            "permission": "buyer_can_pay",
            "mutation": "create_payment",
            "success_transition": "payment_success",
            "error_transition": "payment_error",
        }
    ],
    "flows": [{"id": "checkout", "entry_screen": "checkout"}],
    "transitions": [
        {
            "id": "payment_success",
            "flow": "checkout",
            "from_screen": "checkout",
            "to_screen": "checkout",
            "from_state": "default",
            "to_state": "submitting",
            "trigger": "submit_payment",
            "action": "submit_payment",
        },
        {
            "id": "payment_error",
            "flow": "checkout",
            "from_screen": "checkout",
            "to_screen": "checkout",
            "from_state": "default",
            "to_state": "error",
            "trigger": "submit_payment",
            "action": "submit_payment",
        },
    ],
    "needs_review": False,
    "needs_clarification": [],
}

VISUAL_PEN = {
    "version": "2.11",
    "children": [
        {
            "id": "checkoutScreen",
            "type": "frame",
            "name": "checkout",
            "x": 0,
            "y": 0,
            "width": 390,
            "height": 844,
            "layout": "vertical",
            "gap": 16,
            "padding": 24,
            "alignItems": "stretch",
            "fill": "#FFFFFF",
            "context": "classification=semantic; role=screen; semantic_id=checkout; test_id=checkout-screen",
            "penflow": {
                "lifecycle": {
                    "schema_version": 1,
                    "state": "active",
                    "logical_screen_id": "checkout",
                    "revision_id": "checkout-r1",
                }
            },
            "children": [
                {
                    "id": "orderSummary",
                    "type": "text",
                    "name": "Order summary",
                    "content": "Order summary",
                    "textGrowth": "fixed-width",
                    "width": "fill_container",
                    "fontSize": 24,
                    "fontWeight": "600",
                    "fill": "#111827",
                    "context": "classification=semantic; semantic_id=checkout.order-summary; test_id=checkout-order-summary; role=text; variant=heading",
                },
                {
                    "id": "selectedPaymentMethod",
                    "type": "text",
                    "name": "Selected payment method",
                    "content": "Selected payment method",
                    "textGrowth": "fixed-width",
                    "width": "fill_container",
                    "fontSize": 16,
                    "fontWeight": "400",
                    "fill": "#374151",
                    "context": "classification=semantic; semantic_id=checkout.selected-payment-method; test_id=checkout-selected-payment-method; role=text; variant=body",
                },
                {
                    "id": "payNowButton",
                    "type": "frame",
                    "name": "Pay now",
                    "layout": "horizontal",
                    "width": "fill_container",
                    "height": "fit_content(44)",
                    "padding": [12, 16],
                    "gap": 8,
                    "alignItems": "center",
                    "justifyContent": "center",
                    "cornerRadius": 8,
                    "fill": "#0057FF",
                    "context": "classification=semantic; semantic_id=checkout.pay-now; test_id=checkout-pay-now; role=button; intent=submit_payment",
                    "children": [
                        {
                            "id": "payNowLabel",
                            "type": "text",
                            "content": "Pay now",
                            "fontSize": 16,
                            "fontWeight": "600",
                            "fill": "#FFFFFF",
                            "context": "classification=inherited; inherits_from=checkout.pay-now; relation=content; variant=label",
                        }
                    ],
                },
            ],
        }
    ],
}


def flow_contract() -> dict[str, Any]:
    """Return a fresh copy of the historical checkout contract fixture."""
    return deepcopy(FLOW_CONTRACT)


def visual_pen() -> dict[str, Any]:
    """Return a fresh copy of the historical Pencil fixture."""
    return deepcopy(VISUAL_PEN)
