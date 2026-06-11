# @spec FR-010: Branch, round-trip, determinism tests — .specs/features/055-checklist-from-drift-seeding/spec.md#fr-010
"""Tests for deterministic checklist seeding from a drift report (C30)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from penflow.checklist import (
    ChecklistSeedError,
    checklist_from_drift_report,
    seed_checklist_from_drift,
)
from penflow.cli import main
from penflow.drift import detect_drift


def drift_issue(
    severity: str = "warning",
    code: str = "drift.mockup_node_uncovered",
    path: str = "pencil:0.1",
    message: str = "Mockup node has no semantic anchor",
    blocking: bool = False,
    **anchors: Any,
) -> dict[str, Any]:
    issue: dict[str, Any] = {
        "severity": severity,
        "code": code,
        "path": path,
        "message": message,
        "blocking": blocking,
    }
    issue.update(anchors)
    return issue


def drift_report(issues: list[dict[str, Any]]) -> dict[str, Any]:
    errors = sum(1 for issue in issues if issue["severity"] == "error")
    warnings = sum(1 for issue in issues if issue["severity"] == "warning")
    blocking = sum(1 for issue in issues if issue["blocking"])
    if not issues:
        status = "PASS"
    elif blocking:
        status = "BLOCKED"
    else:
        status = "DRIFT"
    return {
        "version": 1,
        "kind": "penflow-drift-report",
        "status": status,
        "summary": {
            "errors": errors,
            "warnings": warnings,
            "blocking": blocking,
            "total": len(issues),
        },
        "inputs": {
            "flow_ui_contract": "flow-ui-contract",
            "semantic_tree": "semantic-ui-tree.json",
            "pen": "ui.pen",
        },
        "issues": issues,
    }


def write_report(tmp_path: Path, report: dict[str, Any], name: str = "drift-report.json") -> Path:
    report_path = tmp_path / name
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report_path


# @spec AC-001: DRIFT report seeds one open item per issue — .specs/features/055-checklist-from-drift-seeding/spec.md#ac-001
def test_drift_issues_become_anchored_open_items(tmp_path: Path) -> None:
    issues = [
        drift_issue(severity="error", code="drift.spec_screen_not_in_tree", path="$.screens"),
        drift_issue(
            severity="warning",
            code="drift.mockup_node_uncovered",
            path="pencil:0.1",
            semantic_id="checkout.pay-now",
        ),
    ]
    report_path = write_report(tmp_path, drift_report(issues))
    out_path = tmp_path / "checklist.json"

    exit_code = main(["checklist-from-drift", str(report_path), "--out", str(out_path)])

    assert exit_code == 0
    checklist = json.loads(out_path.read_text(encoding="utf-8"))
    assert checklist["kind"] == "penflow-mockup-checklist"
    assert checklist["status"] == "OPEN"
    assert len(checklist["items"]) == len(issues)
    for item in checklist["items"]:
        assert item["gate"] == "contract"
        assert item["status"] == "open"


# @spec AC-002: PASS report yields empty PASS checklist — .specs/features/055-checklist-from-drift-seeding/spec.md#ac-002
def test_pass_report_yields_empty_pass_checklist(tmp_path: Path) -> None:
    report_path = write_report(tmp_path, drift_report([]))
    out_path = tmp_path / "checklist.json"

    exit_code = main(["checklist-from-drift", str(report_path), "--out", str(out_path)])

    assert exit_code == 0
    checklist = json.loads(out_path.read_text(encoding="utf-8"))
    assert checklist["status"] == "PASS"
    assert checklist["items"] == []


def test_blocked_report_seeds_open_status_with_blocking_items(tmp_path: Path) -> None:
    issues = [
        drift_issue(
            severity="error",
            code="drift.clarification_marker",
            path="flow-ui-contract/screens/checkout.md:12",
            blocking=True,
        )
    ]
    report_path = write_report(tmp_path, drift_report(issues))
    out_path = tmp_path / "checklist.json"

    exit_code = main(["checklist-from-drift", str(report_path), "--out", str(out_path)])

    assert exit_code == 0
    checklist = json.loads(out_path.read_text(encoding="utf-8"))
    assert checklist["status"] == "OPEN"
    assert all(item["blocking"] is True for item in checklist["items"])


# @spec AC-005: _issue_sort_key order and per-code ordinals — .specs/features/055-checklist-from-drift-seeding/spec.md#ac-005
def test_items_follow_issue_sort_key_order_with_per_code_ordinals() -> None:
    report = drift_report(
        [
            drift_issue(severity="warning", code="drift.mockup_node_uncovered", path="pencil:0.2"),
            drift_issue(severity="error", code="drift.spec_screen_not_in_tree", path="$.screens"),
            drift_issue(severity="warning", code="drift.mockup_node_uncovered", path="pencil:0.1"),
        ]
    )

    checklist = checklist_from_drift_report(report, source_report="drift-report.json", group=None)

    ids = [item["id"] for item in checklist["items"]]
    # severity sorts first ("error" < "warning"), then code, then path.
    assert ids == [
        "drift-spec_screen_not_in_tree-001",
        "drift-mockup_node_uncovered-001",
        "drift-mockup_node_uncovered-002",
    ]
    assert [item["evidence"] for item in checklist["items"][1:]] == ["pencil:0.1", "pencil:0.2"]


def test_shuffled_schema_valid_report_produces_same_checklist() -> None:
    issues = [
        drift_issue(severity="warning", code="drift.mockup_node_uncovered", path="pencil:0.2"),
        drift_issue(severity="error", code="drift.spec_screen_not_in_tree", path="$.screens"),
        drift_issue(severity="warning", code="drift.mockup_node_uncovered", path="pencil:0.1"),
    ]

    # Same sourceReport on both sides: the determinism claim is about issue
    # array order, while sourceReport intentionally records the CLI path.
    sorted_checklist = checklist_from_drift_report(
        drift_report(issues), source_report="drift-report.json", group=None
    )
    shuffled_checklist = checklist_from_drift_report(
        drift_report(list(reversed(issues))), source_report="drift-report.json", group=None
    )

    sorted_bytes = json.dumps(sorted_checklist, indent=2, sort_keys=True)
    shuffled_bytes = json.dumps(shuffled_checklist, indent=2, sort_keys=True)
    assert sorted_bytes == shuffled_bytes


def test_code_without_drift_prefix_used_verbatim_after_dot_replacement() -> None:
    report = drift_report(
        [drift_issue(code="custom.namespace.check", path="$.flows", severity="info")]
    )

    checklist = checklist_from_drift_report(report, source_report="r.json", group=None)

    assert checklist["items"][0]["id"] == "drift-custom-namespace-check-001"


# @spec AC-006: gate/status/title/evidence/severity/blocking mapping — .specs/features/055-checklist-from-drift-seeding/spec.md#ac-006
def test_item_field_mapping_copies_issue_fields_verbatim() -> None:
    issue = drift_issue(
        severity="error",
        code="drift.semantic_node_missing_in_pen",
        path="$.screens[0].root.children[1]",
        message="Semantic node checkout.pay-now missing in Pencil",
        blocking=True,
        semantic_id="checkout.pay-now",
        pencil_node_id="payBtn",
    )

    checklist = checklist_from_drift_report(
        drift_report([issue]), source_report="r.json", group=None
    )

    item = checklist["items"][0]
    assert item["title"] == issue["message"]
    assert item["gate"] == "contract"
    assert item["severity"] == issue["severity"]
    assert item["blocking"] is True
    assert item["status"] == "open"
    assert item["code"] == issue["code"]
    assert item["evidence"] == issue["path"]
    assert item["semantic_id"] == "checkout.pay-now"
    assert item["pencil_node_id"] == "payBtn"
    assert item["screen_id"] == "checkout"


def test_null_semantic_id_treated_as_absent() -> None:
    issue = drift_issue(
        code="drift.flow_not_in_tree",
        path="$.flows",
        semantic_id=None,
        pencil_node_id=None,
    )

    checklist = checklist_from_drift_report(
        drift_report([issue]), source_report="r.json", group=None
    )

    item = checklist["items"][0]
    assert "semantic_id" not in item
    assert "pencil_node_id" not in item
    assert item["screen_id"] == "_workspace"


# @spec AC-007: screens/<stem>.md derivation and _workspace fallback — .specs/features/055-checklist-from-drift-seeding/spec.md#ac-007
@pytest.mark.parametrize(
    ("semantic_id", "path", "expected_screen_id"),
    [
        ("checkout.pay-now", "pencil:0.1", "checkout"),
        ("checkout", "pencil:0", "checkout"),
        (None, "flow-ui-contract/screens/checkout.md", "checkout"),
        (None, "screens/checkout.md:12", "checkout"),
        (None, "$.flows", "_workspace"),
        (None, "$.screens", "_workspace"),
        (None, "$.screens[0].root.children[0]", "_workspace"),
        (None, "pencil:0.1.2", "_workspace"),
    ],
)
def test_screen_id_derivation_cascade(
    semantic_id: str | None, path: str, expected_screen_id: str
) -> None:
    anchors: dict[str, Any] = {} if semantic_id is None else {"semantic_id": semantic_id}
    issue = drift_issue(path=path, **anchors)

    checklist = checklist_from_drift_report(
        drift_report([issue]), source_report="r.json", group=None
    )

    assert len(checklist["items"]) == 1
    assert checklist["items"][0]["screen_id"] == expected_screen_id


def test_no_issue_is_ever_dropped() -> None:
    issues = [
        drift_issue(code="drift.flow_not_in_tree", path="$.flows", severity="error"),
        drift_issue(code="drift.clarification_marker", path="screens/a.md:3", blocking=True),
        drift_issue(code="drift.mockup_node_uncovered", path="pencil:0.4"),
    ]

    checklist = checklist_from_drift_report(
        drift_report(issues), source_report="r.json", group=None
    )

    assert len(checklist["items"]) == len(issues)


# @spec AC-005: byte-identical reruns — .specs/features/055-checklist-from-drift-seeding/spec.md#ac-005
def test_reruns_are_byte_identical(tmp_path: Path) -> None:
    issues = [
        drift_issue(severity="error", code="drift.spec_screen_not_in_tree", path="$.screens"),
        drift_issue(code="drift.mockup_node_uncovered", path="pencil:0.1"),
    ]
    report_path = write_report(tmp_path, drift_report(issues))
    first_out = tmp_path / "first.json"
    second_out = tmp_path / "second.json"

    assert main(["checklist-from-drift", str(report_path), "--out", str(first_out)]) == 0
    assert main(["checklist-from-drift", str(report_path), "--out", str(second_out)]) == 0

    assert first_out.read_bytes() == second_out.read_bytes()


def test_examples_full_chain_is_deterministic_and_lossless(tmp_path: Path) -> None:
    report_path = tmp_path / "drift-report.json"
    report = detect_drift(
        "examples/full/flow-ui-contract",
        "examples/full/semantic-ui-tree.json",
        "examples/full/ui.pen",
        report_path,
    )
    first_out = tmp_path / "first.json"
    second_out = tmp_path / "second.json"

    assert main(["checklist-from-drift", str(report_path), "--out", str(first_out)]) == 0
    assert main(["checklist-from-drift", str(report_path), "--out", str(second_out)]) == 0

    assert first_out.read_bytes() == second_out.read_bytes()
    checklist = json.loads(first_out.read_text(encoding="utf-8"))
    assert len(checklist["items"]) == len(report["issues"])
    assert main(["validate-report", str(first_out), "--schema"]) == 0


# @spec AC-003: invalid inputs exit 1 with no output — .specs/features/055-checklist-from-drift-seeding/spec.md#ac-003
def test_unreadable_input_exits_1_without_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out_path = tmp_path / "checklist.json"

    exit_code = main(
        ["checklist-from-drift", str(tmp_path / "missing.json"), "--out", str(out_path)]
    )

    assert exit_code == 1
    assert not out_path.exists()
    captured = capsys.readouterr()
    assert "ERROR" in captured.err
    assert captured.out == ""


def test_malformed_json_exits_1_without_output(tmp_path: Path) -> None:
    report_path = tmp_path / "broken.json"
    report_path.write_text("{not json", encoding="utf-8")
    out_path = tmp_path / "checklist.json"

    assert main(["checklist-from-drift", str(report_path), "--out", str(out_path)]) == 1
    assert not out_path.exists()


def test_wrong_kind_exits_1_without_output(tmp_path: Path) -> None:
    report = drift_report([])
    report["kind"] = "penflow-consistency-report"
    report_path = write_report(tmp_path, report)
    out_path = tmp_path / "checklist.json"

    assert main(["checklist-from-drift", str(report_path), "--out", str(out_path)]) == 1
    assert not out_path.exists()


def test_schema_invalid_report_exits_1_without_output(tmp_path: Path) -> None:
    report = drift_report([])
    del report["summary"]
    report_path = write_report(tmp_path, report)
    out_path = tmp_path / "checklist.json"

    assert main(["checklist-from-drift", str(report_path), "--out", str(out_path)]) == 1
    assert not out_path.exists()


# @spec AC-004: pre-existing output never clobbered on failure — .specs/features/055-checklist-from-drift-seeding/spec.md#ac-004
def test_existing_output_unchanged_when_input_invalid(tmp_path: Path) -> None:
    valid_report_path = write_report(tmp_path, drift_report([drift_issue()]))
    out_path = tmp_path / "checklist.json"
    assert main(["checklist-from-drift", str(valid_report_path), "--out", str(out_path)]) == 0
    before = out_path.read_bytes()

    broken_path = tmp_path / "broken.json"
    broken_path.write_text("{not json", encoding="utf-8")
    assert main(["checklist-from-drift", str(broken_path), "--out", str(out_path)]) == 1

    assert out_path.read_bytes() == before


def test_unwritable_out_directory_exits_1(tmp_path: Path) -> None:
    report_path = write_report(tmp_path, drift_report([]))
    out_path = tmp_path / "no-such-dir" / "checklist.json"

    assert main(["checklist-from-drift", str(report_path), "--out", str(out_path)]) == 1


def test_seed_error_is_a_dedicated_domain_exception(tmp_path: Path) -> None:
    with pytest.raises(ChecklistSeedError):
        seed_checklist_from_drift(tmp_path / "missing.json", tmp_path / "out.json")


# @spec AC-008: sourceReport verbatim, no validatedAt, group iff flag — .specs/features/055-checklist-from-drift-seeding/spec.md#ac-008
def test_source_report_recorded_verbatim_and_no_timestamp(tmp_path: Path) -> None:
    report_path = write_report(tmp_path, drift_report([drift_issue()]))
    out_path = tmp_path / "checklist.json"

    assert main(["checklist-from-drift", str(report_path), "--out", str(out_path)]) == 0

    checklist = json.loads(out_path.read_text(encoding="utf-8"))
    assert checklist["sourceReport"] == str(report_path)
    assert "validatedAt" not in checklist
    assert "group" not in checklist
    assert checklist["version"] == 1


def test_group_present_exactly_when_flag_passed(tmp_path: Path) -> None:
    report_path = write_report(tmp_path, drift_report([]))
    out_path = tmp_path / "checklist.json"

    exit_code = main(
        ["checklist-from-drift", str(report_path), "--out", str(out_path), "--group", "checkout"]
    )

    assert exit_code == 0
    checklist = json.loads(out_path.read_text(encoding="utf-8"))
    assert checklist["group"] == "checkout"


# @spec AC-009: schema round-trip for new and undeclared fields — .specs/features/055-checklist-from-drift-seeding/spec.md#ac-009
def test_seeded_checklist_passes_validate_report_schema(tmp_path: Path) -> None:
    report_path = write_report(
        tmp_path,
        drift_report(
            [
                drift_issue(semantic_id="checkout.pay-now", pencil_node_id="payBtn"),
                drift_issue(code="drift.flow_not_in_tree", path="$.flows", severity="error"),
            ]
        ),
    )
    out_path = tmp_path / "checklist.json"
    assert main(["checklist-from-drift", str(report_path), "--out", str(out_path)]) == 0

    assert main(["validate-report", str(out_path), "--schema"]) == 0


def test_checklist_with_undeclared_field_fails_schema_validation(tmp_path: Path) -> None:
    report_path = write_report(tmp_path, drift_report([]))
    out_path = tmp_path / "checklist.json"
    assert main(["checklist-from-drift", str(report_path), "--out", str(out_path)]) == 0
    checklist = json.loads(out_path.read_text(encoding="utf-8"))
    checklist["undeclaredField"] = True
    out_path.write_text(json.dumps(checklist, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    assert main(["validate-report", str(out_path), "--schema"]) == 1


# @spec AC-010: open/blocking items never fail the seeding command — .specs/features/055-checklist-from-drift-seeding/spec.md#ac-010
def test_all_blocking_items_still_exit_0(tmp_path: Path) -> None:
    issues = [
        drift_issue(
            severity="error",
            code="drift.clarification_marker",
            path="screens/a.md:3",
            blocking=True,
        ),
        drift_issue(
            severity="error",
            code="drift.pencil_context_obsolete",
            path="pencil:0.1",
            blocking=True,
        ),
    ]
    report_path = write_report(tmp_path, drift_report(issues))
    out_path = tmp_path / "checklist.json"

    assert main(["checklist-from-drift", str(report_path), "--out", str(out_path)]) == 0


def test_lenient_flag_is_not_accepted_by_the_subcommand(tmp_path: Path) -> None:
    report_path = write_report(tmp_path, drift_report([]))
    out_path = tmp_path / "checklist.json"

    with pytest.raises(SystemExit):
        main(["checklist-from-drift", str(report_path), "--out", str(out_path), "--lenient"])


def test_json_envelope_has_exactly_items_out_status(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    report_path = write_report(tmp_path, drift_report([drift_issue()]))
    out_path = tmp_path / "checklist.json"

    exit_code = main(["checklist-from-drift", str(report_path), "--out", str(out_path), "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {"items": 1, "out": str(out_path), "status": "OPEN"}
