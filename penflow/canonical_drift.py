# @spec FR-005 AC-008 AC-017: Source-bound preparation checks do not require future C51 closure.
"""Canonical C20 projection and Pencil coverage prerequisites for drift reporting."""

from copy import deepcopy
from pathlib import Path
from typing import Any

from .flow_contract import load_flow_contract_v2
from .semantic_contract import semantic_tree_from_contract
from .semantic_context_coverage import audit_semantic_context
from .verification_json import canonical_bytes


def canonical_source_issues(
    contract_path: Path, tree: dict[str, Any], pen: dict[str, Any], *, pen_path: str
) -> list[dict[str, Any]]:
    """Validate the exact stored projection and exhaustive C20-to-Pencil coverage.

    Args:
        contract_path: Selected canonical source; invalid input never falls back to Markdown.
        tree: Stored semantic projection to compare, including every provenance field.
        pen: Parsed Pencil document; no rendering or runtime observation is performed.
        pen_path: Pencil input path included in coverage diagnostics.

    Returns:
        Blocking drift issues, or an empty list when both prerequisites pass.
    """
    try:
        contract = load_flow_contract_v2(contract_path)
        if not isinstance(contract, dict):
            return [_issue("drift.contract_invalid", str(contract_path), "C20 must be an object")]
        expected = semantic_tree_from_contract(contract, source_path=str(contract_path))
    except (OSError, UnicodeError, ValueError) as error:
        return [_issue("drift.contract_invalid", str(contract_path), str(error))]
    try:
        matches = canonical_bytes(_same_source_provenance(tree, contract_path)) == canonical_bytes(
            _same_source_provenance(expected, contract_path)
        )
    except (ValueError, TypeError, RecursionError) as error:
        return [_issue("drift.semantic_tree_invalid", "$", str(error))]
    if not matches:
        return [
            _issue(
                "drift.semantic_projection_changed",
                "$",
                "semantic tree differs from C20 projection, including provenance; regenerate with export-semantic-tree using the selected contract path",
            )
        ]
    if not isinstance(pen, dict):
        return [_issue("drift.contract_context_mismatch", pen_path, "Pencil must be an object")]
    coverage = audit_semantic_context(
        contract, pen, contract_path=str(contract_path), pen_path=pen_path
    )
    return [
        _issue(
            "drift.contract_context_mismatch",
            finding.get("node_path") or finding.get("path") or pen_path,
            f"{finding['code']}: {finding['message']}",
        )
        for bucket in coverage["buckets"].values()
        for finding in bucket
        if finding.get("blocking")
    ]


def _same_source_provenance(tree: Any, contract_path: Path) -> Any:
    """Normalize only recognized contract-path markers resolving to the selected file."""
    result = deepcopy(tree)
    if not isinstance(result, dict):
        return result
    target = contract_path.resolve(strict=True)
    markers = [result.get("source")]
    pending: list[Any] = [result]
    while pending:
        item = pending.pop()
        if isinstance(item, dict):
            if "source_map" in item:
                markers.append(item["source_map"])
            pending.extend(item.values())
        elif isinstance(item, list):
            pending.extend(item)
    for marker in markers:
        if isinstance(marker, dict) and isinstance(marker.get("contract"), str):
            try:
                if Path(marker["contract"]).resolve(strict=True) == target:
                    marker["contract"] = str(target)
            except (OSError, ValueError):
                pass  # An unresolved source remains different; never erase provenance.
    return result


def _issue(code: str, path: str, message: str) -> dict[str, Any]:
    return {"severity": "error", "code": code, "path": path, "message": message, "blocking": True}
