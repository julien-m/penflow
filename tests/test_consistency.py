# @spec(AC-001)
"""Regression tests for deterministic cross-screen consistency reports and CLI behavior."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from penflow.cli import main
from penflow.consistency import (
    CHECKED_PROPERTIES,
    DEFAULT_GROUP_BY,
    NUMERIC_TOLERANCE,
    check_consistency,
)


def _node(
    semantic_id: str,
    role: str,
    *,
    intent: str | None = None,
    variant: str | None = None,
    mask: bool = False,
    visual: dict[str, Any] | None = None,
    bbox: dict[str, Any] | None = None,
    children: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    context: dict[str, Any] = {"semantic_id": semantic_id, "role": role}
    if intent is not None:
        context["intent"] = intent
    if variant is not None:
        context["variant"] = variant
    if mask:
        context["mask"] = True
    return {
        "id": semantic_id,
        "semantic_id": semantic_id,
        "role": role,
        "context": context,
        "bbox": bbox or {"x": 0, "y": 0, "width": 0, "height": 0},
        "visual": visual or {},
        "children": children or [],
    }


def _screen(screen_id: str, children: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "screen_id": screen_id,
        "pencil_id": f"{screen_id}Screen",
        "name": screen_id,
        "viewport": {"x": 0, "y": 0, "width": 390, "height": 844},
        "root": _node(screen_id, "screen", children=children),
    }


def _tree(*screens: dict[str, Any]) -> dict[str, Any]:
    return {"version": 1, "source": "test.pen", "issues": [], "screens": list(screens)}


def _button(semantic_id: str, **visual: Any) -> dict[str, Any]:
    base: dict[str, Any] = {"fill": "#0057FF", "cornerRadius": 8, "padding": [12, 16]}
    base.update(visual)
    return _node(semantic_id, "button", intent="submit", variant="primary", visual=base)


def _write_tree(tmp_path: Path, tree: dict[str, Any], name: str = "expected.json") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(tree), encoding="utf-8")
    return path


def _two_screen_tree(button_a: dict[str, Any], button_b: dict[str, Any]) -> dict[str, Any]:
    return _tree(_screen("s1", [button_a]), _screen("s2", [button_b]))


def test_identical_buttons_across_two_screens_pass(tmp_path: Path) -> None:
    path = _write_tree(tmp_path, _two_screen_tree(_button("s1.pay"), _button("s2.pay")))
    report_path = tmp_path / "consistency-report.json"
    assert main(["check-consistency", str(path), "--out", str(report_path), "--json"]) == 0
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "PASS"
    assert report["issues"] == []
    assert report["summary"]["errors"] == 0
    assert report["summary"]["groups_checked"] >= 1


def test_divergent_fill_reports_error_with_baseline(tmp_path: Path) -> None:
    path = _write_tree(
        tmp_path, _two_screen_tree(_button("s1.pay"), _button("s2.pay", fill="#FF0000"))
    )
    report = check_consistency(path)
    assert report["status"] == "FAIL"
    [issue] = report["issues"]
    assert issue["code"] == "consistency.fill.divergent"
    assert issue["severity"] == "error"
    assert issue["property"] == "fill"
    assert issue["screen_id"] == "s2"
    assert issue["semantic_id"] == "s2.pay"
    assert issue["value"] == "#FF0000"
    assert issue["baseline"] == "#0057FF"
    assert issue["group_size"] == 2
    assert issue["signature"] == "role=button;intent=submit;variant=primary"


def test_divergent_font_family_is_always_error(tmp_path: Path) -> None:
    path = _write_tree(
        tmp_path,
        _two_screen_tree(
            _button("s1.pay", fontFamily="Inter"), _button("s2.pay", fontFamily="Comic Sans MS")
        ),
    )
    report = check_consistency(path)
    [issue] = report["issues"]
    assert issue["code"] == "consistency.fontFamily.divergent"
    assert issue["severity"] == "error"


def test_padding_deviation_within_tolerance_is_warning(tmp_path: Path) -> None:
    # Deviation 16 -> 18 == 2 (within tolerance).
    path = _write_tree(
        tmp_path, _two_screen_tree(_button("s1.pay"), _button("s2.pay", padding=[12, 18]))
    )
    report_path = tmp_path / "report.json"
    # Strict default (feature 049): warning-severity issues fail the gate.
    assert main(["check-consistency", str(path), "--out", str(report_path), "--json"]) == 1
    # --lenient restores the warnings-non-blocking behavior.
    assert (
        main(["check-consistency", str(path), "--out", str(report_path), "--lenient", "--json"])
        == 0
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "PASS"
    [issue] = report["issues"]
    assert issue["code"] == "consistency.padding.divergent"
    assert issue["severity"] == "warning"
    assert issue["value"] == [12, 18, 12, 18]
    assert issue["baseline"] == [12, 16, 12, 16]


def test_padding_deviation_beyond_tolerance_is_error(tmp_path: Path) -> None:
    path = _write_tree(
        tmp_path, _two_screen_tree(_button("s1.pay", padding=12), _button("s2.pay", padding=24))
    )
    report_path = tmp_path / "report.json"
    assert main(["check-consistency", str(path), "--out", str(report_path), "--json"]) == 1
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "FAIL"
    [issue] = report["issues"]
    assert issue["code"] == "consistency.padding.divergent"
    assert issue["severity"] == "error"


def test_padding_scalar_and_list_forms_are_equivalent(tmp_path: Path) -> None:
    path = _write_tree(
        tmp_path,
        _two_screen_tree(
            _button("s1.pay", padding=16), _button("s2.pay", padding=[16, 16, 16, 16])
        ),
    )
    assert check_consistency(path)["issues"] == []


def test_font_size_deviation_within_tolerance_is_warning(tmp_path: Path) -> None:
    path = _write_tree(
        tmp_path,
        _two_screen_tree(_button("s1.pay", fontSize=16), _button("s2.pay", fontSize=17)),
    )
    [issue] = check_consistency(path)["issues"]
    assert issue["code"] == "consistency.fontSize.divergent"
    assert issue["severity"] == "warning"


def test_non_numeric_font_weight_divergence_is_error(tmp_path: Path) -> None:
    path = _write_tree(
        tmp_path,
        _two_screen_tree(_button("s1.pay", fontWeight="600"), _button("s2.pay", fontWeight="400")),
    )
    [issue] = check_consistency(path)["issues"]
    assert issue["code"] == "consistency.fontWeight.divergent"
    assert issue["severity"] == "error"


def test_masked_nodes_are_skipped(tmp_path: Path) -> None:
    masked = _button("s2.pay", fill="#FF0000")
    masked["context"]["mask"] = True
    path = _write_tree(tmp_path, _two_screen_tree(_button("s1.pay"), masked))
    report_path = tmp_path / "report.json"
    assert main(["check-consistency", str(path), "--out", str(report_path), "--json"]) == 0
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "PASS"
    assert report["issues"] == []


def test_volatile_variant_nodes_are_skipped_like_compare(tmp_path: Path) -> None:
    volatile = _node(
        "s2.timer", "text", variant="volatile", visual={"fill": "#FF0000", "fontSize": 99}
    )
    steady = _node("s1.timer", "text", variant="volatile", visual={"fill": "#111827"})
    path = _write_tree(tmp_path, _two_screen_tree(steady, volatile))
    assert check_consistency(path)["issues"] == []


def test_majority_baseline_wins_over_minority(tmp_path: Path) -> None:
    tree = _tree(
        _screen("s1", [_button("s1.pay")]),
        _screen("s2", [_button("s2.pay")]),
        _screen("s3", [_button("s3.pay", fill="#FF0000")]),
    )
    path = _write_tree(tmp_path, tree)
    [issue] = check_consistency(path)["issues"]
    assert issue["baseline"] == "#0057FF"
    assert issue["screen_id"] == "s3"
    assert issue["group_size"] == 3


def test_tie_break_baseline_is_sorted_first(tmp_path: Path) -> None:
    path = _write_tree(
        tmp_path, _two_screen_tree(_button("s1.pay"), _button("s2.pay", fill="#FF0000"))
    )
    [issue] = check_consistency(path)["issues"]
    # 1-1 tie: '"#0057FF"' sorts before '"#FF0000"', so it is the baseline.
    assert issue["baseline"] == "#0057FF"
    assert issue["value"] == "#FF0000"


def test_default_signature_separates_variants(tmp_path: Path) -> None:
    primary = _node(
        "s1.pay", "button", intent="submit", variant="primary", visual={"fill": "#0057FF"}
    )
    secondary = _node(
        "s2.pay", "button", intent="submit", variant="secondary", visual={"fill": "#FF0000"}
    )
    path = _write_tree(tmp_path, _two_screen_tree(primary, secondary))
    report = check_consistency(path)
    assert report["issues"] == []
    assert report["inputs"]["group_by"] == DEFAULT_GROUP_BY


def test_group_by_role_intent_merges_variants(tmp_path: Path) -> None:
    primary = _node(
        "s1.pay", "button", intent="submit", variant="primary", visual={"fill": "#0057FF"}
    )
    secondary = _node(
        "s2.pay", "button", intent="submit", variant="secondary", visual={"fill": "#FF0000"}
    )
    path = _write_tree(tmp_path, _two_screen_tree(primary, secondary))
    report_path = tmp_path / "report.json"
    assert (
        main(
            [
                "check-consistency",
                str(path),
                "--group-by",
                "role+intent",
                "--out",
                str(report_path),
                "--json",
            ]
        )
        == 1
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    [issue] = report["issues"]
    assert issue["code"] == "consistency.fill.divergent"
    assert issue["signature"] == "role=button;intent=submit"
    assert report["inputs"]["group_by"] == "role+intent"


def test_group_by_role_merges_intents(tmp_path: Path) -> None:
    pay = _node("s1.pay", "button", intent="submit", visual={"cornerRadius": 8})
    cancel = _node("s2.cancel", "button", intent="cancel", visual={"cornerRadius": 16})
    path = _write_tree(tmp_path, _two_screen_tree(pay, cancel))
    assert check_consistency(path)["issues"] == []
    [issue] = check_consistency(path, group_by="role")["issues"]
    assert issue["code"] == "consistency.cornerRadius.divergent"
    assert issue["signature"] == "role=button"
    assert issue["severity"] == "error"


def test_bbox_height_divergence_uses_measurable_boxes(tmp_path: Path) -> None:
    short = _button("s1.pay")
    short["bbox"] = {"x": 0, "y": 0, "width": 200, "height": 44}
    tall = _button("s2.pay")
    tall["bbox"] = {"x": 0, "y": 0, "width": 200, "height": 52}
    path = _write_tree(tmp_path, _two_screen_tree(short, tall))
    [issue] = check_consistency(path)["issues"]
    assert issue["code"] == "consistency.bbox.height.divergent"
    assert issue["severity"] == "error"
    assert issue["value"] == 52
    assert issue["baseline"] == 44


def test_bbox_height_within_tolerance_is_warning(tmp_path: Path) -> None:
    short = _button("s1.pay")
    short["bbox"] = {"x": 0, "y": 0, "width": 200, "height": 44}
    tall = _button("s2.pay")
    tall["bbox"] = {"x": 0, "y": 0, "width": 200, "height": 45}
    path = _write_tree(tmp_path, _two_screen_tree(short, tall))
    [issue] = check_consistency(path)["issues"]
    assert issue["severity"] == "warning"


def test_unmeasurable_bbox_does_not_participate(tmp_path: Path) -> None:
    drafted = _button("s1.pay")  # default zero-size bbox
    measured = _button("s2.pay")
    measured["bbox"] = {"x": 0, "y": 0, "width": 200, "height": 44}
    path = _write_tree(tmp_path, _two_screen_tree(drafted, measured))
    assert check_consistency(path)["issues"] == []


def test_absent_property_does_not_participate(tmp_path: Path) -> None:
    with_font = _button("s1.pay", fontSize=16)
    without_font = _button("s2.pay")
    path = _write_tree(tmp_path, _two_screen_tree(with_font, without_font))
    assert check_consistency(path)["issues"] == []


def test_same_screen_same_signature_nodes_group(tmp_path: Path) -> None:
    title = _node("s1.title", "text", visual={"fill": "#111827"})
    label = _node("s1.label", "text", visual={"fill": "#FFFFFF"})
    path = _write_tree(tmp_path, _tree(_screen("s1", [title, label])))
    [issue] = check_consistency(path)["issues"]
    assert issue["code"] == "consistency.fill.divergent"
    assert issue["screen_id"] == "s1"


def test_byte_identical_reruns(tmp_path: Path) -> None:
    path = _write_tree(
        tmp_path,
        _two_screen_tree(
            _button("s1.pay", fontSize=16, padding=24),
            _button("s2.pay", fill="#FF0000", fontSize=17, padding=12),
        ),
    )
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    assert main(["check-consistency", str(path), "--out", str(first), "--json"]) == 1
    assert main(["check-consistency", str(path), "--out", str(second), "--json"]) == 1
    assert first.read_bytes() == second.read_bytes()


def test_issues_are_sorted_deterministically(tmp_path: Path) -> None:
    tree = _tree(
        _screen("s2", [_button("s2.pay", fill="#FF0000", fontSize=30)]),
        _screen("s1", [_button("s1.pay", fontSize=16)]),
        _screen("s3", [_button("s3.pay", fontSize=16)]),
    )
    path = _write_tree(tmp_path, tree)
    issues = check_consistency(path)["issues"]
    keys = [
        (i["code"], i["signature"], i["screen_id"], str(i["semantic_id"]), json.dumps(i["value"]))
        for i in issues
    ]
    assert keys == sorted(keys)
    assert len(issues) >= 2


def test_generated_report_validates_against_bundled_schema(tmp_path: Path) -> None:
    path = _write_tree(
        tmp_path, _two_screen_tree(_button("s1.pay"), _button("s2.pay", fill="#FF0000"))
    )
    report_path = tmp_path / "consistency-report.json"
    main(["check-consistency", str(path), "--out", str(report_path), "--json"])
    assert main(["validate-report", str(report_path), "--schema", "--json"]) == 0


def test_report_schema_fails_closed_on_additional_property(tmp_path: Path) -> None:
    path = _write_tree(tmp_path, _two_screen_tree(_button("s1.pay"), _button("s2.pay")))
    report_path = tmp_path / "consistency-report.json"
    main(["check-consistency", str(path), "--out", str(report_path), "--json"])
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["unexpected"] = True
    report_path.write_text(json.dumps(report), encoding="utf-8")
    assert main(["validate-report", str(report_path), "--schema", "--json"]) == 1


def test_cli_exit_codes_for_usage_and_io_errors(tmp_path: Path) -> None:
    assert main(["check-consistency", str(tmp_path / "missing.json")]) == 2
    invalid = tmp_path / "invalid.json"
    invalid.write_text("not json", encoding="utf-8")
    assert main(["check-consistency", str(invalid)]) == 2
    shapeless = _write_tree(tmp_path, {"version": 1}, name="shapeless.json")
    assert main(["check-consistency", str(shapeless)]) == 2
    bad_screen = _write_tree(
        tmp_path, {"version": 1, "screens": ["not-an-object"]}, name="bad-screen.json"
    )
    assert main(["check-consistency", str(bad_screen)]) == 2
    rootless = _write_tree(
        tmp_path, {"version": 1, "screens": [{"screen_id": "s1"}]}, name="rootless.json"
    )
    assert main(["check-consistency", str(rootless)]) == 2


def test_non_json_scalar_values_are_clamped_to_schema_shape(tmp_path: Path) -> None:
    path = _write_tree(
        tmp_path,
        _two_screen_tree(_button("s1.pay", fontWeight=True), _button("s2.pay", fontWeight="600")),
    )
    report = check_consistency(path)
    [issue] = report["issues"]
    assert issue["code"] == "consistency.fontWeight.divergent"
    # Booleans are not representable in the strict report schema; they are
    # clamped to their deterministic JSON text.
    assert {issue["value"], issue["baseline"]} == {"true", "600"}
    report_path = tmp_path / "report.json"
    main(["check-consistency", str(path), "--out", str(report_path), "--json"])
    assert main(["validate-report", str(report_path), "--schema", "--json"]) == 0


def test_engine_rejects_unknown_group_by(tmp_path: Path) -> None:
    path = _write_tree(tmp_path, _tree())
    with pytest.raises(ValueError):
        check_consistency(path, group_by="role+variant")


def test_empty_screens_pass_trivially(tmp_path: Path) -> None:
    path = _write_tree(tmp_path, _tree())
    report = check_consistency(path)
    assert report["status"] == "PASS"
    assert report["summary"] == {
        "errors": 0,
        "warnings": 0,
        "groups_checked": 0,
        "nodes_checked": 0,
    }


def test_inputs_echo_supplied_path_verbatim(tmp_path: Path) -> None:
    path = _write_tree(tmp_path, _tree())
    report = check_consistency(path)
    assert report["inputs"]["expected_tree"] == str(path)


def test_checked_properties_and_tolerance_match_contract() -> None:
    assert CHECKED_PROPERTIES == (
        "padding",
        "gap",
        "fontSize",
        "fontWeight",
        "fontFamily",
        "fill",
        "cornerRadius",
        "bbox.height",
    )
    assert NUMERIC_TOLERANCE == 2.0
