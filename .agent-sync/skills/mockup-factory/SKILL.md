---
name: mockup-factory
description: >
  Penflow-local guided UX/UI optimizer for pen.dev mockups. Uses flow-ui-contract,
  semantic-ui-tree, theme.css, .pen, pencil-context-map, expected-ui-tree, and
  detect-drift reports as deterministic anchors before any pen.dev/Codex audit loop.
---
<!-- LiveSpec traceability anchors -->
<!-- @spec(FR-004) -->
<!-- @spec(FR-005) -->
<!-- @spec(FR-006) -->
<!-- @spec(FR-007) -->
<!-- @spec(FR-013) -->
<!-- @spec(FR-014) -->

# Mockup Factory — Penflow Guided Optimizer

Use this skill when a user asks for `/mockup-factory`, mockup generation, mockup audit, or UX/UI optimization of pen.dev `.pen` files inside a Penflow-backed project.

## pen.dev naming

Use `pen.dev` for the product, desktop app, editor, renderer, and MCP integration. On macOS, launch the installed app with `open -a Pen`; do not launch `Pencil`. Keep `pencil` only where it is the current MCP server id or part of an existing Penflow command, field, file, issue id, or receipt schema. The standalone CLI executable is `pen`.

## C51 workflow authority

<!-- @spec(FR-015) -->
**Read** [`../../../docs/verification-workflow.md`](../../../docs/verification-workflow.md) before accepting workflow completion. The existing workflow automatically prepares explicit test IDs before source review, binds actual upstream requirements and plan/workflow applicability, and selects `design` after review/native design or `implementation` after the external runner. Pre-review preparation is non-certifying; reuse unchanged design evidence instead of repeating Mockup Factory. Missing requirements, outcomes, native capabilities or review history block; no extra user-maintained ledger or manual verification step.

- Final design: `penflow run --target <target> --profile design --project <consumer-project-root> --json`, then `penflow validate-report <target>/run-report.json --schema --required-profile design --project <consumer-project-root> --json`.
- Final implementation: the same commands with `implementation` and the actual caller-supplied `--build-manifest <runner-path>` on both calls. Require exact-profile PASS, empty issues, report hash/scope/build concordance and exits 0.
- Standalone commands, audit scores, `PASSED_WITH_WARNINGS`, masks, `--lenient`, missing-file heuristics and historical C47 never substitute for C51. The legacy sequences below remain preparation/diagnostics; C51 alone decides cumulative closure and normalizes native geometry.
- Native lifecycle fields must survive actual Save/C46 before draft/archive variants are trusted. pen.dev 2.14 accepting metadata without persisting it does not create a lifecycle revision; keep the valid active canvas and report the unsupported capability.

## Purpose

Mockup Factory is a tree-aware, guided optimizer for pen.dev mockups. It may orchestrate external design/audit tools from the skill layer, but Penflow Python remains runtime-agnostic and never imports pen.dev MCP, cc-hub, browsers, simulators, Playwright, or UI runtimes.

## Consumer Hygiene Gate

At task start, run `penflow doctor --project <consumer-project-root> --check --json` and retain the read-only receipt. Work only below that exact selected project; Doctor never widens it to the enclosing Git worktree, whose internal `git_root` is used only for scoped Git interrogation and transient metadata coordination. Run the same Doctor check again at task end.

- Optimize the sole regular `ui.pen` in each selected project. A collective Git worktree may contain several independent projects. Keep one active revision per logical screen plus optional draft/archive revisions as top-level `penflow.lifecycle` regions inside that canvas; never create a peer `.pen` for an iteration.
- Penflow-managed technical working data belongs under ignored `.penflow-tmp/`, `.penflow-run/`, and `.mockup-validation/`; producer preflight/postflight clean only catalogued, cleanup-eligible runs after durable outputs finalize. Preserve and report live, unknown, linked, escaped, tracked/staged or referenced paths.
- Doctor never picks among multiple `.pen` files or rewrites Git index/history. On `multiple_pen_files`, manually consolidate intended regions into `ui.pen` and deliberately migrate/remove extras. Manually review and unstage/untrack reported temporary leaks, then rerun Doctor.

## Canonical Inputs

Treat these artifacts as first-class inputs, not optional notes:

- `flow-ui-contract/contract.json` — canonical product behavior source.
- `semantic-ui-tree.json` — before-code semantic anchor exported from flow specs.
- `theme.css` — product theme input for canonical forward pen.dev composition.
- `ui.pen` — the only pen.dev visual contract; lifecycle regions hold active, draft and archive revisions.
- `pencil-context-map.json` — `screen_id` / `semantic_id` / `pencil_node_id` linkage and ambiguity buckets.
- `expected-ui-tree.json` — design-derived structural baseline.
- `drift-report.json` from `penflow detect-drift` — deterministic contract drift report.
- Screenshots and exported PNGs — visual evidence captured by pen.dev MCP or an equivalent renderer when available; never a substitute for the tree anchors.

## Preconditions

Run from the target project root and produce missing anchors before auditing UX:

```bash
penflow validate-flow-contract <target>/flow-ui-contract/contract.json --json
penflow export-flow-docs <target>/flow-ui-contract/contract.json --out <target>/flow-ui-contract --json
penflow export-flow-docs <target>/flow-ui-contract/contract.json --out <target>/flow-ui-contract --check --json
penflow export-semantic-tree <target>/flow-ui-contract/contract.json --out <target>/semantic-ui-tree.json --json
penflow validate-semantic-tree <target>/semantic-ui-tree.json --json
penflow draft-pen-from-tree <target>/semantic-ui-tree.json --out <target>/ui.pen --theme-css <target>/theme.css --json
penflow map-pencil-context <target>/ui.pen <target>/semantic-ui-tree.json --out <target>/pencil-context-map.json --strict-coverage --contract <target>/flow-ui-contract/contract.json --coverage-out <target>/semantic-context-coverage.json --json
penflow validate-pen <target>/ui.pen --json
penflow export-expected <target>/ui.pen --out <target>/expected-ui-tree.json --json
penflow lint-tokens <target>/ui.pen --theme-css <target>/theme.css -o <target>/token-lint-report.json --json
penflow check-consistency <target>/expected-ui-tree.json --group-by role+intent+variant+size-class -o <target>/consistency-report.json --json
penflow audit-visual <target>/expected-ui-tree.json --theme-css <target>/theme.css -o <target>/visual-metrics-report.json --json
penflow detect-drift <target>/flow-ui-contract/contract.json <target>/semantic-ui-tree.json <target>/ui.pen --out <target>/drift-report.json --json
```

Treat `draft-pen-from-tree` output as the starting structure only. Its `draft-report.json` metadata must say `fidelity: "wireframe"`: draft = structure / wireframe, PAS un mockup final ; le hi-fi passe par mockup-factory.

All commands run with the strict default exit policy — no `--lenient` in the canonical chain. If any command fails, stop and report the failing artifact. Do not optimize a mockup whose semantic anchors are invalid. `validate-flow-contract --json` must show `interactive_coverage` with every screen either `covered` or `static`; `uncovered` means `contract.interactive_unbound` and blocks the audit. `validate-semantic-tree` must not emit `semantic.downgrade_suspect`; repeated list-like containers need `repeat`.

<!-- @spec FR-007: C46 at design closure — .specs/features/078-pen-dev-operator-compatibility/spec.md#fr-007 -->
Before any pen.dev MCP call, open `<target>/ui.pen` in pen.dev and confirm it with `get_app_state` (Penflow skill, pen.dev 1.2 operator protocol). Before every mutation batch, copy `ui.pen` to a pre snapshot; mutate through `execute` (the legacy `batch_design` tool no longer exists). After each batch, run the save trigger `penflow pencil-sync <target>/ui.pen --expect-screens <expected-screen-count> --json` before any CLI command that reads the `.pen`, then copy `ui.pen` to a post snapshot. If `pencil-sync` sees fewer screens/nodes on disk than the editor state, return `BLOCKED`; editor-memory mutations are not proof that Penflow can inspect the updated file. Penflow reads `ui.pen` from disk by design; preparation reads after a PASS trigger are noncertifying. C46 is required at design closure, before any PASS: write the `penflow-pencil-persistence-observation` for the final batch's pre/post pair (its post snapshot equals the current `ui.pen`), run `penflow verify-pencil-persistence`, then `penflow validate-report <receipt> --schema --json`.

## Design Convention Gate

Before auditing, generating, or fixing any `.pen`, **Read** [`../../../.conventions/index.md`](../../../.conventions/index.md), then load every matching design domain. Treat the loaded convention files as acceptance criteria for visual validity.

- Always load `design-tokens`, `design-components`, `design-views`, and `design-quality`.
- Load `design-dataviz` for dashboard, metrics, KPI, chart, analytics, and usage screens.
- Load `design-payments` for payment, checkout, billing, subscription, pricing, tip, donation, card form, and order summary screens.
- Load `design-realtime` for live status, websocket, SSE, progress, or streaming screens.

A themed but structurally generic output is a failure. Reject screens that ignore required app shell, payment, dashboard, form, table/list, empty/loading/error, responsive, or accessibility patterns from the conventions.

## Workflow

1. **Load anchors and conventions:** **Read** [`references/workflow.md`](references/workflow.md), **Read** [`references/audit-rubric.md`](references/audit-rubric.md), **Read** [`references/visual-validation.md`](references/visual-validation.md), **Read** [`references/design-taste-advisory.md`](references/design-taste-advisory.md), then apply the Design Convention Gate above.
2. **Build an anchor table:** for every screen, list `screen_id`, `semantic_id`, `pencil_node_id` when available, source flow/screen file, and drift severity.
3. **Seed and freeze checklist:** <!-- @spec FR-009: Skill docs seed checklist via command — .specs/features/055-checklist-from-drift-seeding/spec.md#fr-009 -->
   - Seed: `penflow checklist-from-drift <target>/drift-report.json --out .mockup-validation/<group>/checklist.json --group <group> --json` — every drift issue becomes one open `gate: contract` item.
   - Fail-closed: an invalid report exits 1 and writes nothing.
   - Append items for the other five gates (`tokens`, `consistency`, `accessibility_alignment`, `structural_fidelity`, `balance_readability`) at the skill layer only after seeding.
   - Each item must reference `screen_id` plus `semantic_id` or `pencil_node_id` when available.
4. **Run the gates:** use the rubric gate table — every category maps to a scripted command with an exit-code/report-field pass condition. Critical = any error-severity gate issue or any `blocking: true` item; critical UX/UI issues block PASS.
5. **Apply guided fixes (bounded loop, `iteration <= 3`):** change only audited checklist items that are open gate issues. No broad redesign, no unanchored "polish pass", no invented product behavior. After each `execute` mutation batch (legacy `batch_design`), run `penflow pencil-sync` and block on stale disk inspection before continuing.
6. **Revalidate anchors:** rerun the full Penflow command chain from Preconditions after every fix iteration and recompute all gates — no PASS without a final clean run.
7. **Run Visual Evidence Gate:**
   - Artifacts: open the `.pen` in pen.dev, export PNGs via `execute` `Export([nodeId], "png", dir)` (legacy `export_nodes`), expose each exported screen as a Markdown image with its absolute path before writing `vision-report.json`, run `visual-preview url <absolute-path>` when available for browser annotation, dump the native layout printed by `execute` (legacy `snapshot_layout`) to `layout-snapshot.json`, inspect each PNG (or `execute` `TakeScreenshot`, legacy `get_screenshot`) and answer ONLY the five locked vision categories (`visual_balance`, `rendering_artifacts`, `readability`, `perceived_hierarchy`, `imagery_quality`). Every category evidence sentence must cite the evaluated file name.
   - Coherence (multi-screen sets): export all audited screens at a uniform scale, capture one `contact-sheet.png`, expose it through the same Markdown image + `visual-preview url <absolute-path>` channels, answer ONLY the four coherence categories (`cross_screen_rhythm`, `palette_coherence`, `typography_coherence`, `component_recognition`) in the report's `coherence` section — required when the expected tree has ≥ 2 screens; the numeric anchor stays the 047 `check-consistency` report.
   - Reference fidelity (when required by reviewed applicability or inherited source; missing files never disarm it): generate one side-by-side contact sheet per reference/export pair, answer ONLY `layout_match`, `palette_match`, `component_parity`, and `density_match` in `vision-report.json` `reference_fidelity`, and cite both reference and export file names in every criterion evidence sentence.
   - Preview boundary: `visual-preview` is for annotation and iteration only. Preview URLs are not canonical proof and must not be written into `manifest.json` or `vision-report.json`; the canonical proof remains `penflow validate-visual-evidence` exit 0. If `visual-preview` is unavailable, keep the Markdown image and record browser preview unavailable in operator notes/status.
   - Manifest stamps: write `.mockup-validation/visual-evidence/manifest.json` stamped with `runId` (ISO-8601 timestamp + short slug recommended), the `theme` block from `penflow theme-fingerprint <theme.css> --json`, per-screen PNG `sha256`, and `references_manifest` when references are present, plus `vision-report.json` with `generated_by` and `inputs[]` `{file, sha256}` for every evaluated file (legacy `visual-report.json` is deprecated).
   - Receipts: every evaluated PNG/contact sheet must resolve inside `.mockup-validation/visual-evidence/`; each `vision-report.screens[].png` must match the manifest PNG for the same `screen_id`; symlinks into `references/`, SHA mismatch, missing `generated_by`, missing `inputs`, and category evidence that omits the evaluated file are blocking failures. Receipts are mandatory and prose cannot replace them.
   - Durable export operation (C48, when required by the reviewed policy or authenticated inheritance): pen.dev MCP `execute` `Export` runs only in this operator layer; the receipt operation id stays `export_nodes` (historical name of the native export). After exporting, write a `penflow-export-operator-request` declaring the exact `run_id`, `source` `.pen` path + SHA-256, the C46 `persistence_receipt` path, the pen.dev `document` id/name, the frozen product `contract` path + SHA-256, and per declared surface/screen/state the exact `node_id`, the native export PNG (receipt operation `export_nodes`; `path`/`sha256`/`width`/`height`/`scale`/`format`), and two homologous references (`surface`/`role`/`state`/`region`/`design_intent`). Close it with `penflow verify-export-operation <request.json> --source-pen <ui.pen> --run-id <run> --out .mockup-validation/export-operation-receipt.json --json` (exit 0). Penflow only re-reads local bytes; a screenshot, renamed file, synthetic/non-PNG artifact, a receipt operation other than `export_nodes`, missing/duplicate/mismatched coverage, a copied or non-homologous reference, or a stale/tampered receipt fails closed and is never a self-reported PASS.
   - Gate: `penflow validate-visual-evidence .mockup-validation/visual-evidence --expected expected-ui-tree.json --theme-css <theme.css> --json` — the gate is the exit code, not prose.
   - Reference gate: `penflow validate-reference-fidelity .mockup-validation/visual-evidence --references <target>/references --json` — the gate is the exit code, not prose. It fails copied exports (`reference.evidence_is_reference_copy`) and deterministic-vs-LLM disagreement (`reference.llm_metric_disagreement`).
   - Stale theme: a modified theme.css deterministically invalidates stale packets (`evidence.theme.missing`/`evidence.theme.stale`) and forces a re-run of the bounded loop.
   - Renderer coupling: when `layout-snapshot.json` is available from the renderer, rerun the `accessibility_alignment` gate with `--layout-snapshot` so overlap/overflow uses real pen.dev bboxes, not theoretical flex positions.
8. **Run Design Taste Advisory:** <!-- @spec(FR-004) --> <!-- @spec(FR-005) --> <!-- @spec(FR-006) --> after computing the scripted gates and before final proof, read `<target>/design-read.json` when present, then follow [`references/design-taste-advisory.md`](references/design-taste-advisory.md) to write `<target>/.mockup-validation/design-taste-advisory.md`. This report is advisory only: it never decides PASS/FAIL, never adds checklist items, and never changes gate status.
9. **Decide final state and prove it:** write and schema-validate the detailed `audit-report.json` (`kind: penflow-mockup-audit`, `iterations`, `gates[]` with `{gate, command, exit_code, report_path, result}`, `residual_issues[]`). Validate the detailed audit with `penflow validate-report .mockup-validation/audit-report.json --schema --json`; every executed gate must cite an existing `report_path`, with `pass` => 0, `fail` => non-zero, and `not_run` => null/null. Then execute the C51 design production and revalidation above: this is the single CI-able final check for cumulative design closure. Require every applicable required gate and obligation PASS, with no required warnings; unavailable renderer is BLOCKED. Retain the final `penflow doctor --project <consumer-project-root> --check --json` receipt. Pre-review preparation cannot claim this final state.


## Quality Gate

Detailed audit findings come from the rubric gate table (**Read** [`references/audit-rubric.md`](references/audit-rubric.md)) — six scripted gates: `tokens` (`penflow lint-tokens` exit 0), `consistency` (`penflow check-consistency` exit 0), `accessibility_alignment` (`penflow audit-visual` zero errors, with `--layout-snapshot` when a renderer produced `layout-snapshot.json`), `contract` (`penflow detect-drift` `summary.blocking == 0`), `structural_fidelity` (`penflow compare-tree` threshold 0.98, when an actual tree exists), and `balance_readability` (Visual Evidence Gate: `penflow validate-visual-evidence` exit 0 plus `penflow validate-reference-fidelity` exit 0 when references exist, zero blocking vision/reference criteria — every audited screen has inspected screenshot evidence, exported PNG, manifest entry, and a locked `vision-report.json` anchored by `screen_id`, `semantic_id`, `pencil_node_id`, and reference/export pairs when available; proven by exit code, never by prose).

Critical = any error-severity gate issue or any `blocking: true` item (drift or vision). C51 PASS requires a final clean cumulative run and public revalidation. PASSED_WITH_WARNINGS is a legacy audit status only and never certifies C51. ESCALATED is required when a critical issue remains after the bounded fix loop (max 3 iterations), with the residual issue list attached.
`BLOCKED_VISUAL_NOT_RUN` is required when a pen.dev renderer is expected but unavailable. Explicit user acceptance of structural-only validation may close only the legacy structural audit; it never produces a C51 design or implementation PASS, and missing required renderer evidence still blocks certification.

## Runtime Boundary

Allowed from this skill: pen.dev MCP operations, screenshots, exported PNGs, `visual-preview url` browser annotation for exported PNGs/contact sheets, and independent `cc-hub codex` audit calls when available.

Forbidden in Penflow Python core: importing or depending on pen.dev MCP, cc-hub, `visual-preview`, browser automation, simulators, Playwright, React Native, Xcode, or a UI runtime.

## Output Layout

```text
<target>/
  .mockup-validation/
    audit-report.json
    visual-evidence/
      manifest.json
      vision-report.json
      *-reference-contact-sheet.png
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
