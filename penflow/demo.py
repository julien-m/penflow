"""End-to-end demo generation."""

from __future__ import annotations

import json
from pathlib import Path

from .codegen import react, rust_dioxus, swiftui
from .compare import compare_trees, report_to_markdown
from .contracts import code_ir_from_contract, pencil_draft_from_screen, screen_contracts_from_flow
from .tree import expected_tree_from_pen


def build_demo(out_dir: str | Path) -> dict[str, str]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    flow = {
        "id": "checkout-flow",
        "surface": "mobile",
        "screens": [
            {
                "id": "checkout",
                "viewport": {"width": 390, "height": 844},
                "actions": [{"id": "pay", "label": "Pay"}],
                "components": [
                    {"id": "checkout.title", "semantic_id": "checkout.title", "role": "text", "text": "Checkout"},
                    {
                        "id": "checkout.pay",
                        "semantic_id": "checkout.pay",
                        "role": "button",
                        "text": "Pay",
                        "intent": "submit_payment",
                    },
                ],
            }
        ],
    }
    screen = screen_contracts_from_flow(flow)[0]
    pen = pencil_draft_from_screen(screen)
    (out / "flow.json").write_text(json.dumps(flow, indent=2) + "\n", encoding="utf-8")
    (out / "screen.json").write_text(json.dumps(screen, indent=2) + "\n", encoding="utf-8")
    pen_path = out / "ui.pen"
    pen_path.write_text(json.dumps(pen, indent=2) + "\n", encoding="utf-8")
    expected = expected_tree_from_pen(pen_path)
    actual = {
        "version": 1,
        "screen_id": "checkout",
        "viewport": {"width": 390, "height": 844},
        "root": expected["screens"][0]["root"],
    }
    (out / "expected-ui-tree.json").write_text(json.dumps(expected, indent=2) + "\n", encoding="utf-8")
    (out / "actual-ui-tree.json").write_text(json.dumps(actual, indent=2) + "\n", encoding="utf-8")
    report = compare_trees(expected, {"version": 1, "screens": [actual]})
    (out / "compare-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (out / "compare-report.md").write_text(report_to_markdown(report), encoding="utf-8")
    ir = code_ir_from_contract(screen, expected)
    (out / "code-ir.json").write_text(json.dumps(ir, indent=2) + "\n", encoding="utf-8")
    (out / "CheckoutView.swift").write_text(swiftui(ir), encoding="utf-8")
    (out / "Checkout.jsx").write_text(react(ir), encoding="utf-8")
    (out / "checkout.rs").write_text(rust_dioxus(ir), encoding="utf-8")
    return {path.name: str(path) for path in out.iterdir() if path.is_file()}

