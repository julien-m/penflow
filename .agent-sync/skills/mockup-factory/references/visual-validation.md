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
4. **Write the evidence artifacts** — `manifest.json` (one entry per screen with `screen_id`, `semantic_id`, `pencil_node_id`, `png`, `layout_checked`, `screenshot_checked`) and `vision-report.json` (`kind: penflow-vision-report`, `version`, `status`, `renderer`, `sourceFile`, `model`, `screens[]` each with `screen_id`, `png`, and `criteria[]` of `{category, result pass|fail|warning, evidence, blocking}`).
5. **Run the gate:**

   ```bash
   penflow validate-visual-evidence .mockup-validation/visual-evidence --expected expected-ui-tree.json --json
   ```

   Exit 0 is the only acceptable proof. Exit 1 means the packet is incomplete or invalid: missing/empty PNG, invalid manifest or vision report, a screen of the expected tree left uncovered (`evidence.screen.uncovered`), an unanswered vision category, or a layout snapshot mismatch.

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

All five categories are required per screen; `blocking: true` marks a criterion that must block PASS in the audit loop.

## Legacy Artifacts

`visual-report.json` (feature 044 free-text audit) is deprecated in favor of `vision-report.json`; existing packets keep validating through `validate-report --schema`, but new evidence must use the locked vision report.

## PASS Rule

PASS requires:

- deterministic Penflow anchors pass (contract, trees, drift);
- `penflow validate-visual-evidence` exits 0 for the evidence directory;
- no `blocking: true` criterion with result `fail` remains;
- non-critical `warning` results are listed under `PASSED_WITH_WARNINGS`; unresolved critical issues escalate to `ESCALATED`.

If no Pencil renderer is available, do not mark PASS. Use `BLOCKED_VISUAL_NOT_RUN` (or `ESCALATED`) with the missing-tool reason — a layout snapshot and screenshot inspection cannot be faked from tree validation alone.
