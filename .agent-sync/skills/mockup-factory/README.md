# mockup-factory

Penflow-local guided UX/UI optimizer for Pencil mockups.

Use **Read** [`SKILL.md`](SKILL.md) as the canonical workflow. The skill is tree-aware: it treats `flow-ui-contract`, `semantic-ui-tree.json`, `theme.css`, `ui.pen`, `pencil-context-map.json`, `expected-ui-tree.json`, and `detect-drift` reports as required anchors before any UX/UI audit or Pencil fix loop.

Before any audit or fix, **Read** [`../../../.conventions/index.md`](../../../.conventions/index.md) and load the relevant design domains. A themed but generic mockup fails if it ignores app-shell, dashboard, payment, form, list/table, state, responsive, or accessibility conventions.

The audit rubric is prescriptive (**Read** [`references/audit-rubric.md`](references/audit-rubric.md)): every category maps to a scripted gate command with an exit-code/report-field pass condition, Critical = any error-severity gate issue or `blocking: true` item, and fixes run in a bounded fix-re-audit loop (**Read** [`references/workflow.md`](references/workflow.md), max 3 iterations, full chain rerun, no PASS without a final clean run). The final verdict is a strict `audit-report.json` checked by `penflow validate-report audit-report.json --schema` — the single CI-able final check.

Before final PASS, run the Visual Evidence Gate in **Read** [`references/visual-validation.md`](references/visual-validation.md): export PNGs, show every exported screen as a Markdown image with its absolute path, run `visual-preview url <absolute-path>` when available for browser annotation, dump a Pencil layout snapshot, inspect a screenshot answering only the five locked vision categories, then — for multi-screen sets — one cross-mockup coherence pass over a uniform-scale `contact-sheet.png` exposed through the same Markdown image + `visual-preview url` channels and answering only the four coherence categories (numeric anchor: the 047 `check-consistency` report), write `.mockup-validation/visual-evidence/manifest.json` plus `vision-report.json` (legacy `visual-report.json` is deprecated), and gate on `penflow validate-visual-evidence` exit 0 — the exit code, not prose. Preview URLs are annotation-only and not canonical proof.

The old ai-ressources mockup-factory skill is intentionally not canonical. ai-ressources remains a conventions/reference source; orchestration lives in this Penflow project-local skill.
