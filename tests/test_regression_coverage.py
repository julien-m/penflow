# @spec(AC-013)
# @spec(FR-013)
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

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


def test_validate_flow_specs_cli_reports_invalid_markdown(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], governed_consumer_project
) -> None:
    specs = tmp_path / "flow-ui-contract"
    (specs / "flows").mkdir(parents=True)
    (specs / "screens").mkdir()
    (specs / "flows" / "broken.md").write_text("# Missing frontmatter\n", encoding="utf-8")
    governed_consumer_project(tmp_path, tmp_path / "ui.pen")
    capsys.readouterr()

    assert main(["validate-flow-specs", str(specs), "--project", str(tmp_path), "--json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert [issue["code"] for issue in payload["issues"]] == ["flow_specs.contract_json_required"]


@pytest.fixture
def c16_project(tmp_path: Path, governed_consumer_project) -> dict[str, Path]:
    """Prepare isolated C16 inputs without executing the workflow under test."""
    contract_dir = tmp_path / "flow-ui-contract"
    shutil.copytree(FULL / "flow-ui-contract", contract_dir)
    actual_tree = tmp_path / "actual-ui-tree.json"
    shutil.copy2(FULL / "actual-ui-tree.json", actual_tree)
    governed_consumer_project(tmp_path, tmp_path / "ui.pen")
    return {
        "root": tmp_path,
        "contract": contract_dir,
        "actual": actual_tree,
        "semantic": tmp_path / "semantic-ui-tree.json",
        "pen": tmp_path / "ui.pen",
        "expected": tmp_path / "expected-ui-tree.json",
    }


def _run_c16(paths: dict[str, Path], *args: str) -> int:
    """Run one governed JSON command inside the C16 consumer."""
    return main([*args, "--project", str(paths["root"]), "--json"])


def _export_c16_semantic_tree(paths: dict[str, Path]) -> None:
    assert (
        _run_c16(
            paths,
            "export-semantic-tree",
            str(paths["contract"] / "contract.json"),
            "--out",
            str(paths["semantic"]),
        )
        == 0
    )


def test_c16_forward_draft_and_expected_exports(c16_project: dict[str, Path]) -> None:
    paths = c16_project
    assert _run_c16(paths, "validate-flow-specs", str(paths["contract"])) == 0
    _export_c16_semantic_tree(paths)
    assert _run_c16(paths, "validate-semantic-tree", str(paths["semantic"])) == 0
    assert (
        _run_c16(
            paths,
            "draft-pen-from-tree",
            str(paths["semantic"]),
            "--out",
            str(paths["pen"]),
        )
        == 0
    )
    assert _run_c16(paths, "validate-pen", str(paths["pen"])) == 0
    assert (
        _run_c16(
            paths,
            "export-expected",
            str(paths["pen"]),
            "-o",
            str(paths["expected"]),
        )
        == 0
    )


def test_c16_legacy_enrichment_and_reverse(
    c16_project: dict[str, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    paths = c16_project
    _export_c16_semantic_tree(paths)
    paths["pen"].write_bytes((LEGACY / "ui.pen").read_bytes())
    assert (
        _run_c16(
            paths,
            "enrich-pen",
            str(paths["pen"]),
            str(paths["semantic"]),
            "--out",
            str(paths["pen"]),
        )
        == 0
    )
    reverse_output = paths["root"] / "reverse-output"
    capsys.readouterr()
    assert _run_c16(paths, "reverse-pen", str(paths["pen"]), "--out", str(reverse_output)) == 1
    strict_reverse = json.loads(capsys.readouterr().out)
    assert {issue["code"] for issue in strict_reverse["issues"]} == {"reverse.clarification_needed"}
    assert (
        _run_c16(
            paths,
            "reverse-pen",
            str(paths["pen"]),
            "--out",
            str(reverse_output),
            "--lenient",
        )
        == 0
    )
    assert (
        _run_c16(paths, "validate-semantic-tree", str(reverse_output / "semantic-ui-tree.json"))
        == 0
    )


def test_c16_compare_review_and_fix_reports(c16_project: dict[str, Path]) -> None:
    paths = c16_project
    shutil.copy2(FULL / "expected-ui-tree.json", paths["expected"])
    compare_json = paths["root"] / "compare.json"
    review_json = paths["root"] / "review.json"
    fix_json = paths["root"] / "fix.json"
    assert _run_c16(paths, "validate-actual", str(paths["actual"]), "--schema") == 0
    assert (
        _run_c16(
            paths,
            "compare-tree",
            str(paths["expected"]),
            str(paths["actual"]),
            "--out",
            str(compare_json),
        )
        == 0
    )
    assert _run_c16(paths, "review-report", str(compare_json), "--out", str(review_json)) == 0
    assert _run_c16(paths, "fix-report", str(compare_json), "--out", str(fix_json)) == 0
    assert json.loads(compare_json.read_text(encoding="utf-8"))["status"] == "PASS"
    assert json.loads(review_json.read_text(encoding="utf-8"))["kind"] == "penflow-review-report"
    assert json.loads(fix_json.read_text(encoding="utf-8"))["kind"] == "penflow-fix-report"
