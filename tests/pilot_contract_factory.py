"""Exact source contract for the isolated checkout/browser/SQLite test application."""

from copy import deepcopy

from tests.c51_factory import outcome_contract
from tests.contract_factory import valid_contract


def pilot_contract(navigation_sources: list[dict]) -> dict:
    """Build the three real pilot surfaces, using caller-authored requirement records."""
    if len(navigation_sources) != 2:
        raise ValueError("back and close require two actual approved-source definition records")
    base = valid_contract()
    base["entities"][0]["fields"].extend(
        [{"id": "amount", "type": "number"}, {"id": "result", "type": "string"}]
    )
    base["nodes"][0]["children"] = [
        "checkout.title",
        "checkout.amount",
        "checkout.pay",
        "checkout.result",
    ]
    base["nodes"].extend(
        [
            {
                "id": "checkout.amount",
                "semantic_id": "checkout.amount",
                "test_id": "checkout-amount",
                "screen_id": "checkout",
                "role": "input",
                "binding": "checkout.amount",
                "entity": "checkout",
                "action": "edit_amount",
            },
            {
                "id": "checkout.result",
                "semantic_id": "checkout.result",
                "screen_id": "checkout",
                "role": "text",
                "text": "Ready",
                "binding": "checkout.result",
                "entity": "checkout",
                "states": ["default"],
            },
        ]
    )
    base["actions"].append(
        {
            "id": "edit_amount",
            "node": "checkout.amount",
            "trigger": "input",
            "kind": "state_change",
            "event": "change",
            "binding_ref": {"entity": "checkout", "field": "amount", "access": "write"},
        }
    )
    for screen_id, title in (("details", "Payment details"), ("receipt", "Payment receipt")):
        base["screens"].append(
            {
                "id": screen_id,
                "flow_id": "checkout",
                "title": title,
                "surface": "web-desktop",
                "viewport": {"width": 1440, "height": 900},
                "states": [{"id": "default"}],
                "root_node": screen_id + ".root",
                "static": True,
                "static_reason": "Read-only auxiliary page; navigation uses the browser's real system controls.",
            }
        )
        base["nodes"].extend(
            [
                {
                    "id": screen_id + ".root",
                    "semantic_id": screen_id,
                    "screen_id": screen_id,
                    "role": "screen",
                    "children": [screen_id + ".title"],
                },
                {
                    "id": screen_id + ".title",
                    "semantic_id": screen_id + ".title",
                    "screen_id": screen_id,
                    "role": "text",
                    "text": title,
                },
            ]
        )
    base["system_returns"] = [
        {
            "id": "details_back",
            "screen_id": "details",
            "event": "back",
            "source": deepcopy(navigation_sources[0]),
            "destination": {"kind": "history"},
        },
        {
            "id": "receipt_close",
            "screen_id": "receipt",
            "event": "close",
            "source": deepcopy(navigation_sources[1]),
            "destination": {"kind": "closed"},
        },
    ]
    contract = outcome_contract(base)
    for expected in contract["outcome_expectations"]:
        if expected["obligation_id"] == "system-return:details_back":
            expected["assertions"].append(
                {
                    "operator": "equals",
                    "pointer": "/after/screen_id",
                    "expected": "checkout",
                    "capability": "ui",
                }
            )
        if expected["obligation_id"] == "action:edit_amount:allowed":
            expected["assertions"].append(
                {
                    "operator": "equals",
                    "pointer": "/after/value",
                    "expected": 10,
                    "capability": "ui",
                }
            )
        if expected["category"] == "result":
            outcome = next(
                item["expected"]
                for item in expected["assertions"]
                if item["pointer"] == "/result/outcome"
            )
            expected["assertions"].extend(
                [
                    {
                        "operator": "equals",
                        "pointer": "/after/semantic_id",
                        "expected": "checkout.result",
                        "capability": "ui",
                    },
                    {
                        "operator": "equals",
                        "pointer": "/after/text",
                        "expected": outcome,
                        "capability": "ui",
                    },
                ]
            )
    idempotent = deepcopy(
        next(item for item in contract["outcome_expectations"] if item["category"] == "persistence")
    )
    idempotent["obligation_id"] = "persist-payment-idempotent"
    for assertion in idempotent["assertions"]:
        if assertion["pointer"] == "/result/outcome":
            assertion["expected"] = "idempotent"
    contract["outcome_expectations"].append(idempotent)
    return contract
