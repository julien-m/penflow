from __future__ import annotations

from pathlib import Path

from penflow.cli import main


FULL_DEMO_FILES = [
    "flow-ui-contract/flows/checkout.md",
    "flow-ui-contract/screens/checkout.md",
    "semantic-ui-tree.json",
    "ui.visual.pen",
    "ui.pen",
    "pencil-context-map.json",
    "expected-ui-tree.json",
    "code-ir.json",
    "actual-ui-tree.json",
    "compare-report.json",
    "compare-report.md",
    "review-report.md",
    "fix-report.md",
]


def test_demo_command_rebuilds_full_flow_ui_contract_chain(tmp_path: Path) -> None:
    out = tmp_path / "full"

    assert main(["demo", "--out", str(out), "--json"]) == 0
    for relative_path in FULL_DEMO_FILES:
        assert (out / relative_path).exists(), relative_path

    original_bytes = {
        relative_path: (out / relative_path).read_bytes() for relative_path in FULL_DEMO_FILES
    }

    assert (
        main(
            [
                "export-semantic-tree",
                str(out / "flow-ui-contract"),
                "--out",
                str(out / "semantic-ui-tree.json"),
                "--json",
            ]
        )
        == 0
    )
    assert main(["validate-semantic-tree", str(out / "semantic-ui-tree.json"), "--json"]) == 0
    assert (
        main(
            [
                "enrich-pen",
                str(out / "ui.visual.pen"),
                str(out / "semantic-ui-tree.json"),
                "--out",
                str(out / "ui.pen"),
                "--json",
            ]
        )
        == 0
    )
    assert main(["validate-pen", str(out / "ui.pen"), "--json"]) == 0
    assert (
        main(
            [
                "map-pencil-context",
                str(out / "ui.pen"),
                str(out / "semantic-ui-tree.json"),
                "--out",
                str(out / "pencil-context-map.json"),
                "--json",
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "export-expected",
                str(out / "ui.pen"),
                "--out",
                str(out / "expected-ui-tree.json"),
                "--json",
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "code-ir",
                "--from-context",
                str(out / "ui.pen"),
                "--semantic-tree",
                str(out / "semantic-ui-tree.json"),
                "--context-map",
                str(out / "pencil-context-map.json"),
                "--flow-id",
                "checkout",
                "--flow-name",
                "Checkout",
                "--out",
                str(out / "code-ir.json"),
                "--json",
            ]
        )
        == 0
    )
    assert main(["validate-actual", str(out / "actual-ui-tree.json"), "--schema", "--json"]) == 0
    assert (
        main(
            [
                "compare-tree",
                str(out / "expected-ui-tree.json"),
                str(out / "actual-ui-tree.json"),
                "--out",
                str(out / "compare-report.json"),
                "--markdown",
                str(out / "compare-report.md"),
                "--json",
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "review-report",
                str(out / "compare-report.json"),
                "--out",
                str(out / "review-report.md"),
                "--json",
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "fix-report",
                str(out / "compare-report.json"),
                "--out",
                str(out / "fix-report.md"),
                "--json",
            ]
        )
        == 0
    )

    for relative_path, expected_bytes in original_bytes.items():
        assert (out / relative_path).read_bytes() == expected_bytes, relative_path
