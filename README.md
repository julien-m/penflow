# Penflow

Penflow is a deterministic Python CLI for Pencil `.pen` design contracts. It parses `.pen` JSON, validates `context`, exports expected UI trees, validates external actual UI trees, compares both trees structurally, writes JSON reports, and generates simple screen/code artifacts.

## JSON-Only Contract v2

`flow-ui-contract/contract.json` is the canonical strict v2 business contract. Markdown/YAML flow files are documentation or explicit migration input only; strict validation, semantic export, `.pen` contract checks, code IR, and report handoff use JSON artifacts.

## Strict by Default (Breaking Change, Feature 049 / C24)

Penflow exits non-zero on **warning-severity issues by default**. Errors always fail; warnings fail unless you pass the global `--lenient` flag (accepted before or after the subcommand on every validating command):

- Applies to `validate-pen`, `validate-flow-specs`, `validate-flow-contract`, `validate-semantic-tree`, `validate-actual`, `validate-flow`, `validate-screen`, `validate-code-ir`, `validate-report`, `compare-tree`, `detect-drift`, `lint-tokens`, `check-consistency`, `export-expected`, `ci`.
- `compare-tree` and `ci` default threshold is **0.98** (was 0.9). `--lenient` restores the 0.9 default; an explicit `--threshold` always wins.
- `export-semantic-tree`, `reverse-pen`, and `extract-tokens` now report issues and exit 1 on them (previously always exit 0). `reverse-pen` flags every generated artifact still containing `[NEEDS CLARIFICATION]` as `reverse.clarification_needed`; `extract-tokens` flags uninterpretable values as `tokens.value.unparsed`.
- `detect-drift` carries blocking data: each issue has a `blocking` boolean (`BLOCKING_DRIFT_CODES` = `drift.semantic_tree_invalid`, `drift.semantic_node_missing_in_pen`, `drift.pencil_context_obsolete`, `drift.clarification_marker`), the summary has a `blocking` count, and the report status gains `BLOCKED`. **Blocking issues exit 1 even with `--lenient`.**
- Silent coercions now warn: non-keyword string bbox values emit `pen.bbox.invalid` (via `validate-pen`/`inspect`; Pencil sizing keywords `fill_container`/`fit_content(...)` are exempt), and unparsable theme dimensions emit `theme.value.unparsed` (via `lint-tokens`).
- `jsonschema>=4` is a hard dependency; the minimal fallback validators were removed.

Migration: append `--lenient` to any pipeline that tolerated warnings, or fix the warnings (recommended).

## Install

```bash
python3 -m pip install -e ".[dev]"
```

## Core Commands

```bash
penflow inspect examples/demo/ui.pen
penflow validate-pen examples/demo/ui.pen
penflow export-expected examples/demo/ui.pen -o expected-ui-tree.json
penflow check-consistency expected-ui-tree.json --out consistency-report.json [--group-by role|role+intent]
penflow validate-actual examples/demo/actual-ui-tree.json [--schema]
penflow validate-flow-contract examples/full/flow-ui-contract/contract.json --json
penflow export-semantic-tree path/to/flow-ui-contract/contract.json --out semantic-ui-tree.json
penflow validate-semantic-tree semantic-ui-tree.json --json
penflow draft-pen-from-tree semantic-ui-tree.json --out ui.pen --theme-css theme.css --json
penflow lint-tokens ui.pen --theme-css theme.css --out token-lint-report.json --json
penflow enrich-pen existing-ui.pen semantic-ui-tree.json --out ui.enriched.pen --json
penflow map-pencil-context ui.pen semantic-ui-tree.json --out pencil-context-map.json --json
penflow migrate-flow-md-to-contract-json flow-ui-contract --out flow-ui-contract/contract.json --json
penflow reverse-pen ui.pen --out reverse-output --json
penflow detect-drift path/to/flow-ui-contract/contract.json semantic-ui-tree.json ui.pen --out drift-report.json --json
penflow code-ir --from-context ui.pen --contract flow-ui-contract/contract.json --flow-id checkout --flow-name "Checkout flow" --out code-ir.json
penflow validate-code-ir code-ir.json --json
penflow compare-tree expected-ui-tree.json examples/demo/actual-ui-tree.json --out compare-report.json --json
penflow review-report compare-report.json --out review-report.json --json
penflow fix-report compare-report.json --out fix-report.json --json
penflow validate-report review-report.json --schema --json
penflow demo --out examples/full
```

### Three Trees

Penflow reasons about three distinct UI tree contracts. Each has a different producer and a different lifecycle phase. **Penflow itself never executes a runtime** — it validates and compares trees that other producers hand to it.

| Tree | Lifecycle | Producer | Consumer | Contract |
|---|---|---|---|---|
| [`semantic-ui-tree.json`](penflow/schemas/semantic-ui-tree.schema.json) | **BEFORE-CODE** (design intent) | Penflow, exported from strict `contract.json` v2 (Markdown is docs/migration only) | `draft-pen-from-tree`, `enrich-pen`, `detect-drift` | semantic schema |
| `expected-ui-tree.json` | **DESIGN-DERIVED** (post-design) | Penflow, derived from `.pen` + Pencil context (feature 006) | `compare-tree` | pre-existing |
| [`actual-ui-tree.json`](penflow/schemas/actual-ui-tree.schema.json) | **AFTER-CODE** (runtime) | **External** runtime adapter (SwiftUI / React / Rust / …, feature 038) | `validate-actual`, `compare-tree` | **C12** |

Pass `--schema` to `penflow validate-actual` to additionally run the JSON Schema (draft 2020-12) check on top of the structural validator.

### Semantic Tree Formation

Agents normally should not hand-write `semantic-ui-tree.json`; they should author or migrate `flow-ui-contract/contract.json` and run `penflow export-semantic-tree`. The legacy formation rules are documented in **Read** [`.agent-sync/skills/flow-ui-contract/references/semantic-ui-tree.md`](.agent-sync/skills/flow-ui-contract/references/semantic-ui-tree.md): flow specs become `flows[]`, screen specs become `screens[]`, visible hierarchy becomes recursive semantic nodes, and business context becomes `intent`, `binding`, `entity`, `states`, `validations`, `side_effects`, `test_id`, and `source_map`.

### Runtime Adapter Guides

Adapter conformance docs (**contract C13**, feature 038) live under [`docs/adapters/`](docs/adapters/) and tell external producers in three target stacks — [Web DOM](docs/adapters/web-dom.md), [SwiftUI + XCTest](docs/adapters/swiftui-xctest.md), and [React Native](docs/adapters/react-native.md) — how to emit an `actual-ui-tree.json` (contract C12) that `penflow validate-actual --schema` accepts on the first try. Each guide ships a deterministic example fixture under [`examples/adapters/<stack>/actual-ui-tree.json`](examples/adapters/). Penflow ships **zero runtime code** for these stacks — it never launches a browser, a simulator, or the Metro bundler.

### Full Demo

Run `penflow demo --out examples/full` to regenerate the contract **C14/C20** fixture. Use [`examples/full/`](examples/full/) to inspect the complete chain: `contract.json`, documentation flow specs, semantic tree, enriched Pencil file, expected tree, code IR, actual-tree fixture, compare report, review report, and fix report.

### Existing Project Integration

**Read** [`docs/project-integration.md`](docs/project-integration.md) when adding Penflow to an existing app repository. It explains the recommended `penflow/` workspace layout, forward adoption, Pencil enrichment, legacy reverse migration, implementation handoff through `code-ir.json`, runtime `actual-ui-tree.json` verification, and a minimal CI gate.

### Guided Mockup Optimization

**Read** [`.agent-sync/skills/mockup-factory/SKILL.md`](.agent-sync/skills/mockup-factory/SKILL.md) when generating, auditing, or optimizing Pencil mockups. The Penflow-local Mockup Factory uses `flow-ui-contract`, `semantic-ui-tree.json`, `.pen`, `pencil-context-map.json`, `expected-ui-tree.json`, and `detect-drift` reports as deterministic anchors, then gates PASS on both contract coherence and critical UX/UI quality.

Before final PASS, Mockup Factory also runs the Visual Evidence Gate. **Read** [`.agent-sync/skills/mockup-factory/references/visual-validation.md`](.agent-sync/skills/mockup-factory/references/visual-validation.md) before applying it. When Pencil rendering is available, the gate must inspect a screenshot, export PNGs, and write `.mockup-validation/visual-evidence/manifest.json` plus `visual-report.json`; otherwise the status is `BLOCKED_VISUAL_NOT_RUN` or escalated rather than silently passing structural-only validation.

### LLM Workflow Sequences

Install the package first so the `penflow` console script is available.

#### Forward

Start from `flow-ui-contract/contract.json`, create a semantic tree, draft a theme-aware Pencil file, validate it, then produce design/code handoff artifacts.

```bash
penflow validate-flow-contract examples/full/flow-ui-contract/contract.json --json
penflow export-semantic-tree examples/full/flow-ui-contract/contract.json --out semantic-ui-tree.json --json
penflow validate-semantic-tree semantic-ui-tree.json --json
penflow draft-pen-from-tree semantic-ui-tree.json --out ui.pen --theme-css theme.css --json
penflow validate-pen ui.pen --json
penflow export-expected ui.pen --out expected-ui-tree.json --json
penflow code-ir --from-context ui.pen --semantic-tree semantic-ui-tree.json --contract examples/full/flow-ui-contract/contract.json --flow-id checkout --flow-name "Checkout flow" --out code-ir.json --json
penflow validate-code-ir code-ir.json --json
```

Legacy Markdown-only docs may still mention `penflow export-semantic-tree examples/full/flow-ui-contract --out semantic-ui-tree.json --json`; strict v2 uses `contract.json`.

#### Enrichment

Start from an existing visual `.pen`, inject semantic context, preserve layout, validate, and generate expected/code IR artifacts.

```bash
penflow export-semantic-tree examples/full/flow-ui-contract/contract.json --out semantic-ui-tree.json --json
penflow validate-semantic-tree semantic-ui-tree.json --json
penflow enrich-pen examples/full/ui.visual.pen semantic-ui-tree.json --out ui.enriched.pen --json
penflow map-pencil-context ui.enriched.pen semantic-ui-tree.json --out pencil-context-map.json --json
penflow validate-pen ui.enriched.pen --json
penflow export-expected ui.enriched.pen --out expected-ui-tree.json --json
penflow code-ir --from-context ui.enriched.pen --semantic-tree semantic-ui-tree.json --context-map pencil-context-map.json --contract examples/full/flow-ui-contract/contract.json --flow-id checkout --flow-name "Checkout flow" --out code-ir.json --json
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
Strict default: `reverse-pen` exits 1 while clarification markers remain (`reverse.clarification_needed`); pass `--lenient` to keep scripted chains green, then resolve the markers.

#### Post-Implementation Compare

After implementation, an external runtime adapter writes `actual-ui-tree.json`. Penflow validates and compares that file; it does not launch or inspect the running app.

`compare-tree` checks presence, role, text, hierarchy, order, bbox (±`bbox_px`), colors, radius (±`radius_px`), typography (±`font_px`), and — feature 048 — layout properties: `layout` and `alignItems` exact-match (`node.visual.layout`, `node.visual.alignItems`), `gap` and `padding` within ±`spacing_px` (default 2; `node.visual.gap`, `node.visual.padding`). Padding forms are normalized (`16` ≡ `[16, 16]` ≡ `[16, 16, 16, 16]`). Tolerances are overridable per node via `context.tolerance` (e.g. `tolerance: {spacing_px: 4}`); absent keys are never compared, so pre-048 trees stay green.

```bash
penflow validate-actual actual-ui-tree.json --schema --json
penflow compare-tree expected-ui-tree.json actual-ui-tree.json --out compare-report.json --json
penflow review-report compare-report.json --out review-report.json --json
penflow fix-report compare-report.json --out fix-report.json --json
penflow validate-report compare-report.json --schema --json
```

#### Regression

Run the contract **C16** regression proof with pytest, then reproduce the final CLI chain on the stable fixtures.

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

#### Full Demo

```bash
penflow demo --out examples/full --json
penflow validate-semantic-tree examples/full/semantic-ui-tree.json --json
penflow validate-pen examples/full/ui.pen --json
penflow validate-actual examples/full/actual-ui-tree.json --schema --json
penflow compare-tree examples/full/expected-ui-tree.json examples/full/actual-ui-tree.json --out /tmp/penflow-compare.json --json
```

## Contract

- `.pen` stays JSON-first and runtime-agnostic.
- `context` carries semantic design intent: `semantic_id`, `role`, `intent`, `binding`, `repeat`, `entity`, `variant`, `test_id`, `tolerance`.
- Runtime frameworks provide actual UI trees; Penflow validates and compares those trees.
- The primary validation is structural and semantic, not pixel-perfect.
- Demo `.pen` files use Pencil document schema `2.11` with context shorthand strings so they can be opened in Pencil and parsed by Penflow.

## Local Skill

**Read** [`.agent-sync/skills/penflow/SKILL.md`](.agent-sync/skills/penflow/SKILL.md) to use the project-local skill interface. It is stored under `.agent-sync/skills/` so cc-hub/agent-sync can symlink it when requested.

**Read** [`.agent-sync/skills/flow-ui-contract/SKILL.md`](.agent-sync/skills/flow-ui-contract/SKILL.md) to capture flow/screen behavior around Pencil artifacts. Invoke the installed skill as `flow-ui-contract`; legacy wording such as `specify flows` should route there, but no separate `specify-flows` slash command is installed. It writes validated `flow-ui-contract/flows/*.md` and `flow-ui-contract/screens/*.md` files, and reports `fresh` / `stale` / `unspecified` coverage with `python3 .agent-sync/skills/flow-ui-contract/validator.py --status --target <target>`.

**Read** [`.agent-sync/skills/mockup-factory/SKILL.md`](.agent-sync/skills/mockup-factory/SKILL.md) to run the tree-aware guided UX/UI optimizer for Pencil mockups. The skill can orchestrate external Pencil/audit tooling, but Penflow Python core stays runtime-agnostic.

The pre-Pencil semantic contract is defined in [`penflow/schemas/semantic-ui-tree.schema.json`](penflow/schemas/semantic-ui-tree.schema.json), with a deterministic example at [`examples/demo/semantic-ui-tree.json`](examples/demo/semantic-ui-tree.json). Export it from `flow-ui-contract/contract.json` with `penflow export-semantic-tree path/to/flow-ui-contract/contract.json --out semantic-ui-tree.json`, validate it with `penflow validate-semantic-tree semantic-ui-tree.json --json`, then create a theme-aware Pencil draft with `penflow draft-pen-from-tree semantic-ui-tree.json --out ui.pen --theme-css theme.css --json`, enrich an existing Pencil file with `penflow enrich-pen existing-ui.pen semantic-ui-tree.json --out ui.enriched.pen --json`, emit an explicit mapping artifact with `penflow map-pencil-context ui.pen semantic-ui-tree.json --out pencil-context-map.json --json`, reverse an existing Pencil file with `penflow reverse-pen ui.pen --out reverse-output --json`, or report drift with `penflow detect-drift path/to/flow-ui-contract/contract.json semantic-ui-tree.json ui.pen --out drift-report.json --json`. This schema is distinct from post-implementation actual UI trees.

## Conventions

Project conventions are generated from the LiveSpec stack in [`.conventions/index.md`](.conventions/index.md) and [`.conventions/manifest.yaml`](.conventions/manifest.yaml).
The stack refresh also installs the generated Python pre-commit hook in [`.githooks/pre-commit`](.githooks/pre-commit) and GitHub Actions workflows in [`.github/workflows/ci.yml`](.github/workflows/ci.yml) and [`.github/workflows/security.yml`](.github/workflows/security.yml).
