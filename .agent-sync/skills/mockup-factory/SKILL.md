---
name: mockup-factory
description: >
  Penflow-local guided UX/UI optimizer for Pencil mockups. Uses flow-ui-contract,
  semantic-ui-tree, theme.css, .pen, pencil-context-map, expected-ui-tree, and
  detect-drift reports as deterministic anchors before any Pencil/Codex audit loop.
---

# Mockup Factory — Penflow Guided Optimizer

Use this skill when a user asks for `/mockup-factory`, mockup generation, mockup audit, or UX/UI optimization of Pencil `.pen` files inside a Penflow-backed project.

## Purpose

Mockup Factory is a tree-aware, guided optimizer for Pencil mockups. It may orchestrate external design/audit tools from the skill layer, but Penflow Python remains runtime-agnostic and never imports Pencil MCP, cc-hub, browsers, simulators, Playwright, or UI runtimes.

## Canonical Inputs

Treat these artifacts as first-class inputs, not optional notes:

- `flow-ui-contract/contract.json` — canonical product behavior source.
- `semantic-ui-tree.json` — before-code semantic anchor exported from flow specs.
- `theme.css` — product theme input for canonical forward Pencil composition.
- `ui.pen` or `ui.enriched.pen` — Pencil visual contract to optimize.
- `pencil-context-map.json` — `screen_id` / `semantic_id` / `pencil_node_id` linkage and ambiguity buckets.
- `expected-ui-tree.json` — design-derived structural baseline.
- `drift-report.json` from `penflow detect-drift` — deterministic contract drift report.
- Screenshots and exported PNGs — visual evidence captured by Pencil MCP or an equivalent renderer when available; never a substitute for the tree anchors.

## Preconditions

Run from the target project root and produce missing anchors before auditing UX:

```bash
penflow validate-flow-contract <target>/flow-ui-contract/contract.json --json
penflow export-semantic-tree <target>/flow-ui-contract/contract.json --out <target>/semantic-ui-tree.json --json
penflow validate-semantic-tree <target>/semantic-ui-tree.json --json
penflow draft-pen-from-tree <target>/semantic-ui-tree.json --out <target>/ui.pen --theme-css <target>/theme.css --json
penflow validate-pen <target>/ui.pen --json
penflow map-pencil-context <target>/ui.pen <target>/semantic-ui-tree.json --out <target>/pencil-context-map.json --json
penflow export-expected <target>/ui.pen --out <target>/expected-ui-tree.json --json
penflow detect-drift <target>/flow-ui-contract/contract.json <target>/semantic-ui-tree.json <target>/ui.pen --out <target>/drift-report.json --json
```

If any command fails, stop and report the failing artifact. Do not optimize a mockup whose semantic anchors are invalid.

## Design Convention Gate

Before auditing, generating, or fixing any `.pen`, **Read** [`../../../.conventions/index.md`](../../../.conventions/index.md), then load every matching design domain. Treat the loaded convention files as acceptance criteria for visual validity.

- Always load `design-tokens`, `design-components`, `design-views`, and `design-quality`.
- Load `design-dataviz` for dashboard, metrics, KPI, chart, analytics, and usage screens.
- Load `design-payments` for payment, checkout, billing, subscription, pricing, tip, donation, card form, and order summary screens.
- Load `design-realtime` for live status, websocket, SSE, progress, or streaming screens.

A themed but structurally generic output is a failure. Reject screens that ignore required app shell, payment, dashboard, form, table/list, empty/loading/error, responsive, or accessibility patterns from the conventions.

## Workflow

1. **Load anchors and conventions:** **Read** [`references/workflow.md`](references/workflow.md), **Read** [`references/audit-rubric.md`](references/audit-rubric.md), **Read** [`references/visual-validation.md`](references/visual-validation.md), then apply the Design Convention Gate above.
2. **Build an anchor table:** for every screen, list `screen_id`, `semantic_id`, `pencil_node_id` when available, source flow/screen file, and drift severity.
3. **Freeze checklist:** write or update only the orchestrator-owned checklist under `.mockup-validation/<group>/checklist.json`; each item must reference `screen_id` plus `semantic_id` or `pencil_node_id` when available.
4. **Audit UX + contract:** use the rubric to identify semantic contract gaps and critical UX/UI issues. A critical issue in either category blocks PASS.
5. **Apply guided fixes:** change only audited checklist items. No broad redesign, no unanchored "polish pass", no invented product behavior.
6. **Revalidate anchors:** rerun the Penflow commands from Preconditions after fixes.
7. **Run Visual Evidence Gate:** open/render the `.pen`, export PNGs via `export_nodes`, dump `snapshot_layout` to `layout-snapshot.json`, inspect `get_screenshot` and answer ONLY the five locked vision categories (`visual_balance`, `rendering_artifacts`, `readability`, `perceived_hierarchy`, `imagery_quality`), write `.mockup-validation/visual-evidence/manifest.json` plus `vision-report.json` (legacy `visual-report.json` is deprecated), then gate on `penflow validate-visual-evidence .mockup-validation/visual-evidence --expected expected-ui-tree.json --json` — the gate is the exit code, not prose.
8. **Decide final state:** PASS requires valid anchors, no blocking drift, no critical UX/UI checklist items, and complete visual evidence when a renderer is available.

## Quality Gate

PASS is allowed only when both gates pass:

- **Contract gate:** flow specs, semantic tree, Pencil context, expected tree, context map, and drift report validate without blocking issues.
- **UX/UI gate:** visual alignment, hierarchy, CTA placement, density, accessibility, responsive behavior, modernity, and polish have no critical findings.
- **Visual Evidence Gate:** every audited screen has inspected screenshot evidence, exported PNG, manifest entry, and a locked `vision-report.json` anchored by `screen_id`, `semantic_id`, and `pencil_node_id` when available — proven by `penflow validate-visual-evidence` exiting 0, never by prose.

WARNING/PASSED_WITH_WARNINGS is allowed only for non-critical, explicitly listed UX or contract items. ESCALATED is required when a blocking contract drift or critical UX issue remains after the bounded fix loop.
`BLOCKED_VISUAL_NOT_RUN` is required when a Pencil renderer is expected but unavailable, unless the user explicitly accepts structural-only validation.

## Runtime Boundary

Allowed from this skill: Pencil MCP operations, screenshots, exported PNGs, and independent `cc-hub codex` audit calls when available.

Forbidden in Penflow Python core: importing or depending on Pencil MCP, cc-hub, browser automation, simulators, Playwright, React Native, Xcode, or a UI runtime.

## Output Layout

```text
<target>/
  .mockup-validation/
    audit-report.json
    visual-evidence/
      manifest.json
      vision-report.json
      layout-snapshot.json
      visual-report.json   # legacy 044 artifact, deprecated
      *.png
    <group>/
      checklist.json
      state.json
      manifest.json
      drift-report.json
      *.png
```

Every output filename must preserve source linkage in `manifest.json` with `sourceFile`, `sourceNodeId`, `screen_id`, `semantic_id`, and `pencil_node_id` when available.
