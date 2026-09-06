"""Fresh canonical checkout contract factory shared by behavioral tests."""


def _actors_0() -> dict:
    return {"id": "buyer", "name": "Buyer"}


def _entities_0() -> dict:
    return {
        "id": "checkout",
        "fields": [{"id": "title", "type": "string"}, {"id": "payment_method", "type": "string"}],
    }


def _screens_0() -> dict:
    return {
        "id": "checkout",
        "flow_id": "checkout",
        "title": "Checkout",
        "surface": "web-desktop",
        "viewport": {"width": 1440, "height": 900},
        "states": [{"id": "default"}, {"id": "success"}, {"id": "error"}],
        "root_node": "checkout.root",
    }


def _nodes_0() -> dict:
    return {
        "id": "checkout.root",
        "screen_id": "checkout",
        "semantic_id": "checkout",
        "test_id": "checkout-screen",
        "role": "screen",
        "children": ["checkout.title", "checkout.pay"],
    }


def _nodes_1() -> dict:
    return {
        "id": "checkout.title",
        "screen_id": "checkout",
        "semantic_id": "checkout.title",
        "role": "text",
        "text": "Checkout",
        "binding": "checkout.title",
    }


def _nodes_2() -> dict:
    return {
        "id": "checkout.pay",
        "screen_id": "checkout",
        "semantic_id": "checkout.pay",
        "test_id": "checkout-pay",
        "role": "button",
        "text": "Pay",
        "binding": "checkout.payment_method",
        "entity": "checkout",
        "action": "submit_payment",
    }


def _guards_0() -> dict:
    return {
        "id": "payment_ready",
        "variable": "payment_result",
        "operator": "equals",
        "value": "success",
        "source": "runtime_result",
    }


def _guards_1() -> dict:
    return {
        "id": "payment_failed",
        "variable": "payment_result",
        "operator": "equals",
        "value": "error",
        "source": "runtime_result",
    }


def _permissions_0() -> dict:
    return {
        "id": "buyer_can_pay",
        "actor": "buyer",
        "action": "submit_payment",
        "entity": "checkout",
    }


def _mutations_0() -> dict:
    return {
        "id": "create_payment",
        "method": "POST",
        "endpoint": "/payments",
        "entity": "checkout",
        "request": {},
        "response": {},
        "success_state": "success",
        "error_state": "error",
    }


def _actions_0() -> dict:
    return {
        "id": "submit_payment",
        "node": "checkout.pay",
        "trigger": "click",
        "guard": "payment_ready",
        "permission": "buyer_can_pay",
        "mutation": "create_payment",
        "success_transition": "payment_success",
        "error_transition": "payment_error",
    }


def _flows_0() -> dict:
    return {"id": "checkout", "entry_screen": "checkout"}


def _transitions_0() -> dict:
    return {
        "id": "payment_success",
        "flow": "checkout",
        "from_screen": "checkout",
        "to_screen": "checkout",
        "from_state": "default",
        "to_state": "success",
        "trigger": "submit_payment",
        "action": "submit_payment",
        "guard": "payment_ready",
        "kind": "state",
        "label": "Payment succeeds",
        "causal": {
            "version": 1,
            "action_visibility": "user-visible",
            "outcome": "success",
            "fanout": {"group": "payment_result", "policy": "exclusive"},
        },
    }


def _transitions_1() -> dict:
    return {
        "id": "payment_error",
        "flow": "checkout",
        "from_screen": "checkout",
        "to_screen": "checkout",
        "from_state": "default",
        "to_state": "error",
        "trigger": "submit_payment",
        "action": "submit_payment",
        "guard": "payment_failed",
        "kind": "state",
        "label": "Payment fails",
        "causal": {
            "version": 1,
            "action_visibility": "user-visible",
            "outcome": "error",
            "fanout": {"group": "payment_result", "policy": "exclusive"},
        },
    }


def valid_contract() -> dict:
    """Return independent mutable contract data for each test."""
    return {
        "version": 2,
        "kind": "penflow-flow-contract",
        "contract_id": "checkout-contract",
        "actors": [_actors_0()],
        "entities": [_entities_0()],
        "screens": [_screens_0()],
        "nodes": [_nodes_0(), _nodes_1(), _nodes_2()],
        "guards": [_guards_0(), _guards_1()],
        "permissions": [_permissions_0()],
        "mutations": [_mutations_0()],
        "actions": [_actions_0()],
        "flows": [_flows_0()],
        "transitions": [_transitions_0(), _transitions_1()],
        "needs_review": False,
        "needs_clarification": [],
    }
