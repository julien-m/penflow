# @spec FR-011: Deterministic flow docs — .specs/features/076-exhaustive-bidirectional-semantic-context/spec.md#fr-011
# @spec FR-012: Hash-bound manifest — .specs/features/076-exhaustive-bidirectional-semantic-context/spec.md#fr-012
# @spec FR-013: Read-only freshness — .specs/features/076-exhaustive-bidirectional-semantic-context/spec.md#fr-013
# @spec FR-014: Complete or absent docs — .specs/features/076-exhaustive-bidirectional-semantic-context/spec.md#fr-014
"""Generated flow documentation transaction and freshness tests."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
import penflow.cli as cli_module
from penflow.cli import main
from penflow.flow_docs import check_generated_docs, export_flow_docs
from penflow.schema_cache import validator_for
from tests.test_flow_contract_v2 import valid_contract


def _write_contract(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(valid_contract(), sort_keys=True), encoding="utf-8")
    return path


def test_export_is_byte_identical_and_manifest_owns_exact_nonempty_membership(
    tmp_path: Path,
) -> None:
    contract = _write_contract(tmp_path / "contract.json")
    out = tmp_path / "flow-ui-contract"

    first = export_flow_docs(contract, out)
    before = {path.relative_to(out): path.read_bytes() for path in out.rglob("*") if path.is_file()}
    second = export_flow_docs(contract, out)
    after = {path.relative_to(out): path.read_bytes() for path in out.rglob("*") if path.is_file()}

    assert first == second
    assert before == after
    assert set(before) == {
        Path("flows/checkout.md"),
        Path("screens/checkout.md"),
        Path("generated-docs.json"),
    }
    assert all(before[path] for path in before)
    assert list(validator_for("generated-docs.schema.json").iter_errors(first)) == []


def test_check_distinguishes_passive_absence_explicit_missing_and_partial_states(
    tmp_path: Path,
) -> None:
    contract = _write_contract(tmp_path / "contract.json")
    out = tmp_path / "flow-ui-contract"

    assert check_generated_docs(contract, out, explicit=False)["status"] == "DISABLED"
    missing = check_generated_docs(contract, out, explicit=True)
    assert missing["status"] == "FAIL"
    assert [issue["code"] for issue in missing["issues"]] == ["docs.missing"]
    (out / "flows").mkdir(parents=True)
    partial = check_generated_docs(contract, out, explicit=False)
    assert partial["status"] == "FAIL"
    assert [issue["code"] for issue in partial["issues"]] == ["docs.empty"]


def test_check_detects_tampered_bytes_without_rewriting_them(tmp_path: Path) -> None:
    contract = _write_contract(tmp_path / "contract.json")
    out = tmp_path / "flow-ui-contract"
    export_flow_docs(contract, out)
    screen = out / "screens" / "checkout.md"
    screen.write_text("manual edit\n", encoding="utf-8")
    before = screen.read_bytes()

    result = check_generated_docs(contract, out, explicit=True)

    assert result["status"] == "FAIL"
    assert "docs.hash_mismatch" in {issue["code"] for issue in result["issues"]}
    assert screen.read_bytes() == before


def test_publish_failure_restores_prior_manifest_owned_tree_and_retains_journal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    contract = _write_contract(tmp_path / "contract.json")
    out = tmp_path / "flow-ui-contract"
    export_flow_docs(contract, out)
    before = {path.relative_to(out): path.read_bytes() for path in out.rglob("*") if path.is_file()}
    original_replace = os.replace
    failed = False

    def fail_once(source, target):
        nonlocal failed
        if not failed and ".flow-docs-stage-" in str(source) and str(source).endswith(".md"):
            failed = True
            raise OSError("injected replacement failure")
        return original_replace(source, target)

    monkeypatch.setattr("penflow.flow_docs.os.replace", fail_once)

    with pytest.raises(OSError, match="injected replacement failure"):
        export_flow_docs(contract, out)

    after = {path.relative_to(out): path.read_bytes() for path in out.rglob("*") if path.is_file()}
    assert after == before
    assert (tmp_path / ".flow-ui-contract-generated-docs-transaction.json").is_file()


def test_export_flow_docs_check_cli_never_enters_producer_lifecycle(
    tmp_path: Path, governed_consumer_project, monkeypatch
) -> None:
    contract = _write_contract(tmp_path / "contract.json")
    pen = tmp_path / "ui.pen"
    pen.write_text(json.dumps({"children": []}), encoding="utf-8")
    governed_consumer_project(tmp_path, pen)
    out = tmp_path / "flow-ui-contract"
    export_flow_docs(contract, out)

    def forbidden(*args, **kwargs):
        raise AssertionError("check mode must not enter producer lifecycle")

    monkeypatch.setattr(cli_module, "_run_governed_producer", forbidden)

    assert (
        main(
            [
                "export-flow-docs",
                str(contract),
                "--out",
                str(out),
                "--check",
                "--project",
                str(tmp_path),
                "--json",
            ]
        )
        == 0
    )
