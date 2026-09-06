# @spec FR-008: Require outcome evidence for every applicable functional category, including unchanged-state branches. — .specs/features/077-complete-verification-workflow/spec.md#fr-008
"""Validate closed observed facts and evaluate intended outcomes without runtime coupling."""

from __future__ import annotations

from typing import Any

from .verification_assertions import evaluate_assertion
from .verification_schema import issue, schema_issues
from .verification_system_returns import system_return_issues
from .contract_actions import action_mode


# @spec FR-008: typed observed values — .specs/features/077-complete-verification-workflow/spec.md#fr-008
def evaluate_outcome(
    expected: dict[str, Any], observation: dict[str, Any], *, contract: dict[str, Any]
) -> list[dict[str, Any]]:
    """Validate observation shape, source identity, and every expected predicate.

    File hashes and build/session provenance are checked by the enclosing verifier;
    this pure evaluator never treats producer success flags as evidence.
    """
    issues = schema_issues(expected, "expected-outcome") + schema_issues(observation, "observation")
    if issues:
        return issues
    for field, value in (
        ("obligation_id", expected["obligation_id"]),
        ("category", expected["category"]),
    ):
        if observation[field] != value:
            issues.append(
                issue("outcome.identity", field, f"observation {field} differs from expectation")
            )
    issues.extend(_source_identity_issues(observation, contract))
    for index, assertion in enumerate(expected["assertions"]):
        try:
            passed = evaluate_assertion(assertion, observation)
        except (ValueError, TypeError, OverflowError) as exc:
            issues.append(issue("outcome.predicate.invalid", f"assertions/{index}", str(exc)))
            continue
        if not passed:
            issues.append(
                issue(
                    "outcome.predicate.failed",
                    f"assertions/{index}",
                    "expected predicate is not satisfied",
                )
            )
    if observation["capability"] == "storage":
        issues.extend(_storage_issues(observation))
    return issues


def _source_identity_issues(
    observation: dict[str, Any], contract: dict[str, Any]
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    result = observation["result"]
    system_return = next(
        (item for item in contract.get("system_returns", []) if item["id"] == result["action_id"]),
        None,
    )
    if system_return is not None:
        return _system_source_issues(observation, contract, system_return)
    actors = {item["id"] for item in contract["actors"]}
    action = next((item for item in contract["actions"] if item["id"] == result["action_id"]), None)
    node = next(
        (item for item in contract["nodes"] if action and item["id"] == action["node"]), None
    )
    if result["actor_id"] not in actors or node is None or action is None:
        return [
            issue("outcome.source.identity", "result", "actor/action are not defined by the source")
        ]
    if (
        observation["screen_id"] != node["screen_id"]
        or observation["semantic_id"] != node["semantic_id"]
    ):
        issues.append(
            issue(
                "outcome.source.node",
                "semantic_id",
                "observation is attached to another action node",
            )
        )
    if action_mode(action) == "local":
        if observation["capability"] != "ui" or any(
            observation[side]["semantic_id"] != node["semantic_id"]
            or observation[side]["role"] != node["role"]
            for side in ("before", "after")
        ):
            issues.append(
                issue(
                    "outcome.local.identity",
                    "after",
                    "local editing must observe the same actual input before and after",
                )
            )
    _permission_actor_issues(observation, contract, action, result, issues)
    return issues


def _storage_issues(observation: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    before, after, result = observation["before"], observation["after"], observation["result"]
    readback = result["readback"]
    if any(facts[key] != before[key] for facts in (after, readback) for key in ("key", "store_id")):
        issues.append(
            issue(
                "outcome.storage.identity",
                "result/readback",
                "storage identity changed between reads",
            )
        )
    for key in ("exists", "value"):
        if not _same_value(after[key], readback[key]):
            issues.append(
                issue(
                    "outcome.storage.readback",
                    f"result/readback/{key}",
                    "independent readback differs from the intended resulting state",
                )
            )
        if result["outcome"] in {"denied", "invalid", "idempotent", "error"} and not _same_value(
            before[key], after[key]
        ):
            issues.append(
                issue(
                    "outcome.storage.unchanged",
                    f"after/{key}",
                    "non-mutating outcome changed persistent state",
                )
            )
    if observation["category"] == "persistence":
        restart = result["restart"]
        if (
            restart["before_process"] == restart["after_process"]
            or restart["before_process"] != after["process_instance"]
            or restart["after_process"] != readback["process_instance"]
        ):
            issues.append(
                issue(
                    "outcome.storage.restart",
                    "result/restart",
                    "persistence requires independent readback after a distinct process restart",
                )
            )
    return issues


def _same_value(left: Any, right: Any) -> bool:
    return evaluate_assertion(
        {"operator": "equals", "pointer": "/value", "expected": left, "capability": "storage"},
        {"value": right, "capability": "storage"},
    )


def _system_source_issues(
    observation: dict[str, Any], contract: dict[str, Any], system_return: dict[str, Any]
) -> list[dict[str, Any]]:
    screen = next(item for item in contract["screens"] if item["id"] == system_return["screen_id"])
    root = next(item for item in contract["nodes"] if item["id"] == screen["root_node"])
    if (
        observation["screen_id"] != screen["id"]
        or observation["semantic_id"] != root["semantic_id"]
    ):
        return [
            issue(
                "outcome.system.source",
                "screen_id",
                "system event must bind the owning surface",
            )
        ]
    return system_return_issues(observation, system_return)


def _permission_actor_issues(
    observation: dict[str, Any],
    contract: dict[str, Any],
    action: dict[str, Any],
    result: dict[str, Any],
    issues: list[dict[str, Any]],
) -> None:
    permission = next(
        (
            item
            for item in contract.get("permissions", [])
            if item["id"] == action.get("permission")
        ),
        None,
    )
    if permission:
        authorized = result["actor_id"] == permission["actor"]
        if (result["outcome"] == "denied") == authorized:
            issues.append(
                issue(
                    "outcome.permission",
                    "result/actor_id",
                    "actor and permission outcome contradict the source",
                )
            )
    if (
        observation["capability"] == "network"
        and observation["before"]["actor_id"] != result["actor_id"]
    ):
        issues.append(
            issue("outcome.actor.join", "before/actor_id", "request and result actors differ")
        )
