from __future__ import annotations

import json
from pathlib import Path

import pytest

from penflow.cli import main
from penflow.flow_contract_migration import migrate_flow_md_to_contract_json


def test_review_and_fix_report_write_json_objects(tmp_path: Path) -> None:
    assert main(["demo", "--out", str(tmp_path)]) == 0
    actual = json.loads((tmp_path / "actual-ui-tree.json").read_text(encoding="utf-8"))
    actual["root"]["children"] = actual["root"]["children"][:1]
    (tmp_path / "actual-ui-tree.json").write_text(json.dumps(actual), encoding="utf-8")
    compare = tmp_path / "compare-report.json"
    review = tmp_path / "review-report.json"
    fix = tmp_path / "fix-report.json"

    assert (
        main(
            [
                "compare-tree",
                str(tmp_path / "expected-ui-tree.json"),
                str(tmp_path / "actual-ui-tree.json"),
                "--out",
                str(compare),
                "--json",
            ]
        )
        == 1
    )
    assert main(["review-report", str(compare), "--out", str(review), "--json"]) == 0
    assert main(["fix-report", str(compare), "--out", str(fix), "--json"]) == 0

    review_report = json.loads(review.read_text(encoding="utf-8"))
    fix_report = json.loads(fix.read_text(encoding="utf-8"))
    assert review_report["kind"] == "penflow-review-report"
    assert fix_report["kind"] == "penflow-fix-report"
    assert review_report["issues"][0]["likely_cause"]
    assert fix_report["fixes"][0]["fix"]
    assert main(["validate-report", str(compare), "--schema", "--json"]) == 0
    assert main(["validate-report", str(review), "--schema", "--json"]) == 0
    assert main(["validate-report", str(fix), "--schema", "--json"]) == 0


def test_validate_report_rejects_unknown_schema(tmp_path: Path) -> None:
    unknown = tmp_path / "unknown-report.json"
    unknown.write_text(json.dumps({"kind": "unknown", "status": "PASS"}), encoding="utf-8")

    assert main(["validate-report", str(unknown), "--schema", "--json"]) == 2


def test_markdown_report_paths_are_rejected_in_strict_json_mode(tmp_path: Path) -> None:
    assert main(["demo", "--out", str(tmp_path)]) == 0
    markdown = tmp_path / "compare-report.md"

    with pytest.raises(SystemExit) as error:
        main(
            [
                "compare-tree",
                str(tmp_path / "expected-ui-tree.json"),
                str(tmp_path / "actual-ui-tree.json"),
                "--out",
                str(tmp_path / "compare-report.json"),
                "--markdown",
                str(markdown),
                "--json",
            ]
        )
    assert error.value.code == 2
    assert not markdown.exists()


def test_mockup_validation_visual_report_is_json_schema_valid() -> None:
    report = Path("examples/full/.mockup-validation/visual-evidence/visual-report.json")
    manifest = Path("examples/full/.mockup-validation/visual-evidence/manifest.json")

    assert report.exists()
    assert manifest.exists()
    assert main(["validate-report", str(report), "--schema", "--json"]) == 0
    assert main(["validate-report", str(manifest), "--schema", "--json"]) == 0


def test_explicit_markdown_migration_marks_review_and_clarifications(tmp_path: Path) -> None:
    specs = tmp_path / "flow-ui-contract"
    flows = specs / "flows"
    screens = specs / "screens"
    flows.mkdir(parents=True)
    screens.mkdir()
    (flows / "checkout.md").write_text(
        "---\nflow: checkout\ntitle: Checkout\npriority: P1\nstatus: draft\n---\n\n# Checkout\n",
        encoding="utf-8",
    )
    (screens / "checkout.md").write_text(
        "---\nscreen: checkout\nflow: checkout\ntitle: Checkout\nmockup: checkout.png\n---\n\n# Checkout\n",
        encoding="utf-8",
    )

    report = migrate_flow_md_to_contract_json(specs, specs / "contract.json")
    contract = json.loads((specs / "contract.json").read_text(encoding="utf-8"))

    assert report["status"] == "PASS"
    assert report["needs_review"] is True
    assert contract["needs_review"] is True
    assert contract["needs_clarification"]
    assert main(["validate-flow-contract", str(specs / "contract.json"), "--json"]) == 1
