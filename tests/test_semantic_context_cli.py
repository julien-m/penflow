# @spec FR-004: Strict coverage CLI — .specs/features/076-exhaustive-bidirectional-semantic-context/spec.md#fr-004
# @spec FR-005: Delegated coverage CLI — .specs/features/076-exhaustive-bidirectional-semantic-context/spec.md#fr-005
# @spec FR-016: CLI anti-false-PASS matrix — .specs/features/076-exhaustive-bidirectional-semantic-context/spec.md#fr-016
"""Installed-surface semantics for dedicated and delegated coverage commands."""

from __future__ import annotations

import json
from pathlib import Path

from penflow.cli import main
from tests.test_semantic_context_coverage import _contract, _pen, _semantic
from tests.test_semantic_enrichment import semantic_tree


def _write_workspace(root: Path, governed_consumer_project, *, extra: bool = False) -> tuple:
    contract = root / "contract.json"
    pen = root / "ui.pen"
    tree = root / "semantic-ui-tree.json"
    pen_data = _pen()
    if extra:
        pen_data["children"][0]["children"].append(
            _semantic("ghost", "checkout.ghost", "checkout-ghost", "button")
        )
    contract.write_text(json.dumps(_contract()), encoding="utf-8")
    pen.write_text(json.dumps(pen_data), encoding="utf-8")
    tree.write_text(json.dumps(semantic_tree()), encoding="utf-8")
    governed_consumer_project(root, pen)
    return contract, pen, tree


def test_dedicated_and_delegated_strict_commands_share_failure_semantics(
    tmp_path: Path, governed_consumer_project, capsys
) -> None:
    contract, pen, tree = _write_workspace(tmp_path, governed_consumer_project, extra=True)
    dedicated = tmp_path / "dedicated.json"
    delegated = tmp_path / "delegated.json"

    dedicated_exit = main(
        [
            "audit-context-coverage",
            str(pen),
            "--contract",
            str(contract),
            "--out",
            str(dedicated),
            "--project",
            str(tmp_path),
            "--json",
        ]
    )
    capsys.readouterr()
    delegated_exit = main(
        [
            "map-pencil-context",
            str(pen),
            str(tree),
            "--out",
            str(tmp_path / "map.json"),
            "--strict-coverage",
            "--contract",
            str(contract),
            "--coverage-out",
            str(delegated),
            "--project",
            str(tmp_path),
            "--json",
        ]
    )

    assert (dedicated_exit, delegated_exit) == (1, 1)
    assert (
        json.loads(dedicated.read_text())["buckets"] == json.loads(delegated.read_text())["buckets"]
    )


def test_dedicated_legacy_mode_never_emits_strict_pass(
    tmp_path: Path, governed_consumer_project
) -> None:
    contract, pen, _ = _write_workspace(tmp_path, governed_consumer_project)
    report = tmp_path / "coverage.json"

    exit_code = main(
        [
            "audit-context-coverage",
            str(pen),
            "--contract",
            str(contract),
            "--out",
            str(report),
            "--legacy-coverage",
            "--project",
            str(tmp_path),
            "--json",
        ]
    )

    assert exit_code == 0
    assert json.loads(report.read_text())["status"] == "LEGACY_PARTIAL"


def test_delegated_legacy_mode_cites_both_versioned_artifacts(
    tmp_path: Path, governed_consumer_project, capsys
) -> None:
    contract, pen, tree = _write_workspace(tmp_path, governed_consumer_project)
    coverage = tmp_path / "coverage.json"

    assert (
        main(
            [
                "map-pencil-context",
                str(pen),
                str(tree),
                "--out",
                str(tmp_path / "map.json"),
                "--legacy-coverage",
                "--contract",
                str(contract),
                "--coverage-out",
                str(coverage),
                "--project",
                str(tmp_path),
                "--json",
            ]
        )
        == 0
    )
    envelope = json.loads(capsys.readouterr().out)
    assert envelope["version"] == 2
    assert envelope["context_map"]["forward_only"] is True
    assert envelope["coverage"]["status"] == "LEGACY_PARTIAL"
    assert envelope["coverage"]["schema_version"] == 1


def test_delegated_coverage_usage_error_writes_no_partial_map(
    tmp_path: Path, governed_consumer_project
) -> None:
    _, pen, tree = _write_workspace(tmp_path, governed_consumer_project)
    context_map = tmp_path / "map.json"

    exit_code = main(
        [
            "map-pencil-context",
            str(pen),
            str(tree),
            "--out",
            str(context_map),
            "--strict-coverage",
            "--project",
            str(tmp_path),
            "--json",
        ]
    )

    assert exit_code == 2
    assert not context_map.exists()
