---
name: penflow
description: Use the Penflow CLI for Pencil .pen context validation, semantic/expected/actual UI-tree workflows, codegen handoff, reports, and deterministic visual-fix review.
---

# Penflow Skill

Use this skill when a task mentions Penflow, Pencil `.pen`, flow specs, `semantic-ui-tree.json`, Pencil `context`, `expected-ui-tree.json`, `actual-ui-tree.json`, code IR, compare reports, or structural design/runtime validation.

## Purpose

Penflow is a deterministic, runtime-agnostic CLI that connects product flow intent, Pencil design contracts, codegen handoff data, and post-implementation runtime verification.

Strict v2 uses `flow-ui-contract/contract.json` as the canonical machine contract. Markdown/YAML flow docs are human documentation or explicit migration input only.

Penflow owns file validation and tree comparison only:
- `semantic-ui-tree.json`: before-code intent exported from strict `flow-ui-contract/contract.json` (legacy `flow-ui-contract/*.md` docs remain migration/documentation input).
- `expected-ui-tree.json`: design-derived tree exported from contextualized `.pen`.
- `actual-ui-tree.json`: after-code runtime tree produced by an external adapter.

Penflow does **not** run browsers, Xcode, simulators, Playwright, React Native, Metro, or app builds. External adapters produce `actual-ui-tree.json`; Penflow validates and compares it.

## Strict by Default (Feature 049 / C24)

- Warning-severity issues exit 1 on every validating command (`validate-*`, `compare-tree`, `detect-drift`, `lint-tokens`, `check-consistency`, `export-expected`, `ci`); errors always exit 1. The global `--lenient` flag (before or after the subcommand) makes warnings non-blocking.
- `compare-tree`/`ci` default threshold is 0.98; `--lenient` restores 0.9; explicit `--threshold` always wins.
- `export-semantic-tree`, `reverse-pen`, `extract-tokens` report issues and exit 1 on them: `reverse.clarification_needed` per generated artifact still containing `[NEEDS CLARIFICATION]`, `tokens.value.unparsed` for uninterpretable token values.
- `detect-drift` issues carry `blocking: bool` (`BLOCKING_DRIFT_CODES`: `drift.semantic_tree_invalid`, `drift.semantic_node_missing_in_pen`, `drift.pencil_context_obsolete`, `drift.clarification_marker`); summary has a `blocking` count; status adds `BLOCKED`. Blocking issues exit 1 even with `--lenient` — gate on `summary.blocking == 0`.
- Surfaced coercions: `pen.bbox.invalid` warning for non-keyword string bbox values (`fill_container`/`fit_content(...)` exempt) via `validate-pen`/`inspect`; `theme.value.unparsed` warning for unparsable theme dimensions via `lint-tokens`.
- `jsonschema>=4` is a hard dependency (no minimal fallbacks).

## Tree Contracts

The LLM should not hand-write production trees, but it must understand their contracts before debugging or explaining results:

- `semantic-ui-tree.json` is formed by `penflow export-semantic-tree` from `flow-ui-contract/contract.json`. Flow specs become `flows[]`; screen specs become `screens[]` in legacy docs; v2 contract objects become the same tree shape with recursive semantic nodes carrying `semantic_id`, `role`, `intent`, `binding`, `entity`, states, validations, side effects, source maps, and test ids.
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
- Before any UI flow, Pencil draft, mockup, or visual validation work, **Read** [`../../../.conventions/index.md`](../../../.conventions/index.md) and load all matching design domains. UI work must use the convention-defined view/component patterns, not only theme colors.

## Mode Selection

| User intent | Mode |
|---|---|
| "Integrate Penflow into my existing project" | Project integration mode |
| "Generate `.pen` / code IR from flow specs" | Forward mode |
| "Enrich an existing Pencil mockup with business context" | Pencil enrichment mode |
| "Reconstruct flows from legacy Pencil" | Reverse mode |
| "Compare implementation with design contract" | Post-implementation compare mode |
| "Show me the whole chain" | Full demo mode |
| "Generate, audit, or optimize Pencil mockups" | Mockup Factory mode |

## Project Integration Mode

Use when a user already has an application repository and asks how to adopt Penflow, where to store artifacts, how to migrate existing Pencil mockups, or how agents should consume Penflow outputs.

**Read** [`../../../docs/project-integration.md`](../../../docs/project-integration.md). It covers the recommended `penflow/` workspace, forward adoption, existing-Pencil enrichment, legacy reverse migration, code IR handoff, runtime `actual-ui-tree.json` verification, and CI gate.

## Mockup Factory Mode

Use when a user asks for mockup generation, audit, optimization, or `/mockup-factory` on Pencil `.pen` files.

**Read** [`../mockup-factory/SKILL.md`](../mockup-factory/SKILL.md). It is the Penflow-local canonical workflow for guided UX/UI optimization. It requires `flow-ui-contract`, `semantic-ui-tree.json`, `theme.css`, `.pen`, `pencil-context-map.json`, `expected-ui-tree.json`, and `detect-drift` as deterministic anchors before any Pencil/Codex audit loop. **Read** [`../mockup-factory/references/visual-validation.md`](../mockup-factory/references/visual-validation.md) before applying the Visual Evidence Gate: layout snapshot, screenshot inspection, PNG export, manifest, and visual report when a renderer is available. UX/UI improvements must be tied to audited checklist items and `screen_id` / `semantic_id` / `pencil_node_id` when available.

## Forward Mode

Use when `flow-ui-contract/contract.json` is the source of truth. Keep Markdown examples as docs-only/migration references.

```bash
penflow validate-flow-contract examples/full/flow-ui-contract/contract.json --json
penflow export-semantic-tree examples/full/flow-ui-contract/contract.json --out semantic-ui-tree.json --json
penflow validate-semantic-tree semantic-ui-tree.json --json
penflow draft-pen-from-tree semantic-ui-tree.json --out ui.pen --theme-css theme.css --json
penflow lint-tokens ui.pen --theme-css theme.css --out token-lint-report.json --json
penflow validate-pen ui.pen --json
penflow export-expected ui.pen --out expected-ui-tree.json --json
penflow check-consistency expected-ui-tree.json --out consistency-report.json --json
penflow code-ir --from-context ui.pen --semantic-tree semantic-ui-tree.json --contract examples/full/flow-ui-contract/contract.json --flow-id checkout --flow-name "Checkout flow" --out code-ir.json --json
penflow validate-code-ir code-ir.json --json
```

Legacy route phrase for old docs/tests: `penflow export-semantic-tree examples/full/flow-ui-contract --out semantic-ui-tree.json --json`.

## Pencil Enrichment Mode

Use when a visual Pencil file already exists and must keep its layout.

```bash
penflow validate-flow-contract examples/full/flow-ui-contract/contract.json --json
penflow export-semantic-tree examples/full/flow-ui-contract/contract.json --out semantic-ui-tree.json --json
penflow validate-semantic-tree semantic-ui-tree.json --json
penflow enrich-pen examples/full/ui.visual.pen semantic-ui-tree.json --out ui.enriched.pen --json
penflow map-pencil-context ui.enriched.pen semantic-ui-tree.json --out pencil-context-map.json --json
penflow validate-pen ui.enriched.pen --json
penflow export-expected ui.enriched.pen --out expected-ui-tree.json --json
penflow code-ir --from-context ui.enriched.pen --semantic-tree semantic-ui-tree.json --context-map pencil-context-map.json --contract examples/full/flow-ui-contract/contract.json --flow-id checkout --flow-name "Checkout flow" --out code-ir.json --json
```

Preserve existing visual layout. Treat ambiguous or unmapped nodes from `map-pencil-context` as review work, not as permission to overwrite visual design.

## Reverse Mode

Use when a legacy `.pen` exists before flow specs.

```bash
penflow reverse-pen examples/full/ui.pen --out reverse-output --enrich --json
penflow validate-semantic-tree reverse-output/semantic-ui-tree.json --json
penflow validate-pen reverse-output/ui.enriched.pen --json
```

`reverse-pen --out <dir>` writes a directory containing `semantic-ui-tree.json` and `flow-ui-contract/`; validate `<dir>/semantic-ui-tree.json`, not the directory path itself.
Reverse mode marks missing business rules as `[NEEDS CLARIFICATION]`. Do not invent backend side effects, validations, state transitions, or access rules.
Strict default: `reverse-pen` exits 1 while clarification markers remain; use `--lenient` for scripted chains, then resolve the markers.

## Post-Implementation Compare Mode

Use after an external runtime adapter writes `actual-ui-tree.json`.

```bash
penflow validate-actual actual-ui-tree.json --schema --json
penflow compare-tree expected-ui-tree.json actual-ui-tree.json --out compare-report.json --json
penflow review-report compare-report.json --out review-report.json --json
penflow fix-report compare-report.json --out fix-report.json --json
penflow validate-report compare-report.json --schema --json
```

If `validate-actual` fails, fix the external adapter output first. Penflow does not inspect the running app.

## Regression Mode

Use for CI/regression coverage of contract C16. The proof is pytest-first, with the final CLI chain reproducible on `examples/full` and `examples/legacy`.

```bash
python3 -m pytest -q
penflow validate-flow-contract examples/full/flow-ui-contract/contract.json --json
penflow export-semantic-tree examples/full/flow-ui-contract/contract.json --out /tmp/semantic-ui-tree.json --json
penflow validate-semantic-tree /tmp/semantic-ui-tree.json --json
penflow draft-pen-from-tree /tmp/semantic-ui-tree.json --out /tmp/ui.pen --theme-css examples/demo/theme.css --json
penflow validate-pen /tmp/ui.pen --json
penflow export-expected /tmp/ui.pen -o /tmp/expected-ui-tree.json --json
penflow enrich-pen examples/legacy/ui.pen /tmp/semantic-ui-tree.json --out /tmp/ui.enriched.pen --json
penflow validate-pen /tmp/ui.enriched.pen --json
penflow reverse-pen examples/legacy/ui.pen --out /tmp/reverse-output --lenient --json
penflow validate-semantic-tree /tmp/reverse-output/semantic-ui-tree.json --json
penflow validate-actual examples/full/actual-ui-tree.json --schema --json
penflow compare-tree /tmp/expected-ui-tree.json examples/full/actual-ui-tree.json --out /tmp/compare.json --json
penflow review-report /tmp/compare.json --out /tmp/review.json --json
penflow fix-report /tmp/compare.json --out /tmp/fix.json --json
```

`/tmp/reverse-output` is a reverse output directory; its semantic tree lives at `/tmp/reverse-output/semantic-ui-tree.json` and recovered flow specs live under `/tmp/reverse-output/flow-ui-contract/`.

## Full Demo Mode

Use for a reproducible local fixture.

```bash
penflow demo --out examples/full --json
penflow validate-semantic-tree examples/full/semantic-ui-tree.json --json
penflow validate-pen examples/full/ui.pen --json
penflow validate-actual examples/full/actual-ui-tree.json --schema --json
penflow compare-tree examples/full/expected-ui-tree.json examples/full/actual-ui-tree.json --out /tmp/penflow-compare.json --json
```

## Review Mode

1. Run `penflow review-report compare-report.json --out review-report.json --json` for deterministic JSON.
2. **Read** `compare-report.json` and `review-report.json`.
3. **Read** expected and actual UI trees.
4. If screenshots are provided, inspect them as supporting evidence only.
5. Explain each issue by `semantic_id`, severity, likely cause, and whether the fix belongs in code, `.pen`, or upstream actual-tree extraction.

## Fix Mode

1. Run `penflow fix-report compare-report.json --out fix-report.json --json` for deterministic fix suggestions.
2. Fix deterministic errors first: missing nodes, role mismatch, invalid context, broken bindings.
3. Apply code or `.pen` changes only when the report identifies a stable `semantic_id`.
4. Re-run `validate-pen`, `validate-actual --schema`, and `compare-tree`.
5. Stop with the remaining report if the issue requires a runtime artifact not available locally.

## cc-hub Sync

This skill is project-local under `.agent-sync/skills/penflow/` and is ready for cc-hub/agent-sync symlink management.
