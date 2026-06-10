---
name: mockup-factory
description: >
  Penflow-local guided UX/UI optimizer for Pencil mockups. Uses flow-ui-contract,
  semantic-ui-tree, theme.css, .pen, pencil-context-map, expected-ui-tree, and
  detect-drift reports as deterministic anchors before any Pencil/Codex audit loop.
---
<!-- LiveSpec traceability anchors -->
<!-- @spec(FR-006) -->
<!-- @spec(FR-007) -->

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
penflow lint-tokens <target>/ui.pen --theme-css <target>/theme.css -o <target>/token-lint-report.json --json
penflow check-consistency <target>/expected-ui-tree.json -o <target>/consistency-report.json --json
penflow audit-visual <target>/expected-ui-tree.json --theme-css <target>/theme.css -o <target>/visual-metrics-report.json --json
penflow detect-drift <target>/flow-ui-contract/contract.json <target>/semantic-ui-tree.json <target>/ui.pen --out <target>/drift-report.json --json
```

All commands run with the strict default exit policy — no `--lenient` in the canonical chain. If any command fails, stop and report the failing artifact. Do not optimize a mockup whose semantic anchors are invalid.

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
4. **Run the gates:** use the rubric gate table — every category maps to a scripted command with an exit-code/report-field pass condition. Critical = any error-severity gate issue or any `blocking: true` item; critical UX/UI issues block PASS.
5. **Apply guided fixes (bounded loop, `iteration <= 3`):** change only audited checklist items that are open gate issues. No broad redesign, no unanchored "polish pass", no invented product behavior.
6. **Revalidate anchors:** rerun the full Penflow command chain from Preconditions after every fix iteration and recompute all gates — no PASS without a final clean run.
7. **Run Visual Evidence Gate:** open/render the `.pen`, export PNGs via `export_nodes`, dump `snapshot_layout` to `layout-snapshot.json`, inspect `get_screenshot` and answer ONLY the five locked vision categories (`visual_balance`, `rendering_artifacts`, `readability`, `perceived_hierarchy`, `imagery_quality`); for multi-screen sets, also run the cross-mockup coherence pass — export all audited screens at a uniform scale, capture one contact sheet, answer ONLY the four coherence categories (`cross_screen_rhythm`, `palette_coherence`, `typography_coherence`, `component_recognition`) in the report's `coherence` section (required when the expected tree has ≥ 2 screens; the numeric anchor stays the 047 `check-consistency` report); write `.mockup-validation/visual-evidence/manifest.json` plus `vision-report.json` (legacy `visual-report.json` is deprecated), then gate on `penflow validate-visual-evidence .mockup-validation/visual-evidence --expected expected-ui-tree.json --json` — the gate is the exit code, not prose.
8. **Decide final state and prove it:** PASS requires valid anchors, every rubric gate clean on the final run, and complete visual evidence when a renderer is available. Write `audit-report.json` (`kind: penflow-mockup-audit`) recording `iterations`, per-gate `{gate, command, exit_code, report_path, result}`, and `residual_issues[]`, then validate it with `penflow validate-report .mockup-validation/audit-report.json --schema --json` — the single CI-able final check.

## Quality Gate

PASS/FAIL comes only from the rubric gate table (**Read** [`references/audit-rubric.md`](references/audit-rubric.md)) — six scripted gates: `tokens` (`penflow lint-tokens` exit 0), `consistency` (`penflow check-consistency` exit 0), `accessibility_alignment` (`penflow audit-visual` zero errors), `contract` (`penflow detect-drift` `summary.blocking == 0`), `structural_fidelity` (`penflow compare-tree` threshold 0.98, when an actual tree exists), and `balance_readability` (Visual Evidence Gate: `penflow validate-visual-evidence` exit 0 plus zero blocking vision criteria — every audited screen has inspected screenshot evidence, exported PNG, manifest entry, and a locked `vision-report.json` anchored by `screen_id`, `semantic_id`, and `pencil_node_id` when available; proven by exit code, never by prose).

Critical = any error-severity gate issue or any `blocking: true` item (drift or vision). PASS requires a final clean run of all gates and a schema-valid `audit-report.json`. PASSED_WITH_WARNINGS is allowed only for non-critical, explicitly listed residual warnings. ESCALATED is required when a critical issue remains after the bounded fix loop (max 3 iterations), with the residual issue list attached.
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
