# Mockup Factory Workflow

## Sequence

1. Validate `flow-ui-contract/` with `penflow validate-flow-specs`.
2. Export and validate `semantic-ui-tree.json`.
3. Validate the source `.pen`.
4. Build `pencil-context-map.json`.
5. Export `expected-ui-tree.json`.
6. Run `penflow detect-drift` and keep `drift-report.json` / `drift-report.md` with the audit packet.
7. Freeze a checklist whose items reference `screen_id` plus `semantic_id` or `pencil_node_id` when available.
8. Fix only checklist items; no broad redesign and no invented product behavior.
9. Re-run the full Penflow command chain before PASS.
10. Run the Visual Evidence Gate from **Read** [`visual-validation.md`](visual-validation.md): capture layout snapshot, screenshot, exported PNGs, manifest, and visual report.

## Anchor Rules

- Prefer `semantic_id` for product intent, `pencil_node_id` for visual edits, and `screen_id` for grouping.
- Treat `ambiguous` or `unmapped` entries from `pencil-context-map.json` as review work before implementation.
- Treat `drift-report.json` blocking issues as higher priority than visual polish.
- Use screenshots as required visual evidence for final PASS when a renderer is available; tree and drift artifacts remain the deterministic source of truth.

## Terminal States

| State | Meaning |
|---|---|
| PASS | Contract gate and UX/UI gate have zero blocking items. |
| PASSED_WITH_WARNINGS | Only non-critical, listed warnings remain. |
| ESCALATED | Blocking contract drift or critical UX/UI issue remains after the bounded loop. |
| BLOCKED | Required Penflow anchor command failed or input artifact is missing. |
| BLOCKED_VISUAL_NOT_RUN | Pencil renderer/export was expected but no screenshot/PNG evidence could be captured. |
