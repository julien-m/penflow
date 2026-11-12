"""Collection-aware comparison of repeated nodes (C51, outcome F2).

A contract node with ``repeat_model`` is one template on the board and N instances at
runtime (``semantic_id::instance_id``). Each instance must match the declared
``instance_id_template`` exactly and is compared with the template node; its repeated
descendants belong to the same instance. Synthetic contract data only.
"""

from __future__ import annotations

from typing import Any

from penflow.compare import compare_trees
from penflow.tree import validate_actual_tree

REPEAT = {
    "collection": "project.tasks",
    "item_model": "task",
    "item_key": "task",
    "instance_id_template": "tache-{task.id}",
}


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


def _expected(repeat: dict[str, Any] | None = REPEAT) -> dict[str, Any]:
    row = _node(
        "project_tasks.open-task",
        "link",
        children=[_node("project_tasks.task-title", "text")],
    )
    if repeat is not None:
        row["repeat_model"] = dict(repeat)
    root = _node("project_tasks", "screen", children=[_node("project_tasks.new", "button"), row])
    return {"version": 1, "screens": [{"screen_id": "project_tasks", "root": root}]}


def _row(instance: str, *, title_instance: str | None = None, role: str = "link") -> dict[str, Any]:
    title = _node("project_tasks.task-title", "text", instance_id=title_instance or instance)
    title["id"] = f"title-{title_instance or instance}"
    row = _node("project_tasks.open-task", role, instance_id=instance, children=[title])
    row["id"] = f"row-{instance}"
    return row


def _actual(*rows: dict[str, Any]) -> dict[str, Any]:
    root = _node("project_tasks", "screen", children=[_node("project_tasks.new", "button"), *rows])
    return {"version": 1, "screens": [{"screen_id": "project_tasks", "root": root}]}


def _errors(report: dict[str, Any]) -> list[str]:
    return sorted(issue["code"] for issue in report["issues"] if issue["severity"] == "error")


def test_every_conforming_instance_matches_the_template() -> None:
    actual = _actual(_row("tache-1f2e"), _row("tache-9a0b"))
    assert validate_actual_tree(actual) == []
    report = compare_trees(_expected(), actual, mandatory=True)
    assert (report["status"], _errors(report)) == ("PASS", [])
    assert report["summary"]["checks"] >= 4  # Both instances were really compared.


def test_each_instance_keeps_its_own_checks() -> None:
    report = compare_trees(
        _expected(), _actual(_row("tache-1f2e"), _row("tache-9a0b", role="button"))
    )
    roles = [i for i in report["issues"] if i["code"] == "node.role"]
    assert [i["semantic_id"] for i in roles] == ["project_tasks.open-task::tache-9a0b"]


def test_an_instance_outside_the_template_is_refused() -> None:
    for instance in ("other-1f2e", "tache-", "tache-1f2e-extra/x"):
        report = compare_trees(_expected(), _actual(_row("tache-1f2e"), _row(instance)))
        assert "node.instance_unexpected" in _errors(report), instance


def test_a_descendant_of_another_instance_is_refused() -> None:
    report = compare_trees(_expected(), _actual(_row("tache-1f2e", title_instance="tache-9a0b")))
    assert "node.instance_mismatch" in _errors(report)


def test_no_instance_leaves_the_template_missing() -> None:
    report = compare_trees(_expected(), _actual())
    assert "node.missing" in _errors(report)


def test_without_repeat_model_instances_stay_strict() -> None:
    report = compare_trees(_expected(repeat=None), _actual(_row("tache-1f2e")))
    assert {"node.missing", "node.unexpected_interactive"} <= set(_errors(report))


def test_repeated_identities_and_malformed_templates_are_refused() -> None:
    twice = _actual(_row("tache-1f2e"), _row("tache-1f2e"))
    assert validate_actual_tree(twice) != []
    expected = _expected({**REPEAT, "instance_id_template": "tache"})
    assert validate_actual_tree(expected) != []
    expected = _expected({**REPEAT, "instance_id_template": "tache-{}"})
    assert validate_actual_tree(expected) != []
