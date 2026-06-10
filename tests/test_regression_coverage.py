# @spec(AC-013)
# @spec(FR-013)
from __future__ import annotations

import json
from pathlib import Path

from penflow.cli import main
from penflow.flow_specs import validate_flow_specs_dir


ROOT = Path(__file__).resolve().parent.parent
FULL = ROOT / "examples" / "full"
LEGACY = ROOT / "examples" / "legacy"


def test_validate_flow_specs_accepts_full_demo_contract() -> None:
    report = validate_flow_specs_dir(FULL / "flow-ui-contract")

    assert report["status"] == "PASS"
    assert report["flows"] == 1
    assert report["screens"] == 1
    assert report["issues"] == []


def test_validate_flow_specs_cli_reports_invalid_markdown(tmp_path: Path) -> None:
    specs = tmp_path / "flow-ui-contract"
    (specs / "flows").mkdir(parents=True)
    (specs / "screens").mkdir()
    (specs / "flows" / "broken.md").write_text("# Missing frontmatter\n", encoding="utf-8")

    assert main(["validate-flow-specs", str(specs), "--json"]) == 1


def test_c16_final_workflow_regression_chain(tmp_path: Path) -> None:
    semantic_tree = tmp_path / "semantic-ui-tree.json"
    drafted_pen = tmp_path / "ui.pen"
    expected_tree = tmp_path / "expected-ui-tree.json"
    enriched_pen = tmp_path / "ui.enriched.pen"
    reverse_output = tmp_path / "reverse-output"
    compare_json = tmp_path / "compare.json"
    review_json = tmp_path / "review.json"
    fix_json = tmp_path / "fix.json"

    assert main(["validate-flow-specs", str(FULL / "flow-ui-contract"), "--json"]) == 0
    assert (
        main(
            [
                "export-semantic-tree",
                str(FULL / "flow-ui-contract" / "contract.json"),
                "--out",
                str(semantic_tree),
                "--json",
            ]
        )
        == 0
    )
    assert main(["validate-semantic-tree", str(semantic_tree), "--json"]) == 0
    assert (
        main(["draft-pen-from-tree", str(semantic_tree), "--out", str(drafted_pen), "--json"]) == 0
    )
    assert main(["validate-pen", str(drafted_pen), "--json"]) == 0
    assert main(["export-expected", str(drafted_pen), "-o", str(expected_tree), "--json"]) == 0

    assert (
        main(
            [
                "enrich-pen",
                str(LEGACY / "ui.pen"),
                str(semantic_tree),
                "--out",
                str(enriched_pen),
                "--json",
            ]
        )
        == 0
    )
    assert main(["validate-pen", str(enriched_pen), "--json"]) == 0

    # Strict default (feature 049): the legacy reverse output still needs
    # clarification, so the command exits 1; --lenient keeps the chain green.
    assert (
        main(["reverse-pen", str(LEGACY / "ui.pen"), "--out", str(reverse_output), "--json"]) == 1
    )
    assert (
        main(
            [
                "reverse-pen",
                str(LEGACY / "ui.pen"),
                "--out",
                str(reverse_output),
                "--lenient",
                "--json",
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "validate-semantic-tree",
                str(reverse_output / "semantic-ui-tree.json"),
                "--json",
            ]
        )
        == 0
    )

    assert main(["validate-actual", str(FULL / "actual-ui-tree.json"), "--schema", "--json"]) == 0
    assert (
        main(
            [
                "compare-tree",
                str(expected_tree),
                str(FULL / "actual-ui-tree.json"),
                "--out",
                str(compare_json),
                "--json",
            ]
        )
        == 0
    )
    assert main(["review-report", str(compare_json), "--out", str(review_json)]) == 0
    assert main(["fix-report", str(compare_json), "--out", str(fix_json)]) == 0

    assert json.loads(compare_json.read_text(encoding="utf-8"))["status"] == "PASS"
    assert json.loads(review_json.read_text(encoding="utf-8"))["kind"] == "penflow-review-report"
    assert json.loads(fix_json.read_text(encoding="utf-8"))["kind"] == "penflow-fix-report"
