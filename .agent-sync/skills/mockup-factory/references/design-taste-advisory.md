<!-- LiveSpec traceability anchors -->
<!-- @spec(FR-004) -->
<!-- @spec(FR-005) -->
<!-- @spec(FR-006) -->

# Design Taste Advisory

Advisory only. This pass never decides PASS/FAIL, never adds checklist items, never changes gate status.

## Source

Before running this advisory pass, **Read** [`../../../../.conventions/index.md`](../../../../.conventions/index.md), load `design-quality`, then **Read** the routed design taste source from [`../../../../.conventions/index.md`](../../../../.conventions/index.md). Also **Read** [`../../flow-ui-contract/references/design-read.md`](../../flow-ui-contract/references/design-read.md) when `<target>/design-read.json` exists.

## Inputs

- `<target>/design-read.json` when present.
- `<target>/expected-ui-tree.json` for screen, node, text, visual, and hierarchy facts.
- `<target>/theme.css` for accent/radius token observations when available.
- Existing deterministic gate reports for deferrals (`consistency-report.json`, `visual-metrics-report.json`, and `drift-report.json`).

## Checks

| Check | Source | Observable data | Advisory result | Deferral |
|---|---|---|---|---|
| One accent lock | `design-taste.md` Anti-Default Rules | Theme fills, CTA/link/badge/chart fills | `note` when coherent, `warning` when several accent families compete | Token violations stay with `tokens`. |
| One radius lock | `design-taste.md` Anti-Default Rules | `cornerRadius`, theme radius tokens | `note` or `warning` for unexplained radius families | Token violations stay with `tokens`. |
| Eyebrow ratio | `design-taste.md` Anti-Default Rules | Small uppercase text per section | `warning` when more than one eyebrow per three sections appears | Text parsing remains advisory. |
| Section layout-family repetition | `design-taste.md` Anti-Default Rules | Repeated sibling section structures | `warning` when the same landing section pattern repeats more than once | Cross-screen numeric drift stays with `consistency`. |
| Hero one-moment | `design-taste.md` Anti-Default Rules | First screen/hero text nodes | `warning` when hero contains more than eyebrow, headline, short subtext, and CTA group | Viewport fit stays with renderer/visual evidence. |
| AI tells | `design-taste.md` AI Tell Ban | Text content and sample metrics | `warning` for banned names, lorem ipsum, perfect metrics, generic phases, or unsupported trust claims | None; advisory wording only. |
| CTA intent label consistency | `design-taste.md` Landing Pre-Flight | Button/link text and action intent | `warning` when one intent uses multiple labels | Semantic binding issues stay with `contract`. |
| Bento cell count and treatments | `design-taste.md` Landing Pre-Flight | Grid/list/card groups, visual variants | `warning` when cells do not match content items or multi-cell grids lack at least two treatments | Structural issues stay with `structural_fidelity` when actual tree exists. |
| Split-header rule | `design-taste.md` Anti-Default Rules | Two-column headings and body/visual siblings | `warning` when the second column is filler text instead of a real visual or interaction | Layout overlap/overflow stays with `accessibility_alignment`. |

## Report Format

Write `.mockup-validation/design-taste-advisory.md`:

```markdown
# Design Taste Advisory

- Target: <target>
- Generated at: <timestamp>
- Design read: <one_liner or absent/skipped>
- Dials: variance=<n>, motion=<n>, density=<n>
- Advisory boundary: never decides PASS/FAIL, never adds checklist items, never changes gate status.

| Check | Screens | Observation | Recommendation |
|---|---|---|---|
| AI tells | landing-home | No banned placeholder names found. | Keep sample copy domain-specific. |

## Not Applicable On Static Mockups

- Reduced-motion behavior.
- Runtime viewport scroll/hero fit.
- Dynamic mobile collapse.
```

When `design-read.json` is absent or skipped, still emit the report with direction-independent checks such as AI tells, bento, CTA labels, and split headers. Record the absence in the header instead of blocking the audit.

## Boundary

Do not add advisory findings to `checklist.json` under any circumstance. If a deterministic gate issue or blocking vision/reference criterion already exists, cite that existing issue in the advisory report instead. Do not add new `vision-report.json` categories for taste.
