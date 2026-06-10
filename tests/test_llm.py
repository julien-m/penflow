# @spec(FR-007)
"""Feature 054 — direct unit coverage for `penflow/llm.py`.

Invariant protected: review/fix guidance is a pure deterministic mapping from
compare-report issue codes to documented cause, fix, and owner strings — no
LLM, no heuristics, byte-stable envelopes. Every documented code branch is
asserted by name so a silently dropped branch fails here, not downstream.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from penflow.llm import fix_compare_report, review_compare_report

KNOWN_CODES = [
    ("node.missing", "absent from the actual tree", "Add the missing runtime element"),
    ("node.role", "Runtime role diverges", "Align runtime accessibility role"),
    ("node.text", "Runtime text differs", "Update runtime text"),
    ("node.bbox.x", "geometry exceeds the configured tolerance", "tolerance.bbox_px"),
    ("node.visual.fill", "differs from the expected design token", "Align styling"),
    ("node.hierarchy", "parent hierarchy differs", "expected semantic parent"),
    ("node.order", "sibling order differs", "Reorder runtime siblings"),
    ("actual.schema", "does not match the required schema", "Emit the required actual-tree"),
]


def write_report(path: Path, issues: list[dict[str, Any]]) -> Path:
    path.write_text(
        json.dumps({"status": "FAIL", "score": 0.5, "issues": issues}), encoding="utf-8"
    )
    return path


@pytest.mark.parametrize(("code", "cause_part", "fix_part"), KNOWN_CODES)
def test_every_documented_code_maps_to_cause_and_fix(
    tmp_path: Path, code: str, cause_part: str, fix_part: str
) -> None:
    report = write_report(tmp_path / "compare.json", [{"code": code, "semantic_id": "x"}])
    [review_issue] = review_compare_report(report)["issues"]
    assert cause_part in review_issue["likely_cause"]
    [fix] = fix_compare_report(report)["fixes"]
    assert fix_part in fix["fix"]


def test_review_report_envelope_is_stable(tmp_path: Path) -> None:
    report = write_report(
        tmp_path / "compare.json", [{"code": "node.text", "semantic_id": "checkout.title"}]
    )
    review = review_compare_report(report)
    assert review["kind"] == "penflow-review-report"
    assert review["version"] == 1
    assert review["status"] == "FAIL"
    assert review["score"] == 0.5
    [issue] = review["issues"]
    assert issue["semantic_id"] == "checkout.title"
    assert issue["code"] == "node.text"
    assert review_compare_report(report) == review  # deterministic rerun


def test_fix_report_envelope_is_stable(tmp_path: Path) -> None:
    report = write_report(
        tmp_path / "compare.json", [{"code": "node.missing", "semantic_id": "checkout.pay"}]
    )
    fixes = fix_compare_report(report)
    assert fixes["kind"] == "penflow-fix-report"
    assert fixes["version"] == 1
    [fix] = fixes["fixes"]
    assert fix["semantic_id"] == "checkout.pay"
    assert fix["target"] == "runtime implementation or `.pen` contract"
    assert fix_compare_report(report) == fixes  # deterministic rerun


def test_owner_routing_by_code_family(tmp_path: Path) -> None:
    report = write_report(
        tmp_path / "compare.json",
        [
            {"code": "actual.schema"},
            {"code": "node.visual.fill"},
            {"code": "node.bbox.width"},
            {"code": "node.role"},
            {"code": "wat.unknown"},
        ],
    )
    owners = [issue["owner"] for issue in review_compare_report(report)["issues"]]
    assert owners == [
        "actual-tree exporter",
        "runtime layout/styling or `.pen` tolerance",
        "runtime layout/styling or `.pen` tolerance",
        "runtime implementation or `.pen` contract",
        "manual review",
    ]


def test_unknown_code_falls_back_to_message_then_generic(tmp_path: Path) -> None:
    report = write_report(
        tmp_path / "compare.json",
        [{"code": "wat.unknown", "message": "custom message"}, {"code": "wat.unknown"}],
    )
    causes = [issue["likely_cause"] for issue in review_compare_report(report)["issues"]]
    assert causes == ["custom message", "Compare report issue requires inspection."]
    fixes = [fix["fix"] for fix in fix_compare_report(report)["fixes"]]
    assert fixes == ["Inspect the expected and actual trees for this semantic id."] * 2


def test_empty_issue_list_yields_empty_guidance(tmp_path: Path) -> None:
    path = tmp_path / "compare.json"
    path.write_text(json.dumps({"status": "PASS", "score": 1.0, "issues": []}), encoding="utf-8")
    assert review_compare_report(path)["issues"] == []
    assert fix_compare_report(path)["fixes"] == []


def test_missing_status_and_score_default_safely(tmp_path: Path) -> None:
    path = tmp_path / "compare.json"
    path.write_text(json.dumps({}), encoding="utf-8")
    review = review_compare_report(path)
    assert review["status"] == "UNKNOWN"
    assert review["score"] is None
