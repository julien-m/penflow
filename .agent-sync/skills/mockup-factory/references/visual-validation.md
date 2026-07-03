<!-- LiveSpec traceability anchors -->
<!-- @spec(AC-002) -->
<!-- @spec(FR-002) -->
<!-- @spec(FR-004) -->
<!-- @spec(FR-007) -->

# Visual Evidence Gate

Run this gate after the deterministic Penflow anchors pass and before final PASS. It proves the mockup was rendered as a user-visible Pencil screen and that a vision pass answered the vision-only questions — Penflow never runs vision; it validates the evidence packet.

**The gate is the `penflow validate-visual-evidence` exit code, not prose.** No narrative claim of visual quality may substitute for exit 0.

## Protocol

Use Pencil MCP or an equivalent Pencil renderer. All artifacts go to `.mockup-validation/visual-evidence/`:

1. **Export PNGs and expose previews** — `export_nodes` one PNG per audited screen (`<pencil_node_id>.png`). Every PNG must exist and be non-empty. Immediately after each export, expose the image in both human-review channels before writing `vision-report.json`; do not write `vision-report.json` before displaying each image:
   - Terminal: emit a Markdown image using the absolute path, e.g. `![checkoutScreen](/absolute/path/.mockup-validation/visual-evidence/checkoutScreen.png)`.
   - Browser annotation: run `visual-preview url /absolute/path/.mockup-validation/visual-evidence/checkoutScreen.png` when available.

   Browser preview is for annotation and iteration only. Preview URLs are not canonical proof and must not be written into `manifest.json` or `vision-report.json`; the canonical proof remains `penflow validate-visual-evidence` exit 0. If visual-preview is unavailable or fails, keep the Markdown image, record browser preview unavailable in operator notes/status, and continue the evidence packet without downgrading it solely for the missing preview channel.
2. **Dump the layout snapshot** — capture `snapshot_layout` per screen and write `layout-snapshot.json`: `{"screens": [{"screen_id", "pencil_node_id", "width", "height"}]}`. Penflow cross-checks each screen against the expected root bbox within ±4px (`evidence.snapshot.bbox_mismatch`).
3. **Run the vision pass (screenshot inspection)** — inspect each exported screen (e.g. via `get_screenshot`) and answer **ONLY** the five locked vision categories, one evidence sentence each (≥ 10 characters), per screen:
   - `visual_balance`
   - `rendering_artifacts`
   - `readability`
   - `perceived_hierarchy`
   - `imagery_quality`

   Every category evidence sentence must cite the evaluated file name (`png`) it judged, and that file must be the exact manifest PNG for the same `screen_id`, not a prettier replacement. Deterministic facts — contrast, touch targets, overlap/overflow, tokens, consistency — are already computed by `penflow audit-visual`, `lint-tokens`, and `check-consistency`. The vision-report schema **rejects** any other category, so vision cannot hand-wave computable facts.
4. **Run the cross-mockup coherence pass (contact sheet)** — after the per-screen vision pass, judge the mockup *set* as one product. See § Cross-Mockup Coherence below. Required whenever the expected tree has ≥ 2 screens (`evidence.coherence.missing`).
5. **Run the reference-fidelity pass when references exist** — if `<workspace>/references/references-manifest.json` exists, or the evidence manifest declares `references_manifest`, generate one side-by-side contact sheet per reference/export pair and inspect the actual pair, not memory or prose. The locked `reference_fidelity` section answers ONLY:
   - `layout_match`
   - `palette_match`
   - `component_parity`
   - `density_match`

   Every criterion evidence sentence must cite both the reference file and the export file. The contact sheet path is recorded per screen as `contact_sheet`. Deterministic enforcement is `penflow validate-reference-fidelity .mockup-validation/visual-evidence --references references --json`; copied exports fail as `reference.evidence_is_reference_copy`, and strong disagreement between deterministic metrics and the LLM/skill verdict fails as `reference.llm_metric_disagreement`.
6. **Write the evidence artifacts** — <!-- @spec FR-005: Step-5 manifest write includes runId + theme — .specs/features/056-evidence-run-identity-theme-fingerprint/spec.md#fr-005 --> `manifest.json` (one entry per screen with `screen_id`, `semantic_id`, `pencil_node_id`, `png`, `sha256`, `layout_checked`, `screenshot_checked`) and `vision-report.json` (`kind: penflow-vision-report`, `version`, `status`, `renderer`, `sourceFile`, `model`, `generated_by`, `inputs[]` of `{file, sha256}`, `screens[]` each with `screen_id`, `png`, and `criteria[]` of `{category, result pass|fail|warning, evidence, blocking}`, plus top-level `coherence` and `reference_fidelity` sections when those passes ran). Every evaluated PNG/contact sheet must be in `inputs[]`, and each SHA-256 must match the file bytes in `.mockup-validation/visual-evidence/`; receipts are mandatory and prose cannot replace them. The manifest must also carry the run identity and theme binding: a top-level `runId` (opaque string — ISO-8601 timestamp + short slug recommended, e.g. `2026-06-11T08:52:00Z-checkout`) and the top-level `theme` block obtained via `penflow theme-fingerprint <theme.css> --json` (`{path, sha256}` — SHA-256 of the theme's raw bytes, reproducible via `shasum -a 256`), so the packet is traceable to the run and bound to the exact theme bytes the mockups were rendered against. When references exist, add `references_manifest` pointing to `<workspace>/references/references-manifest.json` relative to the evidence directory.
7. **Run the gates:**

   ```bash
   penflow validate-visual-evidence .mockup-validation/visual-evidence --expected expected-ui-tree.json --theme-css theme.css --json
   penflow validate-reference-fidelity .mockup-validation/visual-evidence --references references --json
   ```

   Exit 0 is the only acceptable proof. Exit 1 means the packet is incomplete or invalid: missing/empty PNG, invalid manifest or vision report, missing `generated_by`/`inputs` receipts, SHA mismatch (`evidence.png.sha_mismatch` / `evidence.vision_input.sha_mismatch`), a vision screen PNG that differs from the manifest PNG for the same screen (`evidence.vision_manifest.png_mismatch`), a PNG path outside `.mockup-validation/visual-evidence/` or symlink into `references/` (`evidence.png.outside_evidence_dir`), criterion evidence that does not cite the evaluated file (`evidence.vision.file_evidence_missing`), a screen of the expected tree left uncovered (`evidence.screen.uncovered`), an unanswered vision category, a layout snapshot mismatch, a missing coherence section for a multi-screen tree (`evidence.coherence.missing`), a missing/empty contact sheet (`evidence.contact_sheet.missing` / `evidence.contact_sheet.empty`), an unanswered coherence category (`evidence.coherence.category_missing`), missing/incomplete `reference_fidelity` (`evidence.reference_fidelity.*`), copied reference bytes (`reference.evidence_is_reference_copy`), deterministic-vs-LLM disagreement (`reference.llm_metric_disagreement`), a manifest without a theme stamp while the gate is armed (`evidence.theme.missing`), or a theme stamp that no longer matches the current theme.css bytes (`evidence.theme.stale` — any theme edit deterministically invalidates the packet and forces a re-run of the bounded loop). A `--theme-css` path missing on disk is a usage boundary (exit 2).

## Cross-Mockup Coherence (Contact Sheet)

Per-screen criteria judge each mockup in isolation; the coherence pass proves the set reads as one product. Run it after the per-screen vision pass:

1. **Export all audited screens at a uniform scale** — `export_nodes` every audited screen with the same scale factor, so size differences on the sheet are real design differences, not export artifacts.
2. **Capture one contact sheet** — a single `get_screenshot` of the board showing all screens, or a grid composed from the exported PNGs listed in the manifest. Save it as `contact-sheet.png` in the evidence directory and reference it as `coherence.contact_sheet_png`. It must exist non-empty on disk. Immediately expose it as a Markdown image with its absolute path and run `visual-preview url <absolute-path-to-contact-sheet.png>` when available; this browser preview is annotation-only and never replaces the deterministic contact-sheet PNG check.
3. **Run one vision pass over the contact sheet** answering **ONLY** the four locked coherence categories, one evidence sentence each (≥ 10 characters):
   - `cross_screen_rhythm` — do spacing rhythm and layout density read consistently across screens?
   - `palette_coherence` — does the set read as one palette, with accent colors used for the same intents?
   - `typography_coherence` — do type scale and hierarchy levels read the same across screens?
   - `component_recognition` — are recurring components (buttons, cards, nav) recognizable as the same component everywhere?

   **The numeric anchor for cross-screen consistency remains the feature 047 `penflow check-consistency` report** (the `consistency` gate in the 052 gate table). Signature property divergence — fills, radii, font sizes, gaps — is computed there; the coherence schema **rejects** any other category, so the contact-sheet pass answers only what perception can judge and never restates numeric checks.
4. **Write the `coherence` section** into `vision-report.json`: `{"contact_sheet_png": "...", "criteria": [{category, result pass|fail|warning, evidence, blocking}]}`. All four categories are required (`evidence.coherence.category_missing`).

The section is optional schema-wise but **required by `penflow validate-visual-evidence` whenever the expected tree has ≥ 2 screens** (`evidence.coherence.missing`); single-screen trees pass without it.

## Reference Fidelity

References live under `<workspace>/references/` with `references-manifest.json`:

```json
[
  {"screen_id": "cockpit-live", "file": "cockpit-live.png", "sha256": "<sha256>", "source": "user-reference"}
]
```

Files resolve relative to `references/`. The evidence manifest declares the manifest path with `references_manifest`, relative to `.mockup-validation/visual-evidence/`.

For every referenced screen, export the matching Pencil screen PNG and create a side-by-side contact sheet showing `reference | export`. Write one `reference_fidelity` entry in `vision-report.json`:

```json
{
  "screen_id": "cockpit-live",
  "reference": "cockpit-live.png",
  "export": "cockpit-live-export.png",
  "contact_sheet": "cockpit-live-reference-contact-sheet.png",
  "criteria": [
    {
      "category": "palette_match",
      "result": "pass",
      "evidence": "Compared reference cockpit-live.png with export cockpit-live-export.png in cockpit-live-reference-contact-sheet.png.",
      "blocking": false
    }
  ]
}
```

All four categories are required per referenced screen: `layout_match`, `palette_match`, `component_parity`, `density_match`. A narrative PASS is invalid without both command exits: `validate-visual-evidence` checks section completeness and `validate-reference-fidelity` computes deterministic image metrics.

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
  "generated_by": "mockup-factory.visual-evidence",
  "inputs": [
    {"file": "checkoutScreen.png", "sha256": "<sha256>"},
    {"file": "contact-sheet.png", "sha256": "<sha256>"},
    {"file": "checkout-reference-contact-sheet.png", "sha256": "<sha256>"}
  ],
  "coherence": {
    "contact_sheet_png": "contact-sheet.png",
    "criteria": [
      {
        "category": "palette_coherence",
        "result": "pass",
        "evidence": "The contact-sheet.png image shows one neutral surface palette with a single accent intent.",
        "blocking": false
      }
    ]
  },
    "reference_fidelity": [
      {
        "screen_id": "checkout",
        "reference": "checkout-reference.png",
        "export": "checkoutScreen.png",
        "contact_sheet": "checkout-reference-contact-sheet.png",
        "criteria": [
          {
            "category": "layout_match",
            "result": "pass",
            "evidence": "Compared reference checkout-reference.png with export checkoutScreen.png in checkout-reference-contact-sheet.png.",
            "blocking": false
          }
        ]
      }
    ],
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
          "evidence": "Content in checkoutScreen.png forms one aligned column with even vertical rhythm.",
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
