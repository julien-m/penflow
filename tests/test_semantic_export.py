from __future__ import annotations

import json
import shutil
from pathlib import Path

from penflow.cli import main
from penflow.semantic import semantic_tree_from_specs
from penflow.semantic_validation import validate_semantic_tree


ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / ".agent-sync" / "skills" / "flow-ui-contract" / "tests" / "fixtures"


def build_specs_dir(tmp_path: Path) -> Path:
    specs = tmp_path / "flow-ui-contract"
    flows = specs / "flows"
    screens = specs / "screens"
    flows.mkdir(parents=True)
    screens.mkdir()
    shutil.copy(FIXTURES / "valid_flow.md", flows / "booking.md")
    shutil.copy(FIXTURES / "valid_screen.md", screens / "mobile_booking_form.md")
    return specs


def test_semantic_tree_from_specs_maps_flow_screen_and_actions(tmp_path: Path) -> None:
    specs = build_specs_dir(tmp_path)

    tree = semantic_tree_from_specs(specs)

    assert tree["kind"] == "semantic-ui-tree"
    assert tree["tree_id"] == "flow-ui-contract"
    assert tree["flows"][0]["id"] == "booking"
    assert tree["flows"][0]["entry_screen"] == "mobile_booking_form"
    assert tree["flows"][0]["source_map"]["flow_spec"].endswith("flows/booking.md")
    assert tree["screens"][0]["id"] == "mobile_booking_form"
    assert tree["screens"][0]["flow_id"] == "booking"
    assert tree["screens"][0]["states"][0]["name"] == "chargement"
    root = tree["screens"][0]["root"]
    assert root["semantic_id"] == "mobile_booking_form"
    action_nodes = [node for node in root["children"] if node["role"] in {"button", "link"}]
    assert action_nodes[0]["semantic_id"] == "mobile_booking_form.bouton-confirmer"
    assert action_nodes[0]["intent"] == "post-bookings-redirection-confirmation"
    assert action_nodes[0]["source_map"]["notes"] == ["section: ## Actions"]
    assert validate_semantic_tree(tree) == []


def test_semantic_tree_from_specs_preserves_web_desktop_viewport(tmp_path: Path) -> None:
    specs = tmp_path / "flow-ui-contract"
    flows = specs / "flows"
    screens = specs / "screens"
    flows.mkdir(parents=True)
    screens.mkdir()
    (flows / "booking.md").write_text(
        """---
flow: booking_dashboard
title: Booking Dashboard
mockups:
  - bookings_dashboard
surfaces:
  - web
---

# Flow Spec: Booking Dashboard
""",
        encoding="utf-8",
    )
    (screens / "bookings_dashboard.md").write_text(
        """---
screen: bookings_dashboard
flow: booking_dashboard
mockup: bookings_dashboard.png
platform: web-desktop
viewport: "1440x900"
---

# Écran — Bookings Dashboard

## Données affichées

- Page title
""",
        encoding="utf-8",
    )

    tree = semantic_tree_from_specs(specs)

    assert tree["screens"][0]["surface"] == "web-desktop"
    assert tree["screens"][0]["viewport"] == {"width": 1440, "height": 900}


def test_semantic_tree_from_specs_keeps_escape_and_backdrop_as_non_visual_actions(
    tmp_path: Path,
) -> None:
    specs = tmp_path / "flow-ui-contract"
    flows = specs / "flows"
    screens = specs / "screens"
    flows.mkdir(parents=True)
    screens.mkdir()
    (flows / "booking.md").write_text(
        """---
flow: booking_dashboard
title: Booking Dashboard
mockups:
  - appointment_detail_modal
surfaces:
  - web
---

# Flow Spec: Booking Dashboard

```mermaid
flowchart TD
  A[appointment_detail_modal] -- "Presses Escape" --> B[bookings_dashboard]
  A -- "Clicks backdrop" --> B
```
""",
        encoding="utf-8",
    )
    (screens / "appointment_detail_modal.md").write_text(
        """---
screen: appointment_detail_modal
flow: booking_dashboard
mockup: appointment_detail_modal.png
platform: web-desktop
viewport:
  width: 1440
  height: 900
---

# Écran — Appointment Detail Modal

## Données affichées

- Appointment details title

## Actions

| Élément | Type | Effet |
|---------|------|-------|
| X close button | icon button | Closes modal |
| Escape key | keyboard event | Closes modal |
| Backdrop click | flow transition | Closes modal |
""",
        encoding="utf-8",
    )

    tree = semantic_tree_from_specs(specs)
    children = tree["screens"][0]["root"]["children"]

    assert [child["text"] for child in children if child["role"] == "button"] == ["X close button"]
    assert all(child["text"] != "Escape key" for child in children)
    assert all(child["text"] != "Backdrop click" for child in children)


def test_export_semantic_tree_cli_writes_stable_json(tmp_path: Path) -> None:
    specs = build_specs_dir(tmp_path)
    first = tmp_path / "semantic-ui-tree.json"
    second = tmp_path / "semantic-ui-tree-second.json"

    assert main(["export-semantic-tree", str(specs), "--out", str(first), "--json"]) == 0
    assert main(["export-semantic-tree", str(specs), "--out", str(second), "--json"]) == 0

    assert first.read_bytes() == second.read_bytes()
    exported = json.loads(first.read_text(encoding="utf-8"))
    assert exported["screens"][0]["root"]["children"][0]["source_map"]["screen_spec"].endswith(
        "screens/mobile_booking_form.md"
    )
