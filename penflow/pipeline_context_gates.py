"""Pipeline gates owned by exhaustive semantic context coverage."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .flow_docs import check_generated_docs
from .semantic_context_coverage import write_coverage_report


# @spec FR-009: Exhaustive gate before validate-pen — .specs/features/076-exhaustive-bidirectional-semantic-context/spec.md#fr-009
def gate_semantic_context_coverage(
    contract_path: Path,
    pen_path: Path,
    report_path: Path,
    strict: bool,
) -> tuple[dict[str, Any], int]:
    """Run strict coverage or explicit legacy compatibility."""
    report = write_coverage_report(
        contract_path,
        pen_path,
        report_path,
        legacy=not strict,
    )
    return report, int(strict and report["status"] != "PASS")


# @spec FR-013: Passive generated-doc freshness — .specs/features/076-exhaustive-bidirectional-semantic-context/spec.md#fr-013
def gate_generated_flow_docs(
    contract_path: Path, flow_contract_dir: Path
) -> tuple[dict[str, Any], int]:
    """Treat an absent doc set as passive and an armed stale set as blocking."""
    report = check_generated_docs(contract_path, flow_contract_dir, explicit=False)
    return report, int(report["status"] == "FAIL")
