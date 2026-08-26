<!-- Generated from contract.json; do not edit. -->
<!-- @spec(FR-011) -->

# Flow: checkout

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
  "flow": {
    "entry_screen": "checkout",
    "id": "checkout"
  },
  "relations": [],
  "screens": [
    {
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
  ],
  "transitions": [
    {
      "action": "submit_payment",
      "flow": "checkout",
      "from_screen": "checkout",
      "from_state": "default",
      "id": "payment_error",
      "to_screen": "checkout",
      "to_state": "error",
      "trigger": "submit_payment"
    },
    {
      "action": "submit_payment",
      "flow": "checkout",
      "from_screen": "checkout",
      "from_state": "default",
      "id": "payment_success",
      "to_screen": "checkout",
      "to_state": "submitting",
      "trigger": "submit_payment"
    }
  ]
}
```
