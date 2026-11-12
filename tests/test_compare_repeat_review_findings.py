"""Per-instance coverage and geometry of repeated rows, stateless screen identity (PR 21).

Three defects reported on 5d80ade:
1. A required repeated descendant was matched globally. Row b without its title passed
   because row a had one.
2. Each instance was compared with the template's absolute geometry, so a second row
   translated below the first failed although it is identical.
3. A stateless screen could repeat when its captures differed only by facts, and then
   only the first capture was compared.
"""

from __future__ import annotations

from typing import Any

from penflow.compare import compare_trees
from penflow.tree import validate_actual_tree
from tests.test_compare_repeat_instances import _expected, _node


def _row(
    instance: str, y: int, *, title: dict[str, Any] | None = None, **box: int
) -> dict[str, Any]:
    bbox = {"x": 0, "y": y, "width": 100, "height": 40, **box}
    children = []
    if title is not None:
        children = [title]
    row = _node(
        "project_tasks.open-task", "link", instance_id=instance, bbox=bbox, children=children
    )
    row["id"] = f"row-{instance}"
    return row


def _title(instance: str, y: int, **box: int) -> dict[str, Any]:
    title = _node(
        "project_tasks.task-title",
        "text",
        instance_id=instance,
        bbox={"x": 0, "y": y, "width": 100, "height": 40, **box},
    )
    title["id"] = f"title-{instance}"
    return title


def _actual(*rows: dict[str, Any]) -> dict[str, Any]:
    root = _node("project_tasks", "screen", children=[_node("project_tasks.new", "button"), *rows])
    return {"version": 1, "screens": [{"screen_id": "project_tasks", "root": root}]}


def _issues(report: dict[str, Any]) -> list[tuple[str, str]]:
    return sorted(
        (issue["code"], issue["semantic_id"])
        for issue in report["issues"]
        if issue["severity"] in ("error", "warning")
    )


def test_each_row_needs_its_own_required_descendant() -> None:
    actual = _actual(
        _row("tache-a", 0, title=_title("tache-a", 0)),
        _row("tache-b", 40),
    )
    report = compare_trees(_expected(), actual, mandatory=True)
    assert ("node.missing", "project_tasks.task-title::tache-b") in _issues(report)
    assert report["status"] == "FAIL"


def test_every_row_missing_its_descendant_is_reported() -> None:
    report = compare_trees(_expected(), _actual(_row("tache-a", 0), _row("tache-b", 40)))
    missing = [key for code, key in _issues(report) if code == "node.missing"]
    assert missing == ["project_tasks.task-title::tache-a", "project_tasks.task-title::tache-b"]


def test_translated_identical_rows_pass() -> None:
    actual = _actual(
        _row("tache-a", 0, title=_title("tache-a", 0)),
        _row("tache-b", 40, title=_title("tache-b", 40)),
    )
    report = compare_trees(_expected(), actual, mandatory=True)
    assert (report["status"], _issues(report)) == ("PASS", [])


def test_a_shifted_descendant_or_other_dimensions_still_fail() -> None:
    shifted = _actual(
        _row("tache-a", 0, title=_title("tache-a", 0)),
        _row("tache-b", 40, title=_title("tache-b", 60)),
    )
    assert ("node.bbox.y", "project_tasks.task-title::tache-b") in _issues(
        compare_trees(_expected(), shifted, mandatory=True)
    )
    resized = _actual(
        _row("tache-a", 0, title=_title("tache-a", 0)),
        _row("tache-b", 40, title=_title("tache-b", 40), height=80),
    )
    assert ("node.bbox.height", "project_tasks.open-task::tache-b") in _issues(
        compare_trees(_expected(), resized, mandatory=True)
    )


def test_a_stateless_screen_is_unique_whatever_its_facts() -> None:
    first = {"screen_id": "s", "facts": {"x": 1}, "root": _node("s", "screen")}
    second = {"screen_id": "s", "facts": {"x": 2}, "root": _node("s", "screen")}
    issues = validate_actual_tree({"version": 1, "screens": [first, second]})
    assert any("duplicate screen identity" in issue["message"] for issue in issues)
    scoped = [
        {**first, "state": "default", "scenario_id": "one"},
        {**second, "state": "default", "scenario_id": "two"},
    ]
    assert validate_actual_tree({"version": 1, "screens": scoped}) == []
