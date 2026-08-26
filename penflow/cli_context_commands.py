"""CLI handlers for exhaustive context coverage and generated flow docs."""

from __future__ import annotations

import argparse

from .cli_reporting import PenflowError, _print
from .flow_docs import check_generated_docs, export_flow_docs
from .semantic_context_coverage import write_coverage_report
from .semantic_mapping import write_pencil_context_map
from .semantic_validation import validate_semantic_tree_file


# @spec FR-005: Closed v2 delegated envelope — .specs/features/076-exhaustive-bidirectional-semantic-context/spec.md#fr-005
def cmd_map_pencil_context(args: argparse.Namespace) -> int:
    """Write the forward map and optional exhaustive coverage report."""
    coverage_mode = bool(args.strict_coverage or args.legacy_coverage)
    if coverage_mode and (not args.contract or not args.coverage_out):
        raise PenflowError("coverage mode requires --contract and --coverage-out")
    if coverage_mode and args.strict_anchors:
        raise PenflowError("--strict-anchors cannot be combined with exhaustive coverage")
    passed, issues = validate_semantic_tree_file(args.semantic_tree)
    if not passed:
        _print({"status": "FAIL", "issues": issues}, args.json)
        return 1
    context_map = write_pencil_context_map(
        args.pen,
        args.semantic_tree,
        args.out,
        pen_out=args.pen_out,
        create_placeholders=args.create_placeholders,
    )
    if coverage_mode:
        return _write_delegated_coverage(args, context_map)
    _print(context_map | {"out": args.out, "pen_out": args.pen_out}, args.json)
    return int(bool(args.strict_anchors and context_map["status"] != "PASS"))


def _write_delegated_coverage(args: argparse.Namespace, context_map: dict[str, object]) -> int:
    coverage = write_coverage_report(
        args.contract,
        args.pen,
        args.coverage_out,
        legacy=bool(args.legacy_coverage),
    )
    envelope = {
        "kind": "penflow-context-mapping-result",
        "version": 2,
        "context_map": {
            "path": args.out,
            "status": context_map["status"],
            "forward_only": True,
        },
        "coverage": {
            "path": args.coverage_out,
            "status": coverage["status"],
            "schema_version": coverage["version"],
        },
    }
    _print(envelope, args.json)
    return int(coverage["status"] == "FAIL")


# @spec FR-004: Strict coverage command — .specs/features/076-exhaustive-bidirectional-semantic-context/spec.md#fr-004
def cmd_audit_context_coverage(args: argparse.Namespace) -> int:
    """Write a standalone exhaustive coverage report."""
    report = write_coverage_report(
        args.contract,
        args.pen,
        args.out,
        legacy=bool(args.legacy_coverage),
    )
    _print(report, args.json)
    return int(report["status"] == "FAIL")


# @spec FR-011: Canonical docs CLI — .specs/features/076-exhaustive-bidirectional-semantic-context/spec.md#fr-011
# @spec FR-013: Read-only check mode — .specs/features/076-exhaustive-bidirectional-semantic-context/spec.md#fr-013
def cmd_export_flow_docs(args: argparse.Namespace) -> int:
    """Generate docs or verify their current manifest without writes."""
    if args.check:
        report = check_generated_docs(args.contract, args.out, explicit=True)
        _print(report, args.json)
        return int(report["status"] != "PASS")
    manifest = export_flow_docs(args.contract, args.out)
    _print(manifest, args.json)
    return 0
