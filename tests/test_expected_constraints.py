"""The verification expected tree carries contract states and repeat models (C51 F1/F2).

The design board shows every state and one row template; the contract says which state
each node exists in and which node is a collection. ``apply_contract_constraints``
copies exactly those declared facts, and the required comparison uses them. Synthetic
contract data only.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from penflow.expected_constraints import apply_contract_constraints
from penflow.tree import validate_actual_tree
from penflow.verification_comparison import compare_required_trees

CONTRACT: dict[str, Any] = {
    "screens": [
        {"id": "tasks", "states": [{"id": "default"}, {"id": "error"}], "root_node": "tasks"}
    ],
    "nodes": [
        {"id": "tasks", "screen_id": "tasks", "semantic_id": "tasks", "role": "screen"},
        {
            "id": "open-task",
            "screen_id": "tasks",
            "semantic_id": "tasks.open-task",
            "role": "link",
            "states": ["default"],
            "repeat_model": {
                "collection": "project.tasks",
                "item_model": "task",
                "item_key": "task",
                "instance_id_template": "tache-{task.id}",
            },
        },
        {
            "id": "retry",
            "screen_id": "tasks",
            "semantic_id": "tasks.retry",
            "role": "button",
            "states": ["error"],
        },
    ],
}


def _node(identifier: str, role: str, **extra: Any) -> dict[str, Any]:
    node: dict[str, Any] = {"id": identifier, "semantic_id": identifier, "role": role}
    node.update(bbox={"x": 0, "y": 0, "width": 100, "height": 40}, children=[])
    node.update(extra)
    return node


def _board() -> dict[str, Any]:
    root = _node(
        "tasks",
        "screen",
        children=[_node("tasks.open-task", "link"), _node("tasks.retry", "button")],
    )
    return {"version": 1, "screens": [{"screen_id": "tasks", "root": root}]}


def _capture(state: str, *children: dict[str, Any]) -> dict[str, Any]:
    return {
        "screen_id": "tasks",
        "state": state,
        "scenario_id": f"scenario-{state}",
        "root": _node("tasks", "screen", children=list(children)),
    }


def _actual(*captures: dict[str, Any]) -> dict[str, Any]:
    witnesses = [
        {
            "screen_id": c["screen_id"],
            "state": c["state"],
            "scenario_id": c["scenario_id"],
            "session_id": "session-1",
            "evidence": {"path": f"ui/{c['state']}.json", "sha256": "0" * 64},
        }
        for c in captures
    ]
    return {"version": 1, "screens": list(captures), "observed_states": witnesses}


def _row(instance: str) -> dict[str, Any]:
    row = _node("tasks.open-task", "link", instance_id=instance)
    row["id"] = f"row-{instance}"
    return row


def test_declared_constraints_are_copied_and_nothing_else() -> None:
    expected = _board()
    apply_contract_constraints(expected, CONTRACT)
    screen = expected["screens"][0]
    open_task, retry = screen["root"]["children"]
    assert screen["states"] == ["default", "error"]
    assert open_task["states"] == ["default"]
    assert open_task["repeat_model"]["instance_id_template"] == "tache-{task.id}"
    assert retry["states"] == ["error"] and "repeat_model" not in retry
    assert "states" not in screen["root"] and "repeat_model" not in screen["root"]
    assert validate_actual_tree(expected) == []


def test_required_comparison_joins_states_and_instances() -> None:
    expected = _board()
    apply_contract_constraints(expected, CONTRACT)
    actual = _actual(
        _capture("default", _row("tache-1"), _row("tache-2")),
        _capture("error", _node("tasks.retry", "button")),
    )
    assert validate_actual_tree(actual) == []
    assert compare_required_trees(CONTRACT, expected, actual) == []


def test_required_comparison_still_refuses_a_fused_state_and_a_foreign_instance() -> None:
    expected = _board()
    apply_contract_constraints(expected, CONTRACT)
    fused = _actual(
        _capture("default", _row("tache-1"), _node("tasks.retry", "button")),
        _capture("error", _node("tasks.retry", "button")),
    )
    codes = {f["code"] for f in compare_required_trees(CONTRACT, expected, fused)}
    assert "node.state_unexpected" in codes
    foreign = deepcopy(fused)
    foreign["screens"][0]["root"]["children"] = [_row("projet-1")]
    codes = {f["code"] for f in compare_required_trees(CONTRACT, expected, foreign)}
    assert {"node.instance_unexpected", "node.missing"} <= codes
