from __future__ import annotations

import json
from pathlib import Path

from penflow.cli import main


def test_demo_command_generates_pass_report(tmp_path: Path) -> None:
    out = tmp_path / "demo"
    assert main(["demo", "--out", str(out)]) == 0
    report = json.loads((out / "compare-report.json").read_text())
    assert report["status"] == "PASS"
    assert (out / "Checkout.jsx").exists()


def test_compare_tree_command_writes_reports(tmp_path: Path) -> None:
    assert main(["demo", "--out", str(tmp_path)]) == 0
    expected = tmp_path / "expected-ui-tree.json"
    actual = tmp_path / "actual-ui-tree.json"
    report = tmp_path / "report.json"
    markdown = tmp_path / "report.md"
    assert main(["compare-tree", str(expected), str(actual), "--out", str(report), "--markdown", str(markdown)]) == 0
    assert json.loads(report.read_text())["status"] == "PASS"
    assert "# Penflow Compare Report" in markdown.read_text()

