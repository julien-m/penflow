<!-- Generated from contract.json; do not edit. -->
<!-- @spec(FR-011) -->

# Screen: checkout

Generator: `penflow.flow-docs/1`

```json
{
  "actions": [
    {
      "error_transition": "payment_error",
      "guard": "payment_ready",
      "id": "submit_payment",
      "mutation": "create_payment",
      "node": "checkout.pay_now",
      "permission": "buyer_can_pay",
      "success_transition": "payment_success",
      "trigger": "click"
    }
  ],
  "nodes": [
    {
      "binding": "checkout.order_summary",
      "id": "checkout.order_summary",
      "role": "text",
      "screen_id": "checkout",
      "semantic_id": "checkout.order-summary",
      "test_id": "checkout-order-summary",
      "text": "Order summary"
    },
    {
      "action": "submit_payment",
      "binding": "checkout.selected_payment_method",
      "entity": "checkout",
      "id": "checkout.pay_now",
      "role": "button",
      "screen_id": "checkout",
      "semantic_id": "checkout.pay-now",
      "test_id": "checkout-pay-now",
      "text": "Pay now"
    },
    {
      "children": [
        "checkout.order_summary",
        "checkout.selected_payment_method",
        "checkout.pay_now"
      ],
      "id": "checkout.root",
      "role": "screen",
      "screen_id": "checkout",
      "semantic_id": "checkout",
      "test_id": "checkout-screen"
    },
    {
      "binding": "checkout.selected_payment_method",
      "id": "checkout.selected_payment_method",
      "role": "text",
      "screen_id": "checkout",
      "semantic_id": "checkout.selected-payment-method",
      "test_id": "checkout-selected-payment-method",
      "text": "Selected payment method"
    }
  ],
  "relations": [],
  "screen": {
    "flow_id": "checkout",
    "id": "checkout",
    "root_node": "checkout.root",
    "states": [
      {
        "id": "default"
      },
      {
        "id": "submitting"
      },
      {
        "id": "error"
      }
    ],
    "surface": "web",
    "title": "Checkout",
    "viewport": {
      "height": 844,
      "width": 390
    }
  }
}
```
