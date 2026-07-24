# @spec(FR-001)
# @spec(FR-002)
# @spec(FR-003)
# @spec(FR-004)
# @spec(FR-011)
# @spec(FR-013)
"""End-to-end flow UI contract demo generation."""

from __future__ import annotations

import hashlib
import json
from importlib import resources
from pathlib import Path
from typing import Any

from .actual_provenance import (
    RECEIPT_KIND,
    RECEIPT_VERSION,
    STATIC_DEMO_FIXTURE,
    actual_provenance_path,
)
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
    actual_path = out / "actual-ui-tree.json"
    _write_json(actual_path, actual)
    _write_actual_provenance_fixture(actual_path, expected)
    _write_visual_evidence_fixture(out, expected)

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


def _write_actual_provenance_fixture(actual_path: Path, expected: dict[str, Any]) -> None:
    """Write the content-bound provenance receipt for the demo actual tree.

    The demo actual tree is derived from the expected tree, so its receipt is an
    explicitly qualified ``static-demo-fixture``: it declares a frozen capture
    time and a fixture reason, binds to the written actual bytes by SHA-256, and
    can never masquerade as a fresh runtime capture. ``content.path`` stays
    relative so reruns into any directory are byte-identical.
    """
    screen = expected["screens"][0]
    digest = hashlib.sha256(actual_path.read_bytes()).hexdigest()
    _write_json(
        actual_provenance_path(actual_path),
        {
            "kind": RECEIPT_KIND,
            "version": RECEIPT_VERSION,
            "sourceKind": STATIC_DEMO_FIXTURE,
            "producer": {"name": "penflow.demo", "version": "static-demo-fixture"},
            "capturedAt": "2026-07-24T00:00:00Z",
            "target": {"surface": "web", "screen_id": screen["screen_id"]},
            "content": {"path": actual_path.name, "sha256": digest},
            "fixture": {
                "reason": (
                    "Synthetic example data packaged with Penflow as an immutable "
                    "static-demo-fixture; not fresh runtime evidence."
                )
            },
        },
    )


def _write_visual_evidence_fixture(out: Path, expected: dict[str, Any]) -> None:
    """Write the static synthetic visual packet for the canonical demo.

    The PNG is immutable package data captured once from the canonical Pencil
    demo. Fresh demo generation copies those synthetic example bytes, then
    derives every receipt from the copied bytes. The packet is explicitly a
    ``static-demo-fixture``, not a fresh renderer, runtime, or model verdict.
    No browser, simulator, vision model, or existing ``examples/full``
    workspace is invoked at runtime.

    Args:
        out: Destination directory for the generated demo.
        expected: Expected tree generated in the same demo run.
    """
    evidence_dir = out / ".mockup-validation" / "visual-evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    image_bytes = (
        resources.files("penflow").joinpath("demo-assets", "checkout-screen.png").read_bytes()
    )
    image_path = evidence_dir / "checkoutScreen.png"
    image_path.write_bytes(image_bytes)
    image_digest = hashlib.sha256(image_bytes).hexdigest()

    screen = expected["screens"][0]
    root = screen["root"]
    root_bbox = root["bbox"]
    screen_id = screen["screen_id"]
    pencil_node_id = screen["pencil_id"]
    semantic_id = root["semantic_id"]
    run_id = f"static-demo-{image_digest[:24]}"
    region_id = f"{screen_id}.main"
    crop = {
        "x": 0,
        "y": 0,
        "width": int(root_bbox["width"]),
        "height": int(root_bbox["height"]),
        "source_width": int(root_bbox["width"]),
        "source_height": int(root_bbox["height"]),
    }

    def proof(category: str) -> dict[str, Any]:
        return {
            "run_id": run_id,
            "surface": "web",
            "screen_id": screen_id,
            "region_id": region_id,
            "state": "default",
            "assertion": category,
            "measurement": {"expected": "pass", "actual": "pass", "unit": "result"},
            "artifacts": [
                {
                    "role": "actual",
                    "file": image_path.name,
                    "sha256": image_digest,
                    "crop": crop,
                }
            ],
        }

    _write_json(
        evidence_dir / "manifest.json",
        {
            "renderer": "static-demo-fixture",
            "sourceFile": "ui.pen",
            "status": "PASS",
            "validatedAt": "2026-07-24",
            "runId": run_id,
            "screens": [
                {
                    "screen_id": screen_id,
                    "semantic_id": semantic_id,
                    "pencil_node_id": pencil_node_id,
                    "surface": "web",
                    "state": "default",
                    "regions": [{"region_id": region_id, "crop": crop}],
                    "png": image_path.name,
                    "sha256": image_digest,
                    "layout_checked": True,
                    "screenshot_checked": True,
                    "notes": (
                        "Synthetic example data packaged with Penflow as an "
                        "immutable static-demo-fixture; not fresh runtime evidence."
                    ),
                }
            ],
        },
    )
    _write_json(
        evidence_dir / "layout-snapshot.json",
        {
            "screens": [
                {
                    "screen_id": screen_id,
                    "pencil_node_id": pencil_node_id,
                    "width": root_bbox["width"],
                    "height": root_bbox["height"],
                }
            ]
        },
    )
    _write_json(
        evidence_dir / "vision-report.json",
        {
            "version": 1,
            "kind": "penflow-vision-report",
            "status": "PASS",
            "runId": run_id,
            "renderer": "static-demo-fixture",
            "sourceFile": "ui.pen",
            "model": "static-demo-fixture",
            "generated_by": "penflow.demo.static-demo-fixture",
            "inputs": [{"file": image_path.name, "sha256": image_digest}],
            "validatedAt": "2026-07-24",
            "screens": [
                {
                    "screen_id": screen_id,
                    "semantic_id": semantic_id,
                    "pencil_node_id": pencil_node_id,
                    "surface": "web",
                    "region_id": region_id,
                    "state": "default",
                    "png": image_path.name,
                    "criteria": [
                        {
                            "category": "visual_balance",
                            "result": "pass",
                            "evidence": (
                                "checkoutScreen.png uses one left-aligned content "
                                "column with consistent margins and whitespace."
                            ),
                            "blocking": True,
                            "proof": proof("visual_balance"),
                        },
                        {
                            "category": "rendering_artifacts",
                            "result": "pass",
                            "evidence": (
                                "checkoutScreen.png has no clipping, missing glyphs, "
                                "broken images, or stray frame borders."
                            ),
                            "blocking": True,
                            "proof": proof("rendering_artifacts"),
                        },
                        {
                            "category": "readability",
                            "result": "pass",
                            "evidence": (
                                "All three visible labels in checkoutScreen.png are "
                                "legible at one-to-one display scale."
                            ),
                            "blocking": True,
                            "proof": proof("readability"),
                        },
                        {
                            "category": "perceived_hierarchy",
                            "result": "pass",
                            "evidence": (
                                "checkoutScreen.png presents the title, supporting "
                                "payment text, then the bright primary action."
                            ),
                            "blocking": True,
                            "proof": proof("perceived_hierarchy"),
                        },
                        {
                            "category": "imagery_quality",
                            "result": "pass",
                            "evidence": (
                                "checkoutScreen.png contains crisp text and vector-style "
                                "shapes with no low-quality photographic imagery."
                            ),
                            "blocking": True,
                            "proof": proof("imagery_quality"),
                        },
                    ],
                }
            ],
        },
    )


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
                        "context": "variant=heading",
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
                        "context": "variant=body",
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
                                "context": "variant=label",
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
