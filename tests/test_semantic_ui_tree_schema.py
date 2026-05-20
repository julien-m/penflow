from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = ROOT / "penflow" / "schemas" / "semantic-ui-tree.schema.json"
EXAMPLE_PATH = ROOT / "examples" / "demo" / "semantic-ui-tree.json"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_semantic_ui_tree_schema_defines_pre_pencil_contract() -> None:
    schema = load_json(SCHEMA_PATH)

    assert schema["title"] == "Penflow Semantic UI Tree"
    assert schema["$id"].endswith("/semantic-ui-tree.schema.json")
    assert schema["properties"]["kind"]["const"] == "semantic-ui-tree"
    assert {"version", "kind", "tree_id", "source", "flows", "screens"}.issubset(schema["required"])
    assert "actual" not in schema["description"].lower()


def test_semantic_ui_tree_schema_covers_required_contract_surfaces() -> None:
    schema = load_json(SCHEMA_PATH)
    definitions = schema["$defs"]
    node_props = definitions["semanticNode"]["properties"]
    screen_props = definitions["screen"]["properties"]
    flow_props = definitions["flow"]["properties"]

    for key in (
        "semantic_id",
        "role",
        "intent",
        "binding",
        "entity",
        "states",
        "validations",
        "side_effects",
        "source_map",
        "children",
    ):
        assert key in node_props
    assert {"id", "title", "entry_screen", "steps", "transitions", "source_map"}.issubset(
        flow_props
    )
    assert {"id", "flow_id", "surface", "root", "states", "validations", "side_effects"}.issubset(
        screen_props
    )


def test_semantic_ui_tree_example_uses_schema_fields_deterministically() -> None:
    example = load_json(EXAMPLE_PATH)

    assert example["kind"] == "semantic-ui-tree"
    assert example["version"] == 1
    assert example["flows"][0]["entry_screen"] == "checkout"
    screen = example["screens"][0]
    assert screen["root"]["semantic_id"] == "checkout"
    assert screen["root"]["children"][1]["role"] == "button"
    assert screen["root"]["children"][1]["intent"] == "submit_payment"
    assert screen["root"]["children"][1]["binding"] == "checkout.payment_method"
    assert screen["root"]["children"][1]["entity"] == "payment"
    assert screen["root"]["children"][1]["validations"][0]["rule"] == "payment_method_present"
    assert screen["root"]["children"][1]["side_effects"][0]["effect"] == "create_payment_intent"
    assert screen["root"]["children"][1]["source_map"]["flow_spec"].endswith("checkout.md")


def test_semantic_schema_does_not_add_feature_036_or_later_runtime_pipeline() -> None:
    # Feature 037 (document-validate-actual-ui-tree) is in scope — it ships
    # schema + docs only, no runtime adapter. Feature 038 (runtime adapter
    # guides) is in scope — it ships docs + JSON fixtures + in-process pytest
    # only, still no runtime adapter inside `penflow/`. Feature 039 is in
    # scope — it ships the full local demo fixture. Feature 040 is in scope —
    # it ships docs/tests only. Feature 041 is in scope — it ships regression
    # coverage only. Feature 042 remains guarded.
    future_feature_dirs: list[Path] = []
    for feature_number in range(42, 43):
        future_feature_dirs.extend((ROOT / ".specs" / "features").glob(f"{feature_number:03d}-*"))
    assert future_feature_dirs == []
    assert not (ROOT / "penflow" / "semantic_validator.py").exists()
    assert not (ROOT / "penflow" / "pencil_enrichment.py").exists()
    assert not (ROOT / "penflow" / "pencil_draft_from_tree.py").exists()
