# mockup-factory

Penflow-local guided UX/UI optimizer for Pencil mockups.

Use **Read** [`SKILL.md`](SKILL.md) as the canonical workflow. The skill is tree-aware: it treats `flow-ui-contract`, `semantic-ui-tree.json`, `theme.css`, `ui.pen`, `pencil-context-map.json`, `expected-ui-tree.json`, and `detect-drift` reports as required anchors before any UX/UI audit or Pencil fix loop.

Before any audit or fix, **Read** [`../../../.conventions/index.md`](../../../.conventions/index.md) and load the relevant design domains. A themed but generic mockup fails if it ignores app-shell, dashboard, payment, form, list/table, state, responsive, or accessibility conventions.

Before final PASS, run the Visual Evidence Gate in **Read** [`references/visual-validation.md`](references/visual-validation.md): capture a Pencil layout snapshot, inspect a screenshot, export PNGs, and write `.mockup-validation/visual-evidence/manifest.json` plus `visual-report.md`.

The old ai-ressources mockup-factory skill is intentionally not canonical. ai-ressources remains a conventions/reference source; orchestration lives in this Penflow project-local skill.
