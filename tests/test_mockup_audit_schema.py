# @spec(AC-004)
# @spec(FR-005)
# @spec(FR-007)
# @spec(FR-008)
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from penflow.cli import main

AUDIT_FIXTURE = Path("examples/full/.mockup-validation/audit-report.json")
CHECKLIST_FIXTURE = Path("examples/full/.mockup-validation/checkout/checklist.json")

GATES = (
    "tokens",
    "consistency",
    "accessibility_alignment",
    "contract",
    "structural_fidelity",
    "balance_readability",
)


def _load_audit() -> dict[str, Any]:
    return json.loads(AUDIT_FIXTURE.read_text(encoding="utf-8"))


def _load_checklist() -> dict[str, Any]:
    return json.loads(CHECKLIST_FIXTURE.read_text(encoding="utf-8"))


def _validate(
    tmp_path: Path, report: dict[str, Any], filename: str, *, seed_reports: bool = True
) -> int:
    path = tmp_path / filename
    if seed_reports:
        for gate in report.get("gates", []):
            report_path = gate.get("report_path") if isinstance(gate, dict) else None
            if isinstance(report_path, str):
                receipt = tmp_path / report_path
                receipt.parent.mkdir(parents=True, exist_ok=True)
                receipt.write_text(json.dumps({"status": "PASS"}), encoding="utf-8")
    path.write_text(json.dumps(report), encoding="utf-8")
    return main(["validate-report", str(path), "--schema", "--json"])


# @spec AC-004: valid fixture passes — .specs/features/052-prescriptive-rubric-bounded-fix-loop/spec.md#ac-004
def test_examples_full_audit_report_fixture_passes() -> None:
    assert main(["validate-report", str(AUDIT_FIXTURE), "--schema", "--json"]) == 0


def test_examples_full_checklist_fixture_passes() -> None:
    assert main(["validate-report", str(CHECKLIST_FIXTURE), "--schema", "--json"]) == 0


def test_audit_fixture_proves_all_six_gates() -> None:
    audit = _load_audit()
    assert audit["kind"] == "penflow-mockup-audit"
    assert audit["iterations"] == 1
    assert tuple(entry["gate"] for entry in audit["gates"]) == GATES
    for entry in audit["gates"][:5]:
        assert entry["exit_code"] is None
        assert entry["result"] == "not_run"
        assert entry["report_path"] is None
        assert entry["command"].startswith("penflow ")
    assert audit["gates"][5]["exit_code"] == 0
    assert audit["gates"][5]["result"] == "pass"
    assert audit["gates"][5]["report_path"]


# @spec AC-005: missing gates[] fails — .specs/features/052-prescriptive-rubric-bounded-fix-loop/spec.md#ac-005
def test_audit_report_missing_gates_fails(tmp_path: Path) -> None:
    audit = _load_audit()
    del audit["gates"]

    assert _validate(tmp_path, audit, "audit-report.json") == 1


# @spec AC-006: unknown status fails — .specs/features/052-prescriptive-rubric-bounded-fix-loop/spec.md#ac-006
def test_audit_report_unknown_status_fails(tmp_path: Path) -> None:
    audit = _load_audit()
    audit["status"] = "DONE"

    assert _validate(tmp_path, audit, "audit-report.json") == 1


def test_audit_report_missing_iterations_fails(tmp_path: Path) -> None:
    audit = _load_audit()
    del audit["iterations"]

    assert _validate(tmp_path, audit, "audit-report.json") == 1


def test_audit_report_missing_residual_issues_fails(tmp_path: Path) -> None:
    audit = _load_audit()
    del audit["residual_issues"]

    assert _validate(tmp_path, audit, "audit-report.json") == 1


# @spec AC-007: strictness — .specs/features/052-prescriptive-rubric-bounded-fix-loop/spec.md#ac-007
def test_audit_report_additional_top_level_property_fails(tmp_path: Path) -> None:
    audit = _load_audit()
    audit["notes"] = "prose verdict"

    assert _validate(tmp_path, audit, "audit-report.json") == 1


def test_gate_entry_missing_exit_code_fails(tmp_path: Path) -> None:
    audit = _load_audit()
    del audit["gates"][0]["exit_code"]

    assert _validate(tmp_path, audit, "audit-report.json") == 1


def test_gate_entry_missing_report_path_fails(tmp_path: Path) -> None:
    audit = _load_audit()
    del audit["gates"][0]["report_path"]

    assert _validate(tmp_path, audit, "audit-report.json") == 1


def test_gate_entry_unknown_gate_name_fails(tmp_path: Path) -> None:
    audit = _load_audit()
    audit["gates"][0]["gate"] = "vibes"

    assert _validate(tmp_path, audit, "audit-report.json") == 1


def test_gate_entry_additional_property_fails(tmp_path: Path) -> None:
    audit = _load_audit()
    audit["gates"][0]["comment"] = "looked fine"

    assert _validate(tmp_path, audit, "audit-report.json") == 1


def test_gate_entry_not_run_allows_null_exit_code_and_report_path(tmp_path: Path) -> None:
    audit = _load_audit()
    audit["gates"][4] = {
        "gate": "structural_fidelity",
        "command": "penflow compare-tree expected-ui-tree.json actual-ui-tree.json --json",
        "exit_code": None,
        "report_path": None,
        "result": "not_run",
    }

    assert _validate(tmp_path, audit, "audit-report.json") == 0


def test_audit_report_missing_referenced_report_path_fails(tmp_path: Path) -> None:
    audit = _load_audit()
    audit["gates"][5]["report_path"] = "missing-report.json"

    assert _validate(tmp_path, audit, "audit-report.json", seed_reports=False) == 1


def test_audit_report_pass_result_requires_zero_exit_code(tmp_path: Path) -> None:
    audit = _load_audit()
    audit["gates"][5]["result"] = "pass"
    audit["gates"][5]["exit_code"] = 1

    assert _validate(tmp_path, audit, "audit-report.json") == 1


def test_audit_report_fail_result_requires_nonzero_exit_code(tmp_path: Path) -> None:
    audit = _load_audit()
    audit["gates"][5]["result"] = "fail"
    audit["gates"][5]["exit_code"] = 0

    assert _validate(tmp_path, audit, "audit-report.json") == 1


def test_audit_report_not_run_rejects_receipt_path_or_exit_code(tmp_path: Path) -> None:
    audit = _load_audit()
    audit["gates"][0]["report_path"] = "token-lint-report.json"

    assert _validate(tmp_path, audit, "audit-report.json") == 1


def test_residual_issue_requires_severity_and_blocking(tmp_path: Path) -> None:
    for key in ("severity", "blocking", "gate", "code", "message"):
        audit = _load_audit()
        del audit["residual_issues"][0][key]
        assert _validate(tmp_path, audit, "audit-report.json") == 1, key


# @spec AC-009: kind routing — .specs/features/052-prescriptive-rubric-bounded-fix-loop/spec.md#ac-009
def test_audit_and_checklist_route_by_kind_not_filename(tmp_path: Path) -> None:
    assert _validate(tmp_path, _load_audit(), "final-report.json") == 0
    assert _validate(tmp_path, _load_checklist(), "items-report.json") == 0


def test_legacy_kindless_audit_report_fails(tmp_path: Path) -> None:
    assert _validate(tmp_path, {"status": "PASS"}, "audit-report.json") == 1


# @spec AC-008: anchored checklist items — .specs/features/052-prescriptive-rubric-bounded-fix-loop/spec.md#ac-008
def test_checklist_item_requires_anchor_severity_and_blocking(tmp_path: Path) -> None:
    for key in ("screen_id", "severity", "blocking", "id", "title", "status"):
        checklist = _load_checklist()
        del checklist["items"][0][key]
        assert _validate(tmp_path, checklist, "checklist.json") == 1, key


def test_checklist_item_additional_property_fails(tmp_path: Path) -> None:
    checklist = _load_checklist()
    checklist["items"][0]["note"] = "unanchored"

    assert _validate(tmp_path, checklist, "checklist.json") == 1


def test_checklist_item_status_enum_is_locked(tmp_path: Path) -> None:
    checklist = _load_checklist()
    checklist["items"][0]["status"] = "maybe-later"

    assert _validate(tmp_path, checklist, "checklist.json") == 1
