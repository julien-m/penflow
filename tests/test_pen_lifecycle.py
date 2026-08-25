# @spec(AC-005)
# @spec(AC-006)
# @spec(FR-004)
# @spec(FR-005)
"""Behavior tests for the single-canvas revision lifecycle."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from penflow.pen import inspect_pen, parse_active_pen
from penflow.pen_lifecycle import (
    CanvasLifecycleError,
    CanvasState,
    select_active_canvas_regions,
    validate_canvas_lifecycle,
)
from penflow.tree import expected_tree_from_pen, write_expected_tree


def _frame(
    node_id: str,
    *,
    semantic_id: str | None = None,
    state: str | None = None,
    logical_screen_id: str | None = None,
    revision_id: str | None = None,
    children: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    node: dict[str, Any] = {
        "id": node_id,
        "type": "frame",
        "name": node_id,
        "children": children or [],
    }
    if semantic_id is not None:
        node["context"] = f"semantic_id={semantic_id}; role=screen"
    if state is not None:
        node["penflow"] = {
            "lifecycle": {
                "schema_version": 1,
                "state": state,
                "logical_screen_id": logical_screen_id,
                "revision_id": revision_id,
            }
        }
    return node


def _document(*children: Any) -> dict[str, Any]:
    return {"version": "1.0", "children": list(children)}


def _write(path: Path, data: dict[str, Any]) -> Path:
    path.write_text(json.dumps(data, sort_keys=True) + "\n", encoding="utf-8")
    return path


def test_marked_lifecycle_selects_only_active_roots_in_source_order() -> None:
    document = _document(
        _frame(
            "settings-r2",
            state="draft",
            logical_screen_id="settings",
            revision_id="settings-r2",
        ),
        _frame(
            "home-r3",
            semantic_id="home",
            state="active",
            logical_screen_id="home",
            revision_id="home-r3",
        ),
        _frame(
            "settings-r1",
            state="archive",
            logical_screen_id="settings",
            revision_id="settings-r1",
        ),
        _frame(
            "settings-r3",
            semantic_id="settings",
            state="active",
            logical_screen_id="settings",
            revision_id="settings-r3",
        ),
    )

    result = validate_canvas_lifecycle(document)

    assert result.findings == ()
    assert [region.state for region in result.regions] == [
        CanvasState.DRAFT,
        CanvasState.ACTIVE,
        CanvasState.ARCHIVE,
        CanvasState.ACTIVE,
    ]
    assert [region.node_id for region in result.active_regions] == ["home-r3", "settings-r3"]
    assert [node["id"] for node in select_active_canvas_regions(document)] == [
        "home-r3",
        "settings-r3",
    ]


def test_expected_tree_excludes_draft_and_archive_roots(tmp_path: Path) -> None:
    document = _document(
        _frame(
            "home-r1",
            semantic_id="home",
            state="archive",
            logical_screen_id="home",
            revision_id="home-r1",
        ),
        _frame(
            "home-r2",
            semantic_id="home",
            state="active",
            logical_screen_id="home",
            revision_id="home-r2",
        ),
        _frame(
            "home-r3",
            semantic_id="home",
            state="draft",
            logical_screen_id="home",
            revision_id="home-r3",
        ),
    )
    path = _write(tmp_path / "ui.pen", document)

    expected = expected_tree_from_pen(path)

    assert [screen["pencil_id"] for screen in expected["screens"]] == ["home-r2"]


def test_active_parser_preserves_physical_top_level_source_index(tmp_path: Path) -> None:
    document = _document(
        _frame(
            "home-r1",
            semantic_id="home",
            state="archive",
            logical_screen_id="home",
            revision_id="home-r1",
        ),
        _frame(
            "home-r2",
            semantic_id="home",
            state="active",
            logical_screen_id="home",
            revision_id="home-r2",
        ),
    )
    path = _write(tmp_path / "ui.pen", document)

    roots = parse_active_pen(path)

    assert len(roots) == 1
    assert roots[0].order == 1


def test_inspect_validates_context_on_active_regions_but_lists_physical_regions(
    tmp_path: Path,
) -> None:
    document = _document(
        _frame(
            "home-r1",
            semantic_id="home",
            state="archive",
            logical_screen_id="home",
            revision_id="home-r1",
        ),
        _frame(
            "home-r2",
            semantic_id="home",
            state="active",
            logical_screen_id="home",
            revision_id="home-r2",
        ),
    )
    path = _write(tmp_path / "ui.pen", document)

    report = inspect_pen(path)

    assert [screen["id"] for screen in report["screens"]] == ["home-r1", "home-r2"]
    assert "context.semantic_id_duplicate" not in {issue["code"] for issue in report["errors"]}


def test_unmarked_legacy_regions_derive_active_identities_without_mutating_bytes(
    tmp_path: Path,
) -> None:
    document = _document(
        _frame("home-node", semantic_id="home"),
        _frame("settingsScreen"),
    )
    path = _write(tmp_path / "ui.pen", document)
    before = path.read_bytes()

    roots = parse_active_pen(path)
    expected = expected_tree_from_pen(path)

    assert [(root.id, root.semantic_id) for root in roots] == [
        ("home-node", "home"),
        ("settingsScreen", None),
    ]
    assert [screen["screen_id"] for screen in expected["screens"]] == [
        "home",
        "settingsScreen",
    ]
    assert path.read_bytes() == before


def test_nested_lifecycle_metadata_does_not_create_a_canvas_region() -> None:
    nested_draft = _frame(
        "nested-draft",
        state="draft",
        logical_screen_id="nested",
        revision_id="nested-r1",
    )
    document = _document(_frame("home", semantic_id="home", children=[nested_draft]))

    result = validate_canvas_lifecycle(document)

    assert result.findings == ()
    assert [region.node_id for region in result.regions] == ["home"]


@pytest.mark.parametrize(
    ("child", "code"),
    [
        ("not-an-object", "canvas.top_level_invalid"),
        ({"id": "title", "type": "text"}, "canvas.top_level_non_region"),
        ({"type": "frame"}, "canvas.node_id_missing"),
    ],
)
def test_invalid_top_level_children_block_selection(child: Any, code: str) -> None:
    result = validate_canvas_lifecycle(_document(child))

    assert code in {finding.code for finding in result.findings}
    with pytest.raises(CanvasLifecycleError) as raised:
        select_active_canvas_regions(_document(child))
    assert code in {finding.code for finding in raised.value.findings}


def test_empty_document_blocks_publication() -> None:
    result = validate_canvas_lifecycle(_document())

    assert [finding.code for finding in result.findings] == ["canvas.empty"]


@pytest.mark.parametrize(
    ("lifecycle", "code"),
    [
        (
            {
                "schema_version": 2,
                "state": "active",
                "logical_screen_id": "home",
                "revision_id": "home-r1",
            },
            "canvas.lifecycle_schema_unsupported",
        ),
        (
            {
                "schema_version": 1,
                "state": {"value": "active"},
                "logical_screen_id": "home",
                "revision_id": "home-r1",
            },
            "canvas.lifecycle_state_invalid",
        ),
        (
            {
                "schema_version": 1,
                "state": "active",
                "logical_screen_id": "Home",
                "revision_id": "home-r1",
            },
            "canvas.logical_screen_id_invalid",
        ),
        (
            {
                "schema_version": 1,
                "state": "active",
                "logical_screen_id": "home",
                "revision_id": "home r1",
            },
            "canvas.revision_id_invalid",
        ),
    ],
)
def test_marked_metadata_schema_values_and_identity_grammar_are_strict(
    lifecycle: dict[str, Any], code: str
) -> None:
    node = _frame("home-r1")
    node["penflow"] = {"lifecycle": lifecycle}

    result = validate_canvas_lifecycle(_document(node))

    assert code in {finding.code for finding in result.findings}


def test_marked_lifecycle_rejects_unknown_fields() -> None:
    node = _frame("home-r1")
    node["penflow"] = {
        "lifecycle": {
            "schema_version": 1,
            "state": "active",
            "logical_screen_id": "home",
            "revision_id": "home-r1",
            "published_by": "unknown-extension",
        }
    }

    findings = validate_canvas_lifecycle(_document(node)).findings

    assert [finding.code for finding in findings] == ["canvas.lifecycle_invalid"]


def test_revision_and_node_ids_are_unique_across_the_document() -> None:
    document = _document(
        _frame(
            "same-node",
            state="active",
            logical_screen_id="home",
            revision_id="shared-r1",
        ),
        _frame(
            "same-node",
            state="active",
            logical_screen_id="settings",
            revision_id="shared-r1",
        ),
    )

    codes = {finding.code for finding in validate_canvas_lifecycle(document).findings}

    assert "canvas.node_id_duplicate" in codes
    assert "canvas.revision_id_duplicate" in codes


def test_missing_and_multiple_active_findings_are_per_logical_screen() -> None:
    document = _document(
        _frame(
            "home-r1",
            state="draft",
            logical_screen_id="home",
            revision_id="home-r1",
        ),
        _frame(
            "settings-r1",
            state="active",
            logical_screen_id="settings",
            revision_id="settings-r1",
        ),
        _frame(
            "settings-r2",
            state="active",
            logical_screen_id="settings",
            revision_id="settings-r2",
        ),
    )

    findings = validate_canvas_lifecycle(document).findings

    assert [(finding.code, finding.logical_screen_id) for finding in findings] == [
        ("canvas.active_missing", "home"),
        ("canvas.active_multiple", "settings"),
    ]


def test_invalid_lifecycle_blocks_expected_tree_publication(tmp_path: Path) -> None:
    document = _document(
        _frame(
            "home-r1",
            state="draft",
            logical_screen_id="home",
            revision_id="home-r1",
        )
    )
    pen_path = _write(tmp_path / "ui.pen", document)
    out_path = tmp_path / "expected-ui-tree.json"
    out_path.write_bytes(b"existing-output\n")

    with pytest.raises(CanvasLifecycleError) as raised:
        write_expected_tree(pen_path, out_path)

    assert [finding.code for finding in raised.value.findings] == ["canvas.active_missing"]
    assert out_path.read_bytes() == b"existing-output\n"
    assert pen_path.read_text(encoding="utf-8") == json.dumps(document, sort_keys=True) + "\n"


def test_inspect_reports_lifecycle_errors_without_publishing_or_mutating(tmp_path: Path) -> None:
    document = _document(
        _frame(
            "home-r1",
            state="archive",
            logical_screen_id="home",
            revision_id="home-r1",
        )
    )
    path = _write(tmp_path / "ui.pen", document)
    before = path.read_bytes()

    report = inspect_pen(path)

    assert "canvas.active_missing" in {issue["code"] for issue in report["errors"]}
    assert path.read_bytes() == before
