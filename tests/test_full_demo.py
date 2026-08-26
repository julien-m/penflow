# @spec(AC-014)
# @spec(FR-001)
# @spec(FR-002)
# @spec(FR-003)
# @spec(FR-006)
# @spec FR-005: Canonical producer migration — .specs/features/074-penflow-doctor-consumer-project-hygiene/spec.md#fr-005
from __future__ import annotations

from pathlib import Path

import pytest

from penflow.cli import main


FULL_DEMO_FILES = [
    "flow-ui-contract/contract.json",
    "flow-ui-contract/generated-docs.json",
    "flow-ui-contract/flows/checkout.md",
    "flow-ui-contract/screens/checkout.md",
    "semantic-ui-tree.json",
    "ui.pen",
    "pencil-context-map.json",
    "semantic-context-coverage.json",
    "expected-ui-tree.json",
    "code-ir.json",
    "actual-ui-tree.json",
    "compare-report.json",
    "review-report.json",
    "fix-report.json",
]


@pytest.fixture
def full_demo_project(tmp_path: Path, governed_consumer_project):
    """Generate one governed demo and retain its deterministic artifact bytes."""
    out = tmp_path / "full"
    governed_consumer_project(out, out / "ui.pen")
    assert main(["demo", "--out", str(out), "--project", str(out), "--json"]) == 0
    snapshot = {
        relative_path: (out / relative_path).read_bytes() for relative_path in FULL_DEMO_FILES
    }
    return out, snapshot


def _run_project_command(out: Path, *args: str) -> int:
    """Run one governed JSON command against the demo consumer."""
    return main([*args, "--project", str(out), "--json"])


def test_demo_command_generates_complete_artifact_set(full_demo_project) -> None:
    out, _ = full_demo_project
    assert all((out / relative_path).is_file() for relative_path in FULL_DEMO_FILES)
    assert [path.relative_to(out).as_posix() for path in out.rglob("*.pen")] == ["ui.pen"]


def test_demo_semantic_enrichment_and_mapping_are_idempotent(full_demo_project) -> None:
    out, snapshot = full_demo_project

    assert (
        _run_project_command(
            out,
            "export-semantic-tree",
            str(out / "flow-ui-contract/contract.json"),
            "--out",
            str(out / "semantic-ui-tree.json"),
        )
        == 0
    )
    assert (
        _run_project_command(
            out,
            "enrich-pen",
            str(out / "ui.pen"),
            str(out / "semantic-ui-tree.json"),
            "--out",
            str(out / "ui.pen"),
        )
        == 0
    )
    assert (
        _run_project_command(
            out,
            "map-pencil-context",
            str(out / "ui.pen"),
            str(out / "semantic-ui-tree.json"),
            "--out",
            str(out / "pencil-context-map.json"),
        )
        == 0
    )
    for relative_path in ("semantic-ui-tree.json", "ui.pen", "pencil-context-map.json"):
        assert (out / relative_path).read_bytes() == snapshot[relative_path]


def test_demo_generated_docs_and_coverage_are_fresh(full_demo_project) -> None:
    out, snapshot = full_demo_project

    assert (
        _run_project_command(
            out,
            "export-flow-docs",
            str(out / "flow-ui-contract/contract.json"),
            "--out",
            str(out / "flow-ui-contract"),
            "--check",
        )
        == 0
    )
    assert (
        _run_project_command(
            out,
            "audit-context-coverage",
            str(out / "ui.pen"),
            "--contract",
            str(out / "flow-ui-contract/contract.json"),
            "--out",
            str(out / "semantic-context-coverage.json"),
        )
        == 0
    )
    for relative in ("flow-ui-contract/generated-docs.json", "semantic-context-coverage.json"):
        assert (out / relative).read_bytes() == snapshot[relative]


def test_demo_expected_tree_and_code_ir_are_idempotent(full_demo_project) -> None:
    out, snapshot = full_demo_project
    assert (
        _run_project_command(
            out,
            "export-expected",
            str(out / "ui.pen"),
            "--out",
            str(out / "expected-ui-tree.json"),
        )
        == 0
    )
    assert (
        _run_project_command(
            out,
            "code-ir",
            "--from-context",
            str(out / "ui.pen"),
            "--semantic-tree",
            str(out / "semantic-ui-tree.json"),
            "--context-map",
            str(out / "pencil-context-map.json"),
            "--contract",
            str(out / "flow-ui-contract/contract.json"),
            "--flow-id",
            "checkout",
            "--flow-name",
            "Checkout",
            "--out",
            str(out / "code-ir.json"),
        )
        == 0
    )
    for relative_path in ("expected-ui-tree.json", "code-ir.json"):
        assert (out / relative_path).read_bytes() == snapshot[relative_path]


def test_demo_runtime_compare_reports_are_idempotent(full_demo_project) -> None:
    out, snapshot = full_demo_project
    assert (
        _run_project_command(
            out,
            "compare-tree",
            str(out / "expected-ui-tree.json"),
            str(out / "actual-ui-tree.json"),
            "--out",
            str(out / "compare-report.json"),
        )
        == 0
    )
    for command, destination in (
        ("review-report", "review-report.json"),
        ("fix-report", "fix-report.json"),
    ):
        assert (
            _run_project_command(
                out,
                command,
                str(out / "compare-report.json"),
                "--out",
                str(out / destination),
            )
            == 0
        )
    for relative_path in ("compare-report.json", "review-report.json", "fix-report.json"):
        assert (out / relative_path).read_bytes() == snapshot[relative_path]
