---
name: flow-ui-contract
description: >
  Penflow project-local skill for specifying flow/screen behavior before semantic UI tree
  generation. Recognizes legacy specify flows wording while positioning artifacts for
  forward flow -> semantic tree -> Pencil draft/enrichment workflows, reverse Pencil ->
  flow workflows, and post-implementation runtime comparison.
  Triggers on: flow-ui-contract, flow ui contract, specify flows, génère les flow specs,
  flow specs, spec flows.
---

# flow-ui-contract — Skill Posture

Guided pipeline that captures product behavior visible in Pencil/mockup artifacts and writes validated `flow-ui-contract/flows/*.md` and `flow-ui-contract/screens/*.md` specs.

## Purpose

Use this skill before Penflow needs a `semantic-ui-tree.json`. It turns product behavior into flow/screen Markdown that Penflow can parse, validate, convert into Pencil context, reverse from Pencil, and compare against runtime output later.

This skill prepares inputs. It does **not** run browser, Xcode, simulator, Playwright, React Native, Metro, app builds, or runtime adapters.

## Invocation

| Form | Use |
|---|---|
| `flow-ui-contract` skill | Invoke this skill by its installed name; use the current directory as target. |
| `flow-ui-contract --target <dir>` | Run on a Penflow target directory such as `examples/demo` when the agent runner supports skill arguments. |
| `flow-ui-contract --status --target <dir>` | Show fresh/stale/unspecified screen coverage when the runner supports skill arguments. |
| `specify flows`, `flow specs`, `spec flows` | Legacy wording signals; route to this skill, but do not call a separate `specify-flows` slash command. |

## Positioning

- **Forward mode:** write flow/screen specs, export `semantic-ui-tree.json`, validate it, draft or enrich `ui.pen`, export expected tree, and generate code IR.
- **Pencil enrichment:** use an existing visual `.pen`, inject Penflow context from the semantic tree, map semantic nodes to Pencil nodes, and validate the enriched file.
- **Reverse mode:** run `reverse-pen` on legacy `ui.pen` to reconstruct flow/screen specs and `semantic-ui-tree.json`; unknown business logic becomes `[NEEDS CLARIFICATION]`.
- **Runtime verification:** external adapters emit `actual-ui-tree.json`; Penflow validates, compares, and writes review/fix reports.

## Required Reads

Before generating or validating files, **Read** [`references/grammar.md`](references/grammar.md), **Read** [`references/templates/flow.md`](references/templates/flow.md), **Read** [`references/templates/screen.md`](references/templates/screen.md), and **Read** [`references/semantic-ui-tree.md`](references/semantic-ui-tree.md).

## Tree Formation Contract

This skill does not ask the LLM to hand-write `semantic-ui-tree.json`. It asks the LLM to author flow/screen specs precise enough for `penflow export-semantic-tree` to generate the tree deterministically.

The LLM must still understand the formation contract: flow specs become `flows[]`; screen specs become `screens[]`; visible hierarchy becomes recursive semantic nodes; business intent becomes `intent`, `binding`, `entity`, `states`, `validations`, `side_effects`, `test_id`, and `source_map`; unknown rules stay `[NEEDS CLARIFICATION]`. **Read** [`references/semantic-ui-tree.md`](references/semantic-ui-tree.md) before explaining or debugging tree output.

Mini example:

```text
Input specs:
  flows/checkout.md
    flow: checkout
    entry_screen: checkout-form
    transition: checkout-form --submit_payment--> confirmation

  screens/checkout-form.md
    screen: checkout-form
    action: pay-button
      role: button
      text: Pay now
      intent: submit_payment
      binding: checkout.payment_method
      entity: payment
      validation: payment_method_present
```

Expected `semantic-ui-tree.json` excerpt:

```json
{
  "kind": "semantic-ui-tree",
  "flows": [
    {
      "id": "checkout",
      "entry_screen": "checkout-form",
      "transitions": [
        {"from": "checkout-form", "to": "confirmation", "trigger": "submit_payment"}
      ]
    }
  ],
  "screens": [
    {
      "id": "checkout-form",
      "flow_id": "checkout",
      "root": {
        "semantic_id": "checkout-form",
        "role": "screen",
        "children": [
          {
            "semantic_id": "pay-button",
            "role": "button",
            "text": "Pay now",
            "intent": "submit_payment",
            "binding": "checkout.payment_method",
            "entity": "payment",
            "validations": [{"rule": "payment_method_present"}]
          }
        ]
      }
    }
  ]
}
```

## Hard Constraints

- Keep all outputs inside the target directory; never write into LiveSpec `.specs/`.
- Preserve Pencil visuals during extraction/enrichment; read `.pen` data only, do not overwrite layout.
- Never auto-invent canonical flows; ask the user to declare or confirm them.
- Never skip validation; run [`validator.py`](validator.py) before accepting generated specs.
- If `ui.pen` is missing, continue without Pencil auto-fill and report the warning.

## Target Layout

```text
<target>/
├── ui.pen                         (optional Pencil source)
├── mockups/
│   └── manifest.json              (optional coverage/status source)
└── flow-ui-contract/
    ├── flows/
    │   └── <flow-slug>.md
    └── screens/
        └── <screen-slug>.md
```

## 8-Step Pipeline

### Step 1 — Discovery

Read from `<target>/`:
- `mockups/manifest.json` if present; required only when mapping visual exports.
- `project-profile.md`, `01-exploration.md`, `02-market-research.md`, `theme.css` if present.
- `ui.pen` if present for Pencil auto-fill.

If no manifest exists, continue in manual mode and tell the user mockup status cannot be computed.

### Step 2 — Flow Declaration

Ask for the canonical flow list unless it is already provided. Do not proceed until confirmed.

### Step 3 — Mockup → Flow Mapping

For each `mockups/manifest.json` export:
1. Extract the parent segment from `{product}_{parent}[_{subview}][_{state}]`.
2. Match it to declared flows by exact match, substring, or edit distance <= 2.
3. Ask the user to validate the `Mockup | Proposed Flow | Confidence` table.

### Step 4 — Pencil Auto-Fill

For each mapped screen, inspect `<target>/ui.pen` with Penflow/Pencil tooling when available and extract visible labels, CTA labels, and component hierarchy. If unavailable, proceed with empty auto-fill data.

### Step 5 — Guided Conversation

For each flow, ask only about business details not visible in mockups or profile data: conditional rules, error conditions, backend side effects, entity state transitions, and access rules. Mark skipped answers as `[NEEDS CLARIFICATION]`.

### Step 6 — Generation

Generate:
- `<target>/flow-ui-contract/flows/<flow-slug>.md`
- `<target>/flow-ui-contract/screens/<screen-slug>.md`

Use the templates as skeletons and keep prose language consistent per file.

### Step 7 — Flow Spec Validation

```bash
python3 .agent-sync/skills/flow-ui-contract/validator.py <path>
python3 .agent-sync/skills/flow-ui-contract/validator.py --dir <target>/flow-ui-contract
python3 .agent-sync/skills/flow-ui-contract/validator.py --status --target <target>
```

If validation fails, show the report, correct the draft, and re-run validation before treating the files as accepted.

### Step 8 — Manifest Update + Recap

When `<target>/mockups/manifest.json` exists:
- Set `schemaVersion` to `2`.
- For covered exports, set `specFlow`, `specScreen`, `specStatus: fresh`, and `specGeneratedAt`.
- Preserve unrelated manifest fields.

Recap:

```text
flow-ui-contract recap
Flows produced: <N>
Screens covered: <N>
Screens missing: <N>
Open questions: <N> [NEEDS CLARIFICATION]
```

## Forward Command Sequence

```bash
penflow export-semantic-tree <target>/flow-ui-contract --out semantic-ui-tree.json --json
penflow validate-semantic-tree semantic-ui-tree.json --json
penflow draft-pen-from-tree semantic-ui-tree.json --out ui.pen --json
penflow validate-pen ui.pen --json
penflow export-expected ui.pen --out expected-ui-tree.json --json
penflow code-ir --from-context ui.pen --semantic-tree semantic-ui-tree.json --flow-id <flow-id> --flow-name "<Flow name>" --out code-ir.json --json
```

## Enrichment Command Sequence

```bash
penflow enrich-pen <target>/ui.pen semantic-ui-tree.json --out ui.enriched.pen --json
penflow map-pencil-context ui.enriched.pen semantic-ui-tree.json --out pencil-context-map.json --json
penflow validate-pen ui.enriched.pen --json
penflow export-expected ui.enriched.pen --out expected-ui-tree.json --json
penflow code-ir --from-context ui.enriched.pen --semantic-tree semantic-ui-tree.json --context-map pencil-context-map.json --flow-id <flow-id> --flow-name "<Flow name>" --out code-ir.json --json
```

## Reverse Command Sequence

```bash
penflow reverse-pen <target>/ui.pen --out reverse-output --enrich --json
penflow validate-semantic-tree reverse-output/semantic-ui-tree.json --json
penflow validate-pen reverse-output/ui.enriched.pen --json
```

`reverse-pen --out <dir>` writes a directory containing `semantic-ui-tree.json` and `flow-ui-contract/`; validate `<dir>/semantic-ui-tree.json`, not the directory path itself.

## Post-Implementation Compare Sequence

```bash
penflow validate-actual actual-ui-tree.json --schema --json
penflow compare-tree expected-ui-tree.json actual-ui-tree.json --out compare-report.json --markdown compare-report.md --json
penflow review-report compare-report.json --out review-report.md
penflow fix-report compare-report.json --out fix-report.md
```

## Full Demo Sequence

```bash
penflow demo --out examples/full --json
```

## Status Mode

`--status` reads `<target>/mockups/manifest.json`; compares `sourceGeneratedAt` and `specGeneratedAt`; reports `fresh`, `stale`, or `unspecified`; exits `1` when the manifest is missing or malformed.
