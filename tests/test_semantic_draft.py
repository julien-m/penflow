# @spec(AC-011)
# @spec(FR-001)
# @spec FR-005: Canonical producer migration — .specs/features/074-penflow-doctor-consumer-project-hygiene/spec.md#fr-005
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from penflow.cli import main
from penflow.pen import parse_pen, validate_pen_context
from penflow.pen_lifecycle import CanvasLifecycleError
from penflow.semantic_draft import pen_draft_from_semantic_tree, write_pen_draft_from_semantic_tree


ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "examples" / "demo" / "semantic-ui-tree.json"


def load_example_without_mockup() -> dict:
    tree = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    tree["source"].pop("mockup", None)
    for screen in tree["screens"]:
        screen["source_map"].pop("mockup", None)
        for node in _walk(screen["root"]):
            node.get("source_map", {}).pop("mockup", None)
    return tree


def _walk(node: dict) -> list[dict]:
    nodes = [node]
    for child in node.get("children", []) or []:
        nodes.extend(_walk(child))
    return nodes


def _first_button(root: dict) -> dict:
    return next(child for child in root["children"] if "role=button" in child.get("context", ""))


def _two_screen_tree() -> dict:
    """Build equivalent checkout/settings screens for revision identity tests."""
    tree = load_example_without_mockup()
    second = copy.deepcopy(tree["screens"][0])
    second["id"] = "settings"
    second["root"]["semantic_id"] = "settings"
    for index, child in enumerate(second["root"]["children"]):
        child["semantic_id"] = f"settings.{index}"
        child.pop("test_id", None)
    tree["screens"].append(second)
    return tree


def _lifecycle_region(
    *, identifier: str, logical_screen_id: str, state: str, revision_id: str
) -> dict:
    """Build one minimal top-level managed canvas region."""
    return {
        "id": identifier,
        "type": "frame",
        "name": identifier,
        "context": f"semantic_id={logical_screen_id}; role=screen",
        "penflow": {
            "lifecycle": {
                "schema_version": 1,
                "state": state,
                "logical_screen_id": logical_screen_id,
                "revision_id": revision_id,
            }
        },
        "children": [],
    }


def test_write_pen_draft_from_semantic_tree_creates_valid_pen_with_context(tmp_path: Path) -> None:
    tree_path = tmp_path / "semantic-ui-tree.json"
    tree_path.write_text(json.dumps(load_example_without_mockup()), encoding="utf-8")
    out_path = tmp_path / "ui.pen"

    draft = write_pen_draft_from_semantic_tree(tree_path, out_path)

    assert draft["version"] == "2.11"
    root = draft["children"][0]
    button = _first_button(root)
    assert root["name"] == "checkout"
    lifecycle = root["penflow"]["lifecycle"]
    assert lifecycle["schema_version"] == 1
    assert lifecycle["state"] == "active"
    assert lifecycle["logical_screen_id"] == "checkout"
    assert lifecycle["revision_id"].startswith("checkout-r-")
    assert "role=screen" in root["context"]
    assert "semantic_id=checkout" in root["context"]
    assert "role=button" in button["context"]
    assert "intent=submit_payment" in button["context"]
    assert "binding=checkout.selected_payment_method" in button["context"]
    assert "entity=checkout" in button["context"]
    assert "test_id=checkout-pay-now" in button["context"]
    assert button["source_map"]["contract"].endswith("contract.json")
    assert validate_pen_context(parse_pen(out_path)) == []


def test_write_pen_draft_from_semantic_tree_is_deterministic(tmp_path: Path) -> None:
    tree_path = tmp_path / "semantic-ui-tree.json"
    tree_path.write_text(json.dumps(load_example_without_mockup()), encoding="utf-8")
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    first_dir.mkdir()
    second_dir.mkdir()
    first_path = first_dir / "ui.pen"
    second_path = second_dir / "ui.pen"

    write_pen_draft_from_semantic_tree(tree_path, first_path)
    write_pen_draft_from_semantic_tree(tree_path, second_path)

    assert first_path.read_bytes() == second_path.read_bytes()


def test_new_top_level_screens_have_unique_deterministic_lifecycle_revisions() -> None:
    tree = _two_screen_tree()

    first = pen_draft_from_semantic_tree(tree)
    repeated = pen_draft_from_semantic_tree(tree)
    reordered_tree = copy.deepcopy(tree)
    reordered_tree["screens"].reverse()
    reordered = pen_draft_from_semantic_tree(reordered_tree)
    lifecycles = [child["penflow"]["lifecycle"] for child in first["children"]]
    reordered_revisions = {
        child["penflow"]["lifecycle"]["logical_screen_id"]: child["penflow"]["lifecycle"][
            "revision_id"
        ]
        for child in reordered["children"]
    }

    assert first == repeated
    assert {lifecycle["state"] for lifecycle in lifecycles} == {"active"}
    assert {lifecycle["logical_screen_id"] for lifecycle in lifecycles} == {
        "checkout",
        "settings",
    }
    assert len({lifecycle["revision_id"] for lifecycle in lifecycles}) == 2
    assert {
        lifecycle["logical_screen_id"]: lifecycle["revision_id"] for lifecycle in lifecycles
    } == reordered_revisions


def test_write_pen_draft_updates_ui_pen_without_dropping_unrelated_regions(
    tmp_path: Path,
) -> None:
    tree_path = tmp_path / "semantic-ui-tree.json"
    tree_path.write_text(json.dumps(load_example_without_mockup()), encoding="utf-8")
    out_path = tmp_path / "ui.pen"
    archived = _lifecycle_region(
        identifier="checkoutArchived",
        logical_screen_id="checkout",
        state="archive",
        revision_id="checkout-r1",
    )
    unrelated = {
        "id": "settingsScreen",
        "type": "frame",
        "name": "Settings",
        "context": "semantic_id=settings",
        "children": [],
    }
    out_path.write_text(
        json.dumps(
            {
                "version": "2.11",
                "children": [archived, unrelated],
                "variables": {"consumer-token": {"type": "color", "value": "#123456"}},
            }
        ),
        encoding="utf-8",
    )

    write_pen_draft_from_semantic_tree(tree_path, out_path)

    updated = json.loads(out_path.read_text(encoding="utf-8"))
    assert [node["id"] for node in updated["children"]] == [
        "checkoutArchived",
        "settingsScreen",
        "checkout",
    ]
    assert updated["children"][0] == archived
    assert updated["children"][1] == unrelated
    assert updated["variables"]["consumer-token"]["value"] == "#123456"
    assert list(tmp_path.glob("*.pen")) == [out_path]


def test_write_pen_draft_preserves_managed_active_lifecycle_metadata(tmp_path: Path) -> None:
    tree_path = tmp_path / "semantic-ui-tree.json"
    tree_path.write_text(json.dumps(load_example_without_mockup()), encoding="utf-8")
    out_path = tmp_path / "ui.pen"
    lifecycle = {
        "schema_version": 1,
        "state": "active",
        "logical_screen_id": "checkout",
        "revision_id": "checkout-r7",
    }
    active = _lifecycle_region(
        identifier="checkout-r7",
        logical_screen_id="checkout",
        state="active",
        revision_id="checkout-r7",
    )
    active["penflow"]["stale_generation"] = {"artifact": "obsolete"}
    out_path.write_text(json.dumps({"version": "2.11", "children": [active]}), encoding="utf-8")

    write_pen_draft_from_semantic_tree(tree_path, out_path)

    updated = json.loads(out_path.read_text(encoding="utf-8"))
    assert updated["children"][0]["penflow"]["lifecycle"] == lifecycle
    assert "stale_generation" not in updated["children"][0]["penflow"]
    assert updated["children"][0]["id"] != "checkout-r7"


def test_write_pen_draft_rejects_non_object_existing_variables(tmp_path: Path) -> None:
    tree_path = tmp_path / "semantic-ui-tree.json"
    tree_path.write_text(json.dumps(load_example_without_mockup()), encoding="utf-8")
    out_path = tmp_path / "ui.pen"
    existing = pen_draft_from_semantic_tree(load_example_without_mockup())
    existing["variables"] = []
    out_path.write_text(json.dumps(existing), encoding="utf-8")

    with pytest.raises(CanvasLifecycleError) as error:
        write_pen_draft_from_semantic_tree(tree_path, out_path)

    assert error.value.findings[0].code == "canvas.variables_invalid"


def test_draft_pen_from_tree_cli_writes_json_and_validate_pen_compatible(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], governed_consumer_project
) -> None:
    tree_path = tmp_path / "semantic-ui-tree.json"
    tree_path.write_text(json.dumps(load_example_without_mockup()), encoding="utf-8")
    out_path = tmp_path / "ui.pen"
    governed_consumer_project(tmp_path, out_path)

    assert (
        main(
            [
                "draft-pen-from-tree",
                str(tree_path),
                "--out",
                str(out_path),
                "--project",
                str(tmp_path),
                "--json",
            ]
        )
        == 0
    )
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "PASS"
    assert report["fidelity"] == "wireframe"
    assert main(["validate-pen", str(out_path), "--project", str(tmp_path), "--json"]) == 0


def test_write_pen_draft_from_semantic_tree_applies_theme_tokens(tmp_path: Path) -> None:
    tree_path = tmp_path / "semantic-ui-tree.json"
    tree_path.write_text(json.dumps(load_example_without_mockup()), encoding="utf-8")
    theme_path = tmp_path / "theme.css"
    theme_path.write_text(
        """:root {
  --background: #f6f4ef;
  --foreground: #25302a;
  --card: #ffffff;
  --primary: #0f5132;
  --primary-foreground: #fffaf0;
  --border: #d7d2c8;
  --muted: #ebe6da;
  --muted-foreground: #6a655c;
  --radius: 0.5rem;
  --font-sans: Inter, system-ui, sans-serif;
}
""",
        encoding="utf-8",
    )
    out_path = tmp_path / "ui.pen"

    draft = write_pen_draft_from_semantic_tree(tree_path, out_path, theme_css_path=theme_path)

    assert draft["variables"]["pf-primary"] == {"type": "color", "value": "#0f5132"}
    root = draft["children"][0]
    button = _first_button(root)
    assert root["fill"] == "$pf-background"
    assert button["fill"] == "$pf-primary"
    assert "#0057FF" not in out_path.read_text(encoding="utf-8")
    assert "semantic_id=checkout.pay-now" in button["context"]


def test_draft_propagates_light_root_values_when_dark_block_present(tmp_path: Path) -> None:
    # Invariant: drafted pens carry the light `:root` palette — a `.dark`
    # override block in theme.css must never leak into draft variables
    # (GAP-046-01: the last-declared dark values used to win).
    tree_path = tmp_path / "semantic-ui-tree.json"
    tree_path.write_text(json.dumps(load_example_without_mockup()), encoding="utf-8")
    theme_path = tmp_path / "theme.css"
    theme_path.write_text(
        """:root {
  --background: #f6f4ef;
  --foreground: #25302a;
  --card: #ffffff;
  --primary: #0f5132;
  --primary-foreground: #fffaf0;
  --border: #d7d2c8;
}
.dark {
  --background: #0b1120;
  --foreground: #e2e8f0;
  --primary: #3b82f6;
}
""",
        encoding="utf-8",
    )
    out_path = tmp_path / "ui.pen"

    draft = write_pen_draft_from_semantic_tree(tree_path, out_path, theme_css_path=theme_path)

    assert draft["variables"]["pf-primary"] == {"type": "color", "value": "#0f5132"}
    assert draft["variables"]["pf-background"] == {"type": "color", "value": "#f6f4ef"}
    raw = out_path.read_text(encoding="utf-8")
    assert "#3b82f6" not in raw
    assert "#0b1120" not in raw


def test_draft_pen_from_tree_cli_accepts_theme_css(
    tmp_path: Path, governed_consumer_project
) -> None:
    tree_path = tmp_path / "semantic-ui-tree.json"
    tree_path.write_text(json.dumps(load_example_without_mockup()), encoding="utf-8")
    theme_path = tmp_path / "theme.css"
    theme_path.write_text(
        ":root { --background: #f6f4ef; --foreground: #25302a; --primary: #0f5132; --primary-foreground: #fffaf0; --card: #ffffff; --border: #d7d2c8; }",
        encoding="utf-8",
    )
    out_path = tmp_path / "ui.pen"
    governed_consumer_project(tmp_path, out_path)

    assert (
        main(
            [
                "draft-pen-from-tree",
                str(tree_path),
                "--out",
                str(out_path),
                "--theme-css",
                str(theme_path),
                "--project",
                str(tmp_path),
                "--json",
            ]
        )
        == 0
    )
    data = json.loads(out_path.read_text(encoding="utf-8"))

    assert data["variables"]["pf-primary"]["value"] == "#0f5132"
    assert data["children"][0]["fill"] == "$pf-background"
    assert main(["validate-pen", str(out_path), "--json"]) == 0
