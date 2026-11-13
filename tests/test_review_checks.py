"""Behavioral coverage for useful checks independent of certification metadata."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from penflow.cli import main
from penflow.review_checks import check_workspace
from penflow.tree import expected_tree_from_pen

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    target = tmp_path / "workspace"
    shutil.copytree(ROOT / "examples/full", target)
    return target


def by_name(report: dict) -> dict:
    return {row["name"]: row for row in report["checks"]}


def snapshot(root: Path) -> dict:
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="POSIX named pipe")
def test_fifo_input_is_rejected_without_stopping_independent_checks(workspace: Path) -> None:
    path = workspace / "ui.pen"
    path.unlink()
    os.mkfifo(path)
    checks = by_name(check_workspace(workspace))
    assert checks["validate-pen"]["status"] == "ERROR"
    assert "input.not_regular" in checks["validate-pen"]["issues"][0]["message"]
    assert checks["validate-actual"]["status"] == "PASS"


def test_oversized_input_is_refused_before_reading(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import penflow.review_checks as review

    limit = 1024
    monkeypatch.setattr(review, "MAX_INPUT_BYTES", limit)
    (workspace / "ui.pen").write_bytes(b" " * (limit + 1))
    result = by_name(check_workspace(workspace))["validate-pen"]
    assert result["status"] == "ERROR"
    assert "input.too_large" in result["issues"][0]["message"]


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="POSIX named pipe")
@pytest.mark.parametrize("replacement", ["fifo", "oversized"])
def test_input_recheck_uses_the_same_read_protection(tmp_path: Path, replacement: str) -> None:
    from penflow.verification_files import InputReader, VerificationInputError

    source = tmp_path / "source.json"
    source.write_text("{}")
    reader = InputReader(tmp_path, read_limit=16)
    assert reader.read(source) == b"{}"
    source.unlink()
    if replacement == "fifo":
        os.mkfifo(source)
    else:
        source.write_bytes(b" " * 17)
    with pytest.raises(VerificationInputError, match="input.(not_regular|too_large)"):
        reader.recheck()


def test_check_runs_without_git_or_certification_and_never_writes(workspace: Path) -> None:
    before = snapshot(workspace)
    report = check_workspace(workspace)
    assert report == check_workspace(workspace)
    assert snapshot(workspace) == before
    assert report["certified"] is False
    assert report["review_status"] == "required"
    assert by_name(report)["validate-flow-contract"]["status"] == "PASS"
    assert by_name(report)["validate-pen"]["status"] == "PASS"
    assert "unverified" in " ".join(report["limitations"])
    assert not (workspace / ".git").exists()


def test_invalid_contract_does_not_prevent_independent_checks(workspace: Path) -> None:
    (workspace / "flow-ui-contract/contract.json").write_text('{"version": 2}')
    checks = by_name(check_workspace(workspace))
    assert checks["validate-flow-contract"]["exit_code"] == 1
    assert checks["contract-context"]["status"] == "NOT_RUN"
    assert checks["audit-visual"]["status"] in {"PASS", "FAIL"}
    assert checks["validate-actual"]["status"] == "PASS"
    assert checks["compare-tree"]["status"] in {"PASS", "FAIL"}


@pytest.mark.parametrize("payload", ['{"version": 2, "version": 2}', "[]", "{broken", '{"x": NaN}'])
def test_malformed_contract_is_visible_without_suppressing_canvas(
    workspace: Path, payload: str
) -> None:
    (workspace / "flow-ui-contract/contract.json").write_text(payload)
    report = check_workspace(workspace)
    assert by_name(report)["validate-flow-contract"]["status"] == "ERROR"
    assert by_name(report)["validate-pen"]["status"] == "PASS"
    assert report["exit"] == 1


@pytest.mark.parametrize("name", ["actual-ui-tree.json", "ui.pen"])
def test_missing_inputs_never_become_pass(workspace: Path, name: str) -> None:
    (workspace / name).unlink()
    report = check_workspace(workspace)
    assert by_name(report)["compare-tree"]["status"] == "NOT_RUN"
    assert by_name(report)["compare-tree"]["exit_code"] is None
    assert report["status"] == "FINDINGS"
    assert report["certified"] is False
    assert by_name(report)["validate-flow-contract"]["exit_code"] == 0


def test_real_actual_schema_failure_and_mismatch_are_not_silenced(workspace: Path) -> None:
    path = workspace / "actual-ui-tree.json"
    path.write_text('{"version": 1, "screens": []}')
    report = check_workspace(workspace)
    assert by_name(report)["compare-tree"]["exit_code"] == 1
    assert report["exit"] == 1
    path.write_text('{"version": 1, "screens": "invalid"}')
    report = check_workspace(workspace)
    assert by_name(report)["validate-actual"]["exit_code"] == 1
    assert report["exit"] == 1


def test_stale_docs_history_and_build_metadata_do_not_gate_checks(workspace: Path) -> None:
    (workspace / "flow-ui-contract/screens/stale.md").parent.mkdir(parents=True, exist_ok=True)
    (workspace / "flow-ui-contract/screens/stale.md").write_text("stale projection")
    history = workspace / ".specs/penflow-requirements.json"
    history.parent.mkdir()
    history.write_text("broken approval history")
    checks = by_name(check_workspace(workspace))
    assert checks["validate-flow-contract"]["status"] == "PASS"
    assert checks["validate-actual"]["status"] == "PASS"
    assert checks["compare-tree"]["exit_code"] is not None


def test_supplied_invalid_theme_stays_visible(workspace: Path) -> None:
    report = check_workspace(workspace, theme_css="absent.css")
    assert by_name(report)["theme"]["status"] == "ERROR"
    assert by_name(report)["audit-visual"]["status"] in {"PASS", "FAIL"}
    assert report["exit"] == 1


def test_check_confines_inputs_and_detects_symlink_escape(workspace: Path, tmp_path: Path) -> None:
    foreign = tmp_path / "foreign.json"
    foreign.write_text('{"version": 1}')
    (workspace / "actual-ui-tree.json").unlink()
    (workspace / "actual-ui-tree.json").symlink_to(foreign)
    report = check_workspace(workspace)
    assert by_name(report)["validate-actual"]["status"] == "ERROR"
    with pytest.raises(ValueError, match="outside_project"):
        check_workspace(tmp_path, project_root=workspace)


def test_concurrent_input_edit_is_reported(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import penflow.review_checks as checks

    original = checks.audit_visual

    def mutate(tree_path: str | Path, *, tree_data: dict, theme: dict | None) -> dict:
        result = original(tree_path, tree_data=tree_data, theme=theme)
        path = workspace / "ui.pen"
        path.write_bytes(path.read_bytes() + b"\n")
        return result

    monkeypatch.setattr(checks, "audit_visual", mutate)
    report = checks.check_workspace(workspace)
    assert by_name(report)["input-stability"]["status"] == "ERROR"
    assert report["exit"] == 1


@pytest.mark.parametrize("screens", [1, 3])
def test_current_canvas_drives_comparison_for_different_screen_counts(
    tmp_path: Path, screens: int
) -> None:
    pen = {
        "version": "2.17",
        "children": [
            {
                "id": f"view-{index}",
                "type": "frame",
                "width": 100,
                "height": 100,
                "context": f"semantic_id=view-{index}; role=screen",
                "children": [],
            }
            for index in range(screens)
        ],
    }
    path = tmp_path / "ui.pen"
    path.write_text(json.dumps(pen))
    actual = expected_tree_from_pen(path)
    (tmp_path / "actual-ui-tree.json").write_text(json.dumps(actual))
    assert by_name(check_workspace(tmp_path))["compare-tree"]["exit_code"] == 0
    actual["screens"].pop()
    (tmp_path / "actual-ui-tree.json").write_text(json.dumps(actual))
    assert by_name(check_workspace(tmp_path))["compare-tree"]["exit_code"] == 1


def test_read_only_validator_inspects_explicit_input_despite_hygiene_findings(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    shutil.copy(workspace / "ui.pen", workspace / "peer.pen")
    assert main(["validate-actual", str(workspace / "actual-ui-tree.json"), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["issues"] == []
    assert main(["doctor", "--project", str(workspace), "--check", "--json"]) != 0


def test_check_cli_with_explicit_project_and_relative_workspace(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = main(
        ["check", "--target", workspace.name, "--project", str(workspace.parent), "--json"]
    )
    report = json.loads(capsys.readouterr().out)
    assert report["workspace"] == str(workspace)
    assert exit_code == report["exit"]
    assert report["checks"]


def test_check_scope_error_is_structured_and_noncertifying(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["check", "--target", str(tmp_path / "absent"), "--json"]) == 2
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "ERROR"
    assert report["checks"] == []
    assert report["certified"] is False


@pytest.mark.parametrize("product_exit", [0, 1])
def test_cleanup_refusal_preserves_product_result_and_reports_stderr(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    product_exit: int,
) -> None:
    import penflow.cli_governance as governance

    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, timeout=10)
    assert main(["doctor", "--project", str(tmp_path), "--fix", "--json"]) == 0
    capsys.readouterr()

    def refuse(*args: object) -> None:
        raise governance.LifecycleBlockedError("cleanup.test_refusal", "unsafe test cleanup")

    def producer(args: object) -> int:
        print(json.dumps({"product": "result", "exit": product_exit}))
        return product_exit

    monkeypatch.setattr(governance, "_cleanup_current_run", refuse)
    from penflow.cli_parser import build_parser

    args = build_parser().parse_args(
        ["export-expected", "penflow/ui.pen", "--project", str(tmp_path)]
    )
    args.func = producer
    assert governance._run_governed_producer(args) == product_exit
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {"product": "result", "exit": product_exit}
    finding = json.loads(captured.err)
    assert finding["status"] == "BLOCKED"
    assert finding["producer_exit"] == product_exit
    assert (tmp_path / "penflow/ui.pen").exists()


def test_token_warnings_are_preserved_as_failed_check_findings(workspace: Path) -> None:
    (workspace / "theme.css").write_text(":root { --radius: nonsense; }")
    result = by_name(check_workspace(workspace))["lint-tokens"]
    warnings = [issue for issue in result["issues"] if issue["severity"] == "warning"]
    assert warnings
    assert any(issue["code"] == "theme.value.unparsed" for issue in warnings)
    assert result["exit_code"] == 1
    assert result["status"] == "FAIL"


def test_single_screen_actual_shape_compares_like_multiscreen_envelope(tmp_path: Path) -> None:
    raw = json.loads((ROOT / "examples/full/ui.pen").read_text())
    raw["children"] = raw["children"][:1]
    pen = tmp_path / "ui.pen"
    pen.write_text(json.dumps(raw))
    screen = expected_tree_from_pen(pen)["screens"][0]
    actual = {
        "version": 1,
        "screen_id": screen["screen_id"],
        "root": screen["root"],
        "viewport": screen["viewport"],
    }
    path = tmp_path / "actual-ui-tree.json"
    path.write_text(json.dumps(actual))
    checks = by_name(check_workspace(tmp_path))
    assert checks["validate-actual"]["exit_code"] == 0
    assert checks["compare-tree"]["exit_code"] == 0
    actual["root"]["bbox"]["width"] += 50
    path.write_text(json.dumps(actual))
    assert by_name(check_workspace(tmp_path))["compare-tree"]["exit_code"] == 1
