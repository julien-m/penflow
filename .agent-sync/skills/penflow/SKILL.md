---
name: penflow
description: Use the Penflow CLI for Pencil .pen context validation, semantic/expected/actual UI-tree workflows, codegen handoff, reports, and deterministic visual-fix review.
---

# Penflow Skill

Use this skill when a task mentions Penflow, Pencil `.pen`, flow specs, `semantic-ui-tree.json`, Pencil `context`, `expected-ui-tree.json`, `actual-ui-tree.json`, code IR, compare reports, or structural design/runtime validation.

## Purpose

Penflow is a deterministic, runtime-agnostic CLI that connects product flow intent, Pencil design contracts, codegen handoff data, and post-implementation runtime verification.

Penflow owns file validation and tree comparison only:
- `semantic-ui-tree.json`: before-code intent parsed from `flow-ui-contract/*.md`.
- `expected-ui-tree.json`: design-derived tree exported from contextualized `.pen`.
- `actual-ui-tree.json`: after-code runtime tree produced by an external adapter.

Penflow does **not** run browsers, Xcode, simulators, Playwright, React Native, Metro, or app builds. External adapters produce `actual-ui-tree.json`; Penflow validates and compares it.

## Tree Contracts

The LLM should not hand-write production trees, but it must understand their contracts before debugging or explaining results:

- `semantic-ui-tree.json` is formed by `penflow export-semantic-tree` from `flow-ui-contract/flows/*.md` and `flow-ui-contract/screens/*.md`. Flow specs become `flows[]`; screen specs become `screens[]`; UI hierarchy becomes recursive semantic nodes carrying `semantic_id`, `role`, `intent`, `binding`, `entity`, states, validations, side effects, source maps, and test ids.
- `expected-ui-tree.json` is exported from a contextualized Pencil `.pen`; it is the design-derived baseline for structural comparison.
- `actual-ui-tree.json` is emitted by an external runtime adapter; it is the post-implementation observation. Penflow validates it and compares it to the expected tree.

For the semantic-tree formation rules, **Read** [`../flow-ui-contract/references/semantic-ui-tree.md`](../flow-ui-contract/references/semantic-ui-tree.md). For runtime adapter output rules, **Read** [`../../../docs/adapters/web-dom.md`](../../../docs/adapters/web-dom.md), **Read** [`../../../docs/adapters/swiftui-xctest.md`](../../../docs/adapters/swiftui-xctest.md), or **Read** [`../../../docs/adapters/react-native.md`](../../../docs/adapters/react-native.md) when targeting that stack.

## Preconditions

- Run commands from the Penflow project root.
- Install in editable mode when needed:
  ```bash
  python3 -m pip install -e ".[dev]"
  ```
- **Read** [`README.md`](../../../README.md) for project-level command examples when a user asks for the full workflow.

## Mode Selection

| User intent | Mode |
|---|---|
| "Generate `.pen` / code IR from flow specs" | Forward mode |
| "Enrich an existing Pencil mockup with business context" | Pencil enrichment mode |
| "Reconstruct flows from legacy Pencil" | Reverse mode |
| "Compare implementation with design contract" | Post-implementation compare mode |
| "Show me the whole chain" | Full demo mode |

## Forward Mode

Use when flow/screen Markdown is the source of truth.

```bash
penflow validate-flow-specs examples/full/flow-ui-contract --json
penflow export-semantic-tree examples/full/flow-ui-contract --out semantic-ui-tree.json --json
penflow validate-semantic-tree semantic-ui-tree.json --json
penflow draft-pen-from-tree semantic-ui-tree.json --out ui.pen --json
penflow validate-pen ui.pen --json
penflow export-expected ui.pen --out expected-ui-tree.json --json
penflow code-ir --from-context ui.pen --semantic-tree semantic-ui-tree.json --flow-id checkout --flow-name "Checkout flow" --out code-ir.json --json
```

## Pencil Enrichment Mode

Use when a visual Pencil file already exists and must keep its layout.

```bash
penflow export-semantic-tree examples/full/flow-ui-contract --out semantic-ui-tree.json --json
penflow validate-semantic-tree semantic-ui-tree.json --json
penflow enrich-pen examples/full/ui.visual.pen semantic-ui-tree.json --out ui.enriched.pen --json
penflow map-pencil-context ui.enriched.pen semantic-ui-tree.json --out pencil-context-map.json --json
penflow validate-pen ui.enriched.pen --json
penflow export-expected ui.enriched.pen --out expected-ui-tree.json --json
penflow code-ir --from-context ui.enriched.pen --semantic-tree semantic-ui-tree.json --context-map pencil-context-map.json --flow-id checkout --flow-name "Checkout flow" --out code-ir.json --json
```

Preserve existing visual layout. Treat ambiguous or unmapped nodes from `map-pencil-context` as review work, not as permission to overwrite visual design.

## Reverse Mode

Use when a legacy `.pen` exists before flow specs.

```bash
penflow reverse-pen examples/full/ui.pen --out reverse-output --enrich --json
penflow validate-semantic-tree reverse-output/semantic-ui-tree.json --json
penflow validate-pen reverse-output/ui.enriched.pen --json
```

Reverse mode marks missing business rules as `[NEEDS CLARIFICATION]`. Do not invent backend side effects, validations, state transitions, or access rules.

## Post-Implementation Compare Mode

Use after an external runtime adapter writes `actual-ui-tree.json`.

```bash
penflow validate-actual actual-ui-tree.json --schema --json
penflow compare-tree expected-ui-tree.json actual-ui-tree.json --out compare-report.json --markdown compare-report.md --json
penflow review-report compare-report.json --out review-report.md
penflow fix-report compare-report.json --out fix-report.md
```

If `validate-actual` fails, fix the external adapter output first. Penflow does not inspect the running app.

## Regression Mode

Use for CI/regression coverage of contract C16. The proof is pytest-first, with the final CLI chain reproducible on `examples/full` and `examples/legacy`.

```bash
python3 -m pytest -q
penflow validate-flow-specs examples/full/flow-ui-contract --json
penflow export-semantic-tree examples/full/flow-ui-contract --out /tmp/semantic-ui-tree.json --json
penflow validate-semantic-tree /tmp/semantic-ui-tree.json --json
penflow draft-pen-from-tree /tmp/semantic-ui-tree.json --out /tmp/ui.pen --json
penflow validate-pen /tmp/ui.pen --json
penflow export-expected /tmp/ui.pen -o /tmp/expected-ui-tree.json --json
penflow enrich-pen examples/legacy/ui.pen /tmp/semantic-ui-tree.json --out /tmp/ui.enriched.pen --json
penflow validate-pen /tmp/ui.enriched.pen --json
penflow reverse-pen examples/legacy/ui.pen --out /tmp/reverse-output --json
penflow validate-semantic-tree /tmp/reverse-output/semantic-ui-tree.json --json
penflow validate-actual examples/full/actual-ui-tree.json --schema --json
penflow compare-tree /tmp/expected-ui-tree.json examples/full/actual-ui-tree.json --out /tmp/compare.json --markdown /tmp/compare.md --json
penflow review-report /tmp/compare.json --out /tmp/review.md
penflow fix-report /tmp/compare.json --out /tmp/fix.md
```

## Full Demo Mode

Use for a reproducible local fixture.

```bash
penflow demo --out examples/full --json
penflow validate-semantic-tree examples/full/semantic-ui-tree.json --json
penflow validate-pen examples/full/ui.pen --json
penflow validate-actual examples/full/actual-ui-tree.json --schema --json
penflow compare-tree examples/full/expected-ui-tree.json examples/full/actual-ui-tree.json --out /tmp/penflow-compare.json --markdown /tmp/penflow-compare.md --json
```

## Review Mode

1. Run `penflow review-report compare-report.json --out review.md` for deterministic Markdown.
2. **Read** `compare-report.json`, `review.md`, and optional `compare-report.md`.
3. **Read** expected and actual UI trees.
4. If screenshots are provided, inspect them as supporting evidence only.
5. Explain each issue by `semantic_id`, severity, likely cause, and whether the fix belongs in code, `.pen`, or upstream actual-tree extraction.

## Fix Mode

1. Run `penflow fix-report compare-report.json --out fix.md` for deterministic fix suggestions.
2. Fix deterministic errors first: missing nodes, role mismatch, invalid context, broken bindings.
3. Apply code or `.pen` changes only when the report identifies a stable `semantic_id`.
4. Re-run `validate-pen`, `validate-actual --schema`, and `compare-tree`.
5. Stop with the remaining report if the issue requires a runtime artifact not available locally.

## cc-hub Sync

This skill is project-local under `.agent-sync/skills/penflow/` and is ready for cc-hub/agent-sync symlink management.
