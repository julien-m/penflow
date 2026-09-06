"""Native intrinsic text measurements replace heuristics without hiding clipping."""

import pytest

from penflow.verification_geometry import intrinsic_text_ids
from penflow.visual_metrics import audit_visual


@pytest.mark.parametrize(
    "growth,measured,overflow",
    [
        (None, True, False),
        ("auto", True, False),
        ("fixed-width-height", True, False),
        (None, False, False),
        (None, True, True),
        ("fixed-width", True, False),
        ("fixed-width", True, True),
    ],
)
def test_intrinsic_width_requires_native_source_and_measurement(growth, measured, overflow):
    """Fixed/unmeasured text retains estimation; measured auto text still checks its parent."""
    authored = {"id": "text", "type": "text"}
    if growth is not None:
        authored["textGrowth"] = growth
    pen = {"version": "2.14", "children": [authored]}
    wrapped = growth == "fixed-width"
    node = {
        "id": "text",
        "pencil_id": "text",
        "role": "text",
        "text": (
            "A wrapped paragraph preserves all of its source content across native lines. " * 3
        )
        if wrapped
        else "10",
        "visual": {"fontSize": 16},
        "children": [],
        "bbox": {
            "x": (790 if wrapped else 90) if overflow else 0,
            "y": 0,
            "width": 640 if wrapped else 17,
            "height": 81 if wrapped else 23,
        },
    }
    tree = {
        "version": 1,
        "screens": [
            {
                "screen_id": "screen",
                "root": {
                    "id": "root",
                    "pencil_id": "root",
                    "role": "screen",
                    "children": [node],
                    "bbox": {
                        "x": 0,
                        "y": 0,
                        "width": 800 if wrapped else 100,
                        "height": 200 if wrapped else 100,
                    },
                },
            }
        ],
    }
    result = audit_visual(
        "unused",
        tree_data=tree,
        layout_snapshot=tree if measured else None,
        intrinsic_text_ids=intrinsic_text_ids(pen) if measured else frozenset(),
    )
    codes = {issue["code"] for issue in result["issues"]}
    assert ("visual.text.likely_overflow" in codes) is (
        growth == "fixed-width-height" or not measured
    )
    assert ("visual.bbox.overflow" in codes) is overflow
