# @spec(FR-001)
# @spec(FR-002)
# @spec(FR-003)
# @spec(FR-004)
# @spec(FR-011)
# @spec(FR-013)
"""End-to-end flow UI contract demo generation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .demo_data import flow_contract as _flow_contract, visual_pen as _visual_pen
from .demo_evidence import (
    write_actual_provenance_fixture as _write_actual_provenance_fixture,
    write_visual_evidence_fixture as _write_visual_evidence_fixture,
)
from .codegen import react, rust_dioxus, swiftui
from .compare import STRICT_THRESHOLD, compare_tree_files
from .contracts import code_ir_from_pen, validate_code_ir
from .flow_docs import export_flow_docs
from .json_filesystem import write_json_atomically
from .llm import fix_compare_report, review_compare_report
from .semantic import write_semantic_tree
from .semantic_enrichment import enrich_pen_from_semantic_tree
from .semantic_mapping import write_pencil_context_map
from .semantic_context_coverage import write_coverage_report
from .tree import expected_tree_from_pen


# @spec FR-005: Canonical producer migration — .specs/features/074-penflow-doctor-consumer-project-hygiene/spec.md#fr-005
def build_demo(out_dir: str | Path) -> dict[str, str]:
    # @spec FR-011: Demo fixtures use canonical contract.json and JSON reports — .specs/features/045-penflow-json-only-strict-contract-v2/spec.md#fr-011
    """Write a deterministic full Penflow demo and return generated file paths.

    Args:
        out_dir: Destination directory for the demo project.

    Returns:
        Mapping of relative file path to absolute or relative generated path string.
    """
    out = Path(out_dir)
    canonical_pen_path = out / "ui.pen"
    specs = out / "flow-ui-contract"
    specs.mkdir(parents=True, exist_ok=True)
    _write_json(specs / "contract.json", _flow_contract())
    export_flow_docs(specs / "contract.json", specs)
    _write_json(canonical_pen_path, _visual_pen())

    semantic_path = out / "semantic-ui-tree.json"
    write_semantic_tree(specs, semantic_path)

    enrich_pen_from_semantic_tree(canonical_pen_path, semantic_path, canonical_pen_path)

    context_map_path = out / "pencil-context-map.json"
    write_pencil_context_map(canonical_pen_path, semantic_path, context_map_path)
    write_coverage_report(
        specs / "contract.json",
        canonical_pen_path,
        out / "semantic-context-coverage.json",
    )

    expected_path = out / "expected-ui-tree.json"
    expected = expected_tree_from_pen(canonical_pen_path)
    _write_json(expected_path, expected)

    actual = _actual_tree_from_expected(expected)
    actual_path = out / "actual-ui-tree.json"
    _write_json(actual_path, actual)
    _write_actual_provenance_fixture(actual_path, expected)
    _write_visual_evidence_fixture(out, expected)

    ir = _write_code_ir(out, canonical_pen_path, semantic_path, context_map_path, specs)

    # Strict default threshold (feature 049) so the fixture matches the CLI.
    compare_tree_files(
        expected_path,
        out / "actual-ui-tree.json",
        json_out=out / "compare-report.json",
        threshold=STRICT_THRESHOLD,
    )
    _write_json(out / "review-report.json", review_compare_report(out / "compare-report.json"))
    _write_json(out / "fix-report.json", fix_compare_report(out / "compare-report.json"))

    _write_codegen_files(out, ir)
    return {
        path.relative_to(out).as_posix(): str(path)
        for path in sorted(out.rglob("*"))
        if path.is_file()
    }


def _write_code_ir(
    out: Path, pen: Path, semantic: Path, context_map: Path, specs: Path
) -> dict[str, Any]:
    """Validate generated IR before emitting source-code scaffolds."""
    ir = code_ir_from_pen(
        pen,
        flow_id="checkout",
        flow_name="Checkout",
        semantic_tree=semantic,
        context_map=context_map,
        contract=specs / "contract.json",
    )
    errors = [issue for issue in validate_code_ir(ir) if issue.get("severity") == "error"]
    if errors:
        raise ValueError(f"demo code IR failed validation: {errors[0]}")
    _write_json(out / "code-ir.json", ir)

    return ir


def _write_json(path: Path, data: dict[str, Any]) -> None:
    write_json_atomically(path, data)


def _actual_tree_from_expected(expected: dict[str, Any]) -> dict[str, Any]:
    screen = expected["screens"][0]
    return {
        "version": 1,
        "screen_id": screen["screen_id"],
        "viewport": {
            "width": screen["viewport"]["width"],
            "height": screen["viewport"]["height"],
        },
        "root": screen["root"],
    }


def _write_codegen_files(out: Path, ir: dict[str, Any]) -> None:
    child_ids = {
        str(child.get("id"))
        for component in ir.get("components", [])
        if component.get("role") != "screen"
        for child in component.get("children", []) or []
        if isinstance(child, dict) and child.get("id")
    }
    legacy_ir = {
        "screen": ir["flow"]["id"],
        "components": [
            {
                "id": component.get("semantic_id") or component.get("id"),
                "role": component.get("role"),
                "text": component.get("text"),
                "intent": component.get("intent"),
                "test_id": component.get("test_id"),
                "children": [
                    {
                        "id": child.get("semantic_id") or child.get("id"),
                        "role": child.get("role"),
                        "text": child.get("text"),
                    }
                    for child in component.get("children", []) or []
                    if isinstance(child, dict) and child.get("role") == "text"
                ],
            }
            for component in ir.get("components", [])
            if component.get("role") in {"text", "button"}
            and not str(component.get("id", "")).endswith(".label")
            and str(component.get("id", "")) not in child_ids
        ],
    }
    (out / "Checkout.jsx").write_text(react(legacy_ir), encoding="utf-8")
    (out / "CheckoutView.swift").write_text(swiftui(legacy_ir), encoding="utf-8")
    (out / "checkout.rs").write_text(rust_dioxus(legacy_ir), encoding="utf-8")
