---
name: flow-ui-contract
description: >
  Penflow project-local skill for specifying flow/screen behavior before semantic UI tree
  generation. Recognizes legacy specify flows wording while positioning artifacts for
  forward flow to semantic tree to Pencil draft/enrichment workflows, reverse Pencil to
  flow workflows, and post-implementation runtime comparison.
  Triggers on: flow-ui-contract, flow ui contract, specify flows, génère les flow specs,
  flow specs, spec flows.
---
<!-- LiveSpec traceability anchors -->
<!-- @spec(AC-002) -->
<!-- @spec(FR-001) -->
<!-- @spec(FR-002) -->
<!-- @spec(FR-003) -->
<!-- @spec(FR-004) -->
<!-- @spec(FR-012) -->
<!-- @spec(FR-013) -->
<!-- @spec(FR-014) -->

# flow-ui-contract — Skill Posture

Guided pipeline that promotes reviewed behavior into canonical `flow-ui-contract/contract.json`. Flow/screen Markdown is generated through `export-flow-docs` or supplied only as explicit legacy migration input.

## Purpose

Use this skill before Penflow needs a `semantic-ui-tree.json`. It turns product behavior into a strict JSON contract that Penflow can validate, convert into Pencil context, reverse/migrate from Pencil docs, and compare against runtime output later.

This skill prepares inputs. It does **not** run browser, Xcode, simulator, Playwright, React Native, Metro, app builds, or runtime adapters.

## Consumer Hygiene Gate

At task start, run `penflow doctor --project <consumer-project-root> --check --json` and retain the read-only receipt; run it again at task end. Work only below that exact selected project. Doctor never widens it to the enclosing Git worktree; the internal `git_root` serves only scoped Git interrogation and transient metadata coordination.

For a new project, continue from a failing start receipt only when every issue code belongs to the exact bootstrap allowlist: `pen.missing`, `gitignore.managed_block_missing`, `gitignore.managed_block_outdated`, or `gitignore.managed_block_duplicate`. Run `doctor --fix`, require a passing `doctor --check`, then author the canvas. Every other start finding blocks and requires manual resolution. The final read-only Doctor check must pass.

- Keep exactly one regular `ui.pen` per selected project. A collective Git worktree may contain several independent project canvases. Store one active revision per logical screen plus optional draft/archive revisions as top-level `penflow.lifecycle` regions inside the same canvas; unmarked legacy regions are active.
- Route technical intermediates through producer-managed, ignored `.penflow-tmp/`, `.penflow-run/`, and `.mockup-validation/`; preflight/postflight reconcile cleanup-eligible runs after durable outputs finalize.
- Doctor never chooses among multiple `.pen` files or rewrites Git index/history. Resolve `multiple_pen_files` by manually consolidating intended regions into `ui.pen` and deliberately migrating/removing extras. Manually review and unstage/untrack reported tracked/staged temporary leaks before rerunning Doctor.

## Pencil Context Grammar

When a contract is consumed by Pencil authoring, every id-bearing authored node receives exactly one explicit `semantic`, `inherited`, or `decorative` classification at insertion time. Allowed keys are `classification`, `decorative_owner`, `decorative_reason`, `inherits_from`, `instance_key`, `relation`, `semantic_id`, `role`, `intent`, `binding`, `repeat`, `entity`, `variant`, `test_id`, `action`, `permission`, `mask`, `mask_text`, and `tolerance`. Semantic nodes require `semantic_id`, `test_id`, and `role`; inherited/decorative nodes name an anchored owner and relation/reason. Never infer classification from visible appearance.

Examples:
- Screen frame: `classification=semantic; semantic_id=cockpit-live; test_id=cockpit-live-screen; role=screen`
- Section frame: `classification=semantic; semantic_id=cockpit-live.git; test_id=cockpit-live-git; role=container`
- Button: `classification=semantic; semantic_id=cockpit-live.stop-worker; test_id=stop-worker; role=button; intent=stop-worker; action=stop_worker`
- List: `classification=semantic; semantic_id=cockpit-live.workers; test_id=worker-list; role=list; repeat=worker in workers`

After authoring/enrichment, run `penflow map-pencil-context <target>/ui.pen <target>/semantic-ui-tree.json --project <consumer-project-root> --out <target>/pencil-context-map.json --strict-coverage --contract <target>/flow-ui-contract/contract.json --coverage-out <target>/semantic-context-coverage.json --json`. Only exhaustive coverage `PASS` permits downstream strict work; `--strict-anchors` is forward-only diagnostic evidence. `--create-placeholders` is explicit repair scaffolding and yields `PARTIAL`, never `PASS`.

## Invocation

| Form | Use |
|---|---|
| `flow-ui-contract` skill | Invoke this skill by its installed name; use the current directory as target. |
| `flow-ui-contract --target <dir>` | Run on a Penflow target directory such as `examples/demo` when the agent runner supports skill arguments. |
| `flow-ui-contract --status --target <dir>` | Show fresh/stale/unspecified screen coverage when the runner supports skill arguments. |
| `specify flows`, `flow specs`, `spec flows` | Legacy wording signals; route to this skill, but do not call a separate `specify-flows` slash command. |

## Positioning

- **Forward mode:** write/review `contract.json`, generate/check Markdown projections, export `semantic-ui-tree.json`, draft or enrich `ui.pen`, require exhaustive semantic coverage, then generate downstream artifacts.
- **Pencil enrichment:** use an existing visual `.pen`, inject Penflow context from the semantic tree, map semantic nodes to Pencil nodes, and validate the enriched file.
- **Reverse mode:** run `reverse-pen` on legacy `ui.pen` to reconstruct flow/screen specs and `semantic-ui-tree.json`; unknown business logic becomes `[NEEDS CLARIFICATION]`.
- **Runtime verification:** external adapters emit `actual-ui-tree.json`; Penflow validates, compares, and writes review/fix reports.

## Required Reads

Before generating or validating files, **Read** [`references/grammar.md`](references/grammar.md), **Read** [`references/templates/flow.md`](references/templates/flow.md), **Read** [`references/templates/screen.md`](references/templates/screen.md), **Read** [`references/semantic-ui-tree.md`](references/semantic-ui-tree.md), and **Read** [`references/design-read.md`](references/design-read.md).

## Design Convention Gate

Before writing or editing `flow-ui-contract/` for any UI surface, **Read** [`../../../.conventions/index.md`](../../../.conventions/index.md), then load the matching design domains from that index. This is mandatory input, not optional polish.

- Always load `design-tokens`, `design-components`, `design-views`, and `design-quality` for UI flows.
- Also load `design-dataviz` for dashboard, metrics, KPI, chart, analytics, or usage screens.
- Also load `design-payments` for payment, checkout, billing, subscription, pricing, tip, donation, order summary, or card form screens.
- Also load `design-realtime` for live status, websocket, SSE, progress, or streaming screens.

Screen specs must describe visible hierarchy using those conventions: app shell/sidebar/header/content zones, forms, lists/tables, cards, empty/loading/error states, payment anatomy, metric cards, and responsive variants where relevant. Do not produce a flow/screen spec that only lists labels and buttons when the convention defines a richer view pattern.

## Design Read Capture

<!-- @spec(FR-001) -->
<!-- @spec(FR-002) -->
<!-- @spec(FR-003) -->

During Step 5, landing and showcase workspaces must capture `<target>/design-read.json` before Step 6 Generation. The artifact records the exact `design-read-protocol.md` one-liner:

```text
Reading this as: <page kind> for <audience>, with a <vibe> language, leaning toward <design system or aesthetic family>.
```

It also records integer dials from 1 to 10 for `variance`, `motion`, and `density`, plus the six protocol signals. Use the Design Convention Gate to load `design-read-protocol.md`; do not duplicate its dial table. For non-landing/showcase surfaces, write `status: skipped` with a reason.

`design-read.json` is not a gate. It informs generation and the Mockup Factory advisory pass, but it never decides PASS/FAIL and never changes Penflow validation exit codes.

## Tree Formation Contract

This skill does not ask the LLM to hand-write `semantic-ui-tree.json`. It asks the LLM to author or migrate `contract.json` precise enough for `penflow export-semantic-tree` to generate the tree deterministically.

The LLM must still understand the formation contract: v2 contract objects become `flows[]` and `screens[]`; legacy flow specs become `flows[]`; screen specs become `screens[]`; visible hierarchy becomes recursive semantic nodes; business intent becomes `intent`, `binding`, `entity`, `states`, `validations`, `side_effects`, `test_id`, and `source_map`; unknown rules stay `[NEEDS CLARIFICATION]`. **Read** [`references/semantic-ui-tree.md`](references/semantic-ui-tree.md) before explaining or debugging tree output.

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

Matching Pencil contexts classify every id-bearing node explicitly:

```text
classification=semantic; semantic_id=checkout-form; test_id=checkout-form-screen; role=screen
classification=semantic; semantic_id=pay-button; test_id=pay-button; role=button; intent=submit_payment
classification=inherited; inherits_from=pay-button; relation=content
classification=decorative; decorative_owner=pay-button; decorative_reason=duplicates-label
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
        "test_id": "checkout-form-screen",
        "role": "screen",
        "children": [
          {
            "semantic_id": "pay-button",
            "test_id": "pay-button",
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
- Keep exactly one `.pen` output named `ui.pen`; enrichment/reverse operations update that canonical document rather than producing peers.
- Preserve Pencil visual properties during extraction and enrichment; metadata-only operations may atomically update canonical `ui.pen` in place but must not alter layout or create peer `.pen` files.
- Never auto-invent canonical flows; ask the user to declare or confirm them.
- Never skip validation; run [`validator.py`](validator.py) before accepting generated specs.
- If `ui.pen` is missing, continue only when the failing start receipt contains exclusively the exact bootstrap allowlist, `doctor --fix` succeeds, and the following `doctor --check` passes; otherwise block.

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
- `design-read.json` if present, so reruns preserve or review the prior design direction.
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

If any flow or screen declares surface `landing` or `showcase`, run the Design Read Capture in [`references/design-read.md`](references/design-read.md): ask at most one clarifying question only if required for missing design-read signals, write the exact `Reading this as:` one-liner, and record `variance`, `motion`, and `density` as integers from 1 to 10. If no `landing` or `showcase` surface exists, write `<target>/design-read.json` with `status: skipped` and the non-applicable surfaces.

### Step 6 — Generation

Author or update `<target>/flow-ui-contract/contract.json`, then generate its Markdown projections transactionally:

```bash
penflow export-flow-docs <target>/flow-ui-contract/contract.json --project <consumer-project-root> --out <target>/flow-ui-contract --json
penflow export-flow-docs <target>/flow-ui-contract/contract.json --project <consumer-project-root> --out <target>/flow-ui-contract --check --json
```

The generated `<target>/flow-ui-contract/flows/<flow-slug>.md` and `<target>/flow-ui-contract/screens/<screen-slug>.md` are read-only projections; edit the canonical JSON and regenerate instead of editing Markdown directly.

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
penflow validate-flow-contract <target>/flow-ui-contract/contract.json --project <consumer-project-root> --json
penflow export-flow-docs <target>/flow-ui-contract/contract.json --project <consumer-project-root> --out <target>/flow-ui-contract --json
penflow export-flow-docs <target>/flow-ui-contract/contract.json --project <consumer-project-root> --out <target>/flow-ui-contract --check --json
penflow export-semantic-tree <target>/flow-ui-contract/contract.json --project <consumer-project-root> --out <target>/semantic-ui-tree.json --json
penflow validate-semantic-tree <target>/semantic-ui-tree.json --project <consumer-project-root> --json
penflow draft-pen-from-tree <target>/semantic-ui-tree.json --project <consumer-project-root> --out <target>/ui.pen --theme-css <target>/theme.css --json
penflow map-pencil-context <target>/ui.pen <target>/semantic-ui-tree.json --project <consumer-project-root> --out <target>/pencil-context-map.json --strict-coverage --contract <target>/flow-ui-contract/contract.json --coverage-out <target>/semantic-context-coverage.json --json
penflow validate-pen <target>/ui.pen --project <consumer-project-root> --json
penflow export-expected <target>/ui.pen --project <consumer-project-root> --out <target>/expected-ui-tree.json --json
penflow code-ir --from-context <target>/ui.pen --semantic-tree <target>/semantic-ui-tree.json --contract <target>/flow-ui-contract/contract.json --flow-id <flow-id> --flow-name "<Flow name>" --project <consumer-project-root> --out <target>/code-ir.json --json
```

`draft-pen-from-tree` is only the structural handoff draft. Its JSON output can be saved as `draft-report.json` and carries `fidelity: "wireframe"`: draft = structure / wireframe, PAS un mockup final ; le hi-fi passe par mockup-factory.

## Enrichment Command Sequence

```bash
penflow enrich-pen <target>/ui.pen <target>/semantic-ui-tree.json --project <consumer-project-root> --out <target>/ui.pen --json
penflow map-pencil-context <target>/ui.pen <target>/semantic-ui-tree.json --project <consumer-project-root> --out <target>/pencil-context-map.json --strict-coverage --contract <target>/flow-ui-contract/contract.json --coverage-out <target>/semantic-context-coverage.json --json
penflow validate-pen <target>/ui.pen --project <consumer-project-root> --json
penflow export-expected <target>/ui.pen --project <consumer-project-root> --out <target>/expected-ui-tree.json --json
penflow code-ir --from-context <target>/ui.pen --semantic-tree <target>/semantic-ui-tree.json --context-map <target>/pencil-context-map.json --contract <target>/flow-ui-contract/contract.json --flow-id <flow-id> --flow-name "<Flow name>" --project <consumer-project-root> --out <target>/code-ir.json --json
```

## Reverse Command Sequence

```bash
penflow reverse-pen <target>/ui.pen --project <consumer-project-root> --out <target>/reverse-output --enrich --json
penflow validate-semantic-tree <target>/reverse-output/semantic-ui-tree.json --project <consumer-project-root> --json
penflow map-pencil-context <target>/ui.pen <target>/reverse-output/semantic-ui-tree.json --project <consumer-project-root> --out <target>/pencil-context-map.json --strict-coverage --contract <target>/reverse-output/flow-ui-contract/contract.json --coverage-out <target>/semantic-context-coverage.json --json
penflow validate-pen <target>/ui.pen --project <consumer-project-root> --json
```

`reverse-pen --out <dir>` writes a directory containing `semantic-ui-tree.json` and `flow-ui-contract/`; validate `<dir>/semantic-ui-tree.json`, not the directory path itself.

## Post-Implementation Compare Sequence

```bash
penflow validate-actual actual-ui-tree.json --schema --json
penflow compare-tree expected-ui-tree.json actual-ui-tree.json --out compare-report.json --json
penflow review-report compare-report.json --out review-report.json --json
penflow fix-report compare-report.json --out fix-report.json --json
```

## Full Demo Sequence

```bash
penflow demo --out examples/full --json
```

## Status Mode

`--status` reads `<target>/mockups/manifest.json`; compares `sourceGeneratedAt` and `specGeneratedAt`; reports `fresh`, `stale`, or `unspecified`; exits `1` when the manifest is missing or malformed.
