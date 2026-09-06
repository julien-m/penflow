"""Business transition causality and branch-governance checks."""

from __future__ import annotations
from typing import Any
from .contract_records import record_items, contract_issue

VISUALLY_INTERACTIVE_ROLES = {"button", "link", "input"}
NON_CAUSAL_GUARD_VARIABLES = {
    "destination",
    "entry_state",
    "from_screen",
    "target_screen",
    "to_screen",
    "to_state",
}
CAUSAL_TRANSITION_FIELDS = ("kind", "label", "causal")


def _validate_guard_semantics(contract: dict[str, Any], issues: list[dict[str, Any]]) -> None:
    """Reject partial or route-derived predicates once structured metadata is used."""
    for index, guard in enumerate(record_items(contract, "guards")):
        path = f"$.guards[{index}]"
        structured_fields = ("variable", "operator", "value", "source")
        present = [field for field in structured_fields if field in guard]
        if present and len(present) != len(structured_fields):
            issues.append(
                contract_issue(
                    "error",
                    "contract.guard.incomplete",
                    path,
                    "structured guard requires variable, operator, value, and source",
                )
            )
            continue
        variable = guard.get("variable")
        if isinstance(variable, str) and variable in NON_CAUSAL_GUARD_VARIABLES:
            issues.append(
                contract_issue(
                    "error",
                    "contract.guard.non_causal_variable",
                    f"{path}.variable",
                    f"guard variable cannot be derived from route destination: {variable}",
                )
            )


def _validate_transition_semantics(
    transition: dict[str, Any],
    path: str,
    registries: dict[str, Any],
    issues: list[dict[str, Any]],
) -> None:
    """Validate declared transition causality without executing a UI runtime."""
    metadata_present = any(field in transition for field in CAUSAL_TRANSITION_FIELDS)
    if metadata_present:
        missing = [field for field in CAUSAL_TRANSITION_FIELDS if field not in transition]
        if missing:
            issues.append(
                contract_issue(
                    "error",
                    "contract.transition.causal_metadata_incomplete",
                    path,
                    f"causal transition metadata requires kind, label, and causal: missing {missing}",
                )
            )
    kind = transition.get("kind")
    if kind == "navigation" and transition.get("from_screen") == transition.get("to_screen"):
        issues.append(
            contract_issue(
                "error",
                "contract.transition.kind_mismatch",
                f"{path}.kind",
                "navigation transition must change screen",
            )
        )
    if kind == "state":
        if transition.get("from_screen") != transition.get("to_screen"):
            issues.append(
                contract_issue(
                    "error",
                    "contract.transition.kind_mismatch",
                    f"{path}.kind",
                    "state transition must stay on the same screen",
                )
            )
        if transition.get("from_state") == transition.get("to_state"):
            code = (
                "contract.transition.default_unchanged"
                if transition.get("from_state") == "default"
                else "contract.transition.state_unchanged"
            )
            issues.append(
                contract_issue(
                    "error",
                    code,
                    f"{path}.to_state",
                    "state transition must change state",
                )
            )
    _validate_observable_transition(transition, path, registries, issues)


def _validate_observable_transition(
    transition: dict[str, Any], path: str, registries: dict[str, Any], issues: list[dict[str, Any]]
) -> None:
    flow_id = transition.get("flow")
    for field in ("from_screen", "to_screen"):
        screen = registries["screens"].get(transition.get(field))
        if isinstance(screen, dict) and screen.get("flow_id") != flow_id:
            issues.append(
                contract_issue(
                    "error",
                    "contract.transition.flow_mismatch",
                    f"{path}.{field}",
                    f"{field} must belong to transition flow {flow_id}",
                )
            )
    causal = transition.get("causal")
    if not isinstance(causal, dict):
        return
    fanout = causal.get("fanout")
    if isinstance(fanout, dict) and fanout.get("policy") == "governed":
        governance = fanout.get("governance")
        if not isinstance(governance, str) or not governance.strip():
            issues.append(
                contract_issue(
                    "error",
                    "contract.transition.fanout_governance_missing",
                    f"{path}.causal.fanout.governance",
                    "governed fan-out requires a non-empty governance rule",
                )
            )
    action = registries["actions"].get(transition.get("action"))
    node = registries["nodes"].get(action.get("node")) if isinstance(action, dict) else None
    if (
        not isinstance(node, dict)
        or node.get("role") not in VISUALLY_INTERACTIVE_ROLES
        or not isinstance(node.get("test_id"), str)
        or not node["test_id"].strip()
    ):
        issues.append(
            contract_issue(
                "error",
                "contract.transition.action_not_observable",
                f"{path}.action",
                "causal transition action must bind to a visible node with a stable test_id",
            )
        )


def _validate_transition_fanout(
    contract: dict[str, Any],
    registries: dict[str, Any],
    issues: list[dict[str, Any]],
) -> None:
    """Require explicit governance and unique outcomes for incompatible branches."""
    groups: dict[tuple[str, str, str, str], list[tuple[int, dict[str, Any]]]] = {}
    for index, transition in enumerate(record_items(contract, "transitions")):
        key = (
            str(transition.get("from_screen", "")),
            str(transition.get("from_state", "")),
            str(transition.get("trigger", "")),
            str(transition.get("action", "")),
        )
        groups.setdefault(key, []).append((index, transition))
    for transitions in groups.values():
        _validate_branch_group(transitions, registries, issues)


def _validate_branch_group(
    transitions: list[tuple[int, dict[str, Any]]],
    registries: dict[str, Any],
    issues: list[dict[str, Any]],
) -> None:
    destinations = {(item.get("to_screen"), item.get("to_state")) for _, item in transitions}
    if len(transitions) < 2 or len(destinations) < 2:
        return
    causal_blocks = [
        item.get("causal") if isinstance(item.get("causal"), dict) else None
        for _, item in transitions
    ]
    # Legacy fan-outs make no causal claim and remain v2-compatible. Once
    # any branch opts into C44, every incompatible outcome must participate.
    if all(causal is None for causal in causal_blocks):
        return
    if any(causal is None for causal in causal_blocks):
        for index, transition in transitions:
            if not isinstance(transition.get("causal"), dict):
                issues.append(
                    contract_issue(
                        "error",
                        "contract.transition.fanout_ungoverned",
                        f"$.transitions[{index}].causal",
                        "incompatible fan-out requires explicit causal governance",
                    )
                )
        return
    fanouts = [
        causal.get("fanout") if isinstance(causal, dict) else None for causal in causal_blocks
    ]
    groups_and_policies = {
        (fanout.get("group"), fanout.get("policy"))
        for fanout in fanouts
        if isinstance(fanout, dict)
    }
    if len(groups_and_policies) != 1:
        issues.append(
            contract_issue(
                "error",
                "contract.transition.fanout_governance_mismatch",
                f"$.transitions[{transitions[0][0]}].causal.fanout",
                "fan-out branches must share one group and policy",
            )
        )
    _validate_branch_outcomes(transitions, causal_blocks, fanouts, registries, issues)


def _validate_branch_outcomes(
    transitions: list[tuple[int, dict[str, Any]]],
    causal_blocks: list[Any],
    fanouts: list[Any],
    registries: dict[str, Any],
    issues: list[dict[str, Any]],
) -> None:
    outcomes: set[str] = set()
    predicates: set[tuple[str, str, str, str]] = set()
    for (index, transition), causal, fanout in zip(
        transitions, causal_blocks, fanouts, strict=True
    ):
        outcome = causal.get("outcome") if isinstance(causal, dict) else None
        if not isinstance(outcome, str) or outcome in outcomes:
            issues.append(
                contract_issue(
                    "error",
                    "contract.transition.fanout_outcome_duplicate",
                    f"$.transitions[{index}].causal.outcome",
                    "fan-out outcomes must be non-empty and unique",
                )
            )
        if isinstance(outcome, str):
            outcomes.add(outcome)
        guard = registries["guards"].get(transition.get("guard"))
        predicate = (
            str(guard.get("variable", "")) if isinstance(guard, dict) else "",
            str(guard.get("operator", "")) if isinstance(guard, dict) else "",
            str(guard.get("value", "")) if isinstance(guard, dict) else "",
            str(guard.get("source", "")) if isinstance(guard, dict) else "",
        )
        if not all(predicate):
            issues.append(
                contract_issue(
                    "error",
                    "contract.transition.causal_guard_incomplete",
                    f"$.transitions[{index}].guard",
                    "causal fan-out requires a complete variable/operator/value/source guard",
                )
            )
        if not isinstance(fanout, dict) or fanout.get("policy") != "exclusive":
            continue
        if not all(predicate) or predicate in predicates:
            issues.append(
                contract_issue(
                    "error",
                    "contract.transition.non_exclusive_fanout",
                    f"$.transitions[{index}].guard",
                    "exclusive fan-out requires distinct complete guard predicates",
                )
            )
        predicates.add(predicate)
