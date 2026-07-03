# @spec(AC-001)
"""Regression tests for the deterministic visual metrics audit and CLI behavior."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from penflow.cli import main
from penflow.visual_metrics import (
    BOLD_FONT_WEIGHT,
    CONTRAST_AA_LARGE,
    CONTRAST_AA_NORMAL,
    GEOMETRY_TOLERANCE_PX,
    INTERACTIVE_ROLES,
    LARGE_BOLD_TEXT_PX,
    LARGE_TEXT_PX,
    TEXT_WIDTH_FACTOR,
    TOUCH_TARGET_ERROR_PX,
    TOUCH_TARGET_PASS_PX,
    audit_visual,
    contrast_ratio,
)


def _node(
    semantic_id: str,
    role: str,
    *,
    text: str | None = None,
    mask: bool = False,
    visual: dict[str, Any] | None = None,
    bbox: dict[str, Any] | None = None,
    children: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    context: dict[str, Any] = {"semantic_id": semantic_id, "role": role}
    if mask:
        context["mask"] = True
    node: dict[str, Any] = {
        "id": semantic_id,
        "semantic_id": semantic_id,
        "role": role,
        "context": context,
        "bbox": bbox or {"x": 0, "y": 0, "width": 0, "height": 0},
        "visual": visual or {},
        "children": children or [],
    }
    if text is not None:
        node["text"] = text
    return node


def _screen(screen_id: str, children: list[dict[str, Any]], **root_kwargs: Any) -> dict[str, Any]:
    return {
        "screen_id": screen_id,
        "pencil_id": f"{screen_id}Screen",
        "name": screen_id,
        "viewport": {"x": 0, "y": 0, "width": 390, "height": 844},
        "root": _node(
            screen_id,
            "screen",
            children=children,
            bbox=root_kwargs.pop("bbox", {"x": 0, "y": 0, "width": 390, "height": 844}),
            **root_kwargs,
        ),
    }


def _tree(*screens: dict[str, Any]) -> dict[str, Any]:
    return {"version": 1, "source": "test.pen", "issues": [], "screens": list(screens)}


def _write_tree(tmp_path: Path, tree: dict[str, Any], name: str = "expected.json") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(tree), encoding="utf-8")
    return path


def _write_layout_snapshot(tmp_path: Path, snapshot: dict[str, Any]) -> Path:
    path = tmp_path / "layout-snapshot.json"
    path.write_text(json.dumps(snapshot), encoding="utf-8")
    return path


def _text_on_background(text_fill: str, background_fill: str, **text_visual: Any) -> dict[str, Any]:
    visual = {"fill": text_fill, "fontSize": 16, **text_visual}
    text = _node("s1.label", "text", text="Hi", visual=visual)
    return _tree(_screen("s1", [text], visual={"fill": background_fill}))


def _issues_with_code(report: dict[str, Any], code: str) -> list[dict[str, Any]]:
    return [issue for issue in report["issues"] if issue["code"] == code]


# --- Contrast (FR-002) ---


def test_contrast_767676_on_white_passes(tmp_path: Path) -> None:
    # @spec AC-001: WCAG reference pair pins the luminance formula — .specs/features/050-deterministic-visual-metrics-audit/spec.md#acceptance-criteria
    path = _write_tree(tmp_path, _text_on_background("#767676", "#FFFFFF"))
    report = audit_visual(path)
    assert _issues_with_code(report, "visual.contrast.below_aa") == []
    assert report["status"] == "PASS"


def test_contrast_777777_on_white_fails(tmp_path: Path) -> None:
    path = _write_tree(tmp_path, _text_on_background("#777777", "#FFFFFF"))
    report = audit_visual(path)
    [issue] = _issues_with_code(report, "visual.contrast.below_aa")
    assert issue["severity"] == "error"
    assert issue["semantic_id"] == "s1.label"
    assert issue["ratio"] == 4.48
    assert issue["required"] == CONTRAST_AA_NORMAL
    assert report["status"] == "FAIL"


def test_contrast_ratio_reference_values() -> None:
    gray = (0x76, 0x76, 0x76, 255)
    white = (255, 255, 255, 255)
    assert round(contrast_ratio(gray, white), 2) == 4.54
    # Symmetric: argument order must not matter.
    assert contrast_ratio(gray, white) == contrast_ratio(white, gray)


def test_large_text_uses_3_to_1_threshold(tmp_path: Path) -> None:
    # @spec AC-002: large-text 3:1 rule — .specs/features/050-deterministic-visual-metrics-audit/spec.md#acceptance-criteria
    # Ratio ~4.48 (#777777 on white) is below 4.5 but above 3.0.
    path = _write_tree(tmp_path, _text_on_background("#777777", "#FFFFFF", fontSize=LARGE_TEXT_PX))
    assert _issues_with_code(audit_visual(path), "visual.contrast.below_aa") == []


def test_bold_18px_text_uses_3_to_1_threshold(tmp_path: Path) -> None:
    for weight in ("bold", "700", 700, "bolder"):
        path = _write_tree(
            tmp_path,
            _text_on_background(
                "#777777", "#FFFFFF", fontSize=LARGE_BOLD_TEXT_PX, fontWeight=weight
            ),
        )
        assert _issues_with_code(audit_visual(path), "visual.contrast.below_aa") == []


def test_regular_18px_text_keeps_4_5_threshold(tmp_path: Path) -> None:
    path = _write_tree(
        tmp_path,
        _text_on_background("#777777", "#FFFFFF", fontSize=18, fontWeight="600"),
    )
    [issue] = _issues_with_code(audit_visual(path), "visual.contrast.below_aa")
    assert issue["required"] == CONTRAST_AA_NORMAL


def test_low_ratio_large_text_still_fails(tmp_path: Path) -> None:
    path = _write_tree(tmp_path, _text_on_background("#AAAAAA", "#FFFFFF", fontSize=LARGE_TEXT_PX))
    [issue] = _issues_with_code(audit_visual(path), "visual.contrast.below_aa")
    assert issue["required"] == CONTRAST_AA_LARGE


def test_background_comes_from_nearest_parseable_ancestor(tmp_path: Path) -> None:
    # The direct parent has an unparseable fill; the grandparent (screen) is dark.
    text = _node("s1.label", "text", text="Hi", visual={"fill": "#111111", "fontSize": 16})
    wrapper = _node("s1.wrap", "container", visual={"fill": "$pf-card"}, children=[text])
    path = _write_tree(tmp_path, _tree(_screen("s1", [wrapper], visual={"fill": "#000000"})))
    report = audit_visual(path)
    # #111111 on #000000 is far below 4.5:1.
    [issue] = _issues_with_code(report, "visual.contrast.below_aa")
    assert issue["semantic_id"] == "s1.label"


def test_no_parseable_background_is_info(tmp_path: Path) -> None:
    # @spec AC-003: contrast skip surfaces as info — .specs/features/050-deterministic-visual-metrics-audit/spec.md#acceptance-criteria
    text = _node("s1.label", "text", text="Hi", visual={"fill": "#111111"})
    path = _write_tree(tmp_path, _tree(_screen("s1", [text])))
    report = audit_visual(path)
    [issue] = _issues_with_code(report, "visual.contrast.unresolved")
    assert issue["severity"] == "info"
    assert _issues_with_code(report, "visual.contrast.below_aa") == []
    assert report["status"] == "PASS"


def test_masked_text_is_not_contrast_checked(tmp_path: Path) -> None:
    text = _node(
        "s1.timer", "text", text="00:00", mask=True, visual={"fill": "#777777", "fontSize": 16}
    )
    path = _write_tree(tmp_path, _tree(_screen("s1", [text], visual={"fill": "#FFFFFF"})))
    assert audit_visual(path)["issues"] == []


# --- Touch targets (FR-003) ---


def _button(
    semantic_id: str, width: float, height: float, *, x: float = 0, y: float = 0
) -> dict[str, Any]:
    return _node(semantic_id, "button", bbox={"x": x, "y": y, "width": width, "height": height})


def test_44px_touch_target_passes(tmp_path: Path) -> None:
    path = _write_tree(tmp_path, _tree(_screen("s1", [_button("s1.pay", 44, 44)])))
    assert _issues_with_code(audit_visual(path), "visual.touch_target.too_small") == []


def test_40px_touch_target_is_warning(tmp_path: Path) -> None:
    # @spec AC-004: 24-43px warns, <24px errors — .specs/features/050-deterministic-visual-metrics-audit/spec.md#acceptance-criteria
    path = _write_tree(tmp_path, _tree(_screen("s1", [_button("s1.pay", 40, 40)])))
    [issue] = _issues_with_code(audit_visual(path), "visual.touch_target.too_small")
    assert issue["severity"] == "warning"
    assert issue["width"] == 40
    assert issue["height"] == 40


def test_20px_touch_target_is_error(tmp_path: Path) -> None:
    path = _write_tree(tmp_path, _tree(_screen("s1", [_button("s1.pay", 20, 40)])))
    [issue] = _issues_with_code(audit_visual(path), "visual.touch_target.too_small")
    assert issue["severity"] == "error"
    assert issue["width"] == 20


def test_zero_sized_interactive_bbox_is_info(tmp_path: Path) -> None:
    # @spec AC-005: unmeasured drafts skip with info, not error — .specs/features/050-deterministic-visual-metrics-audit/spec.md#acceptance-criteria
    path = _write_tree(tmp_path, _tree(_screen("s1", [_button("s1.pay", 0, 0)])))
    report = audit_visual(path)
    [issue] = _issues_with_code(report, "visual.bbox.unmeasured")
    assert issue["severity"] == "info"
    assert _issues_with_code(report, "visual.touch_target.too_small") == []
    assert report["status"] == "PASS"


def test_non_interactive_roles_are_not_touch_checked(tmp_path: Path) -> None:
    small_text = _node("s1.note", "text", bbox={"x": 0, "y": 0, "width": 10, "height": 10})
    path = _write_tree(tmp_path, _tree(_screen("s1", [small_text])))
    assert _issues_with_code(audit_visual(path), "visual.touch_target.too_small") == []


# --- Geometry (FR-004) ---


def test_overlapping_siblings_are_error(tmp_path: Path) -> None:
    # @spec AC-006: sibling overlap beyond 1px is an error — .specs/features/050-deterministic-visual-metrics-audit/spec.md#acceptance-criteria
    first = _node("s1.a", "container", bbox={"x": 0, "y": 0, "width": 100, "height": 100})
    second = _node("s1.b", "container", bbox={"x": 50, "y": 50, "width": 100, "height": 100})
    path = _write_tree(tmp_path, _tree(_screen("s1", [first, second])))
    [issue] = _issues_with_code(audit_visual(path), "visual.bbox.overlap")
    assert issue["severity"] == "error"
    assert issue["semantic_id"] == "s1.a"
    assert issue["other_semantic_id"] == "s1.b"


def test_siblings_within_1px_tolerance_pass(tmp_path: Path) -> None:
    first = _node("s1.a", "container", bbox={"x": 0, "y": 0, "width": 100, "height": 100})
    second = _node("s1.b", "container", bbox={"x": 99, "y": 0, "width": 100, "height": 100})
    path = _write_tree(tmp_path, _tree(_screen("s1", [first, second])))
    assert _issues_with_code(audit_visual(path), "visual.bbox.overlap") == []


def test_child_escaping_parent_is_overflow_error(tmp_path: Path) -> None:
    # @spec AC-007: child escapes parent bbox — .specs/features/050-deterministic-visual-metrics-audit/spec.md#acceptance-criteria
    child = _node("s1.child", "container", bbox={"x": 350, "y": 0, "width": 100, "height": 50})
    path = _write_tree(tmp_path, _tree(_screen("s1", [child])))
    [issue] = _issues_with_code(audit_visual(path), "visual.bbox.overflow")
    assert issue["severity"] == "error"
    assert issue["semantic_id"] == "s1.child"
    assert issue["other_semantic_id"] == "s1"


def test_contained_child_produces_no_overflow(tmp_path: Path) -> None:
    child = _node("s1.child", "container", bbox={"x": 10, "y": 10, "width": 100, "height": 50})
    path = _write_tree(tmp_path, _tree(_screen("s1", [child])))
    assert _issues_with_code(audit_visual(path), "visual.bbox.overflow") == []


def test_zero_sized_boxes_skip_geometry_checks(tmp_path: Path) -> None:
    first = _node("s1.a", "container")  # zero bbox
    second = _node("s1.b", "container")  # zero bbox
    path = _write_tree(tmp_path, _tree(_screen("s1", [first, second])))
    report = audit_visual(path)
    assert _issues_with_code(report, "visual.bbox.overlap") == []
    assert _issues_with_code(report, "visual.bbox.overflow") == []


def test_masked_nodes_skip_geometry_checks(tmp_path: Path) -> None:
    first = _node("s1.a", "container", bbox={"x": 0, "y": 0, "width": 100, "height": 100})
    second = _node(
        "s1.b", "container", mask=True, bbox={"x": 50, "y": 50, "width": 100, "height": 100}
    )
    path = _write_tree(tmp_path, _tree(_screen("s1", [first, second])))
    assert _issues_with_code(audit_visual(path), "visual.bbox.overlap") == []


def test_flex_parent_skips_theoretical_overlap_and_overflow(tmp_path: Path) -> None:
    first = _button("s1.primary", 20, 20, x=0, y=0)
    second = _button("s1.secondary", 44, 44, x=0, y=0)
    path = _write_tree(
        tmp_path,
        _tree(
            _screen(
                "s1",
                [first, second],
                visual={"layout": "vertical"},
                bbox={"x": 0, "y": 0, "width": 40, "height": 40},
            )
        ),
    )
    report = audit_visual(path)

    assert _issues_with_code(report, "visual.bbox.overlap") == []
    assert _issues_with_code(report, "visual.bbox.overflow") == []
    [touch_issue] = _issues_with_code(report, "visual.touch_target.too_small")
    assert touch_issue["semantic_id"] == "s1.primary"


def test_clean_layout_snapshot_overrides_theoretical_flex_overlap(tmp_path: Path) -> None:
    first = _node("s1.a", "container", bbox={"x": 0, "y": 0, "width": 100, "height": 100})
    second = _node("s1.b", "container", bbox={"x": 0, "y": 0, "width": 100, "height": 100})
    path = _write_tree(
        tmp_path, _tree(_screen("s1", [first, second], visual={"layout": "vertical"}))
    )
    snapshot_path = _write_layout_snapshot(
        tmp_path,
        {
            "screens": [
                {
                    "screen_id": "s1",
                    "nodes": [
                        {
                            "semantic_id": "s1",
                            "bbox": {"x": 0, "y": 0, "width": 390, "height": 844},
                        },
                        {
                            "semantic_id": "s1.a",
                            "bbox": {"x": 16, "y": 16, "width": 100, "height": 100},
                        },
                        {
                            "semantic_id": "s1.b",
                            "bbox": {"x": 16, "y": 132, "width": 100, "height": 100},
                        },
                    ],
                }
            ]
        },
    )
    report = audit_visual(path, layout_snapshot=snapshot_path)

    assert _issues_with_code(report, "visual.bbox.overlap") == []
    assert _issues_with_code(report, "visual.bbox.overflow") == []
    assert report["inputs"]["layout_snapshot"] == str(snapshot_path)


def test_partial_layout_snapshot_does_not_fall_back_to_flex_theoretical_geometry(
    tmp_path: Path,
) -> None:
    first = _node("s1.a", "container", bbox={"x": 0, "y": 0, "width": 100, "height": 100})
    second = _node("s1.b", "container", bbox={"x": 0, "y": 0, "width": 100, "height": 100})
    path = _write_tree(
        tmp_path, _tree(_screen("s1", [first, second], visual={"layout": "vertical"}))
    )
    snapshot_path = _write_layout_snapshot(
        tmp_path,
        {
            "screens": [
                {
                    "screen_id": "s1",
                    "nodes": [
                        {"semantic_id": "s1", "bbox": {"x": 0, "y": 0, "width": 390, "height": 844}}
                    ],
                }
            ]
        },
    )

    report = audit_visual(path, layout_snapshot=snapshot_path)
    assert _issues_with_code(report, "visual.bbox.overlap") == []
    assert _issues_with_code(report, "visual.bbox.overflow") == []


def test_layout_snapshot_geometry_still_reports_real_overlap(tmp_path: Path) -> None:
    first = _node("s1.a", "container", bbox={"x": 0, "y": 0, "width": 100, "height": 100})
    second = _node("s1.b", "container", bbox={"x": 0, "y": 120, "width": 100, "height": 100})
    path = _write_tree(
        tmp_path, _tree(_screen("s1", [first, second], visual={"layout": "vertical"}))
    )
    snapshot_path = _write_layout_snapshot(
        tmp_path,
        {
            "screens": [
                {
                    "screen_id": "s1",
                    "nodes": [
                        {
                            "semantic_id": "s1",
                            "bbox": {"x": 0, "y": 0, "width": 390, "height": 844},
                        },
                        {
                            "semantic_id": "s1.a",
                            "bbox": {"x": 16, "y": 16, "width": 100, "height": 100},
                        },
                        {
                            "semantic_id": "s1.b",
                            "bbox": {"x": 80, "y": 80, "width": 100, "height": 100},
                        },
                    ],
                }
            ]
        },
    )
    [issue] = _issues_with_code(
        audit_visual(path, layout_snapshot=snapshot_path), "visual.bbox.overlap"
    )
    assert issue["semantic_id"] == "s1.a"
    assert issue["other_semantic_id"] == "s1.b"


# --- Text overflow heuristic (FR-005) ---


def test_long_text_in_narrow_bbox_warns_as_heuristic(tmp_path: Path) -> None:
    # @spec AC-008: heuristic warning labeled heuristic — .specs/features/050-deterministic-visual-metrics-audit/spec.md#acceptance-criteria
    text = _node(
        "s1.title",
        "text",
        text="A very long checkout headline",  # 29 chars * 16 * 0.55 = 255.2 > 120
        visual={"fontSize": 16},
        bbox={"x": 0, "y": 0, "width": 120, "height": 20},
    )
    path = _write_tree(tmp_path, _tree(_screen("s1", [text])))
    [issue] = _issues_with_code(audit_visual(path), "visual.text.likely_overflow")
    assert issue["severity"] == "warning"
    assert "heuristic" in issue["message"]


def test_fitting_text_does_not_warn(tmp_path: Path) -> None:
    text = _node(
        "s1.title",
        "text",
        text="Hi",
        visual={"fontSize": 16},
        bbox={"x": 0, "y": 0, "width": 120, "height": 20},
    )
    path = _write_tree(tmp_path, _tree(_screen("s1", [text])))
    assert _issues_with_code(audit_visual(path), "visual.text.likely_overflow") == []


def test_unmeasured_bbox_skips_text_heuristic(tmp_path: Path) -> None:
    text = _node("s1.title", "text", text="A very long headline", visual={"fontSize": 16})
    path = _write_tree(tmp_path, _tree(_screen("s1", [text])))
    assert _issues_with_code(audit_visual(path), "visual.text.likely_overflow") == []


# --- Theme resolution (FR-006) ---


def _theme_css(tmp_path: Path) -> Path:
    css = tmp_path / "theme.css"
    css.write_text(":root { --foreground: #777777; --background: #FFFFFF; }", encoding="utf-8")
    return css


def test_pf_variable_fill_resolves_via_theme_css(tmp_path: Path) -> None:
    # @spec AC-009: $pf-* resolution via theme.py/color.py — .specs/features/050-deterministic-visual-metrics-audit/spec.md#acceptance-criteria
    text = _node("s1.label", "text", text="Hi", visual={"fill": "$pf-foreground", "fontSize": 16})
    tree = _tree(_screen("s1", [text], visual={"fill": "$pf-background"}))
    path = _write_tree(tmp_path, tree)
    report_path = tmp_path / "report.json"
    assert (
        main(
            [
                "audit-visual",
                str(path),
                "--theme-css",
                str(_theme_css(tmp_path)),
                "--out",
                str(report_path),
                "--json",
            ]
        )
        == 1
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    # Resolved #777777 on #FFFFFF fails AA — proof both references resolved.
    [issue] = [i for i in report["issues"] if i["code"] == "visual.contrast.below_aa"]
    assert issue["ratio"] == 4.48
    assert report["inputs"]["theme_css"] == str(_theme_css(tmp_path))


def test_unresolvable_variable_fill_without_theme_is_info(tmp_path: Path) -> None:
    text = _node("s1.label", "text", text="Hi", visual={"fill": "$pf-primary"})
    path = _write_tree(tmp_path, _tree(_screen("s1", [text])))
    report = audit_visual(path)
    [issue] = _issues_with_code(report, "visual.color.unparsed")
    assert issue["severity"] == "info"
    assert issue["value"] == "$pf-primary"
    assert _issues_with_code(report, "visual.contrast.below_aa") == []
    assert report["status"] == "PASS"


def test_unparseable_literal_fill_is_info(tmp_path: Path) -> None:
    node = _node("s1.box", "container", visual={"fill": "tomato"})
    path = _write_tree(tmp_path, _tree(_screen("s1", [node])))
    [issue] = _issues_with_code(audit_visual(path), "visual.color.unparsed")
    assert issue["severity"] == "info"
    assert issue["value"] == "tomato"


# --- CLI exit codes, determinism, schema (FR-001, FR-007) ---


def test_exit_codes_strict_and_lenient(tmp_path: Path) -> None:
    # @spec AC-011: strict-by-default exit policy — .specs/features/050-deterministic-visual-metrics-audit/spec.md#acceptance-criteria
    warning_tree = _tree(_screen("s1", [_button("s1.pay", 40, 40)]))
    warning_path = _write_tree(tmp_path, warning_tree, name="warning.json")
    out = tmp_path / "report.json"
    assert main(["audit-visual", str(warning_path), "--out", str(out), "--json"]) == 1
    assert main(["audit-visual", str(warning_path), "--out", str(out), "--lenient", "--json"]) == 0

    error_tree = _tree(_screen("s1", [_button("s1.pay", 20, 20)]))
    error_path = _write_tree(tmp_path, error_tree, name="error.json")
    assert main(["audit-visual", str(error_path), "--out", str(out), "--lenient", "--json"]) == 1

    clean_tree = _tree(_screen("s1", [_button("s1.pay", 44, 44)]))
    clean_path = _write_tree(tmp_path, clean_tree, name="clean.json")
    assert main(["audit-visual", str(clean_path), "--out", str(out), "--json"]) == 0


def test_info_only_report_exits_zero(tmp_path: Path) -> None:
    tree = _tree(_screen("s1", [_button("s1.pay", 0, 0)]))
    path = _write_tree(tmp_path, tree)
    out = tmp_path / "report.json"
    assert main(["audit-visual", str(path), "--out", str(out), "--json"]) == 0
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["summary"]["infos"] == 1


def test_cli_exit_codes_for_usage_and_io_errors(tmp_path: Path) -> None:
    assert main(["audit-visual", str(tmp_path / "missing.json")]) == 2
    invalid = tmp_path / "invalid.json"
    invalid.write_text("not json", encoding="utf-8")
    assert main(["audit-visual", str(invalid)]) == 2
    shapeless = _write_tree(tmp_path, {"version": 1}, name="shapeless.json")
    assert main(["audit-visual", str(shapeless)]) == 2
    tree_path = _write_tree(tmp_path, _tree(_screen("s1", [])))
    assert main(["audit-visual", str(tree_path), "--theme-css", str(tmp_path / "no.css")]) == 2


def test_byte_identical_reruns(tmp_path: Path) -> None:
    # @spec AC-010: deterministic ordering, byte-identical reruns — .specs/features/050-deterministic-visual-metrics-audit/spec.md#acceptance-criteria
    tree = _tree(
        _screen(
            "s1",
            [
                _button("s1.pay", 40, 40),
                _node("s1.label", "text", text="Hi", visual={"fill": "$pf-primary"}),
                _node("s1.a", "container", bbox={"x": 0, "y": 0, "width": 100, "height": 100}),
                _node("s1.b", "container", bbox={"x": 50, "y": 50, "width": 100, "height": 100}),
            ],
        )
    )
    path = _write_tree(tmp_path, tree)
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    assert main(["audit-visual", str(path), "--out", str(first), "--json"]) == 1
    assert main(["audit-visual", str(path), "--out", str(second), "--json"]) == 1
    assert first.read_bytes() == second.read_bytes()


def test_issues_are_sorted_deterministically(tmp_path: Path) -> None:
    tree = _tree(
        _screen("s2", [_button("s2.pay", 40, 40)]),
        _screen("s1", [_button("s1.pay", 20, 20), _button("s1.cancel", 40, 40, x=200)]),
    )
    path = _write_tree(tmp_path, tree)
    issues = audit_visual(path)["issues"]
    keys = [(i["code"], i["screen_id"], str(i["semantic_id"]), i["message"]) for i in issues]
    assert keys == sorted(keys)
    assert len(issues) == 3


def test_generated_report_validates_against_bundled_schema(tmp_path: Path) -> None:
    tree = _tree(
        _screen(
            "s1",
            [
                _button("s1.pay", 20, 40),
                _node("s1.label", "text", text="Hi", visual={"fill": "$pf-primary"}),
            ],
        )
    )
    path = _write_tree(tmp_path, tree)
    report_path = tmp_path / "visual-metrics-report.json"
    main(["audit-visual", str(path), "--out", str(report_path), "--json"])
    assert main(["validate-report", str(report_path), "--schema", "--json"]) == 0


def test_cli_accepts_layout_snapshot_for_visual_audit(tmp_path: Path) -> None:
    first = _node("s1.a", "container", bbox={"x": 0, "y": 0, "width": 100, "height": 100})
    second = _node("s1.b", "container", bbox={"x": 0, "y": 0, "width": 100, "height": 100})
    path = _write_tree(
        tmp_path, _tree(_screen("s1", [first, second], visual={"layout": "vertical"}))
    )
    snapshot_path = _write_layout_snapshot(
        tmp_path,
        {
            "screens": [
                {
                    "screen_id": "s1",
                    "nodes": [
                        {
                            "semantic_id": "s1",
                            "bbox": {"x": 0, "y": 0, "width": 390, "height": 844},
                        },
                        {
                            "semantic_id": "s1.a",
                            "bbox": {"x": 8, "y": 8, "width": 100, "height": 100},
                        },
                        {
                            "semantic_id": "s1.b",
                            "bbox": {"x": 8, "y": 128, "width": 100, "height": 100},
                        },
                    ],
                }
            ]
        },
    )
    report_path = tmp_path / "visual-metrics-report.json"

    assert (
        main(
            [
                "audit-visual",
                str(path),
                "--layout-snapshot",
                str(snapshot_path),
                "--out",
                str(report_path),
                "--json",
            ]
        )
        == 0
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["inputs"]["layout_snapshot"] == str(snapshot_path)
    assert main(["validate-report", str(report_path), "--schema", "--json"]) == 0


def test_report_schema_fails_closed_on_additional_property(tmp_path: Path) -> None:
    path = _write_tree(tmp_path, _tree(_screen("s1", [_button("s1.pay", 44, 44)])))
    report_path = tmp_path / "visual-metrics-report.json"
    main(["audit-visual", str(path), "--out", str(report_path), "--json"])
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["unexpected"] = True
    report_path.write_text(json.dumps(report), encoding="utf-8")
    assert main(["validate-report", str(report_path), "--schema", "--json"]) == 1


def test_empty_screens_pass_trivially(tmp_path: Path) -> None:
    path = _write_tree(tmp_path, _tree())
    report = audit_visual(path)
    assert report["status"] == "PASS"
    assert report["summary"] == {
        "errors": 0,
        "warnings": 0,
        "infos": 0,
        "nodes_checked": 0,
        "screens_checked": 0,
    }
    assert report["inputs"] == {
        "expected_tree": str(path),
        "theme_css": None,
        "layout_snapshot": None,
    }


def test_engine_rejects_malformed_screens(tmp_path: Path) -> None:
    bad_screen = _write_tree(
        tmp_path, {"version": 1, "screens": ["not-an-object"]}, name="bad-screen.json"
    )
    with pytest.raises(ValueError):
        audit_visual(bad_screen)
    rootless = _write_tree(
        tmp_path, {"version": 1, "screens": [{"screen_id": "s1"}]}, name="rootless.json"
    )
    with pytest.raises(ValueError):
        audit_visual(rootless)


def test_thresholds_match_contract() -> None:
    assert INTERACTIVE_ROLES == frozenset({"button", "link", "input", "select", "toggle"})
    assert CONTRAST_AA_NORMAL == 4.5
    assert CONTRAST_AA_LARGE == 3.0
    assert LARGE_TEXT_PX == 24.0
    assert LARGE_BOLD_TEXT_PX == 18.0
    assert BOLD_FONT_WEIGHT == 700.0
    assert TOUCH_TARGET_PASS_PX == 44.0
    assert TOUCH_TARGET_ERROR_PX == 24.0
    assert GEOMETRY_TOLERANCE_PX == 1.0
    assert TEXT_WIDTH_FACTOR == 0.55
