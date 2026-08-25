from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from penflow.cli import main
from penflow.semantic_mapping import write_pencil_context_map
from tests.test_semantic_enrichment import legacy_pen, semantic_tree, write_json

# @spec FR-005: Canonical producer migration — .specs/features/074-penflow-doctor-consumer-project-hygiene/spec.md#fr-005


VISUAL_KEYS = {
    "type",
    "x",
    "y",
    "width",
    "height",
    "layout",
    "gap",
    "padding",
    "fill",
    "stroke",
    "content",
}


def mapping_tree() -> dict:
    tree = semantic_tree()
    tree["screens"][0]["root"]["children"].append(
        {
            "semantic_id": "checkout.help",
            "role": "text",
            "text": "Need help?",
            "source_map": {"screen_spec": "flow-ui-contract/screens/checkout.md"},
        }
    )
    return tree


def visual_snapshot_by_id(pen: dict) -> dict[str, dict]:
    result: dict[str, dict] = {}

    def visit(node: dict) -> None:
        result[node["id"]] = {key: copy.deepcopy(node[key]) for key in VISUAL_KEYS if key in node}
        result[node["id"]]["child_order"] = [
            child.get("id") for child in node.get("children", []) or []
        ]
        for child in node.get("children", []) or []:
            visit(child)

    for child in pen.get("children", []) or []:
        visit(child)
    return result


def _active_archive_pen(*, archive_first: bool) -> tuple[dict, dict]:
    """Build one managed active region and its immutable archived predecessor."""
    pen = legacy_pen()
    active = pen["children"][0]
    active["penflow"] = {
        "lifecycle": {
            "schema_version": 1,
            "state": "active",
            "logical_screen_id": "checkout",
            "revision_id": "checkout-r2",
        }
    }
    archived = copy.deepcopy(active)
    archived["id"] = "checkoutArchived"
    archived["penflow"]["lifecycle"].update({"state": "archive", "revision_id": "checkout-r1"})
    pen["children"] = [archived, active] if archive_first else [active, archived]
    return pen, copy.deepcopy(archived)


def _repeated_id_pen_and_tree() -> tuple[dict, dict]:
    """Build two screens whose child IDs collide but exact paths differ."""
    pen = legacy_pen()
    first_screen = pen["children"][0]
    first_screen["children"] = [
        {"id": "shared", "type": "text", "name": "First label", "content": "First label"}
    ]
    second_screen = copy.deepcopy(first_screen)
    second_screen.update(
        {"id": "settings", "name": "settings", "context": "semantic_id=settings; role=screen"}
    )
    second_screen["children"][0].update({"name": "Second label", "content": "Second label"})
    pen["children"] = [first_screen, second_screen]

    tree = semantic_tree()
    tree["screens"][0]["root"]["children"] = [_semantic_label("checkout", "First label")]
    second = copy.deepcopy(tree["screens"][0])
    second.update({"id": "settings", "root": _semantic_screen("settings", "Second label")})
    tree["screens"].append(second)
    return pen, tree


def _semantic_label(screen_id: str, text: str) -> dict:
    return {
        "semantic_id": f"{screen_id}.label",
        "role": "text",
        "text": text,
        "source_map": {"screen_spec": f"flow-ui-contract/screens/{screen_id}.md"},
    }


def _semantic_screen(screen_id: str, text: str) -> dict:
    return {
        "semantic_id": screen_id,
        "role": "screen",
        "source_map": {"screen_spec": f"flow-ui-contract/screens/{screen_id}.md"},
        "children": [_semantic_label(screen_id, text)],
    }


def test_write_pencil_context_map_reports_all_buckets_and_preserves_existing_layout(
    tmp_path: Path,
) -> None:
    pen = legacy_pen()
    pen["children"][0]["children"].insert(
        1,
        {
            "id": "duplicateTitle",
            "type": "text",
            "name": "Checkout duplicate",
            "content": "Checkout",
            "width": 240,
            "fill": "#222222",
        },
    )
    before_visual = visual_snapshot_by_id(pen)
    pen_path = write_json(tmp_path / "ui.pen", pen)
    tree_path = write_json(tmp_path / "semantic-ui-tree.json", mapping_tree())
    map_path = tmp_path / "pencil-context-map.json"

    result = write_pencil_context_map(
        pen_path,
        tree_path,
        map_path,
        pen_out=pen_path,
        create_placeholders=True,
    )
    mapped_pen = json.loads(pen_path.read_text(encoding="utf-8"))
    after_visual = visual_snapshot_by_id(mapped_pen)

    assert result["status"] == "PARTIAL"
    assert [item["semantic_id"] for item in result["matched"]] == ["checkout", "checkout.pay"]
    assert [item["semantic_id"] for item in result["created"]] == ["checkout.help"]
    assert [item["semantic_id"] for item in result["ambiguous"]] == ["checkout.title"]
    assert result["unmapped"] == []
    assert result["status"] == "PARTIAL"
    for node_id, snapshot in before_visual.items():
        assert after_visual[node_id] == snapshot


def test_write_pencil_context_map_is_deterministic(tmp_path: Path) -> None:
    pen_path = write_json(tmp_path / "ui.pen", legacy_pen())
    tree_path = write_json(tmp_path / "semantic-ui-tree.json", mapping_tree())
    first_path = tmp_path / "first-map.json"
    second_path = tmp_path / "second-map.json"

    write_pencil_context_map(pen_path, tree_path, first_path)
    write_pencil_context_map(pen_path, tree_path, second_path)

    assert first_path.read_bytes() == second_path.read_bytes()


def test_write_pencil_context_map_rejects_peer_pen_before_any_write(tmp_path: Path) -> None:
    pen_path = write_json(tmp_path / "ui.pen", legacy_pen())
    tree_path = write_json(tmp_path / "semantic-ui-tree.json", mapping_tree())
    map_path = tmp_path / "pencil-context-map.json"
    peer_path = tmp_path / "ui.mapped.pen"
    before = pen_path.read_bytes()

    with pytest.raises(ValueError, match="canonical input ui.pen"):
        write_pencil_context_map(pen_path, tree_path, map_path, pen_out=peer_path)

    assert pen_path.read_bytes() == before
    assert not peer_path.exists()
    assert not map_path.exists()


def test_write_pencil_context_map_rejects_canonical_pen_as_map_output_before_write(
    tmp_path: Path,
) -> None:
    pen_path = write_json(tmp_path / "ui.pen", legacy_pen())
    tree_path = write_json(tmp_path / "semantic-ui-tree.json", mapping_tree())
    before = pen_path.read_bytes()

    with pytest.raises(ValueError, match="context-map output must not overwrite"):
        write_pencil_context_map(pen_path, tree_path, pen_path, pen_out=pen_path)

    assert pen_path.read_bytes() == before


def test_write_pencil_context_map_updates_only_active_regions_in_place(tmp_path: Path) -> None:
    pen, archived_before = _active_archive_pen(archive_first=False)
    pen_path = write_json(tmp_path / "ui.pen", pen)
    tree_path = write_json(tmp_path / "semantic-ui-tree.json", semantic_tree())
    map_path = tmp_path / "pencil-context-map.json"

    result = write_pencil_context_map(
        pen_path,
        tree_path,
        map_path,
        pen_out=pen_path,
    )

    updated = json.loads(pen_path.read_text(encoding="utf-8"))
    assert result["status"] == "PASS"
    assert "semantic_id=checkout.pay" in updated["children"][0]["children"][1]["context"]
    assert updated["children"][1] == archived_before
    assert list(tmp_path.glob("*.pen")) == [pen_path]


def test_mapping_preserves_physical_root_paths_when_archive_precedes_active(
    tmp_path: Path,
) -> None:
    pen, _ = _active_archive_pen(archive_first=True)
    pen_path = write_json(tmp_path / "ui.pen", pen)
    tree_path = write_json(tmp_path / "semantic-ui-tree.json", semantic_tree())

    context_map = write_pencil_context_map(
        pen_path,
        tree_path,
        tmp_path / "pencil-context-map.json",
    )

    matched = {item["semantic_id"]: item["pencil_path"] for item in context_map["matched"]}
    assert matched["checkout"] == "1"
    assert matched["checkout.pay"] == "1.1"


def test_mapping_enriches_repeated_pencil_ids_by_exact_path(tmp_path: Path) -> None:
    pen, tree = _repeated_id_pen_and_tree()
    pen_path = write_json(tmp_path / "ui.pen", pen)
    tree_path = write_json(tmp_path / "semantic-ui-tree.json", tree)

    context_map = write_pencil_context_map(
        pen_path,
        tree_path,
        tmp_path / "pencil-context-map.json",
        pen_out=pen_path,
    )

    updated = json.loads(pen_path.read_text(encoding="utf-8"))
    matched_paths = {item["semantic_id"]: item["pencil_path"] for item in context_map["matched"]}
    assert matched_paths["checkout.label"] == "0.0"
    assert matched_paths["settings.label"] == "1.0"
    assert "semantic_id=checkout.label" in updated["children"][0]["children"][0]["context"]
    assert "semantic_id=settings.label" in updated["children"][1]["children"][0]["context"]


def test_map_pencil_context_cli_outputs_json_and_buckets(
    tmp_path: Path, governed_consumer_project
) -> None:
    pen_path = write_json(tmp_path / "ui.pen", legacy_pen())
    tree_path = write_json(tmp_path / "semantic-ui-tree.json", mapping_tree())
    map_path = tmp_path / "pencil-context-map.json"
    governed_consumer_project(tmp_path, pen_path)

    assert (
        main(
            [
                "map-pencil-context",
                str(pen_path),
                str(tree_path),
                "--out",
                str(map_path),
                "--pen-out",
                str(pen_path),
                "--create-placeholders",
                "--project",
                str(tmp_path),
                "--json",
            ]
        )
        == 0
    )
    context_map = json.loads(map_path.read_text(encoding="utf-8"))

    assert context_map["status"] == "PARTIAL"
    assert {key for key in ("matched", "created", "ambiguous", "unmapped")} <= set(context_map)
    assert [item["semantic_id"] for item in context_map["created"]] == ["checkout.help"]
    assert pen_path.exists()


def test_map_pencil_context_strict_anchors_fails_with_unmapped_suggestions(
    tmp_path: Path, governed_consumer_project
) -> None:
    pen_path = write_json(tmp_path / "ui.pen", legacy_pen())
    tree_path = write_json(tmp_path / "semantic-ui-tree.json", mapping_tree())
    map_path = tmp_path / "pencil-context-map.json"
    governed_consumer_project(tmp_path, pen_path)

    assert (
        main(
            [
                "map-pencil-context",
                str(pen_path),
                str(tree_path),
                "--out",
                str(map_path),
                "--strict-anchors",
                "--project",
                str(tmp_path),
                "--json",
            ]
        )
        == 1
    )
    context_map = json.loads(map_path.read_text(encoding="utf-8"))

    assert context_map["status"] == "PARTIAL"
    assert [item["semantic_id"] for item in context_map["unmapped"]] == ["checkout.help"]
    first_unmapped = context_map["unmapped"][0]
    assert first_unmapped["screen_id"] == "checkout"
    assert len(first_unmapped["candidates"]) == 3
    assert {"pencil_node_id", "pencil_path", "name", "label", "role"} <= set(
        first_unmapped["candidates"][0]
    )


def test_map_pencil_context_strict_anchors_fails_with_ambiguous_candidate_details(
    tmp_path: Path, governed_consumer_project
) -> None:
    pen = legacy_pen()
    pen["children"][0]["children"].insert(
        1,
        {
            "id": "duplicateTitle",
            "type": "text",
            "name": "Checkout duplicate",
            "content": "Checkout",
            "width": 240,
            "fill": "#222222",
        },
    )
    pen_path = write_json(tmp_path / "ui.pen", pen)
    tree_path = write_json(tmp_path / "semantic-ui-tree.json", mapping_tree())
    map_path = tmp_path / "pencil-context-map.json"
    governed_consumer_project(tmp_path, pen_path)

    assert (
        main(
            [
                "map-pencil-context",
                str(pen_path),
                str(tree_path),
                "--out",
                str(map_path),
                "--strict-anchors",
                "--project",
                str(tmp_path),
                "--json",
            ]
        )
        == 1
    )
    context_map = json.loads(map_path.read_text(encoding="utf-8"))

    assert [item["semantic_id"] for item in context_map["ambiguous"]] == ["checkout.title"]
    ambiguous = context_map["ambiguous"][0]
    assert ambiguous["screen_id"] == "checkout"
    assert [candidate["pencil_node_id"] for candidate in ambiguous["candidates"]] == [
        "hero",
        "duplicateTitle",
    ]
    assert {candidate["role"] for candidate in ambiguous["candidates"]} == {"text"}
