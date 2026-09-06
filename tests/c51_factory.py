"""Official C20 outcome fixture for protocol tests; never native/runtime certification."""

from copy import deepcopy

from penflow.verification_assertions import resolve_pointer
from penflow.verification_obligations import derive_obligations
from penflow.verification_expectations import guard_predicate
from tests.contract_factory import valid_contract


def outcome_contract(base: dict | None = None) -> dict:
    """Build a complete checkout example with explicit actors and intended outcomes."""
    contract = deepcopy(base) if base is not None else valid_contract()
    contract["actors"].append({"id": "visitor", "name": "Visitor"})
    contract["guards"].append(
        {
            "id": "payment_input_valid",
            "variable": "payment_input",
            "operator": "equals",
            "value": "valid",
            "source": "user_input",
        }
    )
    contract["actions"][0]["guard"] = "payment_input_valid"
    expectations = []
    for slot in derive_obligations(contract):
        source = resolve_pointer(contract, slot.source_pointer)
        capability = "network" if slot.category == "effect" else "ui"
        values = {}
        if slot.category == "structure":
            values = (
                {"/after/semantic_id": source["semantic_id"], "/after/role": source["role"]}
                if "semantic_id" in source
                else {"/after/state": source["id"]}
            )
            if isinstance(source.get("text"), str):
                values["/after/text"] = source["text"]
        else:
            values = {
                "/result/actor_id": "visitor" if slot.outcome == "denied" else "buyer",
                "/result/action_id": slot.action_id,
                "/result/outcome": slot.outcome
                or source.get("causal", {}).get("outcome", "success"),
            }
        if slot.category == "transition" and slot.source_pointer.startswith("/system_returns/"):
            values.update(
                {
                    "/before/visible": True,
                    "/after/visible": source["destination"]["kind"] != "closed",
                }
            )
            if source["destination"]["kind"] == "screen":
                values.update(
                    {
                        "/after/screen_id": source["destination"]["screen_id"],
                        "/after/state": source["destination"]["state"],
                    }
                )
        elif slot.category == "transition":
            values.update(
                {
                    "/before/screen_id": source["from_screen"],
                    "/before/state": source["from_state"],
                    "/after/screen_id": source["to_screen"],
                    "/after/state": source["to_state"],
                }
            )
        elif slot.category == "effect":
            values.update(
                {
                    "/before/method": source["method"],
                    "/before/url": source["endpoint"],
                    "/after/status": 201 if slot.outcome == "success" else 500,
                }
            )
        elif slot.category == "result":
            values["/after/state"] = source[f"{slot.outcome}_state"]
        assertions = _equalities(capability, values)
        expectations.append(
            {
                "obligation_id": slot.id,
                "source_pointer": slot.source_pointer,
                "category": slot.category,
                "assertions": assertions,
            }
        )
        if slot.category == "validation":
            predicate = guard_predicate(source, allowed=slot.outcome == "allowed")
            assert predicate is not None
            assertions.append(predicate)
    expectations.append(persistence_expectation())
    contract["outcome_expectations"] = expectations
    return contract


def persistence_expectation() -> dict:
    """Specify durable payment state, without claiming any observation occurred."""
    return {
        "obligation_id": "persist-payment",
        "source_pointer": "/mutations/0",
        "category": "persistence",
        "assertions": _equalities(
            "storage",
            {
                "/result/actor_id": "buyer",
                "/result/action_id": "submit_payment",
                "/result/outcome": "success",
                "/after/key": "payment-1",
                "/after/store_id": "payments",
                "/after/exists": True,
                "/after/value": {"amount": 10, "status": "paid"},
            },
        ),
    }


def persistence_observation() -> dict:
    """Return typed synthetic facts for pure validator tests, with distinct process IDs."""
    after = {
        "store_id": "payments",
        "key": "payment-1",
        "exists": True,
        "value": {"amount": 10, "status": "paid"},
        "process_instance": "101",
    }
    return {
        "kind": "penflow-outcome-observation",
        "version": 1,
        "contract_sha256": "a" * 64,
        "build_id": "build-test",
        "producer_invocation_id": "producer-test",
        "scenario_id": "save",
        "session_id": "session-test",
        "obligation_id": "persist-payment",
        "screen_id": "checkout",
        "semantic_id": "checkout.pay",
        "instance_key": None,
        "category": "persistence",
        "capability": "storage",
        "before": {**after, "exists": False, "value": None},
        "after": deepcopy(after),
        "result": {
            "actor_id": "buyer",
            "action_id": "submit_payment",
            "outcome": "success",
            "readback": {**deepcopy(after), "process_instance": "102"},
            "restart": {"before_process": "101", "after_process": "102"},
        },
        "evidence": {"path": "evidence/readback.json", "sha256": "b" * 64},
    }


def _equalities(capability: str, values: dict) -> list[dict]:
    return [
        {"operator": "equals", "pointer": pointer, "expected": value, "capability": capability}
        for pointer, value in values.items()
    ]
