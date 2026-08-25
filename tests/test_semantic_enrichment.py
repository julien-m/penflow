# @spec FR-005: Canonical producer migration — .specs/features/074-penflow-doctor-consumer-project-hygiene/spec.md#fr-005
from __future__ import annotations

import copy
import errno
import json
import os
import stat
from pathlib import Path

import pytest

import penflow.json_filesystem as json_filesystem_module
from penflow.cli import main
from penflow.json_filesystem import write_json_atomically
from penflow.pen import parse_pen, validate_pen_context
from penflow.semantic_enrichment import enrich_pen_from_semantic_tree


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


def semantic_tree() -> dict:
    return {
        "version": 1,
        "kind": "semantic-ui-tree",
        "tree_id": "checkout-demo",
        "source": {"notes": ["test fixture"]},
        "flows": [
            {
                "id": "checkout",
                "title": "Checkout",
                "entry_screen": "checkout",
                "steps": [{"id": "checkout-step", "screen_id": "checkout", "intent": "checkout"}],
                "transitions": [{"from": "checkout", "to": "checkout", "trigger": "checkout.pay"}],
                "source_map": {"flow_spec": "flow-ui-contract/flows/checkout.md"},
            }
        ],
        "screens": [
            {
                "id": "checkout",
                "flow_id": "checkout",
                "surface": "web",
                "viewport": {"width": 390, "height": 844},
                "states": [{"name": "default"}],
                "validations": [],
                "side_effects": [],
                "source_map": {"screen_spec": "flow-ui-contract/screens/checkout.md"},
                "root": {
                    "semantic_id": "checkout",
                    "role": "screen",
                    "source_map": {"screen_spec": "flow-ui-contract/screens/checkout.md"},
                    "children": [
                        {
                            "semantic_id": "checkout.title",
                            "role": "text",
                            "text": "Checkout",
                            "source_map": {"screen_spec": "flow-ui-contract/screens/checkout.md"},
                        },
                        {
                            "semantic_id": "checkout.pay",
                            "role": "button",
                            "text": "Pay",
                            "intent": "submit_payment",
                            "binding": "checkout.payment_method",
                            "entity": "payment",
                            "test_id": "checkout-pay",
                            "states": [{"name": "enabled"}],
                            "validations": [{"rule": "payment_method_present"}],
                            "side_effects": [
                                {"effect": "create_payment_intent", "target": "payment"}
                            ],
                            "source_map": {
                                "flow_spec": "flow-ui-contract/flows/checkout.md",
                                "screen_spec": "flow-ui-contract/screens/checkout.md",
                            },
                        },
                    ],
                },
            }
        ],
    }


def legacy_pen() -> dict:
    return {
        "version": "2.11",
        "children": [
            {
                "id": "screen",
                "type": "frame",
                "name": "Checkout Screen",
                "x": 32,
                "y": 48,
                "width": 430,
                "height": 900,
                "layout": "vertical",
                "gap": 20,
                "padding": 32,
                "fill": "#FAFAFA",
                "context": "semantic_id=checkout; role=screen",
                "children": [
                    {
                        "id": "hero",
                        "type": "text",
                        "name": "Hero title",
                        "content": "Checkout",
                        "width": 360,
                        "fontSize": 30,
                        "fill": "#111111",
                    },
                    {
                        "id": "payButton",
                        "type": "frame",
                        "name": "Pay",
                        "width": 280,
                        "height": 52,
                        "layout": "horizontal",
                        "gap": 6,
                        "padding": [10, 18],
                        "fill": "#FF00AA",
                        "children": [
                            {
                                "id": "payLabel",
                                "type": "text",
                                "content": "Pay",
                                "fill": "#FFFFFF",
                            }
                        ],
                    },
                ],
            }
        ],
    }


def write_json(path: Path, data: dict) -> Path:
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def visual_snapshot(node: dict) -> dict:
    snapshot = {key: copy.deepcopy(node[key]) for key in VISUAL_KEYS if key in node}
    if "children" in node:
        snapshot["child_order"] = [child.get("id") for child in node["children"]]
    return snapshot


def test_enrich_pen_preserves_layout_and_injects_business_context(tmp_path: Path) -> None:
    pen = legacy_pen()
    pen_path = write_json(tmp_path / "ui.pen", pen)
    tree_path = write_json(tmp_path / "semantic-ui-tree.json", semantic_tree())
    before_root = visual_snapshot(pen["children"][0])
    before_button = visual_snapshot(pen["children"][0]["children"][1])

    result = enrich_pen_from_semantic_tree(pen_path, tree_path, pen_path)
    enriched = json.loads(pen_path.read_text(encoding="utf-8"))
    button = enriched["children"][0]["children"][1]

    assert result["status"] == "PASS"
    assert visual_snapshot(enriched["children"][0]) == before_root
    assert visual_snapshot(button) == before_button
    assert "semantic_id=checkout.pay" in button["context"]
    assert "role=button" in button["context"]
    assert "intent=submit_payment" in button["context"]
    assert "binding=checkout.payment_method" in button["context"]
    assert "entity=payment" in button["context"]
    assert "test_id=checkout-pay" in button["context"]
    assert button["source_map"]["flow_spec"].endswith("flows/checkout.md")
    assert button["semantic"]["validations"][0]["rule"] == "payment_method_present"
    assert validate_pen_context(parse_pen(pen_path)) == []


def test_enrich_pen_updates_only_active_regions_in_place(tmp_path: Path) -> None:
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
    archived_before = copy.deepcopy(archived)
    pen["children"].append(archived)
    pen_path = write_json(tmp_path / "ui.pen", pen)
    tree_path = write_json(tmp_path / "semantic-ui-tree.json", semantic_tree())

    result = enrich_pen_from_semantic_tree(pen_path, tree_path, pen_path)

    updated = json.loads(pen_path.read_text(encoding="utf-8"))
    assert result["status"] == "PASS"
    assert "semantic_id=checkout.pay" in updated["children"][0]["children"][1]["context"]
    assert updated["children"][1] == archived_before
    assert list(tmp_path.glob("*.pen")) == [pen_path]


def test_enrich_pen_is_deterministic(tmp_path: Path) -> None:
    tree_path = write_json(tmp_path / "semantic-ui-tree.json", semantic_tree())
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    first_dir.mkdir()
    second_dir.mkdir()
    first_path = write_json(first_dir / "ui.pen", legacy_pen())
    second_path = write_json(second_dir / "ui.pen", legacy_pen())

    enrich_pen_from_semantic_tree(first_path, tree_path, first_path)
    enrich_pen_from_semantic_tree(second_path, tree_path, second_path)

    assert first_path.read_bytes() == second_path.read_bytes()


def test_enrich_pen_rejects_distinct_destination_before_any_write(tmp_path: Path) -> None:
    pen_path = write_json(tmp_path / "ui.pen", legacy_pen())
    tree_path = write_json(tmp_path / "semantic-ui-tree.json", semantic_tree())
    peer_path = tmp_path / "ui.enriched.pen"
    before = pen_path.read_bytes()

    with pytest.raises(ValueError, match="canonical input ui.pen"):
        enrich_pen_from_semantic_tree(pen_path, tree_path, peer_path)

    assert pen_path.read_bytes() == before
    assert not peer_path.exists()


def test_atomic_writer_preserves_existing_mode_and_uses_private_new_file_mode(
    tmp_path: Path,
) -> None:
    existing = tmp_path / "existing.json"
    existing.write_text("{}\n", encoding="utf-8")
    existing.chmod(0o640)
    created = tmp_path / "created.json"

    write_json_atomically(existing, {"state": "updated"})
    write_json_atomically(created, {"state": "new"})

    assert stat.S_IMODE(existing.stat().st_mode) == 0o640
    assert stat.S_IMODE(created.stat().st_mode) == 0o600


def test_atomic_writer_ignores_only_documented_unsupported_directory_fsync(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path / "document.json"
    original_open = os.open

    def unsupported_directory_open(
        path: str | bytes | os.PathLike[str], flags: int, mode: int = 0o777
    ) -> int:
        if Path(os.fsdecode(path)) == tmp_path:
            raise OSError(errno.EINVAL, "directory fsync unsupported")
        return original_open(path, flags, mode)

    monkeypatch.setattr(json_filesystem_module.os, "open", unsupported_directory_open)

    write_json_atomically(destination, {"status": "PASS"})

    assert json.loads(destination.read_text(encoding="utf-8"))["status"] == "PASS"


def test_atomic_writer_propagates_unexpected_directory_fsync_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_open = os.open

    def failing_directory_open(
        path: str | bytes | os.PathLike[str], flags: int, mode: int = 0o777
    ) -> int:
        if Path(os.fsdecode(path)) == tmp_path:
            raise OSError(errno.EIO, "directory metadata failure")
        return original_open(path, flags, mode)

    monkeypatch.setattr(json_filesystem_module.os, "open", failing_directory_open)

    with pytest.raises(OSError, match="directory metadata failure"):
        write_json_atomically(tmp_path / "document.json", {"status": "PASS"})


def test_atomic_writer_does_not_hide_unix_directory_permission_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_open = os.open

    def denied_directory_open(
        path: str | bytes | os.PathLike[str], flags: int, mode: int = 0o777
    ) -> int:
        if Path(os.fsdecode(path)) == tmp_path:
            raise OSError(errno.EACCES, "directory permission denied")
        return original_open(path, flags, mode)

    monkeypatch.setattr(json_filesystem_module.os, "open", denied_directory_open)

    with pytest.raises(OSError, match="directory permission denied"):
        write_json_atomically(tmp_path / "document.json", {"status": "PASS"})


def test_atomic_writer_applies_mode_before_file_fsync(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    original_fchmod = os.fchmod
    original_fsync = os.fsync

    def recording_fchmod(file_descriptor: int, mode: int) -> None:
        events.append("fchmod")
        original_fchmod(file_descriptor, mode)

    def recording_fsync(file_descriptor: int) -> None:
        events.append("fsync")
        original_fsync(file_descriptor)

    monkeypatch.setattr(json_filesystem_module.os, "fchmod", recording_fchmod)
    monkeypatch.setattr(json_filesystem_module.os, "fsync", recording_fsync)

    write_json_atomically(tmp_path / "document.json", {"status": "PASS"})

    assert events[0:2] == ["fchmod", "fsync"]


def test_enrich_pen_reports_ambiguous_conservative_match_without_overwrite(tmp_path: Path) -> None:
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
    tree_path = write_json(tmp_path / "semantic-ui-tree.json", semantic_tree())

    result = enrich_pen_from_semantic_tree(pen_path, tree_path, pen_path)
    enriched = json.loads(pen_path.read_text(encoding="utf-8"))

    assert result["status"] == "PARTIAL"
    assert any(issue["code"] == "enrich.match_ambiguous" for issue in result["issues"])
    assert "context" not in enriched["children"][0]["children"][0]
    assert "context" not in enriched["children"][0]["children"][1]


def test_enrich_pen_cli_outputs_json_and_validate_pen_compatible(
    tmp_path: Path, governed_consumer_project
) -> None:
    pen_path = write_json(tmp_path / "ui.pen", legacy_pen())
    tree_path = write_json(tmp_path / "semantic-ui-tree.json", semantic_tree())
    governed_consumer_project(tmp_path, pen_path)

    assert (
        main(
            [
                "enrich-pen",
                str(pen_path),
                str(tree_path),
                "--out",
                str(pen_path),
                "--project",
                str(tmp_path),
                "--json",
            ]
        )
        == 0
    )
    assert main(["validate-pen", str(pen_path), "--project", str(tmp_path), "--json"]) == 0
