"""Controls that a record's data offers within one UI state (C51).

Observed: a task detail shows different transition buttons by task status, inside the same
contract state. With one capture per state, every capture missed the exclusive siblings.
A node may now declare ``visible_when`` (a fact and its values). Each capture records its
observed facts with its witness, and one state may be captured once per set of facts. A
node is required exactly when its condition holds, and refused when it does not. Each
conditioned node must be required by at least one capture. No composite state is invented
and no control is hidden.
"""

from __future__ import annotations

from typing import Any

import pytest

from penflow.compare import compare_trees
from penflow.tree import validate_actual_tree


def _node(identifier: str, role: str, **extra: Any) -> dict[str, Any]:
    node: dict[str, Any] = {
        "id": identifier,
        "semantic_id": identifier,
        "role": role,
        "bbox": {"x": 0, "y": 0, "width": 100, "height": 40},
        "children": [],
    }
    node.update(extra)
    return node


def _expected() -> dict[str, Any]:
    root = _node(
        "task",
        "screen",
        children=[
            _node("task.title", "text", text="Task"),
            _node(
                "task.start",
                "button",
                text="Start",
                visible_when={"fact": "task.status", "in": ["todo"]},
            ),
            _node(
                "task.finish",
                "button",
                text="Finish",
                visible_when={"fact": "task.status", "in": ["doing"]},
            ),
        ],
    )
    return {"version": 1, "screens": [{"screen_id": "task", "states": ["default"], "root": root}]}


def _capture(status: str | None, *actions: str) -> dict[str, Any]:
    labels = {"task.start": "Start", "task.finish": "Finish"}
    children = [_node("task.title", "text", text="Task")] + [
        _node(action, "button", text=labels[action]) for action in actions
    ]
    capture: dict[str, Any] = {
        "screen_id": "task",
        "state": "default",
        "scenario_id": f"scenario-{status}",
        "root": _node("task", "screen", children=children),
    }
    if status is not None:
        capture["facts"] = {"task.status": status}
    return capture


def _actual(*captures: dict[str, Any]) -> dict[str, Any]:
    witnesses = [
        {
            "screen_id": c["screen_id"],
            "state": c["state"],
            "scenario_id": c["scenario_id"],
            "session_id": "session-1",
            **({"facts": c["facts"]} if "facts" in c else {}),
            "evidence": {"path": f"ui/{c['scenario_id']}.json", "sha256": "0" * 64},
        }
        for c in captures
    ]
    return {"version": 1, "screens": list(captures), "observed_states": witnesses}


def _codes(report: dict[str, Any]) -> list[str]:
    return sorted(i["code"] for i in report["issues"] if i["severity"] == "error")


def test_each_status_capture_requires_exactly_its_controls() -> None:
    actual = _actual(_capture("todo", "task.start"), _capture("doing", "task.finish"))
    assert validate_actual_tree(actual) == []
    report = compare_trees(_expected(), actual, mandatory=True)
    assert (report["status"], _codes(report)) == ("PASS", [])


@pytest.mark.parametrize(
    ("captures", "code"),
    [
        ((("todo", ("task.start",)),), "node.condition_unwitnessed"),
        ((("todo", ()), ("doing", ("task.finish",))), "node.missing"),
        (
            (("todo", ("task.start", "task.finish")), ("doing", ("task.finish",))),
            "node.condition_unexpected",
        ),
        (((None, ("task.start",)),), "node.condition_fact_missing"),
    ],
)
def test_conditions_never_hide_or_invent_a_control(captures: tuple, code: str) -> None:
    actual = _actual(*(_capture(status, *actions) for status, actions in captures))
    assert code in _codes(compare_trees(_expected(), actual))


def test_facts_must_be_the_witnessed_ones() -> None:
    actual = _actual(_capture("todo", "task.start"), _capture("doing", "task.finish"))
    actual["observed_states"][1]["facts"] = {"task.status": "todo"}
    assert "screen.state_unwitnessed" in _codes(compare_trees(_expected(), actual))
