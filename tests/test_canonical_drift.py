# @spec FR-005 FR-006 AC-008 AC-017 SC-002: Preparation checks exact C20 projections without a future C51 report.
"""Canonical drift uses actual JSON sources while preserving legacy report transport."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

import pytest

from penflow.drift import detect_drift
from penflow.schema_cache import validator_for
from penflow.semantic import write_semantic_tree
from penflow.semantic_enrichment import enrich_pen_from_semantic_tree

ROOT = Path(__file__).resolve().parents[1]


def _workspace(tmp_path: Path, *, enrich: bool = True) -> tuple[Path, Path, Path]:
    specs = tmp_path / "flow-ui-contract"
    shutil.copytree(ROOT / "examples/full/flow-ui-contract", specs)
    pen = tmp_path / "ui.pen"
    shutil.copyfile(ROOT / "examples/full/ui.pen", pen)
    tree = tmp_path / "semantic-ui-tree.json"
    write_semantic_tree(specs, tree)
    if enrich:
        assert enrich_pen_from_semantic_tree(pen, tree, pen)["status"] == "PASS"
    return specs, tree, pen


def _write(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _run_cli(project: Path, arguments: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "penflow", *arguments, "--project", str(project), "--json"],
        cwd=project,
        env=dict(os.environ, PYTHONPATH=str(ROOT)),
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )


@pytest.mark.parametrize("explicit_contract", [False, True])
def test_canonical_example_passes_without_legacy_frontmatter_or_c51_report(
    tmp_path: Path, explicit_contract: bool
) -> None:
    specs, tree, pen = _workspace(tmp_path)
    source = specs / "contract.json" if explicit_contract else specs
    inputs = {p: p.read_bytes() for p in (specs / "contract.json", tree, pen)}
    report = detect_drift(source, tree, pen, tmp_path / "drift.json")
    assert report["status"] == "PASS"
    assert report["issues"] == []
    assert list(validator_for("drift-report.schema.json").iter_errors(report)) == []
    assert {p: p.read_bytes() for p in inputs} == inputs
    assert not (tmp_path / "run-report.json").exists()


@pytest.mark.parametrize(
    "change", ["identity", "screen", "behavior", "unknown_field", "provenance"]
)
def test_stored_semantic_projection_cannot_diverge_from_canonical_contract(
    tmp_path: Path, change: str
) -> None:
    specs, tree_path, pen = _workspace(tmp_path)
    tree = json.loads(tree_path.read_text())
    if change == "identity":
        tree["screens"][0]["root"]["semantic_id"] = "foreign"
    elif change == "screen":
        tree["screens"][0]["id"] = "foreign"
    elif change == "behavior":
        tree["screens"][0]["root"]["children"][0]["intent"] = "delete_payment"
    elif change == "unknown_field":
        tree["extra"] = "unreviewed"
    else:
        tree["source"]["contract"] = "foreign/contract.json"
    _write(tree_path, tree)
    report = detect_drift(specs, tree_path, pen, tmp_path / "drift.json")
    assert report["status"] == "BLOCKED"
    assert any(i["code"] == "drift.semantic_projection_changed" for i in report["issues"])


@pytest.mark.parametrize("invalid", ["{", "{}", "null", '{"version": 1}'])
def test_present_invalid_c20_never_falls_back_to_legacy_docs(tmp_path: Path, invalid: str) -> None:
    specs, tree, pen = _workspace(tmp_path)
    (specs / "contract.json").write_text(invalid)
    report = detect_drift(specs, tree, pen, tmp_path / "drift.json")
    assert report["status"] == "BLOCKED"
    assert report["issues"][0]["code"] == "drift.contract_invalid"


@pytest.mark.parametrize("change", ["identity", "behavior", "extra"])
def test_canonical_drift_rejects_pencil_semantic_changes(tmp_path: Path, change: str) -> None:
    specs, tree, pen_path = _workspace(tmp_path)
    pen = json.loads(pen_path.read_text())
    root = pen["children"][0]
    if change == "identity":
        root["context"] = (
            "classification=semantic; semantic_id=foreign; role=screen; test_id=foreign"
        )
    elif change == "behavior":
        root["context"] += "; intent=rogue_action"
    else:
        root["children"].append({"id": "extra", "type": "frame", "width": 40, "height": 40})
    _write(pen_path, pen)
    report = detect_drift(specs, tree, pen_path, tmp_path / "drift.json")
    assert report["status"] == "BLOCKED"
    assert any(i["code"] == "drift.contract_context_mismatch" for i in report["issues"])


@pytest.mark.parametrize("lenient", [False, True])
def test_real_cli_canonical_export_and_drift_preserve_blocking_exit_policy(
    tmp_path: Path, lenient: bool
) -> None:
    specs, tree, pen = _workspace(tmp_path, enrich=False)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True, timeout=10)
    assert _run_cli(tmp_path, ["doctor", "--fix"]).returncode == 0
    exported = _run_cli(tmp_path, ["export-semantic-tree", str(specs), "--out", str(tree)])
    assert exported.returncode == 0, exported.stdout + exported.stderr
    enriched = _run_cli(tmp_path, ["enrich-pen", str(pen), str(tree), "--out", str(pen)])
    assert enriched.returncode == 0, enriched.stdout + enriched.stderr
    args = ["detect-drift", str(specs), str(tree), str(pen), "--out", str(tmp_path / "drift.json")]
    if lenient:
        args.append("--lenient")
    result = _run_cli(tmp_path, args)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["status"] == "PASS"
    (specs / "contract.json").write_text("{}")
    result = _run_cli(tmp_path, args)
    assert result.returncode == 1, result.stdout + result.stderr
    assert json.loads(result.stdout)["status"] == "BLOCKED"


def test_missing_permission_is_reported_before_enrichment(tmp_path: Path) -> None:
    specs, tree, pen = _workspace(tmp_path, enrich=False)
    document = json.loads(pen.read_text())
    node = document["children"][0]["children"][2]
    node["context"] = node["context"].replace("; permission=buyer_can_pay", "")
    pen.write_text(json.dumps(document))
    report = detect_drift(specs, tree, pen, tmp_path / "drift.json")
    assert report["status"] == "BLOCKED"
    assert any("pencil.permission_mismatch" in item["message"] for item in report["issues"])


def test_real_cli_accepts_relative_export_provenance_for_the_same_absolute_contract(
    tmp_path: Path,
) -> None:
    specs, tree, pen = _workspace(tmp_path)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True, timeout=10)
    assert _run_cli(tmp_path, ["doctor", "--fix"]).returncode == 0
    exported = _run_cli(tmp_path, ["export-semantic-tree", "flow-ui-contract", "--out", str(tree)])
    assert exported.returncode == 0, exported.stdout + exported.stderr
    assert (
        Path(json.loads(tree.read_text())["source"]["contract"]).resolve()
        == specs / "contract.json"
    )
    result = _run_cli(
        tmp_path,
        ["detect-drift", str(specs), str(tree), str(pen), "--out", str(tmp_path / "drift.json")],
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_api_relative_provenance_alias_keeps_all_other_fields_exact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    specs, tree, pen = _workspace(tmp_path)
    monkeypatch.chdir(tmp_path)
    write_semantic_tree(Path("flow-ui-contract"), tree)
    original = tree.read_bytes()
    assert detect_drift(specs, tree, pen, tmp_path / "drift.json")["status"] == "PASS"
    assert tree.read_bytes() == original
    altered = json.loads(original)
    altered["screens"][0]["source_map"]["contract_path"] = "$.screens[999]"
    _write(tree, altered)
    assert detect_drift(specs, tree, pen, tmp_path / "drift.json")["status"] == "BLOCKED"
