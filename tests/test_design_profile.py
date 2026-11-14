"""Policy selection and missing-measurement regressions for convention profiles."""

from __future__ import annotations

import copy
import hashlib

import pytest

from penflow.design_profile import audit_design_profile, resolve_profile


def selection(surface="desktop-app", platform="web", **extra):
    return {"version": 1, "surface": surface, "platform": platform, **extra}


def design(height=40, *, font=14, padding=16, line_height=20):
    return {
        "screens": [
            {
                "screen_id": "editor",
                "root": {
                    "id": "editor",
                    "role": "container",
                    "visual": {"gap": 8, "padding": 16},
                    "bbox": {"width": 900, "height": 600},
                    "children": [
                        {
                            "id": "save",
                            "semantic_id": "editor.save",
                            "role": "button",
                            "bbox": {"width": 108, "height": height},
                            "visual": {"padding": [8, padding]},
                            "children": [
                                {
                                    "id": "label",
                                    "role": "text",
                                    "visual": {
                                        "fontSize": font,
                                        "lineHeight": line_height,
                                        "lineHeightUnit": "px",
                                    },
                                    "children": [],
                                }
                            ],
                        }
                    ],
                },
            }
        ]
    }


def test_profile_resolves_unique_contract_purpose_without_a_flag():
    assert (
        resolve_profile(None, contract={"screens": [{"surface": "desktop-app"}]})["surface"]
        == "desktop-app"
    )
    assert resolve_profile(None, contract={"screens": [{"surface": "web"}]}) is None
    assert resolve_profile(None, contract={"screens": [{"surface": "ios"}]})["platform"] == "ios"
    assert resolve_profile(None, contract={"screens": [False]}) is None
    assert resolve_profile(None, contract={"screens": {"surface": "desktop-app"}}) is None


def test_profile_missing_and_incomplete_metrics_never_pass():
    assert audit_design_profile(design(), None)["status"] == "NOT_OBSERVED"
    tree = design()
    del tree["screens"][0]["root"]["children"][0]["children"][0]["visual"]["lineHeight"]
    result = audit_design_profile(tree, resolve_profile(selection()))
    assert result["status"] == "NOT_OBSERVED"
    assert any(
        item["property"] == "lineHeightRatio" and item["status"] == "NOT_OBSERVED"
        for item in result["observations"]
    )
    assert not result["issues"]


def test_profile_measures_descendant_label_and_preserves_inputs():
    tree = design()
    before = copy.deepcopy(tree)
    result = audit_design_profile(tree, resolve_profile(selection()))
    assert result["status"] == "PASS"
    assert tree == before
    assert (
        next(item for item in result["observations"] if item["rule"] == "button-font")["value"]
        == 14
    )


@pytest.mark.parametrize(
    "height,font,padding,rule",
    [
        (72, 14, 16, "button-height"),
        (40, 23, 16, "button-font"),
        (40, 14, 48, "button-padding-horizontal"),
    ],
)
def test_material_control_metrics_are_independently_reported(height, font, padding, rule):
    result = audit_design_profile(
        design(height, font=font, padding=padding), resolve_profile(selection())
    )
    assert result["status"] == "FAIL"
    assert any(item["rule"] == rule and item["status"] == "FAIL" for item in result["issues"])


def test_product_purpose_changes_policy_without_using_iphone_hit_minima_on_desktop():
    tree = design(height=46, font=16, padding=20, line_height=23)
    assert audit_design_profile(tree, resolve_profile(selection()))["status"] == "FAIL"
    assert audit_design_profile(tree, resolve_profile(selection("landing")))["status"] == "PASS"
    mobile = audit_design_profile(design(28), resolve_profile(selection("mobile", "ios")))
    assert mobile["status"] == "NOT_OBSERVED"
    assert all(item["status"] == "NOT_OBSERVED" for item in mobile["observations"])
    button = tree["screens"][0]["root"]["children"][0]
    button["hitArea"] = {"width": 44, "height": 44}
    assert (
        audit_design_profile(tree, resolve_profile(selection("mobile", "ios")))["status"] == "PASS"
    )


def test_reasoned_override_is_scoped_visible_and_does_not_mask_other_metrics():
    config = selection(
        overrides=[
            {
                "rule": "button-height",
                "node": "editor.save",
                "reason": "Primary touch CTA in the desktop preview",
                "min": 44,
                "max": 48,
            }
        ]
    )
    tree = design(46)
    result = audit_design_profile(tree, resolve_profile(config))
    assert result["status"] == "PASS"
    assert next(item for item in result["observations"] if item["rule"] == "button-height")[
        "override"
    ]["reason"]
    tree["screens"][0]["root"]["children"][0]["visual"]["padding"] = 72
    assert audit_design_profile(tree, resolve_profile(config))["status"] == "FAIL"
    config["overrides"][0]["node"] = "other.save"
    assert any(
        item["code"] == "profile.override.unmatched"
        for item in audit_design_profile(tree, resolve_profile(config))["issues"]
    )


def test_source_snapshots_are_content_bound_and_required_when_declared():
    config = selection(sources=[".conventions/index.md"])
    with pytest.raises(ValueError, match="source.missing"):
        resolve_profile(config)
    raw = b"project conventions"
    resolved = resolve_profile(config, convention_sources={".conventions/index.md": raw})
    assert resolved["provenance"]["sources"] == [
        {"path": ".conventions/index.md", "sha256": hashlib.sha256(raw).hexdigest()}
    ]
    assert len(resolved["provenance"]["snapshot_sha256"]) == 64


@pytest.mark.parametrize(
    "extra",
    [
        {
            "rules": [
                {
                    "id": "custom",
                    "selector": {"role": "button"},
                    "property": "bbox.height",
                    "min": 50,
                    "max": 30,
                    "source": "product",
                }
            ]
        },
        {"overrides": [{"rule": "button-height", "node": "editor.save", "reason": " ", "max": 50}]},
        {"overrides": [{"rule": "unknown", "node": "editor.save", "reason": "product", "max": 50}]},
        {
            "rules": [
                {
                    "id": "custom",
                    "selector": {"role": "button"},
                    "property": "bbox.height",
                    "min": float("inf"),
                    "source": "product",
                }
            ]
        },
        {
            "rules": [
                {
                    "id": "custom",
                    "selector": {"role": "button"},
                    "property": "bbox.height",
                    "min": 30,
                    "values": [40],
                    "source": "product",
                }
            ]
        },
    ],
)
def test_invalid_and_contradictory_constraints_do_not_become_conformity(extra):
    with pytest.raises(ValueError):
        resolve_profile(selection(**extra))


def test_selection_cannot_contradict_explicit_contract_purpose():
    with pytest.raises(ValueError, match="selection.conflict"):
        resolve_profile(selection(), contract={"screens": [{"surface": "landing"}]})


def test_masks_do_not_erase_material_design_findings():
    tree = design(80)
    tree["screens"][0]["root"]["children"][0]["context"] = {"mask": True}
    assert audit_design_profile(tree, resolve_profile(selection()))["status"] == "FAIL"


def test_custom_aspect_ratio_and_font_family_rules_accept_other_dimensions():
    custom = [
        {
            "id": "image-ratio",
            "selector": {"role": "image"},
            "property": "aspectRatio",
            "min": 1.4,
            "max": 1.6,
            "source": "product image crop",
        },
        {
            "id": "brand-font",
            "selector": {"role": "text"},
            "property": "visual.fontFamily",
            "values": ["Cabinet Grotesk"],
            "source": "brand typography",
        },
    ]
    tree = {
        "screens": [
            {
                "screen_id": "gallery",
                "root": {
                    "id": "cover",
                    "role": "image",
                    "bbox": {"width": 450, "height": 300},
                    "children": [
                        {
                            "id": "caption",
                            "role": "text",
                            "visual": {"fontFamily": "Cabinet Grotesk"},
                            "children": [],
                        }
                    ],
                },
            }
        ]
    }
    profile = resolve_profile(selection(rules=custom))
    assert audit_design_profile(tree, profile)["status"] == "PASS"
    tree["screens"][0]["root"]["bbox"]["height"] = 600
    assert audit_design_profile(tree, profile)["status"] == "FAIL"


def test_line_height_units_are_explicit_and_equivalent():
    tree = design()
    visual = tree["screens"][0]["root"]["children"][0]["children"][0]["visual"]
    profile = resolve_profile(selection())
    visual["lineHeight"] = 1.4
    visual["lineHeightUnit"] = "multiplier"
    assert audit_design_profile(tree, profile)["status"] == "PASS"
    del visual["lineHeightUnit"]
    assert audit_design_profile(tree, profile)["status"] == "NOT_OBSERVED"
    visual["lineHeightUnit"] = "px"
    assert audit_design_profile(tree, profile)["status"] == "FAIL"
