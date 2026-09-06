"""Derive the mandatory denominator from C20 records before looking at evidence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .flow_contract import validate_flow_contract_v2
from .contract_actions import action_mode


@dataclass(frozen=True)
class ObligationSlot:
    """One source-derived responsibility, independent of authored observation IDs."""

    id: str
    category: str
    source_pointer: str
    outcome: str | None = None
    action_id: str | None = None
    node_id: str | None = None


# @spec FR-003: complete obligation denominator — .specs/features/077-complete-verification-workflow/spec.md#fr-003
def derive_obligations(
    contract: dict[str, Any], *, approved_expectations: tuple[dict[str, Any], ...] = ()
) -> list[ObligationSlot]:
    """Enumerate structural and functional duties from a fully valid C20 contract.

    Neither outcome expectations nor optional causal metadata control cardinality.
    Invalid source contracts are rejected before their records can be indexed.
    """
    issues = validate_flow_contract_v2(contract)
    if any(issue["severity"] == "error" for issue in issues):
        raise ValueError(f"cannot derive obligations from invalid C20 contract: {issues[:3]}")
    slots = [
        ObligationSlot(
            f"node:{node['semantic_id']}", "structure", f"/nodes/{index}", node_id=node["id"]
        )
        for index, node in enumerate(contract["nodes"])
    ]
    for index, screen in enumerate(contract["screens"]):
        for state_index, state in enumerate(screen["states"]):
            slots.append(
                ObligationSlot(
                    f"state:{screen['id']}:{state['id']}",
                    "structure",
                    f"/screens/{index}/states/{state_index}",
                    node_id=screen["root_node"],
                )
            )
    slots.extend(_functional_slots(contract))
    roots = {screen["id"]: screen["root_node"] for screen in contract["screens"]}
    slots.extend(
        ObligationSlot(
            f"system-return:{item['id']}",
            "transition",
            f"/system_returns/{index}",
            "success",
            item["id"],
            roots[item["screen_id"]],
        )
        for index, item in enumerate(contract.get("system_returns", []))
    )
    _persistence_slots(contract, slots, approved_expectations)
    return slots


def _functional_slots(contract: dict[str, Any]) -> list[ObligationSlot]:
    slots: list[ObligationSlot] = []
    for index, action in enumerate(contract["actions"]):
        slots.append(
            ObligationSlot(
                f"action:{action['id']}:allowed",
                "action",
                f"/actions/{index}",
                "allowed",
                action["id"],
                action["node"],
            )
        )
        if action_mode(action) == "navigation":
            slots.append(
                ObligationSlot(
                    f"navigation:{action['id']}",
                    "transition",
                    f"/actions/{index}",
                    "success",
                    action["id"],
                    action["node"],
                )
            )
    for collection, category, outcomes in (
        ("permissions", "permission", ("allowed", "denied")),
        ("guards", "validation", ("allowed", "invalid")),
        ("mutations", "effect", ("success", "error")),
    ):
        for index, record in enumerate(contract.get(collection, [])):
            actions = _record_actions(contract, collection, record)
            for action in actions:
                for outcome in outcomes:
                    slots.append(
                        ObligationSlot(
                            f"{category}:{record['id']}:{action['id']}:{outcome}",
                            category,
                            f"/{collection}/{index}",
                            outcome,
                            action["id"],
                            action["node"],
                        )
                    )
                if collection == "mutations":
                    slots.extend(_mutation_slots(index, record, action))
    for index, transition in enumerate(contract.get("transitions", [])):
        action_id = transition.get("action") or transition.get("trigger")
        action = next((item for item in contract["actions"] if item["id"] == action_id), None)
        slots.append(
            ObligationSlot(
                f"transition:{transition['id']}",
                "transition",
                f"/transitions/{index}",
                None,
                action_id,
                action["node"] if action else None,
            )
        )
    return slots


def _record_actions(
    contract: dict[str, Any], collection: str, record: dict[str, Any]
) -> list[dict[str, Any]]:
    singular = {"permissions": "permission", "guards": "guard", "mutations": "mutation"}[collection]
    action_ids = {record.get("action")} if collection == "permissions" else set()
    if collection == "guards":
        action_ids.update(
            transition.get("action") or transition.get("trigger")
            for transition in contract.get("transitions", [])
            if transition.get("guard") == record["id"]
        )
    actions = [
        item
        for item in contract["actions"]
        if item.get(singular) == record["id"] or item["id"] in action_ids
    ]
    if not actions and not record.get("unused_allowed"):
        raise ValueError(f"unbound {collection} record cannot disappear: {record['id']}")
    return actions


def _mutation_slots(
    index: int, mutation: dict[str, Any], action: dict[str, Any]
) -> list[ObligationSlot]:
    return [
        ObligationSlot(
            f"{category}:{mutation['id']}:{action['id']}:{outcome}",
            category,
            f"/mutations/{index}",
            outcome,
            action["id"],
            action["node"],
        )
        for category, outcome in (
            ("result", "success"),
            ("result", "error"),
        )
    ]


def _persistence_slots(
    contract: dict[str, Any],
    slots: list[ObligationSlot],
    approved_expectations: tuple[dict[str, Any], ...],
) -> None:
    identities = {slot.id for slot in slots}
    for expected in (*approved_expectations, *contract.get("outcome_expectations", [])):
        if expected["category"] != "persistence" or expected["obligation_id"] in identities:
            continue
        values = {
            item["pointer"]: item["expected"]
            for item in expected["assertions"]
            if item["operator"] == "equals"
        }
        action_id = values.get("/result/action_id")
        action = next((item for item in contract["actions"] if item["id"] == action_id), None)
        slots.append(
            ObligationSlot(
                expected["obligation_id"],
                "persistence",
                expected["source_pointer"],
                values.get("/result/outcome"),
                action_id,
                action["node"] if action else None,
            )
        )
        identities.add(expected["obligation_id"])
