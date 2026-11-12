"""State-scoped comparison of documentation boards (C51, outcome F1).

A design board documents mutually exclusive states side by side; the product renders
one state at a time. The expected tree carries, per node, the contract states in which
the node exists; an actual tree may carry one capture per declared state, each tied to
its ``observed_states`` witness. Synthetic contract data only.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

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
    """A task detail board: a title always, and one action per task status."""
    root = _node(
        "task_detail",
        "screen",
        children=[
            _node("task_detail.title", "text", text="Task"),
            _node("task_detail.submit", "button", text="Submit", states=["todo"]),
            _node("task_detail.reopen", "button", text="Reopen", states=["done"]),
        ],
    )
    return {
        "version": 1,
        "screens": [{"screen_id": "task_detail", "states": ["todo", "done"], "root": root}],
    }


def _capture(state: str, *actions: str, scenario: str | None = None) -> dict[str, Any]:
    children = [_node("task_detail.title", "text", text="Task")]
    labels = {"task_detail.submit": "Submit", "task_detail.reopen": "Reopen"}
    children += [_node(action, "button", text=labels[action]) for action in actions]
    return {
        "screen_id": "task_detail",
        "state": state,
        "scenario_id": scenario or f"scenario-{state}",
        "root": _node("task_detail", "screen", children=children),
    }


def _witness(screen: dict[str, Any]) -> dict[str, Any]:
    return {
        "screen_id": screen["screen_id"],
        "state": screen["state"],
        "scenario_id": screen["scenario_id"],
        "session_id": "session-1",
        "evidence": {"path": f"ui/{screen['state']}.json", "sha256": "0" * 64},
    }


def _actual(*screens: dict[str, Any], witnessed: bool = True) -> dict[str, Any]:
    tree: dict[str, Any] = {"version": 1, "screens": list(screens)}
    if witnessed:
        tree["observed_states"] = [_witness(screen) for screen in screens if "state" in screen]
    return tree


def _codes(report: dict[str, Any]) -> list[str]:
    return sorted(issue["code"] for issue in report["issues"] if issue["severity"] == "error")


def test_each_state_capture_is_compared_with_its_own_nodes() -> None:
    actual = _actual(_capture("todo", "task_detail.submit"), _capture("done", "task_detail.reopen"))
    assert validate_actual_tree(actual) == []
    report = compare_trees(_expected(), actual, mandatory=True)
    assert (report["status"], _codes(report)) == ("PASS", [])


def test_a_declared_state_without_capture_leaves_its_nodes_missing() -> None:
    report = compare_trees(_expected(), _actual(_capture("todo", "task_detail.submit")))
    assert "screen.state_missing" in _codes(report)
    missing = [i for i in report["issues"] if i["code"] == "screen.state_missing"]
    assert "task_detail.reopen" in missing[0]["message"]
    assert report["status"] == "FAIL"


def test_an_unknown_state_is_refused() -> None:
    actual = _actual(
        _capture("todo", "task_detail.submit"),
        _capture("done", "task_detail.reopen"),
        _capture("archived"),
    )
    assert "screen.state_unknown" in _codes(compare_trees(_expected(), actual))


def test_mutually_exclusive_controls_in_one_capture_are_refused() -> None:
    fused = _capture("todo", "task_detail.submit", "task_detail.reopen")
    actual = _actual(fused, _capture("done", "task_detail.reopen"))
    report = compare_trees(_expected(), actual)
    assert "node.state_unexpected" in _codes(report)


def test_a_capture_without_its_witness_is_refused() -> None:
    actual = _actual(
        _capture("todo", "task_detail.submit"), _capture("done", "task_detail.reopen"),
        witnessed=False,
    )  # fmt: skip
    assert _codes(compare_trees(_expected(), actual)).count("screen.state_unwitnessed") == 2
    other = _actual(_capture("todo", "task_detail.submit"), _capture("done", "task_detail.reopen"))
    other["observed_states"][1]["scenario_id"] = "another-scenario"
    assert "screen.state_unwitnessed" in _codes(compare_trees(_expected(), other))


def test_a_state_specific_node_missing_from_its_capture_is_missing() -> None:
    actual = _actual(_capture("todo"), _capture("done", "task_detail.reopen"))
    report = compare_trees(_expected(), actual)
    missing = [i for i in report["issues"] if i["code"] == "node.missing"]
    assert [i["semantic_id"] for i in missing] == ["task_detail.submit"]
    assert "todo" in missing[0]["message"]


def test_two_captures_of_one_state_or_mixed_captures_are_identity_errors() -> None:
    twice = _actual(_capture("todo", "task_detail.submit"), _capture("todo", "task_detail.submit"))
    assert any("duplicate screen state" in i["message"] for i in validate_actual_tree(twice))
    stateless = _capture("todo", "task_detail.submit")
    del stateless["state"], stateless["scenario_id"]
    mixed = _actual(stateless, _capture("done", "task_detail.reopen"))
    assert any("mixes state" in i["message"] for i in validate_actual_tree(mixed))
    assert "actual.schema" in _codes(compare_trees(_expected(), mixed))


def test_states_on_a_stateless_board_are_refused() -> None:
    expected = _expected()
    del expected["screens"][0]["states"]
    for node in expected["screens"][0]["root"]["children"]:
        node.pop("states", None)
    actual = _actual(_capture("todo", "task_detail.submit"))
    assert "screen.state_undeclared" in _codes(compare_trees(expected, actual))


def test_a_legacy_stateless_capture_keeps_the_strict_comparison() -> None:
    capture = _capture("todo", "task_detail.submit")
    del capture["state"], capture["scenario_id"]
    report = compare_trees(_expected(), _actual(capture, witnessed=False))
    # Every node of the board is required in the single capture, as before.
    assert [i["semantic_id"] for i in report["issues"] if i["code"] == "node.missing"] == [
        "task_detail.reopen"
    ]
    legacy = deepcopy(_expected())
    del legacy["screens"][0]["states"]
    for node in legacy["screens"][0]["root"]["children"]:
        node.pop("states", None)
    assert compare_trees(legacy, _actual(capture, witnessed=False))["status"] == "FAIL"


def test_malformed_state_metadata_is_refused_by_the_schema() -> None:
    expected = _expected()
    expected["screens"][0]["root"]["children"][1]["states"] = "todo"
    assert validate_actual_tree(expected) != []
    actual = _actual(_capture("todo", "task_detail.submit"))
    actual["screens"][0]["state"] = ""
    assert validate_actual_tree(actual) != []
