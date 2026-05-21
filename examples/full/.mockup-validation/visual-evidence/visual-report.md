# Visual Evidence Report — examples/full/ui.pen

Status: `PASSED_WITH_WARNINGS`
Renderer: `pencil-mcp`
Source: [`../../ui.pen`](../../ui.pen)
Export: [`checkoutScreen.png`](checkoutScreen.png)

## Screen: checkout

| Field | Value |
|---|---|
| `screen_id` | `checkout` |
| `semantic_id` | `checkout` |
| `pencil_node_id` | `checkoutScreen` |
| Size | `390 × 844` |
| Visible children | `orderSummary`, `selectedPaymentMethod`, `payNowButton` |

## Evidence

- Pencil MCP opened [`../../ui.pen`](../../ui.pen).
- `batch_get` confirmed the contextual screen and child nodes.
- `snapshot_layout` confirmed no overlap and no horizontal overflow: title at `24,24`, secondary text at `24,69`, CTA at `24,104`, all width `342`.
- `get_screenshot` rendered the user-visible checkout screen.
- `export_nodes` wrote [`checkoutScreen.png`](checkoutScreen.png).

## UX Audit

| Category | Result | Finding |
|---|---|---|
| Visual alignment | PASS | All visible elements share the same left/right axis and the CTA fills the content column. |
| Hierarchy | PASS | Title, supporting text, and primary CTA are readable in priority order. |
| CTA placement | PASS | Single primary action is visible and close to the summary copy. |
| Density | WARNING | The demo fixture is intentionally minimal and leaves most of the phone viewport blank; not critical for this regression fixture. |
| Accessibility | PASS | Text is readable, CTA contrast is strong, and touch target height is acceptable for the fixture. |
| Responsive behavior | WARNING | Only a phone-sized frame is present in this fixture; broader responsive proof belongs to product mockups. |
| Modernity | PASS | Simple SaaS-style typography, spacing, radius, and primary button treatment. |
| Polish | PASS | No clipping, text overflow, accidental overlap, or broken image/render artifact observed. |

## Final Gate

The visual evidence gate is complete for this fixture with warnings only. A production mockup would need all target viewports exported before PASS.
