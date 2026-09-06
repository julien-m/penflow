"""Reconcile authored predicates with the independently derived obligation slots."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .verification_assertions import json_values_equal, resolve_pointer
from .verification_obligations import ObligationSlot, derive_obligations
from .verification_schema import issue, schema_issues
from .contract_actions import action_mode


@dataclass
class ExpectedObligation:
    """One mandatory slot, its optional authored expectation and blocking findings."""

    slot: ObligationSlot
    expected: dict[str, Any] | None
    issues: list[dict[str, Any]]


def reconcile_expectations(
    contract: dict[str, Any], *, approved_expectations: tuple[dict[str, Any], ...] = ()
) -> list[ExpectedObligation]:
    """Keep missing or weakened source duties in the denominator as blocking entries."""
    expectations = contract.get("outcome_expectations", [])
    slots = derive_obligations(contract, approved_expectations=approved_expectations)
    by_source: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for expected in expectations:
        identity = (expected["source_pointer"], expected["category"])
        by_source.setdefault(identity, []).append(expected)
    results: list[ExpectedObligation] = []
    used: set[str] = set()
    for slot in slots:
        candidates = by_source.get((slot.source_pointer, slot.category), [])
        matches = [expected for expected in candidates if _matches_slot(expected, slot)]
        if len(matches) != 1:
            results.append(
                ExpectedObligation(
                    slot,
                    None,
                    [
                        issue(
                            "obligation.expectation.cardinality",
                            slot.source_pointer,
                            "one unambiguous expectation is required for this source obligation",
                            obligation_id=slot.id,
                        )
                    ],
                )
            )
            continue
        expected = matches[0]
        findings = validate_expected_semantics(expected, slot, contract)
        if expected["obligation_id"] in used:
            findings.append(
                issue(
                    "obligation.expectation.reused",
                    slot.source_pointer,
                    "one expected outcome cannot substitute for distinct source slots",
                )
            )
        used.add(expected["obligation_id"])
        results.append(ExpectedObligation(slot, expected, findings))
    _unbound_expectations(expectations, used, results)
    return results


def _matches_slot(expected: dict[str, Any], slot: ObligationSlot) -> bool:
    if expected["source_pointer"] != slot.source_pointer or expected["category"] != slot.category:
        return False
    equalities = expected_equalities(expected)
    return (slot.outcome is None or equalities.get("/result/outcome") == slot.outcome) and (
        slot.action_id is None or equalities.get("/result/action_id") == slot.action_id
    )


def expected_equalities(expected: dict[str, Any]) -> dict[str, Any]:
    """Return explicit equality constraints; duplicate/conflicting pointers are rejected separately."""
    return {
        item["pointer"]: item["expected"]
        for item in expected["assertions"]
        if item["operator"] == "equals"
    }


def validate_expected_semantics(
    expected: dict[str, Any], slot: ObligationSlot, contract: dict[str, Any]
) -> list[dict[str, Any]]:
    """Reject identity-only predicates used to weaken a source-defined business duty."""
    issues = schema_issues(expected, "expected-outcome")
    if issues:
        return issues
    equalities = expected_equalities(expected)
    source = resolve_pointer(contract, slot.source_pointer)
    if not isinstance(source, dict):
        return [
            issue(
                "obligation.source_pointer.invalid", slot.source_pointer, "source record is absent"
            )
        ]
    required: dict[str, Any] = _identity_expectations(slot, source, contract, equalities, issues)
    _transition_expectations(slot, source, contract, equalities, required, issues)
    _functional_expectations(expected, slot, source, equalities, required, issues)
    for pointer, value in required.items():
        if pointer not in equalities or not json_values_equal(equalities[pointer], value):
            issues.append(
                issue(
                    "obligation.expected.weakened",
                    slot.source_pointer,
                    f"source requires equality at {pointer}",
                )
            )
    keys = [
        (item["capability"], item["pointer"], item["operator"]) for item in expected["assertions"]
    ]
    if len(keys) != len(set(keys)):
        issues.append(
            issue(
                "obligation.expected.duplicate",
                slot.source_pointer,
                "duplicate predicates are ambiguous",
            )
        )
    return issues


def guard_predicate(source: dict[str, Any], *, allowed: bool) -> dict[str, Any] | None:
    """Project supported source guard semantics without guessing missing conditions."""
    operator = source.get("operator")
    inverse = {"equals": "not_equals", "not_equals": "equals", "exists": "absent"}
    if operator not in inverse or not source.get("variable"):
        return None
    return {
        "operator": operator if allowed else inverse[operator],
        "pointer": "/before/properties/" + source["variable"].replace("~", "~0").replace("/", "~1"),
        "expected": source.get("value"),
        "capability": "ui",
    }


def _identity_expectations(
    slot: ObligationSlot,
    source: dict[str, Any],
    contract: dict[str, Any],
    equalities: dict[str, Any],
    issues: list[dict[str, Any]],
) -> dict[str, Any]:
    required: dict[str, Any] = {}
    if slot.category == "structure":
        required = (
            {"/after/semantic_id": source["semantic_id"], "/after/role": source["role"]}
            if "semantic_id" in source
            else {"/after/state": source["id"]}
        )
        if isinstance(source.get("text"), str):
            required["/after/text"] = source["text"]
    else:
        required["/result/action_id"] = slot.action_id
        if slot.outcome:
            required["/result/outcome"] = slot.outcome
        if equalities.get("/result/actor_id") not in {actor["id"] for actor in contract["actors"]}:
            issues.append(
                issue(
                    "obligation.expected.actor",
                    slot.source_pointer,
                    "expected actor must be explicit and defined by the contract",
                )
            )
    return required


def _transition_expectations(
    slot: ObligationSlot,
    source: dict[str, Any],
    contract: dict[str, Any],
    equalities: dict[str, Any],
    required: dict[str, Any],
    issues: list[dict[str, Any]],
) -> None:
    if (
        slot.category == "action"
        and action_mode(source) == "local"
        and "/after/value" not in equalities
    ):
        issues.append(
            issue(
                "obligation.expected.local_value",
                slot.source_pointer,
                "local editing requires the intended observed field value",
            )
        )
    if slot.category == "transition" and slot.source_pointer.startswith("/system_returns/"):
        required["/before/visible"] = True
        required["/after/visible"] = source["destination"]["kind"] != "closed"
        if source["destination"]["kind"] == "screen":
            required.update(
                {
                    "/after/screen_id": source["destination"]["screen_id"],
                    "/after/state": source["destination"]["state"],
                }
            )
    elif (
        slot.category == "transition"
        and slot.source_pointer.startswith("/actions/")
        and action_mode(source) == "navigation"
    ):
        owner = next(node for node in contract["nodes"] if node["id"] == source["node"])
        required.update(
            {
                "/before/screen_id": owner["screen_id"],
                "/after/screen_id": source["destination"]["screen"],
                "/after/state": source["destination"]["state"],
                "/after/visible": True,
            }
        )
    elif slot.category == "transition":
        required.update(
            {
                "/before/screen_id": source["from_screen"],
                "/before/state": source["from_state"],
                "/after/screen_id": source["to_screen"],
                "/after/state": source["to_state"],
            }
        )


def _functional_expectations(
    expected: dict[str, Any],
    slot: ObligationSlot,
    source: dict[str, Any],
    equalities: dict[str, Any],
    required: dict[str, Any],
    issues: list[dict[str, Any]],
) -> None:
    if slot.category == "effect":
        required.update({"/before/method": source["method"], "/before/url": source["endpoint"]})
        if "/after/status" not in equalities:
            issues.append(
                issue(
                    "obligation.expected.response",
                    slot.source_pointer,
                    "effect requires an intended response status",
                )
            )
    if slot.category == "result":
        required["/after/state"] = source[f"{slot.outcome}_state"]
    if (
        slot.category == "persistence"
        and not {"/after/value", "/after/exists", "/after/key", "/after/store_id"}
        <= equalities.keys()
    ):
        issues.append(
            issue(
                "obligation.expected.persistence",
                slot.source_pointer,
                "persistence requires intended value, existence and stable storage identity",
            )
        )
    if slot.category == "validation":
        predicate = guard_predicate(source, allowed=slot.outcome == "allowed")
        if predicate is None or not any(
            json_values_equal(predicate, item) for item in expected["assertions"]
        ):
            issues.append(
                issue(
                    "obligation.expected.guard",
                    slot.source_pointer,
                    "guard requires its source condition or exact complement over observed facts",
                )
            )
    if slot.category == "permission":
        authorized = equalities.get("/result/actor_id") == source["actor"]
        if authorized != (slot.outcome == "allowed"):
            issues.append(
                issue(
                    "obligation.expected.permission",
                    slot.source_pointer,
                    "permission expectation contradicts source actor",
                )
            )


def _unbound_expectations(
    expectations: list[dict[str, Any]], used: set[str], results: list[ExpectedObligation]
) -> None:
    for expected in expectations:
        if expected["obligation_id"] not in used:
            slot = ObligationSlot(
                expected["obligation_id"], expected["category"], expected["source_pointer"]
            )
            results.append(
                ExpectedObligation(
                    slot,
                    expected,
                    [
                        issue(
                            "obligation.expectation.unbound",
                            slot.source_pointer,
                            "expectation does not bind a derived source duty",
                        )
                    ],
                )
            )
