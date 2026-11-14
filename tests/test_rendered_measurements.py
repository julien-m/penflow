"""Rendered comparisons distinguish absent facts, material drift and invalid measurements."""

from copy import deepcopy

import pytest

from penflow.rendered_measurements import compare_rendered


@pytest.fixture
def trees():
    expected = {
        "version": 1,
        "source": "ui.pen",
        "source_sha256": "current-design",
        "screens": [
            {
                "screen_id": "settings",
                "pencil_id": "physical-desktop",
                "viewport": {"width": 1000, "height": 700},
                "root": {
                    "id": "settings",
                    "role": "screen",
                    "pencil_id": "physical-desktop",
                    "bbox": {"x": 300, "y": 200, "width": 1000, "height": 700},
                    "children": [
                        {
                            "id": "save",
                            "role": "button",
                            "pencil_id": "control",
                            "bbox": {"x": 24, "y": 32, "width": 120, "height": 36},
                            "sizing": {"width": "fixed", "height": "fixed"},
                            "visual": {"fontSize": 14, "fontFamily": "Inter", "padding": [8, 16]},
                        }
                    ],
                },
            }
        ],
    }
    actual = deepcopy(expected)
    actual.pop("source")
    actual.pop("source_sha256")
    actual["measurement"] = {
        "source": "runtime",
        "units": "css-px",
        "coordinate_space": "screen-relative",
        "zoom": 1,
        "device_pixel_ratio": 1,
        "method": "getBoundingClientRect+getComputedStyle",
    }
    actual["screens"][0]["root"]["bbox"].update(x=0, y=0)
    return expected, actual


def control(tree):
    return tree["screens"][0]["root"]["children"][0]


def codes(report):
    return {item["code"] for item in report["issues"]}


def test_fixed_geometry_normalizes_canvas_origin_without_mutating_inputs(trees):
    expected, actual = trees
    before = deepcopy(trees)
    assert compare_rendered(expected, actual)["status"] == "CONFORMING"
    assert trees == before


@pytest.mark.parametrize(("property_name", "value"), [("height", 72), ("width", 230)])
def test_oversized_controls_are_material_even_when_most_properties_match(
    trees, property_name, value
):
    expected, actual = trees
    control(actual)["bbox"][property_name] = value
    report = compare_rendered(expected, actual)
    assert report["status"] == "MATERIAL_DRIFT"
    assert "node.bbox." + property_name in codes(report)


@pytest.mark.parametrize(
    ("property_name", "value"), [("fontSize", 16), ("fontFamily", "serif"), ("padding", [16, 24])]
)
def test_computed_styles_detect_material_differences(trees, property_name, value):
    expected, actual = trees
    control(actual)["visual"][property_name] = value
    assert compare_rendered(expected, actual)["status"] == "MATERIAL_DRIFT"


def test_missing_measurements_never_conform(trees):
    expected, actual = trees
    actual.pop("measurement")
    assert compare_rendered(expected, actual)["status"] == "NOT_OBSERVED"
    assert compare_rendered(expected, None)["status"] == "NOT_OBSERVED"


@pytest.mark.parametrize("units", ["fictional", [], None])
def test_malformed_measurement_units_return_error(trees, units):
    expected, actual = trees
    actual["measurement"]["units"] = units
    assert compare_rendered(expected, actual)["status"] == "MEASUREMENT_ERROR"


def test_wrong_viewport_prevents_geometry_comparison_but_keeps_styles(trees):
    expected, actual = trees
    actual["screens"][0]["viewport"]["width"] = 500
    control(actual)["bbox"]["width"] = 999
    control(actual)["visual"]["fontSize"] = 22
    report = compare_rendered(expected, actual)
    assert report["status"] == "MEASUREMENT_ERROR"
    assert "rendered.viewport.width" in codes(report)
    assert "node.bbox.width" not in codes(report)
    assert "node.visual.fontSize" in codes(report)


def test_missing_viewport_is_unobserved(trees):
    expected, actual = trees
    actual["screens"][0].pop("viewport")
    assert compare_rendered(expected, actual)["status"] == "NOT_OBSERVED"


def test_source_fill_dimension_is_not_compared_as_zero(trees):
    expected, actual = trees
    control(expected)["sizing"]["width"] = "fill"
    control(expected)["bbox"]["width"] = 0
    report = compare_rendered(expected, actual)
    assert report["status"] == "NOT_OBSERVED"
    assert "node.bbox.width" not in codes(report)
    control(actual)["bbox"]["height"] = 92
    assert "node.bbox.height" in codes(compare_rendered(expected, actual))


def native_layout(expected):
    root = expected["screens"][0]["root"]
    return {
        "source_sha256": expected["source_sha256"],
        "coordinate_space": "parent-relative",
        "children": [
            {
                "id": root["pencil_id"],
                **root["bbox"],
                "children": [{"id": control(expected)["pencil_id"], **control(expected)["bbox"]}],
            }
        ],
    }


def test_native_measurement_resolves_fill_when_bound_to_current_source(trees):
    expected, actual = trees
    layout = native_layout(expected)
    control(expected)["sizing"]["width"] = "fill"
    control(expected)["bbox"]["width"] = 0
    assert compare_rendered(expected, actual, design_layout=layout)["status"] == "CONFORMING"
    layout["source_sha256"] = "old-design"
    assert compare_rendered(expected, actual, design_layout=layout)["status"] == "MEASUREMENT_ERROR"
    layout.pop("source_sha256")
    assert compare_rendered(expected, actual, design_layout=layout)["status"] == "NOT_OBSERVED"


def test_layout_error_does_not_partially_mutate_comparison_geometry(trees):
    expected, actual = trees
    layout = native_layout(expected)
    layout["children"][0]["children"][0]["id"] = "wrong-node"
    report = compare_rendered(expected, actual, design_layout=layout)
    assert report["status"] == "MEASUREMENT_ERROR"
    assert not any(code.startswith("node.bbox") for code in codes(report))


def test_responsive_variant_selects_explicit_physical_screen(trees):
    expected, actual = trees
    alternate = deepcopy(expected["screens"][0])
    alternate["pencil_id"] = "physical-mobile"
    alternate["viewport"]["width"] = 400
    expected["screens"].append(alternate)
    actual["screens"][0]["design_screen_id"] = "physical-desktop"
    report = compare_rendered(expected, actual)
    assert report["status"] == "NOT_OBSERVED"
    assert report["coverage"]["observed_design_screens"] == 1
    assert "rendered.screen.ambiguous" not in codes(report)
    actual["screens"][0].pop("design_screen_id")
    assert compare_rendered(expected, actual)["status"] == "MEASUREMENT_ERROR"


def test_masks_require_explanation_and_preserve_other_controls(trees):
    expected, actual = trees
    control(expected)["context"] = {"mask": True}
    control(actual)["bbox"]["width"] = 600
    assert compare_rendered(expected, actual)["status"] == "MEASUREMENT_ERROR"
    control(expected)["context"]["override_reason"] = "External signed-in account label varies"
    report = compare_rendered(expected, actual)
    assert report["status"] == "NOT_OBSERVED"
    assert "rendered.mask.unobserved" in codes(report)


def test_large_tolerance_requires_product_reason(trees):
    expected, actual = trees
    control(expected)["context"] = {"tolerance": {"bbox_px": 99}}
    assert compare_rendered(expected, actual)["status"] == "MEASUREMENT_ERROR"


@pytest.mark.parametrize(
    ("fit", "outcome"),
    [("fill", "MATERIAL_DRIFT"), ("contain", "CONFORMING"), ("cover", "CONFORMING")],
)
def test_intrinsic_image_ratio_distinguishes_stretch_from_crop(trees, fit, outcome):
    expected, actual = trees
    control(expected)["role"] = control(actual)["role"] = "image"
    control(actual)["image"] = {"natural_width": 640, "natural_height": 320, "object_fit": fit}
    assert compare_rendered(expected, actual)["status"] == outcome


def test_parent_relative_runtime_accumulates_ancestors(trees):
    expected, actual = trees
    expected_root, actual_root = expected["screens"][0]["root"], actual["screens"][0]["root"]
    for root in (expected_root, actual_root):
        root["children"] = [
            {
                "id": "section",
                "role": "container",
                "bbox": {"x": 12, "y": 8, "width": 200, "height": 100},
                "children": root["children"],
            }
        ]
    actual["measurement"]["coordinate_space"] = "parent-relative"
    assert compare_rendered(expected, actual)["status"] == "CONFORMING"


def test_physical_pixels_normalize_once_by_declared_dpr(trees):
    expected, actual = trees
    actual["measurement"].update(units="physical-px", device_pixel_ratio=2)
    for node in [actual["screens"][0]["root"], control(actual)]:
        node["bbox"] = {key: value * 2 for key, value in node["bbox"].items()}
        for key, value in node.get("visual", {}).items():
            if key in {"fontSize", "padding"}:
                node["visual"][key] = (
                    [item * 2 for item in value] if isinstance(value, list) else value * 2
                )
    actual["screens"][0]["viewport"] = {
        key: value * 2 for key, value in actual["screens"][0]["viewport"].items()
    }
    assert compare_rendered(expected, actual)["status"] == "CONFORMING"


@pytest.mark.parametrize(
    ("unit", "raw", "outcome"),
    [("multiplier", 1.5, "CONFORMING"), ("px", 21, "CONFORMING"), (None, 1.5, "NOT_OBSERVED")],
)
def test_line_height_unit_is_explicit(trees, unit, raw, outcome):
    expected, actual = trees
    control(expected)["visual"].update(lineHeight=raw)
    if unit:
        control(expected)["visual"]["lineHeightUnit"] = unit
    control(actual)["visual"]["lineHeight"] = 21
    assert compare_rendered(expected, actual)["status"] == outcome


def test_contradictory_border_aliases_are_measurement_error(trees):
    expected, actual = trees
    control(actual)["visual"].update(strokeWidth=1, strokeThickness=2)
    assert compare_rendered(expected, actual)["status"] == "MEASUREMENT_ERROR"


def test_obvious_design_copy_is_rejected_without_rejecting_identical_real_geometry(trees):
    expected, actual = trees
    actual["source"] = expected["source"]
    assert compare_rendered(expected, actual)["status"] == "MEASUREMENT_ERROR"


def state_trees(trees):
    expected, actual = trees
    expected_screen = expected["screens"][0]
    expected_screen["states"] = ["pending", "complete"]
    pending = control(expected)
    pending["states"] = ["pending"]
    complete = deepcopy(pending)
    complete.update(id="reopen", pencil_id="reopen-control", states=["complete"])
    expected_screen["root"]["children"].append(complete)
    actual["screens"] = []
    actual["observed_states"] = []
    for state, node in (("pending", pending), ("complete", complete)):
        capture = deepcopy(expected_screen)
        capture.update(state=state, scenario_id="scenario-" + state)
        capture["root"]["bbox"].update(x=0, y=0)
        capture["root"]["children"] = [deepcopy(node)]
        actual["screens"].append(capture)
        actual["observed_states"].append(
            {
                "screen_id": capture["screen_id"],
                "state": state,
                "scenario_id": capture["scenario_id"],
                "session_id": "runtime-session",
                "evidence": {"path": "capture-" + state + ".json", "sha256": "0" * 64},
            }
        )
    return expected, actual


def test_rendered_groups_all_states_before_computing_coverage(trees):
    expected, actual = state_trees(trees)
    report = compare_rendered(expected, actual)
    assert report["status"] == "CONFORMING"
    assert len(report["comparisons"]) == 1
    actual["screens"].pop()
    assert "screen.state_missing" in codes(compare_rendered(expected, actual))


def test_invalid_viewport_skips_only_its_capture_geometry(trees):
    expected, actual = state_trees(trees)
    actual["screens"][0]["viewport"]["width"] /= 2
    actual["screens"][0]["root"]["children"][0]["bbox"]["height"] *= 2
    actual["screens"][1]["root"]["children"][0]["bbox"]["width"] *= 2
    report = compare_rendered(expected, actual)
    assert "rendered.viewport.width" in codes(report)
    assert "node.bbox.width" in codes(report)
    assert "node.bbox.height" not in codes(report)
    assert "screen.state_missing" not in codes(report)


def test_grouped_capture_preserves_missing_witness_failure(trees):
    expected, actual = state_trees(trees)
    actual["observed_states"].pop()
    report = compare_rendered(expected, actual)
    assert "screen.state_unwitnessed" in codes(report)
    assert "screen.state_missing" not in codes(report)


def test_explicit_physical_selection_projects_matching_state_witnesses(trees):
    expected, actual = state_trees(trees)
    expected["screens"][0]["screen_id"] = "candidate-settings"
    for capture in actual["screens"]:
        capture["design_screen_id"] = expected["screens"][0]["pencil_id"]
    assert compare_rendered(expected, actual)["status"] == "CONFORMING"


@pytest.mark.parametrize(
    ("expected_style", "actual_style"),
    [
        ({"strokeWidth": 1}, {"strokeWidth": 2}),
        ({"strokeThickness": 1}, {"strokeThickness": 2}),
        ({"strokeWidth": {"top": 1, "right": 2}}, {"strokeWidth": {"top": 2, "right": 4}}),
        (
            {"stroke": {"fill": "#112233", "thickness": 1}},
            {"stroke": {"fill": "#112233", "thickness": 2}},
        ),
    ],
)
def test_physical_pixel_border_lengths_normalize_all_supported_aliases(
    trees, expected_style, actual_style
):
    expected, actual = trees
    control(expected)["visual"] = expected_style
    control(actual)["visual"] = actual_style
    actual["measurement"].update(units="physical-px", device_pixel_ratio=2)
    for node in [actual["screens"][0]["root"], control(actual)]:
        node["bbox"] = {key: value * 2 for key, value in node["bbox"].items()}
    actual["screens"][0]["viewport"] = {
        key: value * 2 for key, value in actual["screens"][0]["viewport"].items()
    }
    assert compare_rendered(expected, actual)["status"] == "CONFORMING"


def test_reasoned_tolerance_cannot_hide_large_drift(trees):
    expected, actual = trees
    control(expected)["context"] = {
        "tolerance": {"bbox_px": 99},
        "override_reason": "Font metric differs on this platform",
    }
    control(actual)["bbox"]["width"] *= 2
    report = compare_rendered(expected, actual)
    assert report["status"] == "MEASUREMENT_ERROR"
    assert "rendered.tolerance.enlarged" in codes(report)
    assert "node.bbox.width" in codes(report)


def test_bounded_tolerance_keeps_reviewable_values_and_reason(trees):
    expected, actual = trees
    control(expected)["context"] = {
        "tolerance": {"bbox_px": 0.25},
        "override_reason": "Native vector controls require stricter alignment",
    }
    report = compare_rendered(expected, actual)
    assert report["status"] == "CONFORMING"
    applied = next(
        issue for issue in report["issues"] if issue["code"] == "rendered.tolerance.applied"
    )
    assert "0.25" in applied["message"]
    assert control(expected)["context"]["override_reason"] in applied["message"]


def test_native_layout_cannot_replace_a_contradictory_fixed_constraint(trees):
    expected, actual = trees
    layout = native_layout(expected)
    layout["children"][0]["children"][0]["height"] *= 2
    control(actual)["bbox"]["height"] *= 2
    report = compare_rendered(expected, actual, design_layout=layout)
    assert report["status"] == "MEASUREMENT_ERROR"
    assert "rendered.design_layout.invalid" in codes(report)


def test_matching_boxes_do_not_hide_observed_content_overflow(trees):
    expected, actual = trees
    control(actual)["observed"] = {"overflow_x": True, "overflow_y": False}
    report = compare_rendered(expected, actual)
    assert report["status"] == "NOT_OBSERVED"
    assert "rendered.overflow.review_required" in codes(report)
