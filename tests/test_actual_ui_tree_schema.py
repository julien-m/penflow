"""Tests for feature 037 — document and validate actual UI tree (contract C12).

Covers:
- AC-001: schema file shape (`$schema`, `$id`, recursive `node` / `bbox` `$defs`)
- AC-002: valid demo fixture passes structural validation
- AC-003: valid demo fixture passes schema-mode validation
- AC-004: invalid fixture produces structured errors
- AC-005: byte-deterministic CLI output across two runs
- AC-006: `validate_actual_tree(tree)` v0 signature backward compatibility
- AC-007: schema mode catches missing `version`
- AC-009: no runtime / codegen / adapter leak in this feature's diff
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from penflow.tree import load_tree, validate_actual_tree

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = ROOT / "penflow" / "schemas" / "actual-ui-tree.schema.json"
VALID_FIXTURE = ROOT / "examples" / "demo" / "actual-ui-tree.json"
INVALID_FIXTURE = ROOT / "examples" / "demo" / "actual-ui-tree.invalid.json"


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "penflow", *args],
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=False,
    )


# AC-001
def test_schema_file_exists_and_declares_draft_2020_12() -> None:
    assert SCHEMA_PATH.exists(), "actual-ui-tree JSON Schema must ship at penflow/schemas/"
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["$id"] == "https://penflow.dev/schemas/actual-ui-tree.schema.json"
    assert "node" in schema["$defs"]
    assert "bbox" in schema["$defs"]
    assert set(schema["$defs"]["node"]["required"]) == {"id", "role", "bbox"}
    assert set(schema["$defs"]["bbox"]["required"]) == {"x", "y", "width", "height"}
    assert set(schema["required"]) == {"version", "screens"}


# AC-002, AC-006
def test_valid_demo_fixture_passes_structural() -> None:
    assert validate_actual_tree(load_tree(VALID_FIXTURE)) == []


# AC-003, FR-006
def test_valid_demo_fixture_passes_schema_mode() -> None:
    assert validate_actual_tree(load_tree(VALID_FIXTURE), schema=True) == []


# AC-004
def test_invalid_fixture_fails_structural() -> None:
    issues = validate_actual_tree(load_tree(INVALID_FIXTURE))
    assert any("version" in issue["path"] for issue in issues)
    assert any("bbox" in issue["path"] for issue in issues)
    assert all(issue["severity"] == "error" for issue in issues)


# AC-007
def test_schema_mode_catches_missing_version() -> None:
    tree = {
        "screens": [
            {
                "screen_id": "s",
                "root": {
                    "id": "r",
                    "role": "screen",
                    "bbox": {"x": 0, "y": 0, "width": 1, "height": 1},
                },
            }
        ]
    }
    issues = validate_actual_tree(tree, schema=True)
    assert any("version" in issue["path"] for issue in issues)


# AC-006 — v0 signature, no kwargs, returns legacy shape
def test_v0_signature_backward_compatible() -> None:
    tree = load_tree(VALID_FIXTURE)
    issues = validate_actual_tree(tree)
    # legacy shape: list of dicts with {severity, path, message}
    assert isinstance(issues, list)
    for issue in issues:
        assert set(issue.keys()) == {"severity", "path", "message"}
    # And the v0 default (schema=False) is byte-identical to passing schema=False explicitly
    assert validate_actual_tree(tree) == validate_actual_tree(tree, schema=False)


# AC-002
def test_cli_validate_actual_json_pass() -> None:
    result = _run_cli("validate-actual", str(VALID_FIXTURE), "--json")
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "PASS"
    assert payload["issues"] == []


# AC-003
def test_cli_validate_actual_schema_flag_pass() -> None:
    result = _run_cli("validate-actual", str(VALID_FIXTURE), "--schema", "--json")
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "PASS"
    assert payload["issues"] == []


# AC-004
def test_cli_validate_actual_invalid_fixture_fails() -> None:
    result = _run_cli("validate-actual", str(INVALID_FIXTURE), "--json")
    assert result.returncode != 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "FAIL"
    assert any(
        issue["severity"] == "error" and "bbox" in issue["path"] for issue in payload["issues"]
    )


# AC-005
def test_cli_output_is_byte_deterministic() -> None:
    first = _run_cli("validate-actual", str(VALID_FIXTURE), "--json")
    second = _run_cli("validate-actual", str(VALID_FIXTURE), "--json")
    assert first.returncode == 0 and second.returncode == 0
    assert first.stdout == second.stdout
    # Schema mode is also deterministic
    first_s = _run_cli("validate-actual", str(VALID_FIXTURE), "--schema", "--json")
    second_s = _run_cli("validate-actual", str(VALID_FIXTURE), "--schema", "--json")
    assert first_s.stdout == second_s.stdout


# AC-009 — runtime / codegen / adapter boundary
def test_no_runtime_dependencies_added() -> None:
    # No penflow/codegen/ package introduced or modified by this feature.
    codegen_dir = ROOT / "penflow" / "codegen"
    assert not codegen_dir.exists(), (
        "feature 037 must NOT add penflow/codegen/ — runtime adapters are feature 038"
    )
    # No examples/generated-demo/ mutation: simply assert nothing under that
    # path is required by this feature's tests.
    # And SwiftUI/React/Rust adapter source files outside the legacy demo
    # examples must not have grown new top-level entries here.
    legacy_demo_files = {
        "Checkout.jsx",
        "checkout.rs",
        "CheckoutView.swift",
    }
    demo_dir = ROOT / "examples" / "demo"
    actual_runtime_like = {
        path.name for path in demo_dir.iterdir() if path.suffix in {".swift", ".rs", ".jsx", ".tsx"}
    }
    assert actual_runtime_like.issubset(legacy_demo_files), (
        "feature 037 must not add new runtime adapter files; "
        f"unexpected runtime-like files in examples/demo/: {sorted(actual_runtime_like - legacy_demo_files)}"
    )
