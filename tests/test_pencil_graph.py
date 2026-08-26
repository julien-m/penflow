# @spec FR-002: Complete Pencil graph inventory — .specs/features/076-exhaustive-bidirectional-semantic-context/spec.md#fr-002
"""Closed document-graph inventory tests for feature 076."""

from __future__ import annotations

from penflow.pencil_graph import inventory_pencil_graph


def test_inventory_includes_roots_hidden_descendants_shared_and_orphans() -> None:
    document = {
        "children": [
            {
                "id": "screen",
                "type": "frame",
                "context": "classification=semantic; semantic_id=home; test_id=home; role=screen",
                "children": [
                    {
                        "id": "hidden",
                        "type": "text",
                        "visible": False,
                        "context": "classification=inherited; inherits_from=home; relation=content",
                    },
                    {"id": "gone", "type": "frame", "deleted": True},
                ],
            },
            {"id": "orphan", "type": "frame", "context": "classification=decorative"},
        ],
        "shared_components": [
            {
                "id": "shared.card",
                "type": "component",
                "context": (
                    "classification=semantic; semantic_id=shared.card; "
                    "test_id=shared-card; role=component"
                ),
            }
        ],
    }

    inventory = inventory_pencil_graph(document)

    assert [node.node_id for node in inventory.nodes] == [
        "screen",
        "hidden",
        "orphan",
        "shared.card",
    ]
    assert inventory.out_of_scope_metadata == 1
    assert inventory.nodes[1].screen_id == "home"
    assert inventory.nodes[3].owner_domain == "shared_component"
    assert {finding.code for finding in inventory.findings} == {"pencil.node_outside_screen"}


def test_inventory_is_cycle_safe_and_reports_duplicate_physical_node() -> None:
    cyclic: dict[str, object] = {
        "id": "screen",
        "type": "frame",
        "context": "classification=semantic; semantic_id=home; test_id=home; role=screen",
    }
    cyclic["children"] = [cyclic]

    inventory = inventory_pencil_graph({"children": [cyclic]})

    assert [node.node_id for node in inventory.nodes] == ["screen"]
    assert [finding.code for finding in inventory.findings] == ["pencil.graph_cycle"]


def test_inventory_fails_before_exceeding_the_declared_node_bound() -> None:
    document = {
        "children": [
            {"id": f"node-{index}", "type": "frame", "context": "classification=decorative"}
            for index in range(3)
        ]
    }

    inventory = inventory_pencil_graph(document, max_nodes=2)

    assert len(inventory.nodes) == 2
    assert inventory.findings[-1].code == "pencil.graph_node_limit"
