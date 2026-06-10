# Visual Evidence Gate

Run this gate after the deterministic Penflow anchors pass and before final PASS. It proves the mockup was rendered as a user-visible Pencil screen and that a vision pass answered the vision-only questions — Penflow never runs vision; it validates the evidence packet.

**The gate is the `penflow validate-visual-evidence` exit code, not prose.** No narrative claim of visual quality may substitute for exit 0.

## Protocol

Use Pencil MCP or an equivalent Pencil renderer. All artifacts go to `.mockup-validation/visual-evidence/`:

1. **Export PNGs** — `export_nodes` one PNG per audited screen (`<pencil_node_id>.png`). Every PNG must exist and be non-empty.
2. **Dump the layout snapshot** — capture `snapshot_layout` per screen and write `layout-snapshot.json`: `{"screens": [{"screen_id", "pencil_node_id", "width", "height"}]}`. Penflow cross-checks each screen against the expected root bbox within ±4px (`evidence.snapshot.bbox_mismatch`).
3. **Run the vision pass (screenshot inspection)** — inspect each exported screen (e.g. via `get_screenshot`) and answer **ONLY** the five locked vision categories, one evidence sentence each (≥ 10 characters), per screen:
   - `visual_balance`
   - `rendering_artifacts`
   - `readability`
   - `perceived_hierarchy`
   - `imagery_quality`

   Deterministic facts — contrast, touch targets, overlap/overflow, tokens, consistency — are already computed by `penflow audit-visual`, `lint-tokens`, and `check-consistency`. The vision-report schema **rejects** any other category, so vision cannot hand-wave computable facts.
4. **Run the cross-mockup coherence pass (contact sheet)** — after the per-screen vision pass, judge the mockup *set* as one product. See § Cross-Mockup Coherence below. Required whenever the expected tree has ≥ 2 screens (`evidence.coherence.missing`).
5. **Write the evidence artifacts** — `manifest.json` (one entry per screen with `screen_id`, `semantic_id`, `pencil_node_id`, `png`, `layout_checked`, `screenshot_checked`) and `vision-report.json` (`kind: penflow-vision-report`, `version`, `status`, `renderer`, `sourceFile`, `model`, `screens[]` each with `screen_id`, `png`, and `criteria[]` of `{category, result pass|fail|warning, evidence, blocking}`, plus the top-level `coherence` section when the coherence pass ran).
6. **Run the gate:**

   ```bash
   penflow validate-visual-evidence .mockup-validation/visual-evidence --expected expected-ui-tree.json --json
   ```

   Exit 0 is the only acceptable proof. Exit 1 means the packet is incomplete or invalid: missing/empty PNG, invalid manifest or vision report, a screen of the expected tree left uncovered (`evidence.screen.uncovered`), an unanswered vision category, a layout snapshot mismatch, a missing coherence section for a multi-screen tree (`evidence.coherence.missing`), a missing/empty contact sheet (`evidence.contact_sheet.missing` / `evidence.contact_sheet.empty`), or an unanswered coherence category (`evidence.coherence.category_missing`).

## Cross-Mockup Coherence (Contact Sheet)

Per-screen criteria judge each mockup in isolation; the coherence pass proves the set reads as one product. Run it after the per-screen vision pass:

1. **Export all audited screens at a uniform scale** — `export_nodes` every audited screen with the same scale factor, so size differences on the sheet are real design differences, not export artifacts.
2. **Capture one contact sheet** — a single `get_screenshot` of the board showing all screens, or a grid composed from the exported PNGs listed in the manifest. Save it in the evidence directory and reference it as `coherence.contact_sheet_png`. It must exist non-empty on disk.
3. **Run one vision pass over the contact sheet** answering **ONLY** the four locked coherence categories, one evidence sentence each (≥ 10 characters):
   - `cross_screen_rhythm` — do spacing rhythm and layout density read consistently across screens?
   - `palette_coherence` — does the set read as one palette, with accent colors used for the same intents?
   - `typography_coherence` — do type scale and hierarchy levels read the same across screens?
   - `component_recognition` — are recurring components (buttons, cards, nav) recognizable as the same component everywhere?

   **The numeric anchor for cross-screen consistency remains the feature 047 `penflow check-consistency` report** (the `consistency` gate in the 052 gate table). Signature property divergence — fills, radii, font sizes, gaps — is computed there; the coherence schema **rejects** any other category, so the contact-sheet pass answers only what perception can judge and never restates numeric checks.
4. **Write the `coherence` section** into `vision-report.json`: `{"contact_sheet_png": "...", "criteria": [{category, result pass|fail|warning, evidence, blocking}]}`. All four categories are required (`evidence.coherence.category_missing`).

The section is optional schema-wise but **required by `penflow validate-visual-evidence` whenever the expected tree has ≥ 2 screens** (`evidence.coherence.missing`); single-screen trees pass without it.

## Vision Report

`vision-report.json` example (validates via `penflow validate-report vision-report.json --schema`):

```json
{
  "version": 1,
  "kind": "penflow-vision-report",
  "status": "PASS",
  "renderer": "pencil-mcp",
  "sourceFile": "penflow/ui.pen",
  "model": "claude-fable-5",
  "coherence": {
    "contact_sheet_png": "contact-sheet.png",
    "criteria": [
      {
        "category": "palette_coherence",
        "result": "pass",
        "evidence": "All screens share one neutral surface palette with a single accent intent.",
        "blocking": false
      }
    ]
  },
  "screens": [
    {
      "screen_id": "checkout",
      "semantic_id": "checkout",
      "pencil_node_id": "checkoutScreen",
      "png": "checkoutScreen.png",
      "criteria": [
        {
          "category": "visual_balance",
          "result": "pass",
          "evidence": "Content forms one aligned column with even vertical rhythm.",
          "blocking": false
        }
      ]
    }
  ]
}
```

All five categories are required per screen; all four coherence categories are required when the `coherence` section is present; `blocking: true` marks a criterion (per-screen or coherence) that must block PASS in the audit loop.

## Legacy Artifacts

`visual-report.json` (feature 044 free-text audit) is deprecated in favor of `vision-report.json`; existing packets keep validating through `validate-report --schema`, but new evidence must use the locked vision report.

## PASS Rule

PASS requires:

- deterministic Penflow anchors pass (contract, trees, drift);
- `penflow validate-visual-evidence` exits 0 for the evidence directory;
- no `blocking: true` criterion with result `fail` remains;
- non-critical `warning` results are listed under `PASSED_WITH_WARNINGS`; unresolved critical issues escalate to `ESCALATED`.

If no Pencil renderer is available, do not mark PASS. Use `BLOCKED_VISUAL_NOT_RUN` (or `ESCALATED`) with the missing-tool reason — a layout snapshot and screenshot inspection cannot be faked from tree validation alone.
