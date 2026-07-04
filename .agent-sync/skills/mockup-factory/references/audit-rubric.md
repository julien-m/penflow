<!-- LiveSpec traceability anchors -->
<!-- @spec(FR-004) -->
<!-- @spec(FR-007) -->

# Prescriptive Audit Rubric — Gate Table

PASS/FAIL comes **only** from the scripted gates below. Prose judgment never decides a verdict; it can only annotate. Each checklist item must include severity, blocking, evidence, and the best available anchor: `screen_id`, `semantic_id`, and `pencil_node_id`.

## Gate Table

Run every gate from the target project root with the strict default exit policy — **no `--lenient` in the canonical chain**.

| Gate | Category | Command | Pass condition | Report artifact |
|---|---|---|---|---|
| `tokens` | Design tokens (palette, spacing, radius, typography) | `penflow lint-tokens <target>/ui.pen --theme-css <target>/theme.css -o <target>/token-lint-report.json --json` | exit 0 | `token-lint-report.json` |
| `consistency` | Cross-screen component consistency | `penflow check-consistency <target>/expected-ui-tree.json --group-by role+intent+variant+size-class -o <target>/consistency-report.json --json` | exit 0 | `consistency-report.json` |
| `accessibility_alignment` | Accessibility + Visual alignment (contrast, touch targets, overlap/overflow, text fit) | `penflow audit-visual <target>/expected-ui-tree.json --theme-css <target>/theme.css --layout-snapshot <target>/.mockup-validation/visual-evidence/layout-snapshot.json -o <target>/visual-metrics-report.json --json` when a renderer produced `layout-snapshot.json`; otherwise omit `--layout-snapshot` | zero error-severity issues — exit 0 under the strict default (`info` never blocks) | `visual-metrics-report.json` |
| `contract` | Semantic contract drift | `penflow detect-drift <target>/flow-ui-contract/contract.json <target>/semantic-ui-tree.json <target>/ui.pen --out <target>/drift-report.json --json` | `summary.blocking == 0` and exit 0 | `drift-report.json` |
| `structural_fidelity` | Structural fidelity vs runtime | `penflow compare-tree <target>/expected-ui-tree.json <target>/actual-ui-tree.json --out <target>/compare-report.json --json` | score ≥ 0.98 (strict default threshold) — exit 0 | `compare-report.json` |
| `balance_readability` | Balance / readability (vision-only) | `penflow validate-visual-evidence <target>/.mockup-validation/visual-evidence --expected <target>/expected-ui-tree.json --json`; when references exist, also `penflow validate-reference-fidelity <target>/.mockup-validation/visual-evidence --references <target>/references --json` | both exits 0, zero `blocking: true` criteria with result `fail` in `vision-report.json`, and reference-fidelity status PASS when references exist | `.mockup-validation/visual-evidence/vision-report.json`, optional reference-fidelity report |

Gate notes:

- `structural_fidelity` applies only once an `actual-ui-tree.json` exists (post-implementation). In a BEFORE-CODE mockup audit, record it as `not_run` with `exit_code: null`; it never blocks a design-time PASS.
- `balance_readability` requires a Pencil renderer (Visual Evidence Gate, **Read** [`visual-validation.md`](visual-validation.md)). Without a renderer the gate is `not_run` and the audit status is `BLOCKED_VISUAL_NOT_RUN` — never PASS.
- `accessibility_alignment` requires `--layout-snapshot` whenever the renderer is available; otherwise `audit-visual` skips flex-parent overlap/overflow from theoretical positions and still checks contrast, touch targets, and text fit on the tree.
- Every other gate marked `not_run` blocks PASS: a gate either ran clean or the audit is not done.

## Critical — Single Definition

An issue is **critical** if and only if:

- it has **error severity** in any gate report; or
- it carries **`blocking: true`** (drift issues per C24, vision criteria per C26).

Nothing else is critical. Any critical issue blocks PASS. Warning-severity, non-blocking issues may remain only as documented residual warnings under `PASSED_WITH_WARNINGS`. A critical issue surviving the bounded fix loop forces `ESCALATED` — there are no critical UX/UI issues left in a PASS.

## Blocking Contract Criteria

These anchor failures block the audit before any gate runs (status `BLOCKED`):

- Missing or invalid `flow-ui-contract` source for a screen.
- Invalid `semantic-ui-tree.json`.
- Invalid `.pen` context or duplicate `semantic_id`.
- Missing expected UI tree for an optimized screen.
- Unresolved `[NEEDS CLARIFICATION]` markers.

## Advisory UX Notes — Never Decide PASS/FAIL

The following guidance informs **what to fix and how**, but it cannot pass or fail a gate on its own. Findings here become checklist items only when they map to a gate issue or a `blocking: true` vision criterion:

| Category | Guidance (advisory) |
|---|---|
| Semantic contract | Every visible primary action, state, validation, and data binding maps to the semantic tree — measured by the `contract` gate. |
| Visual alignment | Shared axes are frame-based and consistently aligned — measured by the `accessibility_alignment` gate (overlap/overflow) and the `consistency` gate. |
| Hierarchy | Titles, sections, controls, and content density reveal priority — vision evidence via `perceived_hierarchy`. |
| CTA placement | Primary actions are discoverable, singular per decision zone, and close to the content they affect — vision evidence via `perceived_hierarchy` / `visual_balance`. |
| Density | Layout is scannable; empty/loading/error states represented when relevant — vision evidence via `visual_balance`. |
| Accessibility | Contrast, target size, and text fit are computed by the `accessibility_alignment` gate; labels and non-color cues remain review guidance. |
| Responsive behavior | Desktop/tablet/mobile frame assumptions are explicit when targeted — record gaps as warnings. |
| Modernity | Components follow current SaaS/app conventions without ornamental one-off styling. |
| Polish | Spacing, radius, typography, icons, and borders follow project conventions — measured by the `tokens` gate. |
| Design taste | Anti-default/AI-tell/landing pre-flight subset: **Read** [`design-taste-advisory.md`](design-taste-advisory.md). Reported in `.mockup-validation/design-taste-advisory.md` — advisory report only, never a gate. |

## Visual Evidence Criteria

Final PASS must be backed by **Read** [`visual-validation.md`](visual-validation.md). The reviewer must inspect the actual Pencil-rendered screen and record:

- screenshot/PNG path for each screen;
- layout snapshot dump (`layout-snapshot.json`) for the deterministic bbox cross-check;
- a `vision-report.json` answering only the five locked vision categories (`visual_balance`, `rendering_artifacts`, `readability`, `perceived_hierarchy`, `imagery_quality`) with one evidence sentence each;
- warnings for sparse density, missing responsive variants, or non-critical polish gaps.

Deterministic facts (contrast, target sizes, overlap/overflow, text fit) come from `penflow audit-visual`, not from the vision pass. The visual evidence verdict is the `penflow validate-visual-evidence` exit code; if no screenshot/export exists, the audit is incomplete even when tree validation passes.

## Final Proof

The audit verdict is recorded in `audit-report.json` (`kind: penflow-mockup-audit`) with one `gates[]` entry per gate — `{gate, command, exit_code, report_path, result}` — plus `iterations` and `residual_issues[]`. The single CI-able final check is:

```bash
penflow validate-report <target>/.mockup-validation/audit-report.json --schema --json
```
