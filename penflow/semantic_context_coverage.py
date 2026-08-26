# @spec FR-003: Bidirectional reconciliation — .specs/features/076-exhaustive-bidirectional-semantic-context/spec.md#fr-003
# @spec FR-008: Strict coverage report — .specs/features/076-exhaustive-bidirectional-semantic-context/spec.md#fr-008
"""Deterministic bidirectional semantic-context coverage."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .context import Context, validate_context
from .flow_contract import contract_registries, validate_flow_contract_v2
from .json_filesystem import write_json_atomically
from .pencil_graph import PencilGraphNode, inventory_pencil_graph
from .semantic_context_report import (
    CoverageInputError,
    append_finding as _append,
    coverage_status as _status,
    digest as _digest,
    digest_json as _digest_json,
    empty_summary as _empty_summary,
    finish_summary as _finish_summary,
    node_finding as _node_finding,
    parse_input as _parse_input,
    read_input as _read_input,
    sort_buckets as _sort_buckets,
)

GENERATOR = "penflow.semantic-context-coverage/1"
BUCKETS = (
    "contract_missing_in_pencil",
    "pencil_missing_in_contract",
    "pencil_unclassified",
    "decorative_exclusions",
    "valid_inheritance",
    "behavior_incomplete",
    "reference_invalid",
)
BEHAVIOR_CODES = {"list.model_incomplete", "screen.static_interactive"}


def audit_semantic_context(
    contract: dict[str, Any],
    pencil: dict[str, Any],
    *,
    contract_path: str,
    pen_path: str,
    legacy: bool = False,
    input_digests: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Reconcile canonical contract nodes against every authored Pencil node."""
    graph = inventory_pencil_graph(pencil)
    registries = contract_registries(contract)
    buckets: dict[str, list[dict[str, Any]]] = {name: [] for name in BUCKETS}
    summary = _empty_summary(len(registries["nodes"]), graph.out_of_scope_metadata)
    semantic_nodes: dict[str, list[PencilGraphNode]] = {}
    graph_by_id = {node.node_id: node for node in graph.nodes}
    for node in graph.nodes:
        _classify_node(node, graph_by_id, registries, semantic_nodes, buckets, summary)
    _reconcile_contract(contract, semantic_nodes, buckets, summary)
    _contract_findings(contract, buckets)
    for finding in graph.findings:
        _append(
            buckets,
            "reference_invalid",
            finding.code,
            "pencil",
            node_id=finding.node_id,
            node_path=finding.node_path,
            message=finding.message,
            correction="repair the authored Pencil graph",
        )
    _finish_summary(summary, buckets)
    digests = input_digests or {
        "contract": _digest_json(contract),
        "pencil": _digest_json(pencil),
    }
    report: dict[str, Any] = {
        "kind": "penflow-semantic-context-coverage",
        "version": 1,
        "status": _status(summary["blocking"], legacy),
        "generator": GENERATOR,
        "inputs": {
            "contract": {"path": contract_path, "sha256": digests["contract"]},
            "pencil": {"path": pen_path, "sha256": digests["pencil"]},
        },
        "summary": summary,
        "buckets": buckets,
    }
    _sort_buckets(report["buckets"])
    return report


def write_coverage_report(
    contract_path: str | Path,
    pen_path: str | Path,
    out_path: str | Path,
    *,
    legacy: bool = False,
) -> dict[str, Any]:
    """Hash, parse, re-hash, and atomically publish one stable report."""
    contract_file, pencil_file = Path(contract_path), Path(pen_path)
    contract_bytes = _read_input(contract_file)
    pencil_bytes = _read_input(pencil_file)
    contract, pencil = (
        _parse_input(contract_bytes, "contract"),
        _parse_input(pencil_bytes, "pencil"),
    )
    contract_issues = validate_flow_contract_v2(contract)
    if any(issue["code"].startswith("contract.schema") for issue in contract_issues):
        raise CoverageInputError("input.contract_schema_invalid")
    digests = {"contract": _digest(contract_bytes), "pencil": _digest(pencil_bytes)}
    report = audit_semantic_context(
        contract,
        pencil,
        contract_path=str(contract_file),
        pen_path=str(pencil_file),
        legacy=legacy,
        input_digests=digests,
    )
    if contract_bytes != _read_input(contract_file) or pencil_bytes != _read_input(pencil_file):
        raise CoverageInputError("input.concurrent_modification")
    write_json_atomically(Path(out_path), report)
    return report


def _classify_node(
    node: PencilGraphNode,
    graph_by_id: dict[str, PencilGraphNode],
    registries: dict[str, Any],
    semantic_nodes: dict[str, list[PencilGraphNode]],
    buckets: dict[str, list[dict[str, Any]]],
    summary: dict[str, int],
) -> None:
    context = Context.from_raw(node.node.get("context"))
    classification = context.classification
    if classification in {"semantic", "inherited", "decorative"}:
        summary[classification] += 1
    else:
        summary["unclassified"] += 1
    issues = validate_context(
        node.node_id, str(node.node.get("type", "")), context, require_classification=True
    )
    if issues:
        if any(issue.code == "pencil.classification_conflict" for issue in issues):
            summary["classification_conflict"] += 1
        for issue in issues:
            bucket = (
                "pencil_unclassified"
                if issue.code == "pencil.node_unclassified"
                else "reference_invalid"
            )
            _node_finding(buckets, bucket, issue.code, node, context, issue.message)
        return
    if classification == "semantic" and context.semantic_id:
        semantic_nodes.setdefault(context.semantic_id, []).append(node)
        _semantic_checks(node, context, registries, buckets)
    elif classification == "inherited":
        _owner_check(node, context.inherits_from, graph_by_id, buckets, "valid_inheritance")
    elif classification == "decorative":
        _owner_check(node, context.decorative_owner, graph_by_id, buckets, "decorative_exclusions")


def _semantic_checks(
    node: PencilGraphNode,
    context: Context,
    registries: dict[str, Any],
    buckets: dict[str, list[dict[str, Any]]],
) -> None:
    contract_node = registries["semantic_ids"].get(context.semantic_id)
    if contract_node is None:
        _node_finding(
            buckets,
            "pencil_missing_in_contract",
            "pencil.semantic_unknown",
            node,
            context,
            "semantic id is absent from contract",
        )
        return
    if context.test_id != contract_node.get("test_id"):
        _node_finding(
            buckets,
            "reference_invalid",
            "test_id.mismatch",
            node,
            context,
            "Pencil and contract test ids differ",
        )
    if node.screen_id != contract_node.get("screen_id"):
        _node_finding(
            buckets,
            "reference_invalid",
            "pencil.screen_mismatch",
            node,
            context,
            "semantic anchor belongs to the wrong screen",
        )
    authored = node.node.get("content")
    expected = contract_node.get("text")
    if isinstance(authored, str) and isinstance(expected, str) and authored != expected:
        _node_finding(
            buckets,
            "reference_invalid",
            "pencil.copy_mismatch",
            node,
            context,
            f"authored copy differs: {authored!r} != {expected!r}",
        )


def _owner_check(
    node: PencilGraphNode,
    owner: str | None,
    graph_by_id: dict[str, PencilGraphNode],
    buckets: dict[str, list[dict[str, Any]]],
    valid_bucket: str,
) -> None:
    current = graph_by_id.get(node.parent_id or "")
    while current is not None:
        context = Context.from_raw(current.node.get("context"))
        if context.classification == "semantic" and context.semantic_id == owner:
            _node_finding(
                buckets,
                valid_bucket,
                f"pencil.{valid_bucket[:-1]}_valid",
                node,
                context,
                "valid owner",
                blocking=False,
            )
            return
        current = graph_by_id.get(current.parent_id or "")
    context = Context.from_raw(node.node.get("context"))
    _node_finding(
        buckets,
        "reference_invalid",
        "pencil.owner_not_ancestor",
        node,
        context,
        "declared owner is not an anchored ancestor",
    )


def _reconcile_contract(
    contract: dict[str, Any],
    semantic_nodes: dict[str, list[PencilGraphNode]],
    buckets: dict[str, list[dict[str, Any]]],
    summary: dict[str, int],
) -> None:
    for index, contract_node in enumerate(contract.get("nodes", [])):
        semantic_id = str(contract_node.get("semantic_id", ""))
        anchors = semantic_nodes.get(semantic_id, [])
        if len(anchors) == 1:
            summary["anchored_unique"] += 1
            summary["semantic_resolved"] += 1
        elif not anchors:
            summary["contract_anchor_missing"] += 1
            _append(
                buckets,
                "contract_missing_in_pencil",
                "contract.anchor_missing",
                "contract",
                semantic_id=semantic_id,
                contract_path=f"$.nodes[{index}]",
                message="contract node has no Pencil anchor",
                correction="classify exactly one Pencil node with this semantic id",
            )
        else:
            summary["contract_anchor_duplicate"] += 1
            for anchor in anchors[1:]:
                _node_finding(
                    buckets,
                    "reference_invalid",
                    "pencil.semantic_duplicate",
                    anchor,
                    Context.from_raw(anchor.node.get("context")),
                    "semantic id has multiple functional anchors",
                )


def _contract_findings(contract: dict[str, Any], buckets: dict[str, list[dict[str, Any]]]) -> None:
    for issue in validate_flow_contract_v2(contract):
        if issue["code"].startswith("contract.schema"):
            continue
        bucket = "behavior_incomplete" if issue["code"] in BEHAVIOR_CODES else "reference_invalid"
        _append(
            buckets,
            bucket,
            issue["code"],
            "contract",
            contract_path=issue["path"],
            message=issue["message"],
            correction="repair the canonical contract reference or behavior slot",
        )
