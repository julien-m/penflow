# @spec(FR-001)
# @spec(FR-002)
# @spec(FR-003)
# @spec(FR-004)
# @spec(FR-011)
"""End-to-end flow UI contract demo generation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .codegen import react, rust_dioxus, swiftui
from .compare import STRICT_THRESHOLD, compare_tree_files
from .contracts import code_ir_from_pen, validate_code_ir
from .llm import fix_compare_report, review_compare_report
from .semantic import write_semantic_tree
from .semantic_enrichment import enrich_pen_from_semantic_tree
from .semantic_mapping import write_pencil_context_map
from .tree import expected_tree_from_pen


def build_demo(out_dir: str | Path) -> dict[str, str]:
    # @spec FR-011: Demo fixtures use canonical contract.json and JSON reports — .specs/features/045-penflow-json-only-strict-contract-v2/spec.md#fr-011
    """Write a deterministic full Penflow demo and return generated file paths.

    Args:
        out_dir: Destination directory for the demo project.

    Returns:
        Mapping of relative file path to absolute or relative generated path string.
    """
    out = Path(out_dir)
    specs = out / "flow-ui-contract"
    flows = specs / "flows"
    screens = specs / "screens"
    flows.mkdir(parents=True, exist_ok=True)
    screens.mkdir(parents=True, exist_ok=True)

    (flows / "checkout.md").write_text(_flow_spec(), encoding="utf-8")
    (screens / "checkout.md").write_text(_screen_spec(), encoding="utf-8")
    _write_json(specs / "contract.json", _flow_contract())
    _write_json(out / "ui.visual.pen", _visual_pen())

    semantic_path = out / "semantic-ui-tree.json"
    write_semantic_tree(specs, semantic_path)

    enriched_pen_path = out / "ui.pen"
    enrich_pen_from_semantic_tree(out / "ui.visual.pen", semantic_path, enriched_pen_path)

    context_map_path = out / "pencil-context-map.json"
    write_pencil_context_map(enriched_pen_path, semantic_path, context_map_path)

    expected_path = out / "expected-ui-tree.json"
    expected = expected_tree_from_pen(enriched_pen_path)
    _write_json(expected_path, expected)

    actual = _actual_tree_from_expected(expected)
    _write_json(out / "actual-ui-tree.json", actual)

    ir = code_ir_from_pen(
        enriched_pen_path,
        flow_id="checkout",
        flow_name="Checkout",
        semantic_tree=semantic_path,
        context_map=context_map_path,
        contract=specs / "contract.json",
    )
    errors = [issue for issue in validate_code_ir(ir) if issue.get("severity") == "error"]
    if errors:
        raise ValueError(f"demo code IR failed validation: {errors[0]}")
    _write_json(out / "code-ir.json", ir)

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


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _flow_contract() -> dict[str, Any]:
    return {
        "version": 2,
        "kind": "penflow-flow-contract",
        "contract_id": "checkout-contract",
        "actors": [{"id": "buyer", "name": "Buyer"}],
        "entities": [
            {
                "id": "checkout",
                "fields": [
                    {"id": "order_summary", "type": "string"},
                    {"id": "selected_payment_method", "type": "string"},
                ],
            }
        ],
        "screens": [
            {
                "id": "checkout",
                "flow_id": "checkout",
                "title": "Checkout",
                "surface": "web",
                "viewport": {"width": 390, "height": 844},
                "states": [{"id": "default"}, {"id": "submitting"}, {"id": "error"}],
                "root_node": "checkout.root",
            }
        ],
        "nodes": [
            {
                "id": "checkout.root",
                "screen_id": "checkout",
                "semantic_id": "checkout",
                "role": "screen",
                "children": [
                    "checkout.order_summary",
                    "checkout.selected_payment_method",
                    "checkout.pay_now",
                ],
            },
            {
                "id": "checkout.order_summary",
                "screen_id": "checkout",
                "semantic_id": "checkout.order-summary",
                "role": "text",
                "text": "Order summary",
                "binding": "checkout.order_summary",
            },
            {
                "id": "checkout.selected_payment_method",
                "screen_id": "checkout",
                "semantic_id": "checkout.selected-payment-method",
                "role": "text",
                "text": "Selected payment method",
                "binding": "checkout.selected_payment_method",
            },
            {
                "id": "checkout.pay_now",
                "screen_id": "checkout",
                "semantic_id": "checkout.pay-now",
                "test_id": "checkout-pay-now",
                "role": "button",
                "text": "Pay now",
                "binding": "checkout.selected_payment_method",
                "entity": "checkout",
                "action": "submit_payment",
            },
        ],
        "guards": [{"id": "payment_ready"}],
        "permissions": [
            {
                "id": "buyer_can_pay",
                "actor": "buyer",
                "action": "submit_payment",
                "entity": "checkout",
            }
        ],
        "mutations": [
            {
                "id": "create_payment",
                "method": "POST",
                "endpoint": "/payments",
                "entity": "checkout",
                "request": {},
                "response": {},
                "success_state": "submitting",
                "error_state": "error",
            }
        ],
        "actions": [
            {
                "id": "submit_payment",
                "node": "checkout.pay_now",
                "trigger": "click",
                "guard": "payment_ready",
                "permission": "buyer_can_pay",
                "mutation": "create_payment",
                "success_transition": "payment_success",
                "error_transition": "payment_error",
            }
        ],
        "flows": [{"id": "checkout", "entry_screen": "checkout"}],
        "transitions": [
            {
                "id": "payment_success",
                "flow": "checkout",
                "from_screen": "checkout",
                "to_screen": "checkout",
                "from_state": "default",
                "to_state": "submitting",
                "trigger": "submit_payment",
                "action": "submit_payment",
            },
            {
                "id": "payment_error",
                "flow": "checkout",
                "from_screen": "checkout",
                "to_screen": "checkout",
                "from_state": "default",
                "to_state": "error",
                "trigger": "submit_payment",
                "action": "submit_payment",
            },
        ],
        "needs_review": False,
        "needs_clarification": [],
    }


def _flow_spec() -> str:
    return """---
flow: checkout
title: "Checkout"
status: draft
priority: P1
mockups:
  - checkout
surfaces:
  - web
source:
  - examples/full/project-profile.md
generated_at: "2026-05-20"
---

# Flow Spec: Checkout

- **Project:** penflow-full-demo
- **Flow ID:** FLOW-CHECKOUT
- **Status:** draft
- **Primary Actor:** Returning customer
- **Surfaces:** web
- **Mockups:** checkout
- **Source:** examples/full/project-profile.md

## Input

The full demo proves the Penflow forward chain from canonical `flow-ui-contract/contract.json` to runtime comparison artifacts. These Markdown flow/screen files are documentation-only migration copies; they are not machine inputs for the strict v2 pipeline.

## User Scenarios & Testing

### P1 — Customer pays from checkout

- **As a** returning customer
- **I want** to review my order and submit payment
- **So that** I can complete checkout with confidence

**Priority reason:** This is the shortest flow that exercises data, validation, side effects, code handoff, and runtime comparison.

**Independent test:** Regenerate the demo directory, validate each artifact, and confirm the compare report remains PASS.

```gherkin
Feature: Checkout
  Scenario: Payment succeeds
    Given the customer has an order summary and a selected payment method
    When  the customer activates "Pay now"
    Then  the payment is submitted
    And   the runtime tree matches the Pencil contract

  Scenario: Payment method is missing
    Given the customer has no selected payment method
    When  the customer activates "Pay now"
    Then  the checkout blocks submission with a validation message
```

```mermaid
flowchart TD
    A[Customer opens checkout] --> B{Payment method present?}
    B -- Yes --> C[Customer activates Pay now]
    C --> D[Payment submitted]
    D --> E[Runtime tree compared]
    B -- No --> F[Validation message]
```

## Acceptance Criteria

- **AC-001** — The demo includes canonical `contract.json`; Markdown flow/screen files are documentation-only copies.
- **AC-002** — The semantic tree, enriched Pencil file, expected tree, code IR, actual tree, and reports regenerate deterministically.
- **AC-003** — The generated actual tree validates and the compare report passes.

## Functional Requirements

- **FR-001** — Provide canonical `flow-ui-contract/contract.json`; keep flow/screen Markdown as docs-only migration references. (mappe AC-001)
- **FR-002** — Generate semantic, Pencil, expected, code IR, actual, compare, review, and fix artifacts from local commands. (mappe AC-002)
- **FR-003** — Keep the actual tree external-runtime-shaped while validating through `validate-actual --schema`. (mappe AC-003)

## Key Entities

- **Checkout** — The screen where a customer reviews order details and submits payment.
- **Payment** — The business action triggered by the primary checkout CTA.

## Edge Cases

- Missing payment method prevents submission.
- Runtime implementation omits a semantic node and compare-tree reports the gap.

## Success Criteria

- **SC-001** — The full demo chain exits 0 for validation and comparison commands.
- **SC-002** — Regenerating the chain produces byte-identical artifacts for the same output path.
"""


def _screen_spec() -> str:
    return """---
screen: checkout
mockup: checkout.png
flow: checkout
sourceNodeId: checkoutScreen
sourceFile: ui.pen
generated_at: "2026-05-20"
---

# Écran — Checkout

- **Acteur:** Returning customer
- **Source d'entrée:** Customer opens the checkout route with an order in progress
- **Sortie principale:** Payment is submitted and the runtime contract can be compared

## Données affichées

- Order summary
- Selected payment method

## Actions

| Élément | Type | Effet |
|---------|------|-------|
| Pay now | button | POST /payments → submitting |

## Validations

- A selected payment method is required before submitting payment

## États UI

default · submitting · error

## Erreurs

- Missing payment method → "Choose a payment method before paying."
- Payment failed → "Payment failed. Try again."

## Side effects locaux

- The submitting state is shown while the payment request is in flight
"""


def _visual_pen() -> dict[str, Any]:
    return {
        "version": "2.11",
        "children": [
            {
                "id": "checkoutScreen",
                "type": "frame",
                "name": "checkout",
                "x": 0,
                "y": 0,
                "width": 390,
                "height": 844,
                "layout": "vertical",
                "gap": 16,
                "padding": 24,
                "alignItems": "stretch",
                "fill": "#FFFFFF",
                "context": "role=screen; semantic_id=checkout",
                "children": [
                    {
                        "id": "orderSummary",
                        "type": "text",
                        "name": "Order summary",
                        "content": "Order summary",
                        "textGrowth": "fixed-width",
                        "width": "fill_container",
                        "fontSize": 24,
                        "fontWeight": "600",
                        "fill": "#111827",
                    },
                    {
                        "id": "selectedPaymentMethod",
                        "type": "text",
                        "name": "Selected payment method",
                        "content": "Selected payment method",
                        "textGrowth": "fixed-width",
                        "width": "fill_container",
                        "fontSize": 16,
                        "fontWeight": "400",
                        "fill": "#374151",
                    },
                    {
                        "id": "payNowButton",
                        "type": "frame",
                        "name": "Pay now",
                        "layout": "horizontal",
                        "width": "fill_container",
                        "height": "fit_content(44)",
                        "padding": [12, 16],
                        "gap": 8,
                        "alignItems": "center",
                        "justifyContent": "center",
                        "cornerRadius": 8,
                        "fill": "#0057FF",
                        "children": [
                            {
                                "id": "payNowLabel",
                                "type": "text",
                                "content": "Pay now",
                                "fontSize": 16,
                                "fontWeight": "600",
                                "fill": "#FFFFFF",
                            }
                        ],
                    },
                ],
            }
        ],
    }


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
