<!-- LiveSpec traceability anchors -->
<!-- @spec(FR-005) -->
<!-- @spec(FR-007) -->

# Mockup Factory Workflow — Bounded Fix-Re-Audit Loop

## Deterministic Command Chain

The full chain, run in order (strict default exit policy, no `--lenient`):

1. `penflow validate-flow-contract <target>/flow-ui-contract/contract.json --json`
2. `penflow export-semantic-tree` + `penflow validate-semantic-tree` for `semantic-ui-tree.json`
3. `penflow validate-pen` on the source `.pen`
4. `penflow map-pencil-context` → `pencil-context-map.json`
5. `penflow export-expected` → `expected-ui-tree.json`
6. `penflow lint-tokens` → `token-lint-report.json` (`tokens` gate)
7. `penflow check-consistency` → `consistency-report.json` (`consistency` gate)
8. `penflow audit-visual` → `visual-metrics-report.json` (`accessibility_alignment` gate)
9. `penflow detect-drift` → `drift-report.json` (`contract` gate)
10. Visual Evidence Gate from **Read** [`visual-validation.md`](visual-validation.md): export PNGs, dump the layout snapshot, run the per-screen vision pass over the five locked categories, then the cross-mockup coherence pass — export all audited screens at a uniform scale, capture one contact sheet, one vision pass answering only the four coherence categories (required when the expected tree has ≥ 2 screens; the numeric cross-screen anchor remains the feature 047 `check-consistency` report) — write manifest plus `vision-report.json` (with the `coherence` section), stamping the manifest with `runId` and the `theme` block from `penflow theme-fingerprint <theme.css> --json`, then `penflow validate-visual-evidence <dir> --expected expected-ui-tree.json --theme-css <theme.css> --json` (`balance_readability` gate; `evidence.theme.missing`/`evidence.theme.stale` deterministically invalidate packets rendered against other theme bytes) — the gate is the exit code, not prose.
11. When an `actual-ui-tree.json` exists: `penflow compare-tree` (`structural_fidelity` gate); otherwise record it `not_run`.

Exact commands, pass conditions, and report artifacts: **Read** [`audit-rubric.md`](audit-rubric.md).

## Sequence

1. Run steps 1–5 of the chain. Any failure → status `BLOCKED`; stop and report the failing artifact.
2. Run all gates (steps 6–11) and compute open issues using the rubric's Critical definition (any error-severity issue, any `blocking: true` item).
3. Freeze a checklist under `.mockup-validation/<group>/checklist.json` (`kind: penflow-mockup-checklist`), seeded from the drift report: run `penflow checklist-from-drift <target>/drift-report.json --out .mockup-validation/<group>/checklist.json --group <group> --json` so every drift issue becomes one open `gate: contract` item (deterministic, fail-closed — never hand-author the contract-gate items), then append items for the other five gates (`tokens`, `consistency`, `accessibility_alignment`, `structural_fidelity`, `balance_readability`) at the skill layer after seeding; each item carries `screen_id` plus `semantic_id` or `pencil_node_id` when available, `severity`, `blocking`, and `status: open`.
4. Enter the bounded loop below.
5. Write the final `audit-report.json` and validate it: `penflow validate-report .mockup-validation/audit-report.json --schema --json`.

## Bounded Loop — `iteration <= 3`

Each iteration:

1. **Fix only checklist items that are open gate issues** — anchored by `screen_id` / `semantic_id` / `pencil_node_id`. No broad redesign, no unanchored "polish pass", no invented product behavior, no fixes for issues no gate reported.
2. **Rerun the full command chain** (steps 1–11 above) — fixes can invalidate any anchor, so partial reruns are forbidden.
3. **Recompute all gates** and update item statuses (`open` → `fixed`) plus the iteration counter.

Termination:

- **All gates clean → PASS.** No PASS without a final clean run: if anything was fixed in an iteration, the verdict comes from the full rerun afterwards, never from the pre-fix reports.
- **Any critical issue still open after iteration 3 → ESCALATED**, with every residual issue listed in `residual_issues[]`.
- **Renderer expected but unavailable → BLOCKED_VISUAL_NOT_RUN** (unchanged from 044/051) — structural-only validation never substitutes.

Record the loop state machine in `.mockup-validation/<group>/state.json` (working file: `{group, iteration, gates, open_issues}`). The final `audit-report.json` (`kind: penflow-mockup-audit`) must **prove** gate execution: `iterations` plus one `gates[]` entry per gate with `{gate, command, exit_code, report_path, result}`, and `residual_issues[]` for every surviving issue.

## Anchor Rules

- Prefer `semantic_id` for product intent, `pencil_node_id` for visual edits, and `screen_id` for grouping.
- Treat `ambiguous` or `unmapped` entries from `pencil-context-map.json` as review work before implementation.
- Treat `drift-report.json` blocking issues as higher priority than visual polish.
- Cross-screen styling divergence is decided by `check-consistency` (047), never by the coherence contact-sheet pass — coherence answers perception-only questions, and each loop iteration reruns the contact-sheet pass with the rest of the chain.
- Use screenshots as required visual evidence for final PASS when a renderer is available; tree and drift artifacts remain the deterministic source of truth.

## Terminal States

| State | Meaning |
|---|---|
| PASS | Final clean run: every gate passed (structural fidelity may be `not_run` before code exists), zero critical issues. |
| PASSED_WITH_WARNINGS | Final run clean of critical issues; only non-critical, listed residual warnings remain. |
| ESCALATED | A critical gate issue (error severity or `blocking: true`) survives iteration 3; residual issue list attached. |
| BLOCKED | Required Penflow anchor command failed or input artifact is missing. |
| BLOCKED_VISUAL_NOT_RUN | Pencil renderer/export was expected but no screenshot/PNG evidence could be captured. |
