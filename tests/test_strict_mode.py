"""Feature 049 — strict-by-default exit codes, blocking drift, surfaced coercions."""

from __future__ import annotations

import json
from pathlib import Path

import penflow.contracts
import penflow.schema_cache
import penflow.tree
from penflow.cli import main
from penflow.compare import LENIENT_THRESHOLD, STRICT_THRESHOLD
from penflow.contracts import extract_design_tokens
from penflow.drift import BLOCKING_DRIFT_CODES, detect_drift
from penflow.pen import inspect_pen

ROOT = Path(__file__).resolve().parent.parent


def write_json(path: Path, data: dict) -> Path:
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def minimal_pen(**title_extra: object) -> dict:
    return {
        "version": "2.11",
        "children": [
            {
                "id": "screen",
                "type": "frame",
                "name": "Checkout",
                "context": "semantic_id=checkout; role=screen",
                "children": [
                    {
                        "id": "title",
                        "type": "text",
                        "content": "Checkout",
                        "context": "semantic_id=checkout.title; role=text",
                        **title_extra,
                    }
                ],
            }
        ],
    }


def expected_actual_pair(*, text_drift: bool) -> tuple[dict, dict]:
    """Expected/actual trees differing (at most) by one warning-level text."""

    def node(node_id: str, text: str) -> dict:
        return {
            "id": node_id,
            "semantic_id": node_id,
            "role": "text",
            "text": text,
            "bbox": {"x": 0, "y": 0, "width": 100, "height": 20},
            "children": [],
        }

    expected = {
        "version": 1,
        "screens": [
            {
                "screen_id": "s1",
                "root": {
                    "id": "s1",
                    "semantic_id": "s1",
                    "role": "screen",
                    "bbox": {"x": 0, "y": 0, "width": 390, "height": 844},
                    "children": [node("s1.title", "Hello"), node("s1.subtitle", "World")],
                },
            }
        ],
    }
    actual = json.loads(json.dumps(expected))
    if text_drift:
        actual["screens"][0]["root"]["children"][0]["text"] = "Hi"
    return expected, actual


def specs_with_flow(root: Path, *, marker: str, extra_flow: str | None = None) -> Path:
    specs_dir = root / "flow-ui-contract"
    (specs_dir / "flows").mkdir(parents=True)
    (specs_dir / "screens").mkdir()
    flow_md = (
        "---\nflow: checkout\ntitle: Checkout\nstatus: reviewed\n---\n\n"
        f"# Flow Checkout\n\n- Business intent: {marker}\n"
    )
    (specs_dir / "flows" / "checkout.md").write_text(flow_md, encoding="utf-8")
    if extra_flow:
        extra_md = flow_md.replace("flow: checkout", f"flow: {extra_flow}")
        (specs_dir / "flows" / f"{extra_flow}.md").write_text(extra_md, encoding="utf-8")
    (specs_dir / "screens" / "checkout.md").write_text(
        "---\nscreen: checkout\nflow: checkout\ntitle: Checkout\nstatus: reviewed\n---\n\n"
        f"# Screen Checkout\n\n## Displayed Data\n\n- Checkout\n\n- {marker}\n",
        encoding="utf-8",
    )
    return specs_dir


def aligned_semantic_tree() -> dict:
    return {
        "version": 1,
        "kind": "semantic-ui-tree",
        "tree_id": "checkout",
        "source": {"notes": ["test fixture"]},
        "flows": [
            {
                "id": "checkout",
                "title": "Checkout",
                "entry_screen": "checkout",
                "steps": [{"id": "checkout-step", "screen_id": "checkout", "intent": "checkout"}],
                "transitions": [],
                "source_map": {"flow_spec": "flow-ui-contract/flows/checkout.md"},
            }
        ],
        "screens": [
            {
                "id": "checkout",
                "flow_id": "checkout",
                "surface": "web",
                "viewport": {"width": 390, "height": 844},
                "states": [{"name": "default"}],
                "validations": [],
                "side_effects": [],
                "source_map": {"screen_spec": "flow-ui-contract/screens/checkout.md"},
                "root": {
                    "semantic_id": "checkout",
                    "role": "screen",
                    "source_map": {"screen_spec": "flow-ui-contract/screens/checkout.md"},
                    "children": [
                        {
                            "semantic_id": "checkout.title",
                            "role": "text",
                            "text": "Checkout",
                            "source_map": {"screen_spec": "flow-ui-contract/screens/checkout.md"},
                        }
                    ],
                },
            }
        ],
    }


def test_jsonschema_is_a_hard_dependency() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert '"jsonschema>=4"' in pyproject
    assert not hasattr(penflow.tree, "_validate_actual_tree_schema_minimal")
    assert not hasattr(penflow.tree, "_validate_node_schema_minimal")
    assert not hasattr(penflow.contracts, "_validate_code_ir_minimal")
    # Feature 054 moved validator construction into the shared schema cache;
    # tree/contracts route through it, so the hard-dependency anchor lives there.
    assert hasattr(penflow.schema_cache, "Draft202012Validator")
    assert hasattr(penflow.tree, "validator_for")
    assert hasattr(penflow.contracts, "validator_for")


def test_validate_pen_warning_only_fails_strict_passes_lenient(tmp_path: Path) -> None:
    pen_path = write_json(tmp_path / "ui.pen", minimal_pen(width="12px"))
    assert main(["validate-pen", str(pen_path), "--json"]) == 1
    assert main(["validate-pen", str(pen_path), "--lenient", "--json"]) == 0
    # AC-002: the global flag position (before the subcommand) works identically.
    assert main(["--lenient", "validate-pen", str(pen_path), "--json"]) == 0


def test_validate_pen_reports_bbox_invalid_warning(tmp_path: Path, capsys) -> None:
    pen_path = write_json(tmp_path / "ui.pen", minimal_pen(width="12px"))
    main(["validate-pen", str(pen_path), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "FAIL"
    [issue] = [item for item in payload["issues"] if item["code"] == "pen.bbox.invalid"]
    assert issue["severity"] == "warning"
    assert issue["node_id"] == "title"
    assert "'12px'" in issue["message"]


def test_pen_sizing_keywords_are_not_bbox_warnings(tmp_path: Path) -> None:
    pen = minimal_pen(width="fill_container", height="fit_content(44)")
    pen_path = write_json(tmp_path / "ui.pen", pen)
    assert main(["validate-pen", str(pen_path), "--json"]) == 0


def test_inspect_includes_bbox_invalid_warning(tmp_path: Path) -> None:
    pen_path = write_json(tmp_path / "ui.pen", minimal_pen(height="auto"))
    report = inspect_pen(pen_path)
    assert any(issue["code"] == "pen.bbox.invalid" for issue in report["warnings"])
    assert report["errors"] == []


def test_compare_tree_threshold_resolution(tmp_path: Path) -> None:
    expected, actual = expected_actual_pair(text_drift=False)
    expected_path = write_json(tmp_path / "expected.json", expected)
    actual_path = write_json(tmp_path / "actual.json", actual)
    report_path = tmp_path / "report.json"
    base = ["compare-tree", str(expected_path), str(actual_path), "--out", str(report_path)]

    assert main([*base, "--json"]) == 0
    assert json.loads(report_path.read_text())["threshold"] == STRICT_THRESHOLD

    assert main([*base, "--lenient", "--json"]) == 0
    assert json.loads(report_path.read_text())["threshold"] == LENIENT_THRESHOLD

    # An explicit --threshold always wins, in both modes.
    assert main([*base, "--threshold", "0.5", "--json"]) == 0
    assert json.loads(report_path.read_text())["threshold"] == 0.5
    assert main([*base, "--threshold", "0.5", "--lenient", "--json"]) == 0
    assert json.loads(report_path.read_text())["threshold"] == 0.5


def test_compare_tree_warnings_promote_to_exit_one(tmp_path: Path) -> None:
    expected, actual = expected_actual_pair(text_drift=True)
    expected_path = write_json(tmp_path / "expected.json", expected)
    actual_path = write_json(tmp_path / "actual.json", actual)
    report_path = tmp_path / "report.json"
    base = ["compare-tree", str(expected_path), str(actual_path), "--out", str(report_path)]

    # Permissive threshold keeps the report PASS, but the warning still fails strict.
    assert main([*base, "--threshold", "0.5", "--json"]) == 1
    report = json.loads(report_path.read_text())
    assert report["status"] == "PASS"
    assert report["summary"]["warnings"] >= 1
    assert main([*base, "--threshold", "0.5", "--lenient", "--json"]) == 0


def test_detect_drift_blocking_fails_even_lenient(tmp_path: Path) -> None:
    specs_dir = specs_with_flow(tmp_path, marker="[NEEDS CLARIFICATION]")
    tree_path = write_json(tmp_path / "semantic-ui-tree.json", aligned_semantic_tree())
    pen_path = write_json(tmp_path / "ui.pen", minimal_pen())
    report_path = tmp_path / "drift-report.json"
    base = [
        "detect-drift",
        str(specs_dir),
        str(tree_path),
        str(pen_path),
        "--out",
        str(report_path),
    ]

    assert main([*base, "--json"]) == 1
    # Blocking issues override leniency.
    assert main([*base, "--lenient", "--json"]) == 1
    report = json.loads(report_path.read_text())
    assert report["status"] == "BLOCKED"
    assert report["summary"]["blocking"] >= 1
    blocked = [issue for issue in report["issues"] if issue["blocking"]]
    assert blocked
    assert all(issue["code"] in BLOCKING_DRIFT_CODES for issue in blocked)


def test_detect_drift_warning_only_is_lenient_forgivable(tmp_path: Path) -> None:
    specs_dir = specs_with_flow(tmp_path, marker="submit_payment", extra_flow="billing")
    tree_path = write_json(tmp_path / "semantic-ui-tree.json", aligned_semantic_tree())
    pen_path = write_json(tmp_path / "ui.pen", minimal_pen())
    report_path = tmp_path / "drift-report.json"
    base = [
        "detect-drift",
        str(specs_dir),
        str(tree_path),
        str(pen_path),
        "--out",
        str(report_path),
    ]

    assert main([*base, "--json"]) == 1
    assert main([*base, "--lenient", "--json"]) == 0
    report = json.loads(report_path.read_text())
    assert report["status"] == "DRIFT"
    assert report["summary"]["blocking"] == 0
    assert all(issue["blocking"] is False for issue in report["issues"])


def test_drift_report_schema_validates_and_fails_closed(tmp_path: Path) -> None:
    specs_dir = specs_with_flow(tmp_path, marker="[NEEDS CLARIFICATION]")
    tree_path = write_json(tmp_path / "semantic-ui-tree.json", aligned_semantic_tree())
    pen_path = write_json(tmp_path / "ui.pen", minimal_pen())
    report_path = tmp_path / "drift-report.json"
    detect_drift(specs_dir, tree_path, pen_path, report_path)

    assert main(["validate-report", str(report_path), "--schema", "--json"]) == 0

    report = json.loads(report_path.read_text())
    report["unexpected"] = True
    bad_path = write_json(tmp_path / "drift-report.bad.json", report)
    assert main(["validate-report", str(bad_path), "--schema", "--json"]) == 1


def test_lint_tokens_reports_unparsable_theme_dimension(tmp_path: Path) -> None:
    theme_path = tmp_path / "theme.css"
    theme_path.write_text(":root { --radius: 0.5banana; }", encoding="utf-8")
    pen_path = write_json(tmp_path / "ui.pen", minimal_pen())
    report_path = tmp_path / "token-lint-report.json"
    base = [
        "lint-tokens",
        str(pen_path),
        "--theme-css",
        str(theme_path),
        "--out",
        str(report_path),
    ]

    assert main([*base, "--json"]) == 1
    assert main([*base, "--lenient", "--json"]) == 0
    report = json.loads(report_path.read_text())
    [violation] = [item for item in report["violations"] if item["code"] == "theme.value.unparsed"]
    assert violation["severity"] == "warning"
    assert violation["property"] == "pf-radius"
    assert violation["value"] == "0.5banana"
    assert main(["validate-report", str(report_path), "--schema", "--json"]) == 0


def test_extract_tokens_reports_unparsed_values(tmp_path: Path) -> None:
    pen = minimal_pen()
    pen["children"][0]["gap"] = "stretch"
    pen_path = write_json(tmp_path / "ui.pen", pen)
    out_path = tmp_path / "tokens.json"

    assert main(["extract-tokens", str(pen_path), "--out", str(out_path), "--json"]) == 1
    assert (
        main(["extract-tokens", str(pen_path), "--out", str(out_path), "--lenient", "--json"]) == 0
    )
    tokens = json.loads(out_path.read_text())
    [issue] = tokens["issues"]
    assert issue["code"] == "tokens.value.unparsed"
    assert issue["severity"] == "warning"
    assert issue["path"] == "screen.gap"


def test_extract_tokens_clean_pen_has_no_issues(tmp_path: Path) -> None:
    pen_path = write_json(tmp_path / "ui.pen", minimal_pen())
    assert main(["extract-tokens", str(pen_path), "--json"]) == 0
    assert extract_design_tokens(pen_path)["issues"] == []


def test_export_semantic_tree_validates_output(tmp_path: Path, capsys) -> None:
    out_path = tmp_path / "semantic-ui-tree.json"
    code = main(
        [
            "export-semantic-tree",
            str(ROOT / "examples" / "demo" / "flow-ui-contract" / "contract.json"),
            "--out",
            str(out_path),
            "--json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["status"] == "PASS"
    assert payload["issues"] == []
