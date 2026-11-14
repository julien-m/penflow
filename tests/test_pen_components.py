"""Native local component expansion invariants, independent of runtime comparison."""

from __future__ import annotations

from copy import deepcopy

import pytest

from penflow.pen_components import resolve_pen_components


def component():
    return {
        "id": "control",
        "type": "frame",
        "reusable": True,
        "width": 112,
        "height": 36,
        "padding": [8, 16],
        "context": "role=button; semantic_id=action.save",
        "children": [
            {
                "id": "label",
                "type": "text",
                "content": "Save",
                "fontSize": 14,
                "context": {"role": "text", "intent": "action-label"},
            }
        ],
    }


def flatten(root):
    nodes = [root]
    for child in root.get("children", []):
        nodes.extend(flatten(child))
    return nodes


def test_instances_inherit_metrics_without_changing_source_or_semantic_contexts():
    pen = {
        "version": "2.22",
        "children": [
            component(),
            {
                "id": "save-action",
                "type": "ref",
                "ref": "control",
                "x": 24,
                "height": 40,
                "context": "semantic_id=editor.save; role=button",
            },
            {"id": "other-action", "type": "ref", "ref": "control"},
        ],
    }
    before = deepcopy(pen)
    resolved, issues = resolve_pen_components(pen)
    assert issues == []
    assert pen == before
    instance, other = resolved["children"][1:]
    assert (instance["width"], instance["height"], instance["padding"]) == (112, 40, [8, 16])
    assert instance["context"] == "semantic_id=editor.save; role=button"
    assert instance["children"][0]["id"] == "save-action/label"
    assert other["children"][0]["id"] == "other-action/label"
    assert other["context"] == pen["children"][0]["context"]
    assert instance["children"][0]["context"] == pen["children"][0]["children"][0]["context"]
    assert "reusable" not in instance
    assert instance["type"] == "frame"


def test_nested_refs_apply_outer_overrides_after_inner_overrides():
    wrapper = {
        "id": "toolbar",
        "type": "frame",
        "reusable": True,
        "children": [
            {
                "id": "save-button",
                "type": "ref",
                "ref": "control",
                "descendants": {"label": {"content": "Publish"}},
            }
        ],
    }
    pen = {
        "children": [
            component(),
            wrapper,
            {
                "id": "editor-toolbar",
                "type": "ref",
                "ref": "toolbar",
                "descendants": {"save-button/label": {"content": "Submit", "fontSize": 15}},
            },
        ]
    }
    resolved, issues = resolve_pen_components(pen)
    assert issues == []
    button = resolved["children"][-1]["children"][0]
    assert button["id"] == "editor-toolbar/save-button"
    assert button["children"][0]["id"] == "editor-toolbar/save-button/label"
    assert button["children"][0]["content"] == "Submit"
    assert button["children"][0]["fontSize"] == 15


def test_ordinary_nested_frame_does_not_add_an_instance_segment():
    template = component()
    template["children"] = [
        {"id": "label-group", "type": "frame", "children": template["children"]}
    ]
    resolved, issues = resolve_pen_components(
        {
            "children": [
                template,
                {
                    "id": "action",
                    "type": "ref",
                    "ref": "control",
                    "descendants": {"label": {"content": "Continue"}},
                },
            ]
        }
    )
    assert issues == []
    label = resolved["children"][-1]["children"][0]["children"][0]
    assert label["id"] == "action/label"
    assert label["content"] == "Continue"


def test_type_override_replaces_node_instead_of_retaining_old_properties():
    resolved, issues = resolve_pen_components(
        {
            "children": [
                component(),
                {
                    "id": "icon-action",
                    "type": "ref",
                    "ref": "control",
                    "descendants": {
                        "label": {"id": "check", "type": "icon", "width": 18, "height": 18}
                    },
                },
            ]
        }
    )
    assert issues == []
    child = resolved["children"][-1]["children"][0]
    assert child == {"id": "icon-action/check", "type": "icon", "width": 18, "height": 18}
    assert "content" not in child and "fontSize" not in child and "context" not in child


def test_children_replacement_resolves_new_instances_without_old_children():
    panel = {
        "id": "panel",
        "type": "frame",
        "reusable": True,
        "children": [
            {
                "id": "content",
                "type": "frame",
                "fill": "#fff",
                "children": [{"id": "old", "type": "text"}],
            }
        ],
    }
    resolved, issues = resolve_pen_components(
        {
            "children": [
                component(),
                panel,
                {
                    "id": "settings-panel",
                    "type": "ref",
                    "ref": "panel",
                    "descendants": {
                        "content": {"children": [{"id": "save", "type": "ref", "ref": "control"}]},
                        "save/label": {"content": "Apply"},
                    },
                },
            ]
        }
    )
    assert issues == []
    content = resolved["children"][-1]["children"][0]
    assert content["fill"] == "#fff"
    assert content["children"][0]["id"] == "settings-panel/save"
    assert content["children"][0]["children"][0]["content"] == "Apply"
    assert not any(node["id"].endswith("/old") for node in flatten(resolved["children"][-1]))


def test_reference_components_can_be_reusable_and_resolved_again():
    alias = {
        "id": "primary",
        "type": "ref",
        "ref": "control",
        "reusable": True,
        "fill": "#08f",
        "descendants": {"label": {"content": "Create"}},
    }
    resolved, issues = resolve_pen_components(
        {
            "children": [
                component(),
                alias,
                {"id": "create", "type": "ref", "ref": "primary", "width": 160},
            ]
        }
    )
    assert issues == []
    instance = resolved["children"][-1]
    assert instance["id"] == "create" and instance["width"] == 160 and instance["height"] == 36
    assert instance["children"][0]["id"] == "create/label"
    assert instance["children"][0]["content"] == "Create"
    assert "reusable" not in instance


@pytest.mark.parametrize(
    "bad,code",
    [
        ({"id": "missing", "type": "ref", "ref": "absent", "height": 40}, "component.ref.missing"),
        (
            {"id": "external", "type": "ref", "ref": "kit:button"},
            "component.ref.external_not_observed",
        ),
        ({"id": "plain-ref", "type": "ref", "ref": "plain"}, "component.ref.not_reusable"),
    ],
)
def test_unresolved_branch_preserves_explicit_properties_and_independent_nodes(bad, code):
    good = component()
    resolved, issues = resolve_pen_components(
        {
            "children": [
                good,
                {"id": "plain", "type": "frame"},
                bad,
                {"id": "valid", "type": "ref", "ref": "control"},
            ]
        }
    )
    assert any(item["code"] == code for item in issues)
    unresolved = resolved["children"][2]
    assert unresolved["id"] == bad["id"] and unresolved["ref"] == bad["ref"]
    assert unresolved["unresolved_ref"]
    assert resolved["children"][-1]["height"] == 36
    if bad.get("height"):
        assert unresolved["height"] == bad["height"]
    if code.endswith("external_not_observed"):
        assert next(item for item in issues if item["code"] == code)["outcome"] == "NOT_OBSERVED"


def test_cycles_and_duplicate_targets_never_pick_an_arbitrary_template():
    cyclic = {
        "id": "loop",
        "type": "frame",
        "reusable": True,
        "children": [{"id": "inside", "type": "ref", "ref": "loop"}],
    }
    resolved, issues = resolve_pen_components(
        {"children": [cyclic, {"id": "copy", "type": "ref", "ref": "loop"}]}
    )
    assert any(item["code"] == "component.ref.cycle" for item in issues)
    assert resolved["children"][-1]["children"][0]["unresolved_ref"] == "cycle"
    one, two = component(), component()
    two["height"] = 90
    resolved, issues = resolve_pen_components(
        {"children": [one, two, {"id": "copy", "type": "ref", "ref": "control"}]}
    )
    assert any(item["code"] == "component.id.duplicate" for item in issues)
    assert resolved["children"][-1]["unresolved_ref"] == "duplicate"
    assert "height" not in resolved["children"][-1]


def test_unknown_and_invalid_descendant_overrides_remain_findings():
    resolved, issues = resolve_pen_components(
        {
            "children": [
                component(),
                {
                    "id": "copy",
                    "type": "ref",
                    "ref": "control",
                    "descendants": {
                        "missing/label": {"fontSize": 28},
                        "label": {"type": "icon"},
                    },
                },
            ]
        }
    )
    assert {item["code"] for item in issues} == {
        "component.override.unmatched",
        "component.override.replacement_invalid",
    }
    assert resolved["children"][-1]["unresolved_ref"] == "unmatched-override"


def test_bounded_expansion_stops_repeated_branching():
    template = component()
    pen = {
        "children": [
            template,
            *[{"id": f"copy-{index}", "type": "ref", "ref": "control"} for index in range(20)],
        ]
    }
    resolved, issues = resolve_pen_components(pen, max_nodes=12)
    assert any(item["code"] == "component.expansion.limit" for item in issues)
    assert any(
        node.get("unresolved_ref") == "expansion-limit"
        for root in resolved["children"]
        for node in flatten(root)
    )
    assert len([node for root in resolved["children"] for node in flatten(root)]) < 35


def test_depth_and_limit_arguments_are_checked():
    with pytest.raises(ValueError, match="limit.invalid"):
        resolve_pen_components({"children": []}, max_nodes=0)
    with pytest.raises(ValueError, match="document.invalid"):
        resolve_pen_components({"children": {}})
    tree = {
        "id": "root",
        "type": "frame",
        "children": [
            {"id": "child", "type": "frame", "children": [{"id": "deep", "type": "text"}]}
        ],
    }
    _, issues = resolve_pen_components({"children": [tree]}, max_depth=1)
    assert any(item["code"] == "component.source.limit" for item in issues)
    assert any(item["code"] == "component.expansion.limit" for item in issues)
