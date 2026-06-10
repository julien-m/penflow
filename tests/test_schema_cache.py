# @spec(FR-003)
"""Feature 054 — schema cache contract (C29) and perf regression.

Invariant protected: bundled JSON Schemas are immutable package data read at
most once per process — repeated validations perform zero schema file reads —
while callers never share mutable schema state (`load_schema` hands out
defensive deep copies) and validation semantics stay byte-identical.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from penflow import schema_cache
from penflow.cli import _validate_report_schema, main
from penflow.llm import review_compare_report
from penflow.schema_cache import SCHEMAS_DIR, load_schema, validator_for
from penflow.tree import validate_actual_tree

ROOT = Path(__file__).resolve().parent.parent


class SchemaReadCounter:
    """Count `Path.read_text` calls that target bundled schema files."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.reads: list[str] = []
        original = Path.read_text

        def counting_read_text(
            path: Path, encoding: str | None = None, errors: str | None = None
        ) -> str:
            if path.is_relative_to(SCHEMAS_DIR):
                self.reads.append(path.name)
            return original(path, encoding=encoding, errors=errors)

        monkeypatch.setattr(Path, "read_text", counting_read_text)

    def reset(self) -> None:
        self.reads.clear()


def valid_actual_tree() -> dict[str, Any]:
    return {
        "version": 1,
        "screens": [
            {
                "screen_id": "checkout",
                "viewport": {"width": 390, "height": 844},
                "root": {
                    "id": "checkout",
                    "role": "screen",
                    "bbox": {"x": 0, "y": 0, "width": 390, "height": 844},
                    "children": [],
                },
            }
        ],
    }


# --- cache contract ---------------------------------------------------------


def test_load_schema_returns_equal_but_isolated_copies() -> None:
    first = load_schema("code-ir.schema.json")
    second = load_schema("code-ir.schema.json")
    assert first == second
    assert first is not second
    first["title"] = "mutated by caller"
    first["properties"]["injected"] = {}
    assert load_schema("code-ir.schema.json") == second


def test_validator_for_returns_the_same_compiled_instance() -> None:
    assert validator_for("actual-ui-tree.schema.json") is validator_for(
        "actual-ui-tree.schema.json"
    )
    assert validator_for("actual-ui-tree.schema.json") is not validator_for("code-ir.schema.json")


def test_unknown_schema_name_raises_file_not_found() -> None:
    with pytest.raises(FileNotFoundError):
        load_schema("no-such.schema.json")
    with pytest.raises(FileNotFoundError):
        validator_for("no-such.schema.json")


def test_no_schema_file_reads_outside_schema_cache() -> None:
    """AC-003 — the cache is the single read path for bundled schemas."""
    offenders: list[str] = []
    for module in sorted((ROOT / "penflow").rglob("*.py")):
        if module.name == "schema_cache.py":
            continue
        for number, line in enumerate(module.read_text(encoding="utf-8").splitlines(), start=1):
            if "read_text" in line and "schema" in line.lower():
                offenders.append(f"{module.name}:{number}: {line.strip()}")
    assert offenders == []


# --- perf regression (FR-003) ------------------------------------------------


def test_second_actual_tree_validation_performs_zero_schema_file_reads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schema_cache.clear_cache()
    counter = SchemaReadCounter(monkeypatch)
    tree = valid_actual_tree()

    assert validate_actual_tree(tree, schema=True) == []
    assert counter.reads.count("actual-ui-tree.schema.json") == 1

    counter.reset()
    assert validate_actual_tree(tree, schema=True) == []
    assert counter.reads == []


def test_second_report_schema_validation_performs_zero_schema_file_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    compare_path = tmp_path / "compare-report.json"
    compare_path.write_text(
        json.dumps({"status": "PASS", "score": 1.0, "issues": []}), encoding="utf-8"
    )
    report = review_compare_report(compare_path)

    schema_cache.clear_cache()
    counter = SchemaReadCounter(monkeypatch)

    assert _validate_report_schema(report, "review-report.json") == []
    assert counter.reads.count("review-report.schema.json") == 1

    counter.reset()
    assert _validate_report_schema(report, "review-report.json") == []
    assert counter.reads == []


def test_repeated_cli_validate_report_reads_each_schema_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end: two CLI runs over the same report read its schema once."""
    compare_path = tmp_path / "compare-report.json"
    compare_path.write_text(
        json.dumps({"status": "PASS", "score": 1.0, "issues": []}), encoding="utf-8"
    )
    report_path = tmp_path / "review-report.json"
    report_path.write_text(json.dumps(review_compare_report(compare_path)), encoding="utf-8")

    schema_cache.clear_cache()
    counter = SchemaReadCounter(monkeypatch)

    assert main(["validate-report", str(report_path), "--schema", "--json"]) == 0
    assert counter.reads.count("review-report.schema.json") == 1
    counter.reset()
    assert main(["validate-report", str(report_path), "--schema", "--json"]) == 0
    assert counter.reads == []


def test_cached_validation_output_is_identical_to_first_run(tmp_path: Path) -> None:
    """Cache must not change validation semantics — same issues both runs."""
    invalid = {"version": 1, "screens": [{"screen_id": "s", "viewport": {}, "root": {}}]}
    schema_cache.clear_cache()
    first = validate_actual_tree(invalid, schema=True)
    second = validate_actual_tree(invalid, schema=True)
    assert first == second
    assert first  # the fixture is intentionally invalid
