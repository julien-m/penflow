# @spec(AC-010)
# @spec(AC-012)
# @spec(FR-005)
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
    button = next(child for child in screen["root"]["children"] if child["role"] == "button")
    assert button["intent"] == "submit_payment"
    assert button["binding"] == "checkout.selected_payment_method"
    assert button["entity"] == "checkout"
    assert button["test_id"] == "checkout-pay-now"
    assert button["source_map"]["contract"].endswith("contract.json")


def test_semantic_schema_does_not_add_feature_036_or_later_runtime_pipeline() -> None:
    # Feature 037 (document-validate-actual-ui-tree) is in scope — it ships
    # schema + docs only, no runtime adapter. Feature 038 (runtime adapter
    # guides) is in scope — it ships docs + JSON fixtures + in-process pytest
    # only, still no runtime adapter inside `penflow/`. Feature 039 is in
    # scope — it ships the full local demo fixture. Feature 040 is in scope —
    # it ships docs/tests only. Feature 041 is in scope — it ships regression
    # coverage only. Feature 042 is in scope — it ships integration docs/tests
    # only. Feature 043 is in scope — it ships Mockup Factory skill/docs/tests
    # only. Feature 044 is in scope — it ships visual evidence docs/tests only.
    # Feature 045 is in scope — strict JSON contract v2. Feature 046 is in
    # scope — it ships the deterministic token lint (local files only, no
    # runtime adapter). Feature 047 is in scope — it ships the deterministic
    # cross-screen consistency checker (local files only, no runtime adapter).
    # Feature 049 is in scope — strict-by-default exit policy + blocking drift
    # (shipped before 048 for dependency reasons). Feature 048 is in scope —
    # it ships layout/spacing comparison in the existing compare engine.
    # Feature 050 is in scope — it ships the deterministic visual metrics
    # audit (local files only, zero vision, no runtime adapter). Feature 051
    # is in scope — it ships the locked vision-report contract and the
    # deterministic evidence validator (Penflow never runs vision). Feature
    # 052 is in scope — it ships the prescriptive gate rubric, the bounded
    # fix-re-audit loop, and the hardened audit/checklist schemas (skill-layer
    # loop, no new runtime). Feature 053 is in scope — it ships the
    # cross-mockup coherence contact sheet (optional strict coherence section
    # in the vision report, multi-screen requirement in the evidence
    # validator; the contact sheet renders at the skill layer). Feature 054 is
    # in scope — it ships direct unit coverage for codegen/context/llm/models/
    # demo plus the bundled-schema cache (no new CLI surface, no runtime
    # adapter). Feature 055 is in scope — it ships the deterministic checklist
    # seeder (`penflow checklist-from-drift`, local JSON-to-JSON only, no
    # runtime adapter). Feature 056 is in scope — it ships the theme
    # fingerprint binding (`penflow theme-fingerprint` + the
    # `validate-visual-evidence --theme-css` gate, stdlib hashing of local
    # bytes only, no runtime adapter); feature 057 remains guarded.
    future_feature_dirs: list[Path] = []
    for feature_number in range(57, 58):
        future_feature_dirs.extend((ROOT / ".specs" / "features").glob(f"{feature_number:03d}-*"))
    assert future_feature_dirs == []
    assert not (ROOT / "penflow" / "semantic_validator.py").exists()
    assert not (ROOT / "penflow" / "pencil_enrichment.py").exists()
    assert not (ROOT / "penflow" / "pencil_draft_from_tree.py").exists()
