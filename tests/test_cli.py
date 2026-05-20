from __future__ import annotations

import json
from pathlib import Path

from penflow.cli import main


def test_demo_command_generates_pass_report(tmp_path: Path) -> None:
    out = tmp_path / "demo"
    assert main(["demo", "--out", str(out)]) == 0
    report = json.loads((out / "compare-report.json").read_text())
    assert report["status"] == "PASS"
    pen = json.loads((out / "ui.pen").read_text())
    assert pen["version"] == "2.11"
    assert isinstance(pen["children"][0]["context"], str)
    assert (out / "Checkout.jsx").exists()


def test_compare_tree_command_writes_reports(tmp_path: Path) -> None:
    assert main(["demo", "--out", str(tmp_path)]) == 0
    expected = tmp_path / "expected-ui-tree.json"
    actual = tmp_path / "actual-ui-tree.json"
    report = tmp_path / "report.json"
    markdown = tmp_path / "report.md"
    assert (
        main(
            [
                "compare-tree",
                str(expected),
                str(actual),
                "--out",
                str(report),
                "--markdown",
                str(markdown),
            ]
        )
        == 0
    )
    assert json.loads(report.read_text())["status"] == "PASS"
    assert "# Penflow Compare Report" in markdown.read_text()


def test_review_and_fix_report_commands_write_markdown(tmp_path: Path) -> None:
    assert main(["demo", "--out", str(tmp_path)]) == 0
    expected = tmp_path / "expected-ui-tree.json"
    actual = tmp_path / "actual-ui-tree.json"
    actual_tree = json.loads(actual.read_text())
    actual_tree["root"]["children"] = actual_tree["root"]["children"][:1]
    actual.write_text(json.dumps(actual_tree), encoding="utf-8")

    report = tmp_path / "report.json"
    review = tmp_path / "review.md"
    fix = tmp_path / "fix.md"
    assert main(["compare-tree", str(expected), str(actual), "--out", str(report)]) == 1
    assert main(["review-report", str(report), "--out", str(review)]) == 0
    assert main(["fix-report", str(report), "--out", str(fix)]) == 0
    assert "# Penflow Review" in review.read_text()
    assert "Expected semantic node is absent" in review.read_text()
    assert "# Penflow Fix Plan" in fix.read_text()
    assert "Add the missing runtime element" in fix.read_text()
