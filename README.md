# Penflow

Penflow is a deterministic Python CLI for Pencil `.pen` design contracts. It parses `.pen` JSON, validates `context`, exports expected UI trees, validates external actual UI trees, compares both trees structurally, writes JSON/Markdown reports, and generates simple screen/code artifacts.

## Install

```bash
python -m pip install -e ".[dev]"
```

## Core Commands

```bash
penflow inspect examples/demo/ui.pen
penflow validate-pen examples/demo/ui.pen
penflow export-expected examples/demo/ui.pen -o expected-ui-tree.json
penflow validate-actual examples/demo/actual-ui-tree.json [--schema]
penflow validate-flow-specs examples/full/flow-ui-contract --json
penflow export-semantic-tree path/to/flow-ui-contract --out semantic-ui-tree.json
penflow validate-semantic-tree semantic-ui-tree.json --json
penflow draft-pen-from-tree semantic-ui-tree.json --out ui.pen --json
penflow enrich-pen existing-ui.pen semantic-ui-tree.json --out ui.enriched.pen --json
penflow map-pencil-context ui.pen semantic-ui-tree.json --out pencil-context-map.json --json
penflow reverse-pen ui.pen --out reverse-output --json
penflow detect-drift path/to/flow-ui-contract semantic-ui-tree.json ui.pen --out drift-report.json --markdown drift-report.md --json
penflow code-ir --from-context ui.pen --flow-id checkout --flow-name "Checkout flow" --out code-ir.json
penflow compare-tree expected-ui-tree.json examples/demo/actual-ui-tree.json --markdown compare-report.md
penflow review-report compare-report.json --out review.md
penflow fix-report compare-report.json --out fix.md
penflow demo --out examples/full
```

### Three Trees

Penflow reasons about three distinct UI tree contracts. Each has a different producer and a different lifecycle phase. **Penflow itself never executes a runtime** — it validates and compares trees that other producers hand to it.

| Tree | Lifecycle | Producer | Consumer | Contract |
|---|---|---|---|---|
| [`semantic-ui-tree.json`](penflow/schemas/semantic-ui-tree.schema.json) | **BEFORE-CODE** (design intent) | Penflow, parsed from `flow-ui-contract/*.md` (features 028–030) | `draft-pen-from-tree`, `enrich-pen`, `detect-drift` | semantic schema |
| `expected-ui-tree.json` | **DESIGN-DERIVED** (post-design) | Penflow, derived from `.pen` + Pencil context (feature 006) | `compare-tree` | pre-existing |
| [`actual-ui-tree.json`](penflow/schemas/actual-ui-tree.schema.json) | **AFTER-CODE** (runtime) | **External** runtime adapter (SwiftUI / React / Rust / …, feature 038) | `validate-actual`, `compare-tree` | **C12** |

Pass `--schema` to `penflow validate-actual` to additionally run the JSON Schema (draft 2020-12) check on top of the structural validator.

### Semantic Tree Formation

Agents normally should not hand-write `semantic-ui-tree.json`; they should write flow/screen specs and run `penflow export-semantic-tree`. The formation rules are documented in **Read** [`.agent-sync/skills/flow-ui-contract/references/semantic-ui-tree.md`](.agent-sync/skills/flow-ui-contract/references/semantic-ui-tree.md): flow specs become `flows[]`, screen specs become `screens[]`, visible hierarchy becomes recursive semantic nodes, and business context becomes `intent`, `binding`, `entity`, `states`, `validations`, `side_effects`, `test_id`, and `source_map`.

### Runtime Adapter Guides

Adapter conformance docs (**contract C13**, feature 038) live under [`docs/adapters/`](docs/adapters/) and tell external producers in three target stacks — [Web DOM](docs/adapters/web-dom.md), [SwiftUI + XCTest](docs/adapters/swiftui-xctest.md), and [React Native](docs/adapters/react-native.md) — how to emit an `actual-ui-tree.json` (contract C12) that `penflow validate-actual --schema` accepts on the first try. Each guide ships a deterministic example fixture under [`examples/adapters/<stack>/actual-ui-tree.json`](examples/adapters/). Penflow ships **zero runtime code** for these stacks — it never launches a browser, a simulator, or the Metro bundler.

### Full Demo

Run `penflow demo --out examples/full` to regenerate the contract **C14** fixture. Use [`examples/full/`](examples/full/) to inspect the complete chain: flow specs, semantic tree, enriched Pencil file, expected tree, code IR, actual-tree fixture, compare report, review report, and fix report.

### LLM Workflow Sequences

Install the package first so the `penflow` console script is available.

#### Forward

Start from flow/screen specs, create a semantic tree, draft a Pencil file, validate it, then produce design/code handoff artifacts.

```bash
penflow validate-flow-specs examples/full/flow-ui-contract --json
penflow export-semantic-tree examples/full/flow-ui-contract --out semantic-ui-tree.json --json
penflow validate-semantic-tree semantic-ui-tree.json --json
penflow draft-pen-from-tree semantic-ui-tree.json --out ui.pen --json
penflow validate-pen ui.pen --json
penflow export-expected ui.pen --out expected-ui-tree.json --json
penflow code-ir --from-context ui.pen --semantic-tree semantic-ui-tree.json --flow-id checkout --flow-name "Checkout flow" --out code-ir.json --json
```

#### Enrichment

Start from an existing visual `.pen`, inject semantic context, preserve layout, validate, and generate expected/code IR artifacts.

```bash
penflow export-semantic-tree examples/full/flow-ui-contract --out semantic-ui-tree.json --json
penflow validate-semantic-tree semantic-ui-tree.json --json
penflow enrich-pen examples/full/ui.visual.pen semantic-ui-tree.json --out ui.enriched.pen --json
penflow map-pencil-context ui.enriched.pen semantic-ui-tree.json --out pencil-context-map.json --json
penflow validate-pen ui.enriched.pen --json
penflow export-expected ui.enriched.pen --out expected-ui-tree.json --json
penflow code-ir --from-context ui.enriched.pen --semantic-tree semantic-ui-tree.json --context-map pencil-context-map.json --flow-id checkout --flow-name "Checkout flow" --out code-ir.json --json
```

#### Reverse

Start from legacy Pencil, recover flow/screen specs and a semantic tree, then validate the recovered contract.

```bash
penflow reverse-pen examples/full/ui.pen --out reverse-output --enrich --json
penflow validate-semantic-tree reverse-output/semantic-ui-tree.json --json
penflow validate-pen reverse-output/ui.enriched.pen --json
```

`reverse-pen --out <dir>` writes a directory containing `semantic-ui-tree.json` and `flow-ui-contract/`; validate `<dir>/semantic-ui-tree.json`, not the directory path itself.
Reverse output marks missing business logic as `[NEEDS CLARIFICATION]`; do not invent unknown validations, side effects, or state transitions.

#### Post-Implementation Compare

After implementation, an external runtime adapter writes `actual-ui-tree.json`. Penflow validates and compares that file; it does not launch or inspect the running app.

```bash
penflow validate-actual actual-ui-tree.json --schema --json
penflow compare-tree expected-ui-tree.json actual-ui-tree.json --out compare-report.json --markdown compare-report.md --json
penflow review-report compare-report.json --out review-report.md
penflow fix-report compare-report.json --out fix-report.md
```

#### Regression

Run the contract **C16** regression proof with pytest, then reproduce the final CLI chain on the stable fixtures.

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

`/tmp/reverse-output` is a reverse output directory; its semantic tree lives at `/tmp/reverse-output/semantic-ui-tree.json` and recovered flow specs live under `/tmp/reverse-output/flow-ui-contract/`.

#### Full Demo

```bash
penflow demo --out examples/full --json
penflow validate-semantic-tree examples/full/semantic-ui-tree.json --json
penflow validate-pen examples/full/ui.pen --json
penflow validate-actual examples/full/actual-ui-tree.json --schema --json
penflow compare-tree examples/full/expected-ui-tree.json examples/full/actual-ui-tree.json --out /tmp/penflow-compare.json --markdown /tmp/penflow-compare.md --json
```

## Contract

- `.pen` stays JSON-first and runtime-agnostic.
- `context` carries semantic design intent: `semantic_id`, `role`, `intent`, `binding`, `repeat`, `entity`, `variant`, `test_id`, `tolerance`.
- Runtime frameworks provide actual UI trees; Penflow validates and compares those trees.
- The primary validation is structural and semantic, not pixel-perfect.
- Demo `.pen` files use Pencil document schema `2.11` with context shorthand strings so they can be opened in Pencil and parsed by Penflow.

## Local Skill

**Read** [`.agent-sync/skills/penflow/SKILL.md`](.agent-sync/skills/penflow/SKILL.md) to use the project-local skill interface. It is stored under `.agent-sync/skills/` so cc-hub/agent-sync can symlink it when requested.

**Read** [`.agent-sync/skills/flow-ui-contract/SKILL.md`](.agent-sync/skills/flow-ui-contract/SKILL.md) to capture flow/screen behavior around Pencil artifacts. Invoke the installed skill as `flow-ui-contract`; legacy wording such as `specify flows` should route there, but no separate `specify-flows` slash command is installed. It writes validated `flow-ui-contract/flows/*.md` and `flow-ui-contract/screens/*.md` files, and reports `fresh` / `stale` / `unspecified` coverage with `python .agent-sync/skills/flow-ui-contract/validator.py --status --target <target>`.

The pre-Pencil semantic contract is defined in [`penflow/schemas/semantic-ui-tree.schema.json`](penflow/schemas/semantic-ui-tree.schema.json), with a deterministic example at [`examples/demo/semantic-ui-tree.json`](examples/demo/semantic-ui-tree.json). Export it from flow/screen Markdown with `penflow export-semantic-tree path/to/flow-ui-contract --out semantic-ui-tree.json`, validate it with `penflow validate-semantic-tree semantic-ui-tree.json --json`, then create a structural Pencil draft with `penflow draft-pen-from-tree semantic-ui-tree.json --out ui.pen --json`, enrich an existing Pencil file with `penflow enrich-pen existing-ui.pen semantic-ui-tree.json --out ui.enriched.pen --json`, emit an explicit mapping artifact with `penflow map-pencil-context ui.pen semantic-ui-tree.json --out pencil-context-map.json --json`, reverse an existing Pencil file with `penflow reverse-pen ui.pen --out reverse-output --json`, or report drift with `penflow detect-drift path/to/flow-ui-contract semantic-ui-tree.json ui.pen --out drift-report.json --markdown drift-report.md --json`. This schema is distinct from post-implementation actual UI trees.

## Conventions

Project conventions are generated from the LiveSpec stack in [`.conventions/index.md`](.conventions/index.md) and [`.conventions/manifest.yaml`](.conventions/manifest.yaml).
The stack refresh also installs the generated Python pre-commit hook in [`.githooks/pre-commit`](.githooks/pre-commit) and GitHub Actions workflows in [`.github/workflows/ci.yml`](.github/workflows/ci.yml) and [`.github/workflows/security.yml`](.github/workflows/security.yml).
