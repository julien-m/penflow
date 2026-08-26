# @spec FR-017: Read-only Routempo proof — .specs/features/076-exhaustive-bidirectional-semantic-context/spec.md#fr-017
"""Confined publication of an external consumer migration diagnosis."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Callable

from .read_only_filesystem import ReadOnlyConsumerError, ReadOnlyConsumerFilesystem
from .semantic_context_coverage import audit_semantic_context


def run_guard_self_test(filesystem: ReadOnlyConsumerFilesystem) -> dict[str, Any]:
    """Prove the guard blocks a deliberate decoy write-and-restore attempt."""
    blocked = False
    try:
        filesystem.block_mutation("write_and_restore", "guard-self-test.txt")
    except ReadOnlyConsumerError:
        blocked = True
    attempts = list(filesystem.attempted_mutations)
    status = "PASS" if blocked and len(attempts) == 1 else "FAIL"
    return {"status": status, "attempts": attempts}


def build_migration_report(filesystem: ReadOnlyConsumerFilesystem) -> dict[str, Any]:
    """Run the live audit exclusively through the injected read-only adapter."""
    before = filesystem.manifest()
    contract = filesystem.read_json("flow-ui-contract/contract.json")
    pencil = filesystem.read_json("ui.pen")
    forward = filesystem.read_json("pencil-context-map.json")
    coverage = audit_semantic_context(
        contract,
        pencil,
        contract_path="flow-ui-contract/contract.json",
        pen_path="ui.pen",
    )
    after = filesystem.manifest()
    findings = _ordered_findings(coverage)
    return {
        "kind": "penflow-routempo-migration-report",
        "version": 1,
        "status": "ACTION_REQUIRED" if coverage["status"] != "PASS" else "PASS",
        "historical_forward_evidence": _forward_evidence(contract, forward),
        "strict_coverage": {"status": coverage["status"], "summary": coverage["summary"]},
        "findings": findings,
        "gap_categories": _gap_categories(findings),
        "consumer_immutability": {
            "before": before,
            "after": after,
            "manifests_equal": before == after,
            "attempted_mutations": list(filesystem.attempted_mutations),
        },
    }


def generate_migration_report(
    consumer_root: str | Path,
    feature_root: str | Path,
    output_path: str | Path,
    *,
    filesystem_factory: Callable[
        [str | Path], ReadOnlyConsumerFilesystem
    ] = ReadOnlyConsumerFilesystem,
) -> dict[str, Any]:
    """Self-test a decoy guard, audit with a fresh guard, then publish outside consumer."""
    consumer, output = _confined_paths(consumer_root, feature_root, output_path)
    with tempfile.TemporaryDirectory(prefix="penflow-read-only-decoy-") as decoy:
        self_test = run_guard_self_test(filesystem_factory(decoy))
    if self_test["status"] != "PASS":
        raise ReadOnlyConsumerError("mutation guard self-test failed")
    report = build_migration_report(filesystem_factory(consumer))
    immutable = report["consumer_immutability"]
    if not immutable["manifests_equal"]:
        raise ReadOnlyConsumerError("consumer manifest changed")
    if immutable["attempted_mutations"]:
        raise ReadOnlyConsumerError("consumer mutation attempt observed")
    report["guard_self_test"] = self_test
    _publish(output, report)
    return report


def _confined_paths(
    consumer_root: str | Path, feature_root: str | Path, output_path: str | Path
) -> tuple[Path, Path]:
    consumer = Path(consumer_root).resolve(strict=True)
    feature = Path(feature_root).resolve(strict=True)
    output = Path(output_path).resolve(strict=False)
    if output.is_relative_to(consumer) or not output.is_relative_to(feature):
        raise ReadOnlyConsumerError("output must be outside consumer and below feature root")
    return consumer, output


def _publish(output: Path, report: dict[str, Any]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    descriptor, temporary = tempfile.mkstemp(prefix=f".{output.name}.", dir=output.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, output)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _ordered_findings(coverage: dict[str, Any]) -> list[dict[str, Any]]:
    findings = [
        item | {"bucket": bucket} for bucket, items in coverage["buckets"].items() for item in items
    ]
    return sorted(
        findings,
        key=lambda item: (
            str(item.get("owner_screen") or ""),
            str(item.get("node_path") or ""),
            str(item.get("semantic_id") or ""),
            str(item["code"]),
        ),
    )


def _forward_evidence(contract: dict[str, Any], forward: dict[str, Any]) -> dict[str, Any]:
    matched = len(forward.get("matched", []))
    ambiguous = len(forward.get("ambiguous", []))
    unmapped = len(forward.get("unmapped", []))
    return {
        "screens": len(contract.get("screens", [])),
        "matched": matched,
        "total": matched + ambiguous + unmapped,
        "ambiguous": ambiguous,
        "unmapped": unmapped,
        "status": forward.get("status"),
        "strictly_sufficient": False,
        "explanation": "forward anchors do not classify every authored Pencil node",
    }


def _gap_categories(findings: list[dict[str, Any]]) -> dict[str, Any]:
    codes = [str(item["code"]) for item in findings]
    behavior = {"behavior_incomplete", "reference_invalid"}
    return {
        "reverse_coverage": sum(code.startswith("pencil.") for code in codes),
        "behavior_graph": sum(item["bucket"] in behavior for item in findings),
        "authored_copy_conflicts": codes.count("pencil.copy_mismatch"),
        "named_repairs": _named_repairs(findings),
        "classification_source": "explicit contract and Pencil context fields only",
    }


def _named_repairs(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selectors = {
        "import_tabs": ("import-payload",),
        "map_controls": ("active-route-map", "active-session-block.map"),
        "selectable_blocks": ("pre-ride-review.blocks",),
        "filters": ("diagnostic-log.filters",),
        "list_structures": ("pre-ride-review.blocks", "ride-summary.blocks"),
        "misplaced_ajuster_context": ("pre-ride-review.adjust",),
    }
    repairs = []
    for category, prefixes in selectors.items():
        locations = [
            _repair_location(item)
            for item in findings
            if item["document"] == "pencil"
            and any(
                str(item.get("semantic_id") or item.get("owner_screen") or "").startswith(prefix)
                for prefix in prefixes
            )
        ]
        repairs.append({"category": category, "locations": locations})
    return repairs


def _repair_location(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "pencil_node_id": item.get("node_id"),
        "pencil_path": item.get("node_path"),
        "owner_screen": item.get("owner_screen"),
        "semantic_id": item.get("semantic_id"),
        "classification_reason": item["message"],
        "required_correction": item["correction"],
    }
