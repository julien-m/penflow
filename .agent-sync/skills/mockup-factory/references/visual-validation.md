# Visual Evidence Gate

Run this gate after the deterministic Penflow anchors pass and before final PASS. It proves the mockup was rendered as a user-visible Pencil screen, not only validated as JSON trees.

## Required When Available

Use Pencil MCP or an equivalent Pencil renderer to capture visual evidence:

1. Open the source `.pen`.
2. Read the target screen node IDs.
3. Capture `snapshot_layout` for each optimized screen.
4. Capture `get_screenshot` for visual inspection.
5. Export a PNG for each audited screen.
6. Write `.mockup-validation/visual-evidence/manifest.json`.
7. Write `.mockup-validation/visual-evidence/visual-report.json`.

If no renderer is available, do not mark PASS. Use `BLOCKED_VISUAL_NOT_RUN` or `ESCALATED` and include the missing tool reason.

## Manifest

`manifest.json` must link every proof to deterministic anchors:

```json
{
  "status": "PASS",
  "sourceFile": "penflow/ui.pen",
  "renderer": "pencil-mcp",
  "screens": [
    {
      "screen_id": "checkout",
      "semantic_id": "checkout",
      "pencil_node_id": "checkoutScreen",
      "png": "checkoutScreen.png",
      "layout_checked": true,
      "screenshot_checked": true
    }
  ]
}
```

## Visual Report

`visual-report.json` must include:

- status: `PASS`, `PASSED_WITH_WARNINGS`, `ESCALATED`, or `BLOCKED_VISUAL_NOT_RUN`;
- source `.pen` path and renderer;
- exported PNG path per screen;
- layout evidence: size, visible children, overlap/overflow result;
- UX evidence: visual alignment, hierarchy, CTA placement, density, accessibility, responsive assumptions, modernity, polish;
- anchored findings using `screen_id`, `semantic_id`, and `pencil_node_id` when available.

## PASS Rule

PASS requires:

- deterministic Penflow anchors pass;
- exported PNG exists for every audited screen;
- screenshot was inspected by an agent or reviewer;
- no critical visual issue remains;
- non-critical issues are listed under `PASSED_WITH_WARNINGS`.
