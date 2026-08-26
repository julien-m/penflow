"""Argument parser registration for context coverage and generated docs."""

from __future__ import annotations

from typing import Any

from .cli_context_commands import (
    cmd_audit_context_coverage,
    cmd_export_flow_docs,
    cmd_map_pencil_context,
)


# @spec FR-004: Exhaustive coverage CLI surface — .specs/features/076-exhaustive-bidirectional-semantic-context/spec.md#fr-004
def register_context_artifact_commands(sub: Any) -> None:
    """Register standalone coverage and generated-doc commands."""
    audit_context = sub.add_parser(
        "audit-context-coverage", help="audit exhaustive bidirectional semantic coverage"
    )
    audit_context.add_argument("--json", action="store_true", help="print machine-readable JSON")
    audit_context.add_argument("pen")
    audit_context.add_argument("--contract", required=True)
    audit_context.add_argument("--out", required=True)
    audit_context.add_argument(
        "--legacy-coverage", action="store_true", help="emit explicit LEGACY_PARTIAL compatibility"
    )
    audit_context.set_defaults(func=cmd_audit_context_coverage)

    flow_docs = sub.add_parser(
        "export-flow-docs", help="generate or verify canonical contract documentation"
    )
    flow_docs.add_argument("--json", action="store_true", help="print machine-readable JSON")
    flow_docs.add_argument("contract")
    flow_docs.add_argument("--out", required=True)
    flow_docs.add_argument("--check", action="store_true", help="verify freshness without writes")
    flow_docs.set_defaults(func=cmd_export_flow_docs)


# @spec FR-005: Exclusive delegated modes — .specs/features/076-exhaustive-bidirectional-semantic-context/spec.md#fr-005
def register_context_mapping(sub: Any) -> None:
    """Register the forward mapper and its exhaustive delegation flags."""
    map_context = sub.add_parser("map-pencil-context", help="map semantic nodes to Pencil nodes")
    map_context.add_argument("--json", action="store_true", help="print machine-readable JSON")
    map_context.add_argument("pen")
    map_context.add_argument("semantic_tree")
    map_context.add_argument("-o", "--out", required=True)
    map_context.add_argument("--pen-out", default=None)
    map_context.add_argument(
        "--strict-anchors",
        action="store_true",
        help="exit 1 when mapping leaves ambiguous, unmapped, or placeholder anchors",
    )
    coverage_mode = map_context.add_mutually_exclusive_group()
    coverage_mode.add_argument(
        "--strict-coverage", action="store_true", help="run exhaustive bidirectional coverage"
    )
    coverage_mode.add_argument(
        "--legacy-coverage", action="store_true", help="emit explicit LEGACY_PARTIAL coverage"
    )
    map_context.add_argument("--contract", default=None, help="canonical v2 flow contract")
    map_context.add_argument("--coverage-out", default=None, help="semantic coverage report path")
    map_context.add_argument(
        "--create-placeholders",
        action="store_true",
        help="record missing semantic nodes as placeholders; report status stays PARTIAL",
    )
    map_context.set_defaults(func=cmd_map_pencil_context)
