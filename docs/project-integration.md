<!-- LiveSpec traceability anchors -->
<!-- @spec(FR-007) -->
<!-- @spec(FR-012) -->
<!-- @spec(FR-013) -->
<!-- @spec(FR-014) -->

# Integrating Penflow Into an Existing Project

Use this guide when an application already exists and you want Penflow to become the project-local contract layer between product intent, Pencil mockups, code generation, and runtime verification.

Start and end every Penflow task with a read-only consumer-project receipt:

```bash
penflow doctor --project . --check --json
```

Run it from the exact application subproject or pass that directory explicitly with `--project`. The selected `<consumer-project-root>` is the exact normalized directory, or an existing selector file's parent; it is never widened to the enclosing Git worktree or to the Penflow source checkout. The internal `git_root` exists only for scoped Git interrogation and transient Git metadata coordination.

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
      contract.json
      flows/
      screens/
    semantic-ui-tree.json
    ui.pen
    pencil-context-map.json
    expected-ui-tree.json
    code-ir.json
    actual-ui-tree.json
    compare-report.json
    review-report.json
    fix-report.json
```

Recommended ownership:

| Path | Commit? | Owner | Purpose |
|---|---:|---|---|
| `penflow/flow-ui-contract/contract.json` | yes | product / design / agent | Canonical strict v2 business contract. |
| `penflow/flow-ui-contract/generated-docs.json` | generated when docs enabled | Penflow | Hash-binds generated flow/screen Markdown to the canonical contract. |
| `penflow/flow-ui-contract/flows/*.md`, `screens/*.md` | generated when docs enabled | Penflow | Deterministic human projections; edit `contract.json` and regenerate. Legacy Markdown is migration-only. |
| `penflow/semantic-ui-tree.json` | yes | Penflow | Generated semantic contract from `flow-ui-contract/contract.json`. |
| `penflow/ui.pen` | yes | design / agent | The only Pencil document; active, draft and archive revisions remain inside its infinite canvas. |
| `penflow/pencil-context-map.json` | yes | Penflow | Review map for matched, ambiguous, and unmapped Pencil nodes. |
| `penflow/expected-ui-tree.json` | yes | Penflow | Design-derived baseline for runtime comparison. |
| `penflow/code-ir.json` | yes | Penflow / codegen | Handoff artifact for implementation agents. |
| `penflow/actual-ui-tree.json` | optional | app runtime adapter | Runtime observation from the implemented app. |
| `penflow/compare-report.json`, `review-report.json`, `fix-report.json` | optional | Penflow | JSON review artifacts; commit when useful for PR evidence. |

Keep one canonical `ui.pen` per selected consumer project, including large apps. Separate product areas with `logical_screen_id` values and top-level lifecycle regions inside that canvas. A collective Git worktree may hold several independent consumer projects, each selected and governed separately:

```text
my-app/
  penflow/
    flow-ui-contract/
    ui.pen
    expected-ui-tree.json
  .penflow-tmp/
    manifests/
    runs/
    receipts/
```

`ui.pen` top-level frames may declare `penflow.lifecycle` schema 1 with `state: active|draft|archive`, `logical_screen_id`, and unique `revision_id`. Each logical screen has exactly one active revision; exports ignore draft/archive regions but preserve them in the document. Unmarked legacy top-level frames are active for compatibility.

`.penflow-tmp/`, `.penflow-run/`, and `.mockup-validation/` are ignored and managed below `<consumer-project-root>`. Producer preflight reconciles cleanup-eligible completed, failed or proven-dead runs; postflight removes successful working payload only after durable outputs finalize. Do not put source files or manually managed evidence there, and do not bypass a cleanup block for live owners, unknown paths, symlinks, Git-tracked/staged data or referenced artifacts. Ancestor, sibling and repository-root `.gitignore` files are outside ownership when they are not the selected project file.

## Install and Run

For local development, install Penflow from the Penflow repository or a pinned internal package:

```bash
python3 -m pip install -e /path/to/penflow
```

Run commands from the exact application project root and use paths inside that selected boundary:

```bash
penflow doctor --project . --check --json
penflow validate-flow-contract penflow/flow-ui-contract/contract.json --json
penflow export-flow-docs penflow/flow-ui-contract/contract.json --out penflow/flow-ui-contract --json
penflow export-flow-docs penflow/flow-ui-contract/contract.json --out penflow/flow-ui-contract --check --json
```

## Path A: New Project or New Feature Area

Start with `flow-ui-contract/contract.json` and `theme.css`, then let Penflow generate the tree and themed Pencil draft.

```bash
penflow doctor --project . --check --json
penflow validate-flow-contract penflow/flow-ui-contract/contract.json --json
penflow export-semantic-tree penflow/flow-ui-contract/contract.json --out penflow/semantic-ui-tree.json --json
penflow validate-semantic-tree penflow/semantic-ui-tree.json --json
penflow draft-pen-from-tree penflow/semantic-ui-tree.json --out penflow/ui.pen --theme-css theme.css --json
penflow validate-pen penflow/ui.pen --json
penflow export-expected penflow/ui.pen --out penflow/expected-ui-tree.json --json
penflow code-ir --from-context penflow/ui.pen --semantic-tree penflow/semantic-ui-tree.json --contract penflow/flow-ui-contract/contract.json --out penflow/code-ir.json --json
penflow validate-code-ir penflow/code-ir.json --json
```

After this path:

- `flow-ui-contract/contract.json` is the canonical machine contract; Markdown/YAML are docs-only after migration;
- `semantic-ui-tree.json` is the before-code semantic contract;
- `ui.pen` is the contextualized, theme-aware Pencil file;
- `expected-ui-tree.json` is the design baseline;
- `code-ir.json` is the handoff artifact an implementation agent can read.

## Path B: Existing Pencil Mockups

Use this when designers already have a `.pen` file and you want to preserve the layout.
First perform a reviewed one-time move or import of the existing document into the canonical `penflow/ui.pen` path. Only move `design/ui.pen` when the canonical destination is absent. If `penflow/ui.pen` already exists, do not replace it: manually consolidate the intended lifecycle regions into that canonical canvas, validate it, and remove the old source only after validation passes. Confirm that the former path no longer leaves a second `.pen`; enrichment then updates the canonical canvas in place.

```bash
penflow validate-flow-contract penflow/flow-ui-contract/contract.json --json
penflow export-semantic-tree penflow/flow-ui-contract/contract.json --out penflow/semantic-ui-tree.json --json
penflow enrich-pen penflow/ui.pen penflow/semantic-ui-tree.json --out penflow/ui.pen --json
penflow map-pencil-context penflow/ui.pen penflow/semantic-ui-tree.json --out penflow/pencil-context-map.json --strict-coverage --contract penflow/flow-ui-contract/contract.json --coverage-out penflow/semantic-context-coverage.json --json
penflow validate-pen penflow/ui.pen --json
penflow export-expected penflow/ui.pen --out penflow/expected-ui-tree.json --json
penflow code-ir --from-context penflow/ui.pen --semantic-tree penflow/semantic-ui-tree.json --context-map penflow/pencil-context-map.json --contract penflow/flow-ui-contract/contract.json --out penflow/code-ir.json --json
```

Review `pencil-context-map.json` before implementation. Ambiguous or unmapped nodes mean the mockup and product intent need a human or agent decision.

## Path C: Legacy Project With Mockups but No Flows

Use reverse mode to bootstrap missing docs from an old Pencil file, then explicitly migrate/review into `contract.json`.

```bash
penflow reverse-pen penflow/ui.pen --out penflow/reverse-output --enrich --json
penflow migrate-flow-md-to-contract-json penflow/reverse-output/flow-ui-contract --out penflow/reverse-output/flow-ui-contract/contract.json --json
penflow validate-semantic-tree penflow/reverse-output/semantic-ui-tree.json --json
penflow validate-pen penflow/ui.pen --json
```

`reverse-pen --out <dir>` creates a directory. The semantic tree is `<dir>/semantic-ui-tree.json`; recovered specs are under `<dir>/flow-ui-contract/`.

Reverse/migration mode marks unknown business logic as `[NEEDS CLARIFICATION]`. Treat those markers as migration work. Strict default (feature 049): `reverse-pen` exits 1 while markers remain (`reverse.clarification_needed`); add `--lenient` to keep bootstrap scripts green until the markers are resolved. Do not let an agent invent validations, side effects, permissions, or state transitions that were not present in the source material.

Once reviewed, promote the recovered files into the project workspace:

```text
penflow/reverse-output/flow-ui-contract/ -> penflow/flow-ui-contract/
penflow/reverse-output/semantic-ui-tree.json -> penflow/semantic-ui-tree.json
```

The canonical `penflow/ui.pen` remains in place throughout reverse migration; only recovered JSON/Markdown contract artifacts move into their durable locations.

## Implementation Handoff

Give implementation agents the contextualized Pencil file and code IR:

```text
Implement the checkout flow from:
- penflow/ui.pen
- penflow/semantic-ui-tree.json
- penflow/code-ir.json

Preserve semantic_id, role, binding, entity, state, validation, side_effect, and test_id mappings.
```

The agent should use `semantic_id` and `test_id` as stable anchors. Visual details stay in Pencil; business intent lives in the Pencil `context`, semantic tree, and code IR.

## Runtime Verification

After implementation, the app must export an `actual-ui-tree.json` through a runtime adapter. Penflow validates and compares that file; it does not launch the app.

```bash
penflow validate-actual penflow/actual-ui-tree.json --schema --json
penflow compare-tree penflow/expected-ui-tree.json penflow/actual-ui-tree.json --out penflow/compare-report.json --json  # strict default threshold 0.98; --lenient restores 0.9
penflow review-report penflow/compare-report.json --out penflow/review-report.json --json
penflow fix-report penflow/compare-report.json --out penflow/fix-report.json --json
penflow validate-report penflow/compare-report.json --schema --json
```

Legacy pre-v2 guides may mention `review.md`, `fix.md`, or Markdown compare reports. In strict v2, keep those names as historical references only; write `review-report.json`, `fix-report.json`, and `compare-report.json`.

Adapter guides:

- **Read** [`adapters/web-dom.md`](adapters/web-dom.md) for Web DOM.
- **Read** [`adapters/swiftui-xctest.md`](adapters/swiftui-xctest.md) for SwiftUI + XCTest.
- **Read** [`adapters/react-native.md`](adapters/react-native.md) for React Native.

## Guided Mockup Optimization

**Read** [`../.agent-sync/skills/mockup-factory/SKILL.md`](../.agent-sync/skills/mockup-factory/SKILL.md) after the project has valid Penflow anchors and needs Pencil mockup generation, audit, or optimization.

Mockup Factory requires these project-local artifacts before UX/UI work starts:

- `penflow/flow-ui-contract/`
- `penflow/semantic-ui-tree.json`
- `penflow/ui.pen`
- `penflow/pencil-context-map.json`
- `penflow/expected-ui-tree.json`
- `penflow/drift-report.json`

The skill is a guided optimizer, not a freeform redesign tool. Every UX/UI fix must reference an audited checklist item and the best available anchor: `screen_id`, `semantic_id`, or `pencil_node_id`. PASS requires semantic contract coherence, no critical UX/UI issues in visual alignment, hierarchy, CTA placement, density, accessibility, responsive behavior, modernity, or polish, and the Visual Evidence Gate from **Read** [`../.agent-sync/skills/mockup-factory/references/visual-validation.md`](../.agent-sync/skills/mockup-factory/references/visual-validation.md). Since feature 052, every rubric category is a scripted gate, fixes run in a bounded fix-re-audit loop (max 3 iterations, no PASS without a final clean run), and the final proof is a strict `audit-report.json` (`kind: penflow-mockup-audit`) checked by one command:

```bash
penflow validate-report penflow/.mockup-validation/audit-report.json --schema --json
```

When Pencil rendering is available, store proof next to the workspace:

```text
penflow/.mockup-validation/
  audit-report.json
  visual-evidence/
    manifest.json
    vision-report.json   # with a coherence section when the expected tree has >= 2 screens (053)
    layout-snapshot.json
    visual-report.json   # legacy 044 artifact, deprecated
    checkout.png
    contact-sheet.png    # uniform-scale cross-mockup contact sheet (053)
  <group>/
    checklist.json
    state.json
```

Gate the packet deterministically — the gate is the exit code, not prose:

```bash
penflow validate-visual-evidence penflow/.mockup-validation/visual-evidence --expected penflow/expected-ui-tree.json --json
```

If the renderer is unavailable, record `BLOCKED_VISUAL_NOT_RUN` or escalate; do not call the mockup visually validated from tree checks alone.

## CI Gate

A minimal CI gate for a project-local Penflow workspace:

```bash
penflow validate-flow-contract penflow/flow-ui-contract/contract.json --json
penflow validate-semantic-tree penflow/semantic-ui-tree.json --json
penflow validate-pen penflow/ui.pen --json
penflow export-expected penflow/ui.pen --out penflow/expected-ui-tree.json --json
penflow validate-actual penflow/actual-ui-tree.json --schema --json
penflow compare-tree penflow/expected-ui-tree.json penflow/actual-ui-tree.json --out penflow/compare-report.json --json
penflow validate-report penflow/compare-report.json --schema --json
penflow doctor --project . --check --json
```

For early migration, make `validate-flow-contract`, `validate-semantic-tree`, and `validate-pen` blocking. `validate-flow-specs` is compatibility-only for explicitly migrated legacy Markdown and must not run in the strict v2 gate. Add `actual-ui-tree.json` comparison once the app has a runtime adapter.

## Migration Checklist

- Choose one Penflow workspace path, usually `penflow/`.
- Run read-only Doctor at task start and keep its receipt.
- Add or migrate `flow-ui-contract/contract.json`; keep Markdown/YAML docs-only.
- Generate and validate `semantic-ui-tree.json`.
- Draft or enrich the one canonical `ui.pen`; keep active/draft/archive revisions inside it.
- Review `pencil-context-map.json` for ambiguous or unmapped nodes.
- Export `expected-ui-tree.json`.
- Generate and validate `code-ir.json` for implementation handoff.
- Add a runtime adapter that emits `actual-ui-tree.json`.
- Compare expected vs actual and use `review-report.json` / `fix-report.json` for correction planning.
- Add CI commands once the artifacts are stable.
- Run read-only Doctor again at task end and keep the final receipt.

## Common Decisions

| Decision | Recommended default |
|---|---|
| Where to store artifacts? | `penflow/` inside the app repo. |
| One workspace or many? | One canonical `ui.pen` per selected consumer project; independent projects may share one enclosing non-bare Git worktree. Standalone non-Git paths are rejected because Doctor cannot prove tracked/staged hygiene. |
| Commit generated JSON? | Yes for contract artifacts; optional for transient reports. |
| Who owns `actual-ui-tree.json`? | The app runtime adapter, not Penflow. |
| Can agents edit `.pen` directly? | Yes, but only through Penflow commands or Pencil-aware tooling that preserves context. |
| Can agents hand-write semantic trees? | No for production; author or migrate `contract.json` and run `export-semantic-tree`. |

## Manual Doctor Resolution

- `multiple_pen_files`: Doctor does not select, rename, move or delete a candidate. Inspect every file, consolidate the intended revisions as active/draft/archive regions in the canonical `ui.pen`, then deliberately migrate or remove the extras and rerun `penflow doctor --project . --check --json`.
- Tracked or staged `.penflow-tmp/`, `.penflow-run/` or `.mockup-validation/` paths: Doctor reports exact Git states but never rewrites the index/history. Review the content, manually unstage or untrack it, keep the managed ignore block, then rerun Doctor.
- Cleanup block: preserve the run. Resolve the reported live owner, unknown descendant, link/path escape, Git state or durable reference; never broaden deletion to make the command pass.
