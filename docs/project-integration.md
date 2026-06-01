# Integrating Penflow Into an Existing Project

Use this guide when an application already exists and you want Penflow to become the project-local contract layer between product intent, Pencil mockups, code generation, and runtime verification.

Penflow does not replace your app stack. It stores and validates UI contracts next to the app so agents and humans can answer:

- what each screen is supposed to do;
- which Pencil element maps to which business intent;
- what codegen should implement;
- whether the implemented runtime still matches the design contract.

## Recommended Layout

Create one project-local Penflow workspace. Keep it versioned with the app unless a generated artifact is intentionally temporary.

```text
my-app/
  penflow/
    flow-ui-contract/
      flows/
      screens/
    semantic-ui-tree.json
    ui.pen
    ui.enriched.pen
    pencil-context-map.json
    expected-ui-tree.json
    code-ir.json
    actual-ui-tree.json
    compare-report.json
    compare-report.md
    review.md
    fix.md
```

Recommended ownership:

| Path | Commit? | Owner | Purpose |
|---|---:|---|---|
| `penflow/flow-ui-contract/` | yes | product / design / agent | Source flow and screen intent. |
| `penflow/semantic-ui-tree.json` | yes | Penflow | Generated semantic contract from flow specs. |
| `penflow/ui.pen` or `penflow/ui.enriched.pen` | yes | design / agent | Pencil contract with business context. |
| `penflow/pencil-context-map.json` | yes | Penflow | Review map for matched, ambiguous, and unmapped Pencil nodes. |
| `penflow/expected-ui-tree.json` | yes | Penflow | Design-derived baseline for runtime comparison. |
| `penflow/code-ir.json` | yes | Penflow / codegen | Handoff artifact for implementation agents. |
| `penflow/actual-ui-tree.json` | optional | app runtime adapter | Runtime observation from the implemented app. |
| `penflow/compare-report.*`, `review.md`, `fix.md` | optional | Penflow | Review artifacts; commit when useful for PR evidence. |

Use one workspace per product area if the app is large:

```text
my-app/
  penflow/
    checkout/
      flow-ui-contract/
      ui.pen
      expected-ui-tree.json
    account-settings/
      flow-ui-contract/
      ui.pen
      expected-ui-tree.json
```

## Install and Run

For local development, install Penflow from the Penflow repository or a pinned internal package:

```bash
python3 -m pip install -e /path/to/penflow
```

Run commands from the application repository root and use paths inside the app:

```bash
penflow validate-flow-specs penflow/flow-ui-contract --json
```

## Path A: New Project or New Feature Area

Start with flow specs and `theme.css`, then let Penflow generate the tree and themed Pencil draft.

```bash
penflow validate-flow-specs penflow/flow-ui-contract --json
penflow export-semantic-tree penflow/flow-ui-contract --out penflow/semantic-ui-tree.json --json
penflow validate-semantic-tree penflow/semantic-ui-tree.json --json
penflow draft-pen-from-tree penflow/semantic-ui-tree.json --out penflow/ui.pen --theme-css theme.css --json
penflow validate-pen penflow/ui.pen --json
penflow export-expected penflow/ui.pen --out penflow/expected-ui-tree.json --json
penflow code-ir --from-context penflow/ui.pen --semantic-tree penflow/semantic-ui-tree.json --out penflow/code-ir.json --json
```

After this path:

- `flow-ui-contract/` explains the product behavior;
- `semantic-ui-tree.json` is the before-code semantic contract;
- `ui.pen` is the contextualized, theme-aware Pencil file;
- `expected-ui-tree.json` is the design baseline;
- `code-ir.json` is the handoff artifact an implementation agent can read.

## Path B: Existing Pencil Mockups

Use this when designers already have a `.pen` file and you want to preserve the layout.

```bash
penflow validate-flow-specs penflow/flow-ui-contract --json
penflow export-semantic-tree penflow/flow-ui-contract --out penflow/semantic-ui-tree.json --json
penflow enrich-pen design/ui.pen penflow/semantic-ui-tree.json --out penflow/ui.enriched.pen --json
penflow map-pencil-context penflow/ui.enriched.pen penflow/semantic-ui-tree.json --out penflow/pencil-context-map.json --json
penflow validate-pen penflow/ui.enriched.pen --json
penflow export-expected penflow/ui.enriched.pen --out penflow/expected-ui-tree.json --json
penflow code-ir --from-context penflow/ui.enriched.pen --semantic-tree penflow/semantic-ui-tree.json --context-map penflow/pencil-context-map.json --out penflow/code-ir.json --json
```

Review `pencil-context-map.json` before implementation. Ambiguous or unmapped nodes mean the mockup and product intent need a human or agent decision.

## Path C: Legacy Project With Mockups but No Flows

Use reverse mode to bootstrap missing flow specs from an old Pencil file.

```bash
penflow reverse-pen design/ui.pen --out penflow/reverse-output --enrich --json
penflow validate-semantic-tree penflow/reverse-output/semantic-ui-tree.json --json
penflow validate-pen penflow/reverse-output/ui.enriched.pen --json
```

`reverse-pen --out <dir>` creates a directory. The semantic tree is `<dir>/semantic-ui-tree.json`; recovered specs are under `<dir>/flow-ui-contract/`.

Reverse mode marks unknown business logic as `[NEEDS CLARIFICATION]`. Treat those markers as migration work. Do not let an agent invent validations, side effects, permissions, or state transitions that were not present in the source material.

Once reviewed, promote the recovered files into the project workspace:

```text
penflow/reverse-output/flow-ui-contract/ -> penflow/flow-ui-contract/
penflow/reverse-output/semantic-ui-tree.json -> penflow/semantic-ui-tree.json
penflow/reverse-output/ui.enriched.pen -> penflow/ui.enriched.pen
```

## Implementation Handoff

Give implementation agents the contextualized Pencil file and code IR:

```text
Implement the checkout flow from:
- penflow/ui.enriched.pen
- penflow/semantic-ui-tree.json
- penflow/code-ir.json

Preserve semantic_id, role, binding, entity, state, validation, side_effect, and test_id mappings.
```

The agent should use `semantic_id` and `test_id` as stable anchors. Visual details stay in Pencil; business intent lives in the Pencil `context`, semantic tree, and code IR.

## Runtime Verification

After implementation, the app must export an `actual-ui-tree.json` through a runtime adapter. Penflow validates and compares that file; it does not launch the app.

```bash
penflow validate-actual penflow/actual-ui-tree.json --schema --json
penflow compare-tree penflow/expected-ui-tree.json penflow/actual-ui-tree.json --out penflow/compare-report.json --markdown penflow/compare-report.md --json
penflow review-report penflow/compare-report.json --out penflow/review.md
penflow fix-report penflow/compare-report.json --out penflow/fix.md
```

Adapter guides:

- **Read** [`adapters/web-dom.md`](adapters/web-dom.md) for Web DOM.
- **Read** [`adapters/swiftui-xctest.md`](adapters/swiftui-xctest.md) for SwiftUI + XCTest.
- **Read** [`adapters/react-native.md`](adapters/react-native.md) for React Native.

## Guided Mockup Optimization

**Read** [`../.agent-sync/skills/mockup-factory/SKILL.md`](../.agent-sync/skills/mockup-factory/SKILL.md) after the project has valid Penflow anchors and needs Pencil mockup generation, audit, or optimization.

Mockup Factory requires these project-local artifacts before UX/UI work starts:

- `penflow/flow-ui-contract/`
- `penflow/semantic-ui-tree.json`
- `penflow/ui.pen` or `penflow/ui.enriched.pen`
- `penflow/pencil-context-map.json`
- `penflow/expected-ui-tree.json`
- `penflow/drift-report.json`

The skill is a guided optimizer, not a freeform redesign tool. Every UX/UI fix must reference an audited checklist item and the best available anchor: `screen_id`, `semantic_id`, or `pencil_node_id`. PASS requires semantic contract coherence, no critical UX/UI issues in visual alignment, hierarchy, CTA placement, density, accessibility, responsive behavior, modernity, or polish, and the Visual Evidence Gate from **Read** [`../.agent-sync/skills/mockup-factory/references/visual-validation.md`](../.agent-sync/skills/mockup-factory/references/visual-validation.md).

When Pencil rendering is available, store proof next to the workspace:

```text
penflow/.mockup-validation/
  visual-evidence/
    manifest.json
    visual-report.md
    checkout.png
```

If the renderer is unavailable, record `BLOCKED_VISUAL_NOT_RUN` or escalate; do not call the mockup visually validated from tree checks alone.

## CI Gate

A minimal CI gate for a project-local Penflow workspace:

```bash
penflow validate-flow-specs penflow/flow-ui-contract --json
penflow validate-semantic-tree penflow/semantic-ui-tree.json --json
penflow validate-pen penflow/ui.enriched.pen --json
penflow export-expected penflow/ui.enriched.pen --out /tmp/expected-ui-tree.json --json
penflow validate-actual penflow/actual-ui-tree.json --schema --json
penflow compare-tree /tmp/expected-ui-tree.json penflow/actual-ui-tree.json --out /tmp/compare-report.json --markdown /tmp/compare-report.md --json
```

For early migration, make `validate-flow-specs`, `validate-semantic-tree`, and `validate-pen` blocking. Add `actual-ui-tree.json` comparison once the app has a runtime adapter.

## Migration Checklist

- Choose one Penflow workspace path, usually `penflow/`.
- Add or recover `flow-ui-contract/flows/*.md` and `flow-ui-contract/screens/*.md`.
- Generate and validate `semantic-ui-tree.json`.
- Draft or enrich a Pencil file.
- Review `pencil-context-map.json` for ambiguous or unmapped nodes.
- Export `expected-ui-tree.json`.
- Generate `code-ir.json` for implementation handoff.
- Add a runtime adapter that emits `actual-ui-tree.json`.
- Compare expected vs actual and use `review.md` / `fix.md` for correction planning.
- Add CI commands once the artifacts are stable.

## Common Decisions

| Decision | Recommended default |
|---|---|
| Where to store artifacts? | `penflow/` inside the app repo. |
| One workspace or many? | One per bounded product area for large apps. |
| Commit generated JSON? | Yes for contract artifacts; optional for transient reports. |
| Who owns `actual-ui-tree.json`? | The app runtime adapter, not Penflow. |
| Can agents edit `.pen` directly? | Yes, but only through Penflow commands or Pencil-aware tooling that preserves context. |
| Can agents hand-write semantic trees? | No for production; write flow specs and run `export-semantic-tree`. |
