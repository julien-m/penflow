"""C51 compares styles only when the contract declares shared component identity."""

import pytest

from penflow.consistency import check_consistency


@pytest.mark.parametrize("shared", [False, True])
def test_explicit_component_identity_controls_consistency(shared: bool) -> None:
    """Unrelated title/body styles coexist; declared matching variants must agree."""
    children = []
    for name, fill, size in (("title", "#000000", 32), ("body", "#666666", 16)):
        children.append(
            {
                "id": name,
                "semantic_id": name,
                "role": "text",
                "context": {"variant": "heading"} if shared else {},
                "bbox": {"x": 0, "y": 0, "width": 0, "height": 0},
                "visual": {"fill": fill, "fontSize": size},
                "children": [],
            }
        )
    tree = {
        "version": 1,
        "screens": [
            {
                "screen_id": "screen",
                "root": {
                    "id": "screen",
                    "role": "screen",
                    "children": children,
                },
            }
        ],
    }
    result = check_consistency("unused.json", tree_data=tree, shared_identity_only=True)
    assert bool(result["issues"]) is shared
