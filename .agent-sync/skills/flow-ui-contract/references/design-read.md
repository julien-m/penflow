<!-- LiveSpec traceability anchors -->
<!-- @spec(FR-001) -->
<!-- @spec(FR-002) -->
<!-- @spec(FR-003) -->

# Design Read Artifact

Scope: applies to `landing` and `showcase` surfaces. Other surfaces record `status: "skipped"` so reruns can see that the decision was deliberate.

## Source

Before capture, **Read** [`../../../../.conventions/index.md`](../../../../.conventions/index.md), load `design-views`, then **Read** the routed design-read protocol from [`../../../../.conventions/index.md`](../../../../.conventions/index.md). The protocol is the source of truth for the one-liner and dial inference; do not copy its table into this file.

## Write Timing

- Step 1 reads `<target>/design-read.json` when present so reruns preserve or review the prior direction.
- Step 5 writes `<target>/design-read.json` after the guided design questions and before Step 6 Generation.
- Step 6 uses the artifact as input only; it is not a validator and not a gate.

## Guided Questions

Ask at most one clarifying question when the target has at least one `landing` or `showcase` surface and the missing signals cannot be inferred from project artifacts; the question may request the remaining signal buckets together:

- Page kind: what type of page is this: SaaS landing, consumer landing, portfolio, agency site, event page, editorial, or redesign?
- Audience: who is the primary reader or buyer?
- Vibe words: which language should the design speak: minimal, calm, premium, playful, serious B2B, trust-first, or another explicit direction?
- References: which URLs, screenshots, named products, or competitors should influence the read?
- Existing assets: which logo, palette, type, photos, screenshots, or product UI must be respected?
- Quiet constraints: which accessibility, trust, regulation, finance, health, kids, or government constraints should shape the taste boundary?

## JSON Contract

```json
{
  "schema_version": 1,
  "generated_at": "2026-07-04T00:00:00Z",
  "source": "design-read-protocol.md",
  "surfaces": ["landing"],
  "status": "captured",
  "one_liner": "Reading this as: SaaS landing for technical buyers, with a calm trust-first language, leaning toward Linear-style product clarity.",
  "dials": {
    "variance": 5,
    "motion": 3,
    "density": 4
  },
  "signals": {
    "page_kind": "SaaS landing",
    "audience": "technical buyers",
    "vibe_words": ["calm", "trust-first"],
    "references": ["Linear"],
    "existing_assets": ["product screenshots", "theme.css"],
    "quiet_constraints": ["accessibility", "trust"]
  }
}
```

Fields:

| Field | Required | Notes |
|---|---|---|
| `schema_version` | yes | Integer, currently `1`. |
| `generated_at` | yes | ISO-8601 timestamp from the run. |
| `source` | yes | `design-read-protocol.md`. |
| `surfaces` | yes | Surfaces observed in `flow-ui-contract/contract.json` or legacy flow docs. |
| `status` | yes | `captured` or `skipped`. |
| `one_liner` | yes when captured | Exact format: `Reading this as: <page kind> for <audience>, with a <vibe> language, leaning toward <design system or aesthetic family>.` |
| `dials` | yes when captured | `variance`, `motion`, and `density`; integers from 1 to 10. |
| `signals` | yes | Six signal buckets from the design-read protocol. Use empty arrays or strings only when unknown after asking. |
| `reason` | yes when skipped | Human-readable reason for non-applicable surfaces. |

Skipped example:

```json
{
  "schema_version": 1,
  "generated_at": "2026-07-04T00:00:00Z",
  "source": "design-read-protocol.md",
  "surfaces": ["admin"],
  "status": "skipped",
  "reason": "No landing or showcase surface is present; design-taste scope does not apply to app/dashboard/admin screens.",
  "signals": {
    "page_kind": "",
    "audience": "",
    "vibe_words": [],
    "references": [],
    "existing_assets": [],
    "quiet_constraints": []
  }
}
```

## Boundary

`design-read.json` is an input artifact for generation and advisory review. It never decides PASS/FAIL, never changes `audit-report.json`, and never substitutes for Penflow gates.
