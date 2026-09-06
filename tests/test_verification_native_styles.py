"""Native Pencil style forms are observed and compared without losing border geometry."""

from copy import deepcopy

import pytest

from penflow.compare import compare_trees
from penflow.pen import parse_pen
from penflow.tree import _screen_to_expected


def _tree():
    root = parse_pen(
        {
            "children": [
                {
                    "id": "screen",
                    "type": "frame",
                    "width": 400,
                    "height": 300,
                    "context": "classification=semantic; semantic_id=screen; role=screen; test_id=screen",
                    "children": [
                        {
                            "id": "box",
                            "type": "frame",
                            "width": 80,
                            "height": 48,
                            "stroke": "#123456",
                            "strokeWidth": 1,
                            "strokeAlignment": "inner",
                            "context": "classification=decorative",
                        }
                    ],
                }
            ]
        }
    )[0]
    return {"version": 1, "screens": [_screen_to_expected(root)]}


@pytest.mark.parametrize("value", [1, {"top": 1, "right": 2, "bottom": 3, "left": 4}])
def test_native_border_width_is_preserved_and_compared(value):
    expected = _tree()
    expected["screens"][0]["root"]["children"][0]["visual"]["strokeWidth"] = value
    assert compare_trees(expected, expected)["issues"] == []
    actual = deepcopy(expected)
    actual["screens"][0]["root"]["children"][0]["visual"]["strokeWidth"] = 99
    assert any(
        item["code"] == "node.visual.strokeWidth"
        for item in compare_trees(expected, actual)["issues"]
    )


def test_native_parser_does_not_drop_stroke_width_or_alignment():
    visual = _tree()["screens"][0]["root"]["children"][0]["visual"]
    assert visual["strokeWidth"] == 1
    assert visual["strokeAlignment"] == "inner"


def test_design_variable_and_css_color_representations_are_equivalent():
    from penflow.verification_comparison import compare_required_trees
    from penflow.verification_styles import resolve_design_variables

    expected = _tree()
    expected["screens"][0]["root"]["visual"] = {"fill": "$background", "fontFamily": "$font"}
    resolve_design_variables(
        expected,
        {
            "background": {"type": "color", "value": "#ffffff"},
            "font": {"type": "string", "value": "Inter"},
        },
    )
    actual = deepcopy(expected)
    actual["screens"][0]["root"]["visual"] = {
        "fill": "rgb(255, 255, 255)",
        "fontFamily": '"Inter", sans-serif',
    }
    contract = {"nodes": [{"semantic_id": "screen"}]}
    assert compare_required_trees(contract, expected, actual) == []
    actual["screens"][0]["root"]["visual"]["fill"] = "#000000"
    assert compare_required_trees(contract, expected, actual)


@pytest.mark.parametrize("theme", [{"mode": "dark"}, {}, {"mode": "unknown"}])
def test_explicit_native_theme_resolves_only_one_matching_value(theme):
    from penflow.verification_styles import resolve_design_variables
    from penflow.verification_files import VerificationInputError

    expected = _tree()
    expected["screens"][0]["root"]["visual"] = {"fill": "$background"}
    variables = {
        "background": {
            "type": "color",
            "value": [
                {"theme": {"mode": "light"}, "value": "#ffffff"},
                {"theme": {"mode": "dark"}, "value": "#000000"},
            ],
        }
    }
    source = {"children": [{"id": "screen", "theme": theme}]}
    if theme == {"mode": "dark"}:
        resolve_design_variables(expected, variables, pen_data=source)
        assert expected["screens"][0]["root"]["visual"]["fill"] == "#000000"
    else:
        with pytest.raises(VerificationInputError):
            resolve_design_variables(expected, variables, pen_data=source)


@pytest.mark.parametrize("key", ["cornerRadius", "strokeThickness", "strokeWidth", "padding"])
def test_unrepresentable_visual_measurement_fails_without_overflow(key):
    from penflow.tree import validate_actual_tree

    value = _tree()
    value["screens"][0]["root"]["visual"][key] = 10**400
    assert validate_actual_tree(value)


@pytest.mark.parametrize(
    "legacy",
    [{"stroke": {"fill": "#123456", "thickness": 1}}, {"stroke": "#123456", "strokeThickness": 1}],
)
def test_border_generations_normalize_without_losing_width(legacy):
    from penflow.verification_styles import normalize_observed_styles

    old, new = _tree(), _tree()
    old["screens"][0]["root"]["visual"] = legacy
    new["screens"][0]["root"]["visual"] = {"stroke": "#123456", "strokeWidth": 1}
    normalize_observed_styles(old)
    normalize_observed_styles(new)
    assert old["screens"][0]["root"]["visual"] == new["screens"][0]["root"]["visual"]


def test_conflicting_border_aliases_are_not_silently_selected():
    from penflow.verification_styles import normalize_observed_styles
    from penflow.verification_files import VerificationInputError

    tree = _tree()
    tree["screens"][0]["root"]["visual"] = {"strokeThickness": 1, "strokeWidth": 9}
    with pytest.raises(VerificationInputError):
        normalize_observed_styles(tree)
