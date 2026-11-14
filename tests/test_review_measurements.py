"""Default check integration for profiles and independent rendered observations."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from penflow.review_checks import check_workspace


def write_workspace(tmp_path: Path, height: float = 32) -> dict:
    pen = {
        "version": "2.17",
        "children": [
            {
                "id": "primary-frame",
                "type": "frame",
                "width": 420,
                "height": 240,
                "x": 800,
                "y": 200,
                "context": "semantic_id=workspace; role=screen",
                "layout": "none",
                "children": [
                    {
                        "id": "action",
                        "type": "frame",
                        "width": 100,
                        "height": height,
                        "x": 24,
                        "y": 24,
                        "context": "semantic_id=workspace.save; role=button",
                        "layout": "none",
                        "fontSize": 14,
                        "lineHeight": 20,
                        "lineHeightUnit": "px",
                        "padding": [8, 16],
                    }
                ],
            }
        ],
    }
    (tmp_path / "ui.pen").write_text(json.dumps(pen))
    (tmp_path / "design-profile.json").write_text(
        json.dumps(
            {
                "version": 1,
                "surface": "desktop-app",
                "platform": "web",
            }
        )
    )
    return pen


def checks(tmp_path: Path) -> dict:
    return {row["name"]: row for row in check_workspace(tmp_path)["checks"]}


def capture(height: float = 32) -> dict:
    # Independent adapter-shaped input: no expected-tree exporter is used here.
    return {
        "version": 1,
        "measurement": {
            "source": "runtime",
            "units": "css-px",
            "coordinate_space": "screen-relative",
            "zoom": 1,
            "device_pixel_ratio": 2,
            "method": "DOM rect and computed style",
        },
        "screens": [
            {
                "screen_id": "workspace",
                "design_screen_id": "primary-frame",
                "viewport": {"width": 420, "height": 240},
                "root": {
                    "id": "runtime-main",
                    "semantic_id": "workspace",
                    "role": "screen",
                    "visual": {"layout": "none"},
                    "bbox": {"x": 0, "y": 0, "width": 420, "height": 240},
                    "children": [
                        {
                            "id": "runtime-save",
                            "semantic_id": "workspace.save",
                            "role": "button",
                            "bbox": {"x": 24, "y": 24, "width": 100, "height": height},
                            "visual": {
                                "layout": "none",
                                "fontSize": 14,
                                "lineHeight": 20,
                                "lineHeightUnit": "px",
                                "padding": [8, 16],
                            },
                        }
                    ],
                },
            }
        ],
    }


@pytest.mark.parametrize("height", [64, 92])
def test_default_check_detects_oversized_design(tmp_path: Path, height: float) -> None:
    write_workspace(tmp_path, height)
    result = checks(tmp_path)
    assert result["design-profile"]["status"] == "FAIL"
    assert any(
        item["code"] == "profile.metric.out_of_range" for item in result["design-profile"]["issues"]
    )
    assert result["compare-rendered"]["status"] == "NOT_RUN"


def test_default_check_measures_geometry_then_observes_correction(tmp_path: Path) -> None:
    write_workspace(tmp_path)
    path = tmp_path / "actual-ui-tree.json"
    path.write_text(json.dumps(capture(76)))
    result = checks(tmp_path)
    assert result["compare-rendered"]["details"]["status"] == "MATERIAL_DRIFT"
    path.write_text(json.dumps(capture()))
    result = checks(tmp_path)
    assert result["compare-rendered"]["details"]["status"] == "CONFORMING"
    assert result["compare-rendered"]["status"] == "PASS"


def test_legacy_structural_tree_is_not_rendered_evidence(tmp_path: Path) -> None:
    write_workspace(tmp_path)
    actual = capture()
    del actual["measurement"]
    (tmp_path / "actual-ui-tree.json").write_text(json.dumps(actual))
    result = checks(tmp_path)
    assert result["compare-rendered"]["status"] == "NOT_OBSERVED"
    assert result["compare-rendered"]["exit_code"] is None


def test_lifecycle_ambiguity_keeps_independent_source_audits(tmp_path: Path) -> None:
    pen = write_workspace(tmp_path, 80)
    root = pen["children"][0]
    other = copy.deepcopy(root)
    other["id"] = "other-frame"
    other["children"][0]["id"] = "other-action"
    pen["children"].append(other)
    (tmp_path / "ui.pen").write_text(json.dumps(pen))
    result = checks(tmp_path)
    assert result["validate-pen"]["status"] == "ERROR"
    assert result["design-profile"]["status"] == "FAIL"
    assert result["lint-tokens"]["status"] != "ERROR"
    assert result["audit-visual"]["exit_code"] is not None
    assert result["compare-tree"]["status"] == "NOT_RUN"


def test_bad_policy_and_runtime_metadata_do_not_stop_other_checks(tmp_path: Path) -> None:
    write_workspace(tmp_path)
    (tmp_path / "design-profile.json").write_text('{"version":1,"surface":"fiction"}')
    actual = capture()
    actual["measurement"]["device_pixel_ratio"] = 0
    (tmp_path / "actual-ui-tree.json").write_text(json.dumps(actual))
    result = checks(tmp_path)
    assert result["design-profile"]["status"] == "ERROR"
    assert result["compare-rendered"]["status"] == "ERROR"
    assert result["lint-tokens"]["exit_code"] is not None


def test_compact_desktop_visual_is_not_an_iphone_hit_area(tmp_path: Path) -> None:
    write_workspace(tmp_path, 32)
    result = checks(tmp_path)
    assert not any(
        item["code"] == "visual.touch_target.too_small" for item in result["audit-visual"]["issues"]
    )
    assert any(
        item["code"] == "visual.hit_area.profile_scoped"
        for item in result["audit-visual"]["issues"]
    )


def test_responsive_captures_select_distinct_physical_frames_explicitly(tmp_path: Path) -> None:
    from penflow.tree import validate_actual_tree

    actual = capture()
    alternate = copy.deepcopy(actual["screens"][0])
    alternate["design_screen_id"] = "mobile-frame"
    actual["screens"].append(alternate)
    assert validate_actual_tree(actual) == []
    alternate["design_screen_id"] = "primary-frame"
    assert validate_actual_tree(actual)
    alternate["design_screen_id"] = "mobile-frame"
    del actual["measurement"]
    assert validate_actual_tree(actual)


def test_real_source_preserves_reasoned_mask_and_explicit_variant(tmp_path: Path) -> None:
    pen = write_workspace(tmp_path)
    root = pen["children"][0]
    root["context"] += "; variant=desktop"
    root["children"][0]["context"] = {
        "semantic_id": "workspace.save",
        "role": "button",
        "intent": "save",
        "mask": True,
        "override_reason": "Runtime clock is excluded from geometric comparison",
    }
    (tmp_path / "ui.pen").write_text(json.dumps(pen))
    actual = capture(80)
    actual["screens"][0]["variant"] = "desktop"
    (tmp_path / "actual-ui-tree.json").write_text(json.dumps(actual))
    result = checks(tmp_path)["compare-rendered"]
    assert not any(
        item["code"] in {"rendered.override.unjustified", "rendered.screen.ambiguous"}
        for item in result["issues"]
    )
    assert result["status"] != "ERROR"


def test_native_default_layout_orientation_is_compared(tmp_path: Path) -> None:
    pen = write_workspace(tmp_path)
    del pen["children"][0]["layout"]
    pen["children"][0]["alignItems"] = "start"
    (tmp_path / "ui.pen").write_text(json.dumps(pen))
    actual = capture()
    actual["screens"][0]["root"]["visual"] = {"layout": "vertical", "alignItems": "flex-start"}
    (tmp_path / "actual-ui-tree.json").write_text(json.dumps(actual))
    result = checks(tmp_path)["compare-rendered"]
    assert any(item["code"] == "node.visual.layout" for item in result["issues"])
    assert not any(item["code"] == "node.visual.alignItems" for item in result["issues"])


def test_local_component_inheritance_is_in_default_check(tmp_path: Path) -> None:
    pen = write_workspace(tmp_path)
    template = copy.deepcopy(pen["children"][0]["children"][0])
    template.update(id="button-definition", reusable=True, context="role=button; intent=save")
    pen["children"].insert(0, template)
    pen["children"][1]["children"] = [
        {
            "id": "action",
            "type": "ref",
            "ref": "button-definition",
            "x": 24,
            "y": 24,
            "context": "semantic_id=workspace.save; role=button; intent=save",
        }
    ]
    original = json.dumps(pen)
    (tmp_path / "ui.pen").write_text(original)
    (tmp_path / "actual-ui-tree.json").write_text(json.dumps(capture(80)))
    result = checks(tmp_path)
    assert result["resolve-components"]["status"] == "PASS"
    assert any(item["code"] == "node.bbox.height" for item in result["compare-rendered"]["issues"])
    assert not any(
        item["code"] == "rendered.screen.unobserved"
        for item in result["compare-rendered"]["issues"]
    )
    assert (tmp_path / "ui.pen").read_text() == original


def test_imported_component_never_establishes_inherited_compliance(tmp_path: Path) -> None:
    pen = write_workspace(tmp_path)
    pen["children"][0]["children"][0].update(type="ref", ref="external:button")
    (tmp_path / "ui.pen").write_text(json.dumps(pen))
    (tmp_path / "actual-ui-tree.json").write_text(json.dumps(capture()))
    result = checks(tmp_path)
    assert result["resolve-components"]["status"] == "NOT_OBSERVED"
    assert result["design-profile"]["status"] == "NOT_OBSERVED"
    assert result["compare-rendered"]["status"] == "NOT_OBSERVED"


def test_native_theme_inheritance_and_dimension_tokens_resolve_before_compare(
    tmp_path: Path,
) -> None:
    pen = write_workspace(tmp_path)
    pen["themes"] = {"mode": ["light", "dark"]}
    pen["variables"] = {
        "control-height": {
            "type": "number",
            "value": [
                {"value": 40, "theme": {}},
                {"value": 32, "theme": {"mode": "light"}},
                {"value": 36, "theme": {"mode": "dark"}},
            ],
        }
    }
    pen["children"][0]["theme"] = {"mode": "dark"}
    pen["children"][0]["children"][0]["height"] = "$control-height"
    (tmp_path / "ui.pen").write_text(json.dumps(pen))
    (tmp_path / "actual-ui-tree.json").write_text(json.dumps(capture(36)))
    result = checks(tmp_path)
    assert "resolve-design-variables" not in result
    assert result["compare-rendered"]["details"]["status"] == "CONFORMING"
    assert not any(item["code"] == "pen.bbox.invalid" for item in result["validate-pen"]["issues"])
