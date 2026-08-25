# @spec(AC-003)
# @spec(AC-014)
# @spec(FR-001)
# @spec(FR-002)
# @spec(FR-003)
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

import penflow.cli as cli_module
from penflow.artifact_policy import (
    LIFECYCLE_EXEMPT_COMMANDS,
    PRODUCER_COMMANDS,
    READ_ONLY_COMMANDS,
)
from penflow.cli import _PRODUCER_PATH_ARGUMENTS, _validate_json_schema_subset, build_parser, main
from penflow.theme import theme_fingerprint
from tests.test_flow_contract_v2 import valid_contract, write_json


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
    assert (
        main(
            [
                "compare-tree",
                str(expected),
                str(actual),
                "--out",
                str(report),
            ]
        )
        == 0
    )
    assert json.loads(report.read_text())["status"] == "PASS"


# @spec FR-003: spacing warnings follow strict/lenient exit policy — .specs/features/048-compare-layout-spacing-properties/spec.md#fr-003
def test_compare_tree_command_reports_gap_drift(tmp_path: Path) -> None:
    def screen(gap: int) -> dict:
        return {
            "screen_id": "checkout",
            "viewport": {"width": 390, "height": 844},
            "root": {
                "id": "checkout",
                "semantic_id": "checkout",
                "role": "screen",
                "bbox": {"x": 0, "y": 0, "width": 390, "height": 844},
                "children": [
                    {
                        "id": "checkout.box",
                        "semantic_id": "checkout.box",
                        "role": "container",
                        "bbox": {"x": 0, "y": 0, "width": 320, "height": 120},
                        "visual": {"layout": "vertical", "gap": gap, "padding": 16},
                    }
                ],
            },
        }

    expected = tmp_path / "expected.json"
    actual = tmp_path / "actual.json"
    report = tmp_path / "report.json"
    expected.write_text(json.dumps({"version": 1, "screens": [screen(16)]}), encoding="utf-8")
    actual.write_text(json.dumps({"version": 1, "screens": [screen(19)]}), encoding="utf-8")

    # Strict default (feature 049): the spacing warning blocks.
    assert main(["compare-tree", str(expected), str(actual), "--out", str(report)]) == 1
    issues = json.loads(report.read_text())["issues"]
    assert [issue["code"] for issue in issues] == ["node.visual.gap"]
    assert issues[0]["severity"] == "warning"

    # Lenient mode with an explicit threshold keeps the warning non-blocking.
    assert (
        main(
            [
                "compare-tree",
                str(expected),
                str(actual),
                "--out",
                str(report),
                "--lenient",
                "--threshold",
                "0.4",
            ]
        )
        == 0
    )


def test_review_and_fix_report_commands_write_json(tmp_path: Path) -> None:
    assert main(["demo", "--out", str(tmp_path)]) == 0
    expected = tmp_path / "expected-ui-tree.json"
    actual = tmp_path / "actual-ui-tree.json"
    actual_tree = json.loads(actual.read_text())
    actual_tree["root"]["children"] = actual_tree["root"]["children"][:1]
    actual.write_text(json.dumps(actual_tree), encoding="utf-8")

    report = tmp_path / "report.json"
    review = tmp_path / "review.json"
    fix = tmp_path / "fix.json"
    assert main(["compare-tree", str(expected), str(actual), "--out", str(report)]) == 1
    assert main(["review-report", str(report), "--out", str(review)]) == 0
    assert main(["fix-report", str(report), "--out", str(fix)]) == 0
    assert json.loads(review.read_text())["kind"] == "penflow-review-report"
    assert (
        "Expected semantic node is absent"
        in json.loads(review.read_text())["issues"][0]["likely_cause"]
    )
    assert json.loads(fix.read_text())["kind"] == "penflow-fix-report"
    assert "Add the missing runtime element" in json.loads(fix.read_text())["fixes"][0]["fix"]


def test_strict_v2_contract_cli_commands_cover_json_pen_and_ir(tmp_path: Path) -> None:
    contract_path = write_json(tmp_path / "flow-ui-contract" / "contract.json", valid_contract())
    pen_path = write_json(tmp_path / "ui.pen", _contextualized_pen())
    ir_path = tmp_path / "code-ir.json"

    assert main(["validate-flow-contract", str(contract_path), "--json"]) == 0
    assert main(["validate-pen", str(pen_path), "--contract", str(contract_path), "--json"]) == 0
    assert (
        main(
            [
                "code-ir",
                "--from-context",
                str(pen_path),
                "--contract",
                str(contract_path),
                "--out",
                str(ir_path),
                "--json",
            ]
        )
        == 0
    )
    assert main(["validate-code-ir", str(ir_path), "--json"]) == 0


def test_contract_migration_command_requires_review_before_validation(tmp_path: Path) -> None:
    specs = tmp_path / "flow-ui-contract"
    (specs / "flows").mkdir(parents=True)
    (specs / "screens").mkdir()
    (specs / "flows" / "checkout.md").write_text(
        "---\nflow: checkout\ntitle: Checkout\n---\n\n# Checkout\n",
        encoding="utf-8",
    )
    (specs / "screens" / "checkout.md").write_text(
        "---\nscreen: checkout\nflow: checkout\ntitle: Checkout\n---\n\n# Checkout\n",
        encoding="utf-8",
    )
    contract_path = specs / "contract.json"

    assert (
        main(
            [
                "migrate-flow-md-to-contract-json",
                str(specs),
                "--out",
                str(contract_path),
                "--json",
            ]
        )
        == 0
    )
    assert main(["validate-flow-contract", str(contract_path), "--json"]) == 1


def test_validate_report_rejects_non_object_reports(tmp_path: Path) -> None:
    report_path = tmp_path / "compare-report.json"
    report_path.write_text(json.dumps(["not", "an", "object"]), encoding="utf-8")

    assert main(["validate-report", str(report_path), "--schema", "--json"]) == 1


def test_report_schema_subset_fails_closed_on_unsupported_keywords() -> None:
    # `pattern` became supported in feature 056; `format` stays a genuinely
    # unsupported keyword pinning the fail-closed contract.
    issues = _validate_json_schema_subset(
        {"status": "PASS"},
        {"type": "object", "properties": {"status": {"type": "string", "format": "uri"}}},
        "$",
    )

    assert issues == [
        {
            "severity": "error",
            "path": "$.status.__schema__.format",
            "message": "unsupported schema keyword: format",
        }
    ]


def test_report_schema_subset_ignores_json_schema_comments() -> None:
    issues = _validate_json_schema_subset(
        {"status": "PASS"},
        {
            "$comment": "LiveSpec traceability anchors: @spec(FR-001)",
            "type": "object",
            "properties": {
                "status": {
                    "$comment": "status traceability",
                    "type": "string",
                    "const": "PASS",
                }
            },
        },
        "$",
    )

    assert issues == []


def _contextualized_pen() -> dict:
    return {
        "version": "2.11",
        "children": [
            {
                "id": "screen",
                "type": "frame",
                "name": "Checkout",
                "width": 1440,
                "height": 900,
                "context": "semantic_id=checkout; role=screen; test_id=checkout-screen",
                "semantic": {"states": [{"name": "default"}, {"name": "success"}]},
                "children": [
                    {
                        "id": "title",
                        "type": "text",
                        "name": "Checkout",
                        "content": "Checkout",
                        "context": "semantic_id=checkout.title; role=text; binding=checkout.title; entity=checkout",
                    },
                    {
                        "id": "pay",
                        "type": "frame",
                        "name": "Pay",
                        "context": "semantic_id=checkout.pay; role=button; intent=submit_payment; binding=checkout.payment_method; entity=checkout; test_id=checkout-pay; action=submit_payment; permission=buyer_can_pay",
                    },
                ],
            }
        ],
    }


# Published SHA-256 of the empty byte string — pins `shasum -a 256` parity by
# algorithm identity without spawning a subprocess.
EMPTY_BYTES_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


# @spec AC-001: Fingerprint payload shape and digest parity — .specs/features/056-evidence-run-identity-theme-fingerprint/spec.md#ac-001
def test_theme_fingerprint_helper_hashes_raw_bytes(tmp_path: Path) -> None:
    theme = tmp_path / "theme.css"
    theme.write_bytes(b":root { --primary: #0057FF; }\n")

    payload = theme_fingerprint(theme)

    assert payload == {
        "path": str(theme),
        "sha256": hashlib.sha256(theme.read_bytes()).hexdigest(),
    }
    assert len(payload["sha256"]) == 64
    assert payload["sha256"] == payload["sha256"].lower()


def test_theme_fingerprint_helper_empty_file_matches_published_vector(tmp_path: Path) -> None:
    theme = tmp_path / "theme.css"
    theme.write_bytes(b"")

    assert theme_fingerprint(theme)["sha256"] == EMPTY_BYTES_SHA256


# @spec AC-002: Byte sensitivity including CRLF/comment edits — .specs/features/056-evidence-run-identity-theme-fingerprint/spec.md#ac-002
def test_theme_fingerprint_helper_is_byte_sensitive(tmp_path: Path) -> None:
    lf = tmp_path / "lf.css"
    crlf = tmp_path / "crlf.css"
    comment = tmp_path / "comment.css"
    lf.write_bytes(b"--radius: 8px;\n")
    crlf.write_bytes(b"--radius: 8px;\r\n")
    comment.write_bytes(b"--radius: 8px;\n/* note */\n")

    digests = {theme_fingerprint(path)["sha256"] for path in (lf, crlf, comment)}

    assert len(digests) == 3


def test_theme_fingerprint_helper_fails_closed_on_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        theme_fingerprint(tmp_path / "missing.css")


# @spec AC-001: theme-fingerprint exits 0 with exact {path, sha256} JSON — .specs/features/056-evidence-run-identity-theme-fingerprint/spec.md#ac-001
def test_theme_fingerprint_command_emits_path_and_sha256(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    theme = tmp_path / "theme.css"
    theme.write_bytes(b":root { --primary: #0057FF; }\n")

    assert main(["theme-fingerprint", str(theme), "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "path": str(theme),
        "sha256": hashlib.sha256(theme.read_bytes()).hexdigest(),
    }


# @spec AC-002: Reruns are byte-identical — .specs/features/056-evidence-run-identity-theme-fingerprint/spec.md#ac-002
def test_theme_fingerprint_command_reruns_are_byte_identical(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    theme = tmp_path / "theme.css"
    theme.write_bytes(b"--radius: 8px;\n")

    assert main(["theme-fingerprint", str(theme), "--json"]) == 0
    first = capsys.readouterr().out
    assert main(["theme-fingerprint", str(theme), "--json"]) == 0
    second = capsys.readouterr().out

    assert first == second


def test_theme_fingerprint_command_human_mode_prints_lines_without_status(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    theme = tmp_path / "theme.css"
    theme.write_bytes(b"--radius: 8px;\n")

    assert main(["theme-fingerprint", str(theme)]) == 0

    out = capsys.readouterr().out
    assert f"path: {theme}" in out
    assert "sha256: " in out
    assert "Status:" not in out


# @spec AC-003: Missing file is a usage boundary, exit 2 — .specs/features/056-evidence-run-identity-theme-fingerprint/spec.md#ac-003
def test_theme_fingerprint_command_missing_file_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["theme-fingerprint", str(tmp_path / "missing.css")]) == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("ERROR:")


def test_theme_fingerprint_command_directory_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["theme-fingerprint", str(tmp_path)]) == 2

    assert capsys.readouterr().err.startswith("ERROR:")


# @spec FR-001: pattern keyword supported by the report subset validator — .specs/features/056-evidence-run-identity-theme-fingerprint/spec.md#fr-001
def test_report_schema_subset_validates_pattern_keyword() -> None:
    schema = {
        "type": "object",
        "properties": {"sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"}},
    }

    assert _validate_json_schema_subset({"sha256": EMPTY_BYTES_SHA256}, schema, "$") == []
    assert _validate_json_schema_subset({"sha256": "ABC"}, schema, "$") == [
        {
            "severity": "error",
            "path": "$.sha256",
            "message": "expected string matching ^[0-9a-f]{64}$",
        }
    ]


def test_schema_subset_pattern_keyword_fails_closed_on_malformed_schema() -> None:
    # Invariant: a malformed bundled schema (non-string or invalid-regex
    # `pattern`) must surface as a deterministic validation issue, never crash.
    non_string = {"type": "string", "pattern": 42}
    assert _validate_json_schema_subset("abc", non_string, "$") == [
        {
            "severity": "error",
            "path": "$.__schema__.pattern",
            "message": "schema pattern must be a string",
        }
    ]
    bad_regex = {"type": "string", "pattern": "["}
    issues = _validate_json_schema_subset("abc", bad_regex, "$")
    assert len(issues) == 1
    assert issues[0]["path"] == "$.__schema__.pattern"
    assert issues[0]["message"].startswith("schema pattern is not a valid regex:")


# @spec AC-013: every argparse command is closed over the lifecycle registry.
def test_cli_subcommands_match_closed_lifecycle_registry() -> None:
    parser = build_parser()
    subparsers = next(
        action for action in parser._actions if isinstance(action, argparse._SubParsersAction)
    )
    registered = set(subparsers.choices)
    registered.discard("validate")
    registered.discard("migrate-flow-md-to-contract-json")
    registered.add("migrate-flow-contract")

    assert registered == (
        set(PRODUCER_COMMANDS)
        | set(READ_ONLY_COMMANDS)
        | (set(LIFECYCLE_EXEMPT_COMMANDS) - {"--help", "--version"})
    )
    assert set(_PRODUCER_PATH_ARGUMENTS) == set(PRODUCER_COMMANDS)
    for command in sorted(set(PRODUCER_COMMANDS) | set(READ_ONLY_COMMANDS)):
        parser_command = (
            "migrate-flow-md-to-contract-json" if command == "migrate-flow-contract" else command
        )
        command_parser = subparsers.choices[parser_command]
        assert any(action.dest == "project" for action in command_parser._actions), command


def _init_git_consumer(tmp_path: Path) -> tuple[Path, Path]:
    """Create a governed consumer with one canonical nested canvas."""
    project = tmp_path / "consumer"
    project.mkdir()
    # Git setup is a bounded system contract: success is mandatory within 10s.
    subprocess.run(["git", "init", "-q"], cwd=project, check=True, timeout=10)
    subprocess.run(
        ["git", "config", "user.email", "penflow-tests@example.invalid"],
        cwd=project,
        check=True,
        timeout=10,
    )
    subprocess.run(
        ["git", "config", "user.name", "Penflow Tests"],
        cwd=project,
        check=True,
        timeout=10,
    )
    canvas = project / "design" / "ui.pen"
    canvas.parent.mkdir()
    canvas.write_bytes((Path(__file__).parents[1] / "examples/demo/ui.pen").read_bytes())
    return project, canvas


def _run_governed_cli(
    capsys: pytest.CaptureFixture[str], project: Path, *args: str
) -> tuple[int, dict[str, object]]:
    """Run one JSON CLI command after clearing its prior captured output."""
    capsys.readouterr()
    code = main([*args, "--project", str(project), "--json"])
    return code, json.loads(capsys.readouterr().out)


def _assert_clean_managed_run(project: Path, *, receipt_count: int) -> None:
    """Assert a producer finalized all transient run state."""
    assert list((project / ".penflow-tmp/runs").iterdir()) == []
    assert len(list((project / ".penflow-tmp/receipts").glob("*.json"))) == receipt_count


def test_governed_producer_cleans_managed_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project, canvas = _init_git_consumer(tmp_path)

    assert main(["doctor", "--project", str(project), "--fix", "--json"]) == 0
    expected = project / "expected-ui-tree.json"
    code, report = _run_governed_cli(
        capsys, project, "export-expected", str(canvas), "--out", str(expected)
    )
    assert code == 0
    assert report["screens"]
    assert expected.is_file()
    _assert_clean_managed_run(project, receipt_count=1)


def test_governed_producer_rejects_peer_pen(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project, canvas = _init_git_consumer(tmp_path)
    assert main(["doctor", "--project", str(project), "--fix", "--json"]) == 0

    updates = project / "updates.json"
    updates.write_text("{}\n", encoding="utf-8")
    peer = project / "draft.pen"
    code, blocked = _run_governed_cli(
        capsys,
        project,
        "update-pen",
        str(canvas),
        str(updates),
        "--out",
        str(peer),
    )
    assert code == 3
    assert blocked["status"] == "BLOCKED"
    assert blocked["issues"] == [
        {
            "severity": "error",
            "code": "project.path_blocked",
            "message": (
                "update-pen --out must resolve to canonical design/ui.pen; "
                "peer .pen files are forbidden"
            ),
        }
    ]
    assert not peer.exists()


# @spec AC-016: Feature 074 core remains local-artifact/Git only.
def test_runtime_isolation_forbidden_dependencies_are_absent() -> None:
    forbidden_import_roots = {
        "cc_hub",
        "metro",
        "pencil",
        "playwright",
        "react_native",
        "selenium",
        "pencil_mcp",
        "xcode",
        "simctl",
    }
    forbidden_process_tokens = (
        "react-native",
        "metro",
        "cc-hub",
        "pencil",
        "playwright",
        "xcode",
        "simctl",
        "browser",
    )
    subprocess_calls = {"run", "call", "check_call", "check_output", "popen"}
    os_process_calls = {"system", "popen", "spawn", "spawnl", "spawnlp", "spawnv", "spawnvp"}
    source_root = Path(__file__).parents[1] / "penflow"
    # pencil_sync.py is the explicitly reviewed OS adapter; Feature 074 core
    # isolation covers every other production Python module discovered here.
    reviewed_runtime_adapter_allowlist = {Path("pencil_sync.py")}
    discovered_modules = {path.relative_to(source_root) for path in source_root.rglob("*.py")}
    assert reviewed_runtime_adapter_allowlist <= discovered_modules
    feature_modules = sorted(discovered_modules - reviewed_runtime_adapter_allowlist)
    observed_imports: set[str] = set()
    subprocess_literals: list[str] = []
    for relative_path in feature_modules:
        source = (source_root / relative_path).read_text(encoding="utf-8")
        tree = ast.parse(source)
        module_aliases: dict[str, str] = {}
        call_aliases: dict[str, tuple[str, str]] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                observed_imports.update(alias.name.split(".", 1)[0] for alias in node.names)
                for alias in node.names:
                    root = alias.name.split(".", 1)[0]
                    if root in {"subprocess", "os"}:
                        module_aliases[alias.asname or root] = root
            elif isinstance(node, ast.ImportFrom) and node.module:
                root = node.module.split(".", 1)[0]
                observed_imports.add(root)
                if root in {"subprocess", "os"}:
                    for alias in node.names:
                        call_aliases[alias.asname or alias.name] = (root, alias.name.lower())

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                process_call: tuple[str, str] | None = None
                function = node.func
                if isinstance(function, ast.Name):
                    process_call = call_aliases.get(function.id)
                elif isinstance(function, ast.Attribute) and isinstance(function.value, ast.Name):
                    module = module_aliases.get(function.value.id)
                    if module is not None:
                        process_call = (module, function.attr.lower())
                elif (
                    isinstance(function, ast.Call)
                    and isinstance(function.func, ast.Name)
                    and function.func.id == "getattr"
                    and len(function.args) >= 2
                    and isinstance(function.args[0], ast.Name)
                    and isinstance(function.args[1], ast.Constant)
                    and isinstance(function.args[1].value, str)
                ):
                    module = module_aliases.get(function.args[0].id)
                    if module is not None:
                        process_call = (module, function.args[1].value.lower())
                if process_call is not None and (
                    (process_call[0] == "subprocess" and process_call[1] in subprocess_calls)
                    or (
                        process_call[0] == "os"
                        and (
                            process_call[1] in os_process_calls
                            or process_call[1].startswith(("exec", "spawn"))
                        )
                    )
                ):
                    subprocess_literals.extend(
                        child.value.lower()
                        for child in ast.walk(node)
                        if isinstance(child, ast.Constant) and isinstance(child.value, str)
                    )

    assert observed_imports.isdisjoint(forbidden_import_roots)
    assert not any(
        token in literal for literal in subprocess_literals for token in forbidden_process_tokens
    )


def test_read_only_command_runs_health_without_managed_run(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project = tmp_path / "read-only-consumer"
    project.mkdir()
    # Git setup is a bounded system contract: success is mandatory within 10s.
    subprocess.run(["git", "init", "-q"], cwd=project, check=True, timeout=10)
    canvas = project / "ui.pen"
    canvas.write_bytes((Path(__file__).parents[1] / "examples/demo/ui.pen").read_bytes())
    assert main(["doctor", "--project", str(project), "--fix", "--json"]) == 0
    capsys.readouterr()
    manifests = project / ".penflow-tmp" / "manifests"
    before = sorted(path.name for path in manifests.glob("*.json"))

    assert main(["validate-pen", str(canvas), "--project", str(project), "--json"]) == 0

    assert sorted(path.name for path in manifests.glob("*.json")) == before
    assert not (project / ".penflow-tmp" / "receipts").exists()


def test_process_cli_producer_defaults_project_to_cwd(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project = tmp_path / "cwd-consumer"
    project.mkdir()
    # Git setup is a bounded system contract: success is mandatory within 10s.
    subprocess.run(["git", "init", "-q"], cwd=project, check=True, timeout=10)
    subprocess.run(
        ["git", "config", "user.email", "penflow-tests@example.invalid"],
        cwd=project,
        check=True,
        timeout=10,
    )
    subprocess.run(
        ["git", "config", "user.name", "Penflow Tests"],
        cwd=project,
        check=True,
        timeout=10,
    )
    canvas = project / "ui.pen"
    canvas.write_bytes((Path(__file__).parents[1] / "examples/demo/ui.pen").read_bytes())
    assert main(["doctor", "--project", str(project), "--fix", "--json"]) == 0
    capsys.readouterr()

    monkeypatch.chdir(project)
    monkeypatch.setattr(
        sys,
        "argv",
        ["penflow", "export-expected", "ui.pen", "--out", "expected-ui-tree.json", "--json"],
    )
    assert main() == 0
    assert (project / "expected-ui-tree.json").is_file()
    assert list((project / ".penflow-tmp/runs").iterdir()) == []


def test_programmatic_cli_producer_defaults_project_to_cwd(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project = tmp_path / "programmatic-consumer"
    project.mkdir()
    # Git setup is a bounded system contract: success is mandatory within 10s.
    subprocess.run(["git", "init", "-q"], cwd=project, check=True, timeout=10)
    canvas = project / "ui.pen"
    canvas.write_bytes((Path(__file__).parents[1] / "examples/demo/ui.pen").read_bytes())
    assert main(["doctor", "--project", str(project), "--fix", "--json"]) == 0
    capsys.readouterr()

    monkeypatch.chdir(project)
    assert cli_module.main(["export-expected", "ui.pen", "--out", "expected.json", "--json"]) == 0

    assert (project / "expected.json").is_file()
    assert list((project / ".penflow-tmp/runs").iterdir()) == []


def test_cli_project_selector_and_boundary_have_distinct_exit_codes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "missing"
    assert main(["doctor", "--project", str(missing), "--check", "--json"]) == 2
    missing_report = json.loads(capsys.readouterr().out)
    assert missing_report["issues"][0]["code"] == "project.path_missing"

    outside_git = tmp_path / "outside-git"
    outside_git.mkdir()
    assert main(["doctor", "--project", str(outside_git), "--check", "--json"]) == 3
    unsafe_report = json.loads(capsys.readouterr().out)
    assert unsafe_report["issues"][0]["code"] == "not_git_project"
