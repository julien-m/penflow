---
name: penflow
description: Use the Penflow CLI for pen.dev .pen context validation, semantic/expected/actual UI-tree workflows, codegen handoff, reports, and deterministic visual-fix review.
---
<!-- LiveSpec traceability anchors -->
<!-- @spec(FR-001) -->
<!-- @spec(FR-002) -->
<!-- @spec(FR-003) -->
<!-- @spec(FR-006) -->
<!-- @spec(FR-008) -->
<!-- @spec(FR-012) -->
<!-- @spec(FR-013) -->
<!-- @spec(FR-014) -->

# Penflow Skill

Use this skill when a task mentions Penflow, pen.dev `.pen`, flow specs, `semantic-ui-tree.json`, `.pen` `context`, `expected-ui-tree.json`, `actual-ui-tree.json`, code IR, compare reports, or structural design/runtime validation.

## pen.dev naming

Use `pen.dev` for the product, desktop app, editor, renderer, and MCP integration. On macOS, launch the installed app with `open -a Pen`; do not launch `Pencil`. Keep `pencil` only where it is the current MCP server id or part of an existing Penflow command, field, file, issue id, or receipt schema. The standalone CLI executable is `pen`.

## pen.dev 1.2 operator protocol

<!-- @spec FR-005: current pen.dev MCP surface — .specs/features/078-pen-dev-operator-compatibility/spec.md#fr-005 -->
<!-- @spec FR-006: C46 file-copy protocol — .specs/features/078-pen-dev-operator-compatibility/spec.md#fr-006 -->
<!-- @spec FR-007: C46 at design closure — .specs/features/078-pen-dev-operator-compatibility/spec.md#fr-007 -->
The pen.dev MCP server (id `pencil`) exposes `get_app_state`, `execute`, `read_skill`, `get_style` and `browser`. MCP and app control stay in the operator layer; Penflow core only reads local files.

1. **Open `ui.pen` in pen.dev before any MCP call.** Ask the user to open it (or run `open -a ~/Applications/Pen.app <project>/penflow/ui.pen`), then call `get_app_state` and confirm the open document is that exact `ui.pen` and is not reported empty. A Dashboard or another document blocks; MCP errors such as "A file needs to be open in the editor" mean this step was skipped.
2. Call `read_skill` with `path: "execute.md"` once per session for the current `execute` API.
3. Copy the document before mutating: `cp <workspace>/ui.pen <run-dir>/pre.pen`.
4. Mutate and read through `execute` (always pass `filePath`). Penflow reads `ui.pen` from disk by design; no rule forbids Penflow commands from reading it.
5. Save with `penflow pencil-sync <workspace>/ui.pen --expect-screens <N> --json` (add `--app <Pen.app>` when several installs exist). It resolves the single pen.dev bundle and its running process by executable path; it never targets a legacy `Pencil.app` sharing the bundle id `dev.pencil.desktop`. It stays a trigger: `persistence_status: UNVERIFIED`.
6. Copy the saved document: `cp <workspace>/ui.pen <run-dir>/post.pen`. Preparation reads (`validate-pen`, `export-expected`, mapping, audits) may continue after a PASS trigger; they are explicitly noncertifying.
7. **At design closure** (before a Mockup Factory PASS, C47 `--strict-closure` or the C51 design profile), write the `penflow-pencil-persistence-observation` binding the run, operation, trigger and the distinct `pre.pen`/`post.pen` digests, then run `penflow verify-pencil-persistence <observation> --document <workspace>/ui.pen --run-id <run> --operation <operation> --out <workspace>/.penflow-run/pencil-persistence-receipt.json --json` (the path C51 reads) and `penflow validate-report <workspace>/.penflow-run/pencil-persistence-receipt.json --schema --json`. C46 is not required before the first preparation read.

| Former MCP tool (pen.dev < 1.2, legacy) | pen.dev 1.2 `execute` equivalent |
|---|---|
| `batch_design` (legacy) | `Insert`, `Update`, `Replace`, `Copy`, `Move`, `Delete` in one snippet |
| `batch_get` (legacy) | `Print(Get(id, {depth: 2}))` |
| `snapshot_layout` (legacy) | `Get(screenId, visitor)` printing `ctx.bounds` (native layout below) |
| `get_screenshot` (legacy) | `TakeScreenshot([nodeId])` |
| `export_nodes` (legacy tool; still the C48 receipt operation id) | `Export([nodeId], "png", dir)`, one node per call when multi-node exports misbehave |
| `get_editor_state` (legacy) | `get_app_state` |

Native layout for C51 geometry: run one `execute` call that prints only the parent-relative layout and save its raw MCP response as the observation file:

```js
const idx={},roots=[];Get(screenId,(n,c)=>{const e={id:n.id,x:c.bounds.x,y:c.bounds.y,width:c.bounds.width,height:c.bounds.height,children:[]};idx[n.id]=e;(c.parentCtx?idx[c.parentCtx.node.id].children:roots).push(e)});Print(roots)
```

The response text is `OK`, a blank line, `## Print output` and that single JSON line. Save the whole MCP response (`{"content": [{"type": "text", "text": ...}]}`) as the observation and set the `penflow-native-layout` envelope `children` to the printed list. A single printed `penflow-native-get-layout` object (`roots` plus per-node `measurements` with `parent_id` and `bounds`) is also accepted; `children` is then the tree rebuilt by `penflow.verification_transport.native_layout_children`. C51 decodes the Print transport, still accepts a bare JSON legacy observation, and rejects failed calls, several Print lines, duplicate sections, non-finite JSON, any node, parent or context mismatch, and measurements carrying pen.dev `problems` (clipping).

## C51 workflow authority

<!-- @spec(FR-015) -->
**Read** [`../../../docs/verification-workflow.md`](../../../docs/verification-workflow.md) before accepting workflow completion. The existing workflow automatically prepares explicit test IDs before source review, binds actual upstream requirements and plan/workflow applicability, and selects `design` after review/native design or `implementation` after the external runner. Pre-review preparation is non-certifying; reuse unchanged design evidence instead of repeating Mockup Factory. Missing requirements, outcomes, native capabilities or review history block; no extra user-maintained ledger or manual verification step.

- Final design: `penflow run --target <target> --profile design --project <consumer-project-root> --json`, then `penflow validate-report <target>/run-report.json --schema --required-profile design --project <consumer-project-root> --json`.
- Final implementation: the same commands with `implementation` and the actual caller-supplied `--build-manifest <runner-path>` on both calls. Require exact-profile PASS, empty issues, report hash/scope/build concordance and exits 0.
- Standalone commands, audit scores, `PASSED_WITH_WARNINGS`, masks, `--lenient`, missing-file heuristics and historical C47 never substitute for C51. The legacy sequences below remain preparation/diagnostics; C51 alone decides cumulative closure and normalizes native geometry.
- Native lifecycle fields must survive actual Save/C46 before draft/archive variants are trusted. pen.dev 2.14 accepting metadata without persisting it does not create a lifecycle revision; keep the valid active canvas and report the unsupported capability.

## Purpose

Penflow is a deterministic, runtime-agnostic CLI that connects product flow intent, pen.dev design contracts, codegen handoff data, and post-implementation runtime verification.

Strict v2 uses `flow-ui-contract/contract.json` as the canonical machine contract. Markdown flow/screen docs are deterministic `export-flow-docs` projections or explicit legacy migration input, never competing sources.

Penflow owns file validation and tree comparison only:
- `semantic-ui-tree.json`: before-code intent exported from strict `flow-ui-contract/contract.json` (legacy `flow-ui-contract/*.md` docs remain migration/documentation input).
- `expected-ui-tree.json`: design-derived tree exported from contextualized `.pen`.
- `actual-ui-tree.json`: after-code runtime tree produced by an external adapter.

Penflow does **not** run browsers, Xcode, simulators, Playwright, React Native, Metro, or app builds. External adapters produce `actual-ui-tree.json`; Penflow validates and compares it.

## Consumer Project Hygiene

At task start, run `penflow doctor --project <consumer-project-root> --check --json` before reading or mutating Penflow artifacts and retain the read-only receipt. At task end, run the same command again and retain the final receipt. The selector is the exact project directory (or an existing file's parent), never the enclosing Git worktree. `git_root` is internal and used only for scoped Git interrogation and transient metadata coordination; discovery, uniqueness, ignore ownership, repair and cleanup stay below `<consumer-project-root>`. Never aim Doctor at the Penflow source checkout when the task belongs to another application project.

- Exactly one regular, case-sensitive `ui.pen` may exist in each selected consumer project. A collective Git worktree may contain several independently selected projects. Keep all screen revisions as top-level regions inside the project's canvas: one `active` revision per `logical_screen_id`, plus optional `draft` and `archive` revisions with unique `revision_id`; unmarked legacy regions are active.
- All technical working data belongs below ignored `.penflow-tmp/`, `.penflow-run/`, and `.mockup-validation/`. Producer preflight reconciles eligible terminal/dead-owner runs; postflight cleans successful working payload only after durable outputs finalize. Preserve live, unknown, linked, escaped, tracked/staged, referenced or canonical-document paths when cleanup blocks.
- `doctor --fix` may initialize `penflow/ui.pen` when none exists and repair the managed ignore block. It never chooses among multiple candidates or rewrites Git index/history.
- On `multiple_pen_files`, manually inspect and consolidate the intended regions into `ui.pen`, then deliberately migrate/remove extras. On tracked/staged temporary findings, manually review and unstage/untrack the exact reported paths before rerunning Doctor.
- Exit codes: `0` PASS, `1` project-health block, `2` usage, `3` untrustworthy I/O/schema, `4` cleanup safety block.

## Strict by Default (Feature 049 / C24)

- Warning-severity issues exit 1 on every validating command (`validate-*` including `validate-visual-evidence`, `compare-tree`, `detect-drift`, `lint-tokens`, `check-consistency`, `audit-visual`, `export-expected`, `ci`); errors always exit 1. The global `--lenient` flag (before or after the subcommand) makes warnings non-blocking. `info`-severity issues never affect exit codes.
- `compare-tree`/`ci` default threshold is 0.98; `--lenient` restores 0.9; explicit `--threshold` always wins.
- `export-semantic-tree`, `reverse-pen`, `extract-tokens` report issues and exit 1 on them: `reverse.clarification_needed` per generated artifact still containing `[NEEDS CLARIFICATION]`, `tokens.value.unparsed` for uninterpretable token values.
- `detect-drift` issues carry `blocking: bool` (`BLOCKING_DRIFT_CODES`: `drift.semantic_tree_invalid`, `drift.semantic_node_missing_in_pen`, `drift.pencil_context_obsolete`, `drift.clarification_marker`); summary has a `blocking` count; status adds `BLOCKED`. Blocking issues exit 1 even with `--lenient` — gate on `summary.blocking == 0`.
- Surfaced coercions: `pen.bbox.invalid` warning for non-keyword string bbox values (`fill_container`/`fit_content(...)` exempt) via `validate-pen`/`inspect`; `theme.value.unparsed` warning for unparsable theme dimensions via `lint-tokens`.
- `jsonschema>=4` is a hard dependency (no minimal fallbacks).

## Tree Contracts

The LLM should not hand-write production trees, but it must understand their contracts before debugging or explaining results:

- `semantic-ui-tree.json` is formed by `penflow export-semantic-tree` from `flow-ui-contract/contract.json`. Flow specs become `flows[]`; screen specs become `screens[]` in legacy docs; v2 contract objects become the same tree shape with recursive semantic nodes carrying `semantic_id`, `role`, `intent`, `binding`, `entity`, states, validations, side effects, source maps, and test ids.
- `expected-ui-tree.json` is exported from a contextualized pen.dev `.pen`; it is the design-derived baseline for structural comparison.
- `actual-ui-tree.json` is emitted by an external runtime adapter; it is the post-implementation observation. Penflow validates it and compares it to the expected tree.

For the semantic-tree formation rules, **Read** [`../flow-ui-contract/references/semantic-ui-tree.md`](../flow-ui-contract/references/semantic-ui-tree.md). For runtime adapter output rules, **Read** [`../../../docs/adapters/web-dom.md`](../../../docs/adapters/web-dom.md), **Read** [`../../../docs/adapters/swiftui-xctest.md`](../../../docs/adapters/swiftui-xctest.md), or **Read** [`../../../docs/adapters/react-native.md`](../../../docs/adapters/react-native.md) when targeting that stack.

## Preconditions

- Run commands from the Penflow project root.
- Install in editable mode when needed:
  ```bash
  python3 -m pip install -e ".[dev]"
  ```
- **Read** [`README.md`](../../../README.md) for project-level command examples when a user asks for the full workflow.
- **Read** [`../../../docs/theme-contract.md`](../../../docs/theme-contract.md) before generating `theme.css` for `draft-pen-from-tree`, `lint-tokens`, or Brander-style handoff. It defines accepted `--pf-*` aliases, extended status/panel/font tokens, dynamic `palette-*` slots, dynamic `radius-*` slots, and the strict report inputs.
- Before any UI flow, pen.dev draft, mockup, or visual validation work, **Read** [`../../../.conventions/index.md`](../../../.conventions/index.md) and load all matching design domains. UI work must use the convention-defined view/component patterns, not only theme colors.
- After every pen.dev editor/MCP mutation (`execute` snippets, manual edit, or equivalent; the legacy `batch_design` tool no longer exists), run `penflow pencil-sync <ui.pen> --expect-screens <N> --json` or add `--expect-min-nodes <N>`. This trigger always remains `persistence_status: UNVERIFIED` with `closes_persistence: false`; mtime, trigger text, and inspection counts never close persistence; before any Penflow CLI command that reads the `.pen` after a mutation, require a PASS trigger, otherwise report `BLOCKED`; such preparation reads stay noncertifying. At design closure the operator preserves distinct pre/post snapshots, writes the C46 observation, runs `penflow verify-pencil-persistence ... --out <workspace>/.penflow-run/pencil-persistence-receipt.json --json`, then `penflow validate-report` on that receipt with `--schema --json` (see the pen.dev 1.2 operator protocol above).

## .pen Context Grammar

pen.dev `.pen` `context` is the shorthand string parsed by [`../../../penflow/context.py`](../../../penflow/context.py): `key=value` pairs separated by `;`. Allowed keys: `classification`, `decorative_owner`, `decorative_reason`, `inherits_from`, `instance_key`, `relation`, `semantic_id`, `role`, `intent`, `binding`, `repeat`, `entity`, `variant`, `test_id`, `action`, `permission`, `mask`, `mask_text`, `tolerance`. Every authored id-bearing node declares exactly one `classification=semantic|inherited|decorative`. Semantic nodes require `semantic_id`, `test_id`, and `role`; inherited nodes require `inherits_from` and `relation`; decorative nodes require `decorative_owner` and `decorative_reason`. Appearance never supplies classification.

Examples:
- Screen frame: `classification=semantic; semantic_id=cockpit-live; test_id=cockpit-live-screen; role=screen`
- Button: `classification=semantic; semantic_id=cockpit-live.stop-worker; test_id=stop-worker; role=button; intent=stop-worker; action=stop_worker`
- Internal label: `classification=inherited; inherits_from=cockpit-live.stop-worker; relation=content`
- Icon: `classification=decorative; decorative_owner=cockpit-live.stop-worker; decorative_reason=duplicates-label`

When creating frames/components through `execute` `Insert` (formerly the legacy `batch_design` tool), attach classification context at insertion time; adding it later is repair work. Run `penflow map-pencil-context <ui.pen> <semantic-ui-tree.json> --out pencil-context-map.json --strict-coverage --contract flow-ui-contract/contract.json --coverage-out semantic-context-coverage.json --json`; only coverage `PASS` authorizes downstream strict gates. `--strict-anchors` remains labeled forward-only diagnostic evidence and cannot prove reverse coverage. `--create-placeholders` is opt-in repair scaffolding only: its report remains `PARTIAL`, never `PASS`, and never closes exhaustive coverage.

## Mode Selection

| User intent | Mode |
|---|---|
| "Integrate Penflow into my existing project" | Project integration mode |
| "Generate `.pen` / code IR from flow specs" | Forward mode |
| "Enrich an existing pen.dev mockup with business context" | pen.dev enrichment mode |
| "Reconstruct flows from a legacy pen.dev file" | Reverse mode |
| "Compare implementation with design contract" | Post-implementation compare mode |
| "Show me the whole chain" | Full demo mode |
| "Generate, audit, or optimize pen.dev mockups" | Mockup Factory mode |

## Project Integration Mode

Use when a user already has an application repository and asks how to adopt Penflow, where to store artifacts, how to migrate existing pen.dev mockups, or how agents should consume Penflow outputs.

**Read** [`../../../docs/project-integration.md`](../../../docs/project-integration.md). It covers the recommended `penflow/` workspace, forward adoption, existing-pen.dev enrichment, legacy reverse migration, code IR handoff, runtime `actual-ui-tree.json` verification, and CI gate.

## Mockup Factory Mode

Use when a user asks for mockup generation, audit, optimization, or `/mockup-factory` on pen.dev `.pen` files.

**Read** [`../mockup-factory/SKILL.md`](../mockup-factory/SKILL.md). It is the Penflow-local canonical workflow for guided UX/UI optimization. It requires `flow-ui-contract`, `semantic-ui-tree.json`, `theme.css`, `.pen`, `pencil-context-map.json`, `expected-ui-tree.json`, and `detect-drift` as deterministic anchors before any pen.dev/Codex audit loop. **Read** [`../mockup-factory/references/visual-validation.md`](../mockup-factory/references/visual-validation.md) before applying the Visual Evidence Gate: layout snapshot dump, screenshot inspection over the five locked vision categories, PNG export, manifest, and `vision-report.json` when a renderer is available — gated by `penflow validate-visual-evidence` exit 0, not prose. UX/UI improvements must be tied to audited checklist items and `screen_id` / `semantic_id` / `pencil_node_id` when available. The audit rubric is prescriptive (feature 052): each category maps to a scripted gate (`lint-tokens`, `check-consistency`, `audit-visual`, `detect-drift`, `compare-tree`, `validate-visual-evidence`), fixes run in a bounded loop (`iteration <= 3`, full chain rerun, no PASS without a final clean run), and the verdict is the strict `audit-report.json` checked by `penflow validate-report audit-report.json --schema`.

## Forward Mode

Use when `flow-ui-contract/contract.json` is the source of truth. Keep Markdown examples as docs-only/migration references.

```bash
penflow run --target penflow --theme-css penflow/theme.css --references penflow/references --strict --json
penflow validate-flow-contract examples/full/flow-ui-contract/contract.json --json
penflow export-flow-docs examples/full/flow-ui-contract/contract.json --out examples/full/flow-ui-contract --json
penflow export-flow-docs examples/full/flow-ui-contract/contract.json --out examples/full/flow-ui-contract --check --json
penflow export-semantic-tree examples/full/flow-ui-contract/contract.json --out semantic-ui-tree.json --json
penflow validate-semantic-tree semantic-ui-tree.json --json
penflow draft-pen-from-tree semantic-ui-tree.json --out ui.pen --theme-css theme.css --json
penflow lint-tokens ui.pen --theme-css theme.css --out token-lint-report.json --json
penflow map-pencil-context ui.pen semantic-ui-tree.json --out pencil-context-map.json --strict-coverage --contract examples/full/flow-ui-contract/contract.json --coverage-out semantic-context-coverage.json --json
penflow validate-pen ui.pen --json
penflow export-expected ui.pen --out expected-ui-tree.json --json
penflow check-consistency expected-ui-tree.json --group-by role+intent+variant+size-class --out consistency-report.json --json
penflow audit-visual expected-ui-tree.json --theme-css theme.css [--layout-snapshot .mockup-validation/visual-evidence/layout-snapshot.json] --out visual-metrics-report.json --json
penflow code-ir --from-context ui.pen --semantic-tree semantic-ui-tree.json --contract examples/full/flow-ui-contract/contract.json --flow-id checkout --flow-name "Checkout flow" --out code-ir.json --json
penflow validate-code-ir code-ir.json --json
```

`draft-pen-from-tree` emits a structural pen.dev draft only. When its JSON output is saved as `draft-report.json`, it includes `fidelity: "wireframe"`: draft = structure / wireframe, PAS un mockup final ; le hi-fi passe par mockup-factory.

Use `--group-by role+intent+variant+size-class` on dense screens: `check-consistency` skips anonymous containers with no stable intent, variant, or human name; height buckets keep 56px headers out of 820px panel groups; repeated divergences are aggregated. `--lenient` downgrades non-`fill`/`fontFamily` divergences to warnings in the report; `fill` and `fontFamily` stay errors.

`penflow run --target <workspace> [--theme-css f] [--references dir] [--strict] --json` is the single DX wrapper for an already authored workspace. It runs the deterministic gates in order: `validate-flow-contract`, generated-flow-doc freshness, `export-semantic-tree`, `pencil-sync` when explicitly armed (`PENFLOW_RUN_PENCIL_SYNC=1`), forward mapping, exhaustive `semantic-context-coverage`, `validate-pen`, `export-expected`, `lint-tokens`, `check-consistency`, `audit-visual`, `detect-drift`, `validate-visual-evidence`, optional `reference-fidelity`, `code-ir`, and `validate-actual-provenance`. Strict execution stops before `validate-pen` unless coverage is `PASS`; non-strict execution records `LEGACY_PARTIAL`. The output is one JSON summary plus an aggregate exit code; the summary and every gate cite the same `runId`, identity `version`, current-run provenance, and SHA-256 lineage for `ui.pen`, contract, expected/actual trees, theme, references, renderer, and export timestamp. Missing required inputs, explicitly requested missing optional paths, source mutation, or citation/provenance divergence exit nonzero; unarmed absent theme/reference inputs receive deterministic `not-provided` receipts. Individual gate reports remain in the workspace.

Use `penflow run --target <workspace> --references <workspace>/references --strict-closure
--json` only as the explicit C47 final check. It is read-only over evidence and writes only
`.penflow-run/strict-closure.json`. PASS requires the revalidatable C46 persistence receipt,
fresh independent `runtime-capture` actual provenance with `sessionId`, a declared
homologous references manifest, PASS-only structured blocking C45 visual/reference proof,
and one identical run id. Missing, SKIP, warning-only, stale, replayed, mismatched,
non-blocking, generic, duplicated, or tampered evidence exits 1 with structured issues.
Omitting `--strict-closure` preserves the existing pipeline.

APEX integration rule: `penflow run` is the unite naturelle qu'une tache APEX encapsule cote orchestrateur. Penflow ne cree jamais de goal runtime propre: le goal appartient au run parent. Any APEX invocation that wraps Penflow must use `-G/--no-goal` so goal ownership is not nested or duplicated.

`code-ir --from-context` expects the contextualized `.pen` file, not `expected-ui-tree.json`; wrong-tree inputs must fail before code IR generation with an explicit message.

Legacy `export_nodes` batch limitation (historical, pen.dev < 1.2): Penflow core must not drive pen.dev MCP/app exports. With pen.dev 1.2 export through `execute` `Export([nodeId], "png", dir)`. If a multi-node legacy `export_nodes` (or `Export`) call fails as `wrong .pen file` while unitary exports pass, keep the deterministic Penflow gates intact and use exports unitaires at the skill/operator layer. The reproduced issue is tracked as [`PF-PENCIL-EXPORT-NODES-BATCH-20260701`](../../../docs/pencil-export-nodes-batch-issue.md); cite that ID in worker receipts instead of treating the fallback as untracked debt. Do not add browser, pen.dev MCP, or renderer dependencies to Penflow Python core.

Legacy route phrase for old docs/tests: `penflow export-semantic-tree examples/full/flow-ui-contract --out semantic-ui-tree.json --json`.

Anti-gaming gates are strict: `validate-semantic-tree` emits `semantic.downgrade_suspect` for repeated list-like `container` children without `repeat`, and `validate-flow-contract --json` includes `interactive_coverage` while failing `contract.interactive_unbound` when a `button`/`link`/`input` has neither `action` nor transition binding. Static screens without interactive actions must declare `static: true` and a non-empty `static_reason`.

`audit-visual` (feature 050/061) computes deterministic visual metrics from the expected tree, zero vision: WCAG AA contrast via parent-walk backgrounds (`visual.contrast.below_aa` error; 3:1 for fontSize ≥ 24 or ≥ 18 bold, else 4.5:1), touch targets on interactive roles (`visual.touch_target.too_small` — error < 24px, warning 24–43px; ≥ 44px passes; zero-sized drafts emit `visual.bbox.unmeasured` info), sibling overlap / parent overflow beyond 1px (`visual.bbox.overlap`, `visual.bbox.overflow`, errors), heuristic text overflow (`visual.text.likely_overflow` warning), and unparseable fills (`visual.color.unparsed` info). `$pf-*` fills resolve via `--theme-css`. When a renderer produced `layout-snapshot.json`, pass `--layout-snapshot` so overlap/overflow uses real pen.dev bboxes; without it, flex-parent theoretical geometry is skipped while non-geometric checks still run on the tree.

`validate-visual-evidence` (feature 051) deterministically gates the skill-layer visual evidence packet — Penflow never runs vision, it validates that vision happened:

```bash
penflow validate-visual-evidence .mockup-validation/visual-evidence --expected expected-ui-tree.json --json
penflow validate-reference-fidelity .mockup-validation/visual-evidence --references references --json
```

Checks: `manifest.json` validates, every manifest screen PNG exists non-empty, `vision-report.json` (`kind: penflow-vision-report`) validates against the locked category enum (`visual_balance`, `rendering_artifacts`, `readability`, `perceived_hierarchy`, `imagery_quality` — deterministic categories like contrast/touch targets/overflow are rejected by schema), every screen answers all five categories, every expected-tree screen is covered (`evidence.screen.uncovered`), an optional `layout-snapshot.json` matches expected root bboxes within ±4px (`evidence.snapshot.bbox_mismatch`), and — when the expected tree has ≥ 2 screens — the report carries a `coherence` section (`evidence.coherence.missing`) whose `contact_sheet_png` exists non-empty (`evidence.contact_sheet.missing`/`.empty`) and whose criteria answer all four coherence categories (`cross_screen_rhythm`, `palette_coherence`, `typography_coherence`, `component_recognition` — `evidence.coherence.category_missing`; numeric cross-screen facts stay with `check-consistency`). All issues are errors; exit 0 is the only PASS. The vision report also validates standalone via `penflow validate-report vision-report.json --schema --json`.

Feature 070/C45 makes every required criterion explicitly `blocking: true` and PASS-only. `manifest.json` and `vision-report.json` share one exact `runId`; each criterion carries structured `proof` for surface/screen/hierarchical region/state/assertion/measurement plus hashed actual/reference/contact-sheet artifacts and in-bounds crops. Warning/SKIP/non-pass status, narrative-only proof, run mismatch, invalid or stretched crops, expected/reference copied into actual, mismatched homology, or artifact reuse across non-homologous mappings blocks with exit 1.

Feature 071/C46 separates the pen.dev trigger from persistence proof. `pencil-sync` never closes the gate. An operator-layer `penflow-pencil-persistence-observation` binds the exact run, document, requested operation, trigger, and distinct pre/post snapshot digests; `penflow verify-pencil-persistence <observation> --document <ui.pen> --run-id <run> --operation <operation> --out <receipt> --json` independently re-reads all bytes and writes the structured receipt. Run `penflow validate-report <receipt> --schema --json` to reject stale/tampered receipt content. Only `status: PASS`, verifier `result: pass`, and `closes_persistence: true` close persistence; no-op, trigger-only, stale, replayed, tampered, missing, or mismatched evidence exits nonzero.

When references exist, `manifest.json` declares `references_manifest` pointing to `references/references-manifest.json` (`[{screen_id, file, sha256, source}]`, files relative to `references/`). `vision-report.json` must include `reference_fidelity` for every referenced screen, with one side-by-side contact sheet and exactly `layout_match`, `palette_match`, `component_parity`, and `density_match`; every evidence sentence cites both reference and export files. Run `penflow validate-reference-fidelity .mockup-validation/visual-evidence --references references --json` after `validate-visual-evidence`; copied exports (`reference.evidence_is_reference_copy`) and deterministic-vs-LLM disagreement (`reference.llm_metric_disagreement`) block PASS.

## pen.dev Enrichment Mode

Use when a visual pen.dev file already exists and must keep its layout.

```bash
consumer=$(mktemp -d)
trap 'rm -rf -- "$consumer"' EXIT
git -C "$consumer" init
cp -R examples/full/flow-ui-contract "$consumer/flow-ui-contract"
cp examples/full/ui.pen "$consumer/ui.pen"
penflow doctor --project "$consumer" --check --json > "$consumer/.penflow-doctor-start.json" || test "$?" -eq 1
python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); a={"pen.missing","gitignore.managed_block_missing","gitignore.managed_block_outdated","gitignore.managed_block_duplicate"}; c={i["code"] for i in d["stable_result"]["findings"]}; raise SystemExit(0 if c and c <= a else 1)' "$consumer/.penflow-doctor-start.json"
penflow doctor --project "$consumer" --fix --json
penflow doctor --project "$consumer" --check --json
penflow validate-flow-contract "$consumer/flow-ui-contract/contract.json" --project "$consumer" --json
penflow export-flow-docs "$consumer/flow-ui-contract/contract.json" --project "$consumer" --out "$consumer/flow-ui-contract" --json
penflow export-flow-docs "$consumer/flow-ui-contract/contract.json" --project "$consumer" --out "$consumer/flow-ui-contract" --check --json
penflow export-semantic-tree "$consumer/flow-ui-contract/contract.json" --project "$consumer" --out "$consumer/semantic-ui-tree.json" --json
penflow validate-semantic-tree "$consumer/semantic-ui-tree.json" --project "$consumer" --json
penflow enrich-pen "$consumer/ui.pen" "$consumer/semantic-ui-tree.json" --project "$consumer" --out "$consumer/ui.pen" --json
penflow map-pencil-context "$consumer/ui.pen" "$consumer/semantic-ui-tree.json" --project "$consumer" --out "$consumer/pencil-context-map.json" --strict-coverage --contract "$consumer/flow-ui-contract/contract.json" --coverage-out "$consumer/semantic-context-coverage.json" --json
penflow validate-pen "$consumer/ui.pen" --project "$consumer" --json
penflow export-expected "$consumer/ui.pen" --project "$consumer" --out "$consumer/expected-ui-tree.json" --json
penflow code-ir --from-context "$consumer/ui.pen" --semantic-tree "$consumer/semantic-ui-tree.json" --context-map "$consumer/pencil-context-map.json" --contract "$consumer/flow-ui-contract/contract.json" --flow-id checkout --flow-name "Checkout flow" --project "$consumer" --out "$consumer/code-ir.json" --json
penflow doctor --project "$consumer" --check --json
```

Preserve existing visual layout. Treat ambiguous or unmapped nodes from `map-pencil-context` as review work, not as permission to overwrite visual design.

## Reverse Mode

Use when a legacy `.pen` exists before flow specs.

```bash
consumer=$(mktemp -d)
trap 'rm -rf -- "$consumer"' EXIT
git -C "$consumer" init
cp examples/full/ui.pen "$consumer/ui.pen"
penflow doctor --project "$consumer" --check --json > "$consumer/.penflow-doctor-start.json" || test "$?" -eq 1
python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); a={"pen.missing","gitignore.managed_block_missing","gitignore.managed_block_outdated","gitignore.managed_block_duplicate"}; c={i["code"] for i in d["stable_result"]["findings"]}; raise SystemExit(0 if c and c <= a else 1)' "$consumer/.penflow-doctor-start.json"
penflow doctor --project "$consumer" --fix --json
penflow doctor --project "$consumer" --check --json
penflow reverse-pen "$consumer/ui.pen" --project "$consumer" --out "$consumer/reverse-output" --lenient --json
penflow export-flow-docs "$consumer/reverse-output/flow-ui-contract/contract.json" --project "$consumer" --out "$consumer/reverse-output/flow-ui-contract" --json
penflow export-flow-docs "$consumer/reverse-output/flow-ui-contract/contract.json" --project "$consumer" --out "$consumer/reverse-output/flow-ui-contract" --check --json
penflow validate-semantic-tree "$consumer/reverse-output/semantic-ui-tree.json" --project "$consumer" --json
penflow map-pencil-context "$consumer/ui.pen" "$consumer/reverse-output/semantic-ui-tree.json" --project "$consumer" --out "$consumer/pencil-context-map.json" --strict-coverage --contract "$consumer/reverse-output/flow-ui-contract/contract.json" --coverage-out "$consumer/semantic-context-coverage.json" --json
penflow validate-pen "$consumer/ui.pen" --project "$consumer" --json
penflow doctor --project "$consumer" --check --json
```

`reverse-pen --out <dir>` writes a directory containing `semantic-ui-tree.json` and `flow-ui-contract/`; validate `<dir>/semantic-ui-tree.json`, not the directory path itself.
Reverse mode marks missing business rules as `[NEEDS CLARIFICATION]`. Do not invent backend side effects, validations, state transitions, or access rules.
Strict default: `reverse-pen` exits 1 while clarification markers remain; use `--lenient` for scripted chains, then resolve the markers.

## Post-Implementation Compare Mode

Use after an external runtime adapter writes `actual-ui-tree.json`.

```bash
penflow validate-actual actual-ui-tree.json --schema --json
penflow validate-actual-provenance <workspace> --expected expected-ui-tree.json --surface web --json
penflow compare-tree expected-ui-tree.json actual-ui-tree.json --out compare-report.json --json
penflow review-report compare-report.json --out review-report.json --json
penflow fix-report compare-report.json --out fix-report.json --json
penflow validate-report compare-report.json --schema --json
```

If `validate-actual` fails, fix the external adapter output first. Penflow does not inspect the running app.

### Actual Provenance (P0-2 / C2)

The runtime adapter writes a sidecar `actual-ui-tree.provenance.json` receipt next to `actual-ui-tree.json`, describing what produced those exact bytes. Penflow never captures a runtime; it only validates this receipt from local files, and it is the last `penflow run` gate (`validate-actual-provenance`). Required fields (`kind: penflow-actual-provenance`, `version: 1`): `sourceKind` (`runtime-capture` = fresh capture/export, or `static-demo-fixture` = explicitly qualified frozen example data), `producer` (`{name, version?}`), `capturedAt` (ISO-8601 UTC), `target` (`{surface, screen_id?, device?}`), and `content` (`{path, sha256}` = SHA-256 of the actual-tree bytes); optional `sessionId`; `fixture.reason` required for and only for a `static-demo-fixture`.

`penflow validate-actual-provenance <workspace|actual.json> [--expected f] [--surface s] [--max-age-seconds N] [--require-fresh] --json` fails closed with a structured reason for each way an actual can lie:
- `provenance.receipt.missing` / `provenance.receipt.invalid` — absent, non-JSON, or incomplete receipt (missing producer, bad field, unknown source kind, unqualified fixture, or a fixture block on a capture).
- `provenance.digest.mismatch` — receipt `content.sha256` does not match the actual-tree bytes.
- `provenance.content.path_mismatch` — receipt `content.path` basename does not name the validated actual file (the field is traceability, never an ignored/decoy value).
- `provenance.timestamp.stale` / `.future` / `.invalid` — a `runtime-capture` older than the freshness window, in the future, or unparseable (a qualified fixture is exempt — it declares itself frozen).
- `provenance.source_kind.inadmissible` — `--require-fresh` rejects a fixture; only fresh runtime captures qualify.
- `provenance.target.incompatible` — capture `surface` not among the contract surfaces (`--surface`).
- `provenance.actual.derived_from_expected` — a `runtime-capture` whose root is byte-identical to the design-derived expected tree; independence requires measured runtime geometry. A qualified `static-demo-fixture` may reuse expected bytes but can never masquerade as fresh (`--require-fresh` rejects it).

The `penflow run` gate — not only the standalone CLI — arms this freshness policy: it evaluates `capturedAt` against the current run's export boundary with a documented default window `RUN_ACTUAL_FRESHNESS_MAX_AGE_SECONDS = 86400` (24h), overridable via `penflow run --actual-max-age-seconds N`. A `runtime-capture` with an invalid, future, or beyond-window `capturedAt` fails the gate; a `static-demo-fixture` is exempt and that exemption is impossible to obtain with `sourceKind=runtime-capture`. If the internal run boundary cannot be parsed, the run fails explicitly instead of disabling freshness.

Any explicit max-age value — `penflow run --actual-max-age-seconds`, `penflow validate-actual-provenance --max-age-seconds`, or the programmatic `run_pipeline`/`validate_actual_provenance` calls — must be finite and strictly positive: `nan`, `inf`, `-inf`, overflowing literals like `1e999`, `0`, and negatives are rejected fail-closed with a structured `ProvenanceError` and a non-zero exit **before** any report is written (report writers use `allow_nan=False`, so `NaN`/`Infinity` JSON is never emitted). `run` applies the 86400s default; the standalone command applies a max-age only when provided. `content.path` must be a relative name without `..` traversal (`provenance.content.path_invalid` for absolute or traversal); the `content.sha256` digest — not the path — is the authority over the actual-tree bytes.

`compare-tree` also checks layout properties (feature 048): `layout`/`alignItems` exact-match (`node.visual.layout`, `node.visual.alignItems`), `gap`/`padding` within ±2px (`spacing_px`, override via `context.tolerance.spacing_px`; `node.visual.gap`, `node.visual.padding`). Padding `16` ≡ `[16, 16]` ≡ `[16, 16, 16, 16]`. Absent keys emit no issues.

## Regression Mode

Use for CI/regression coverage of contract C16. The proof is pytest-first, with the final CLI chain reproducible on `examples/full` and `examples/legacy`.

```bash
set -euo pipefail
python3 -m pytest -q
consumer=$(mktemp -d)
trap 'rm -rf -- "$consumer"' EXIT
git -C "$consumer" init
cp -R examples/full/flow-ui-contract "$consumer/flow-ui-contract"
cp examples/full/actual-ui-tree.json "$consumer/actual-ui-tree.json"
cp examples/demo/theme.css "$consumer/theme.css"
penflow doctor --project "$consumer" --check --json > "$consumer/.penflow-doctor-start.json" || test "$?" -eq 1
python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); a={"pen.missing","gitignore.managed_block_missing","gitignore.managed_block_outdated","gitignore.managed_block_duplicate"}; c={i["code"] for i in d["stable_result"]["findings"]}; raise SystemExit(0 if c and c <= a else 1)' "$consumer/.penflow-doctor-start.json"
penflow doctor --project "$consumer" --fix --json
penflow doctor --project "$consumer" --check --json
penflow validate-flow-contract "$consumer/flow-ui-contract/contract.json" --project "$consumer" --json
penflow export-flow-docs "$consumer/flow-ui-contract/contract.json" --project "$consumer" --out "$consumer/flow-ui-contract" --json
penflow export-flow-docs "$consumer/flow-ui-contract/contract.json" --project "$consumer" --out "$consumer/flow-ui-contract" --check --json
penflow export-semantic-tree "$consumer/flow-ui-contract/contract.json" --project "$consumer" --out "$consumer/semantic-ui-tree.json" --json
penflow validate-semantic-tree "$consumer/semantic-ui-tree.json" --project "$consumer" --json
penflow draft-pen-from-tree "$consumer/semantic-ui-tree.json" --project "$consumer" --out "$consumer/penflow/ui.pen" --theme-css "$consumer/theme.css" --json
penflow map-pencil-context "$consumer/penflow/ui.pen" "$consumer/semantic-ui-tree.json" --project "$consumer" --out "$consumer/pencil-context-map.json" --strict-coverage --contract "$consumer/flow-ui-contract/contract.json" --coverage-out "$consumer/semantic-context-coverage.json" --json
penflow validate-pen "$consumer/penflow/ui.pen" --project "$consumer" --json
penflow export-expected "$consumer/penflow/ui.pen" --project "$consumer" -o "$consumer/expected-ui-tree.json" --json
penflow enrich-pen "$consumer/penflow/ui.pen" "$consumer/semantic-ui-tree.json" --project "$consumer" --out "$consumer/penflow/ui.pen" --json
penflow map-pencil-context "$consumer/penflow/ui.pen" "$consumer/semantic-ui-tree.json" --project "$consumer" --out "$consumer/pencil-context-map.json" --strict-coverage --contract "$consumer/flow-ui-contract/contract.json" --coverage-out "$consumer/semantic-context-coverage.json" --json
penflow validate-pen "$consumer/penflow/ui.pen" --project "$consumer" --json
penflow reverse-pen "$consumer/penflow/ui.pen" --project "$consumer" --out "$consumer/reverse-output" --lenient --json
penflow validate-semantic-tree "$consumer/reverse-output/semantic-ui-tree.json" --project "$consumer" --json
penflow validate-actual "$consumer/actual-ui-tree.json" --schema --project "$consumer" --json
penflow compare-tree "$consumer/expected-ui-tree.json" "$consumer/actual-ui-tree.json" --project "$consumer" --out "$consumer/compare.json" --json
penflow review-report "$consumer/compare.json" --project "$consumer" --out "$consumer/review.json" --json
penflow fix-report "$consumer/compare.json" --project "$consumer" --out "$consumer/fix.json" --json
penflow doctor --project "$consumer" --check --json
```

`$consumer/reverse-output` is a reverse output directory; its semantic tree lives at `$consumer/reverse-output/semantic-ui-tree.json` and recovered flow specs live under `$consumer/reverse-output/flow-ui-contract/`. Managed run payloads remain under `$consumer/.penflow-tmp/` until safe preflight/postflight cleanup.

## Full Demo Mode

Use for a reproducible local fixture.

```bash
fresh=$(mktemp -d)
penflow demo --out "$fresh" --json
penflow run --target "$fresh" --json
```

The demo deterministically derives its actual tree from the generated expected tree and writes package-owned synthetic example data labeled `static-demo-fixture`. This immutable packet is not a fresh runtime, renderer, or model verdict. It never launches or copies from a browser, simulator, runtime adapter, test helper, or `examples/full`; removing `actual-ui-tree.json` or deleting/corrupting load-bearing visual evidence must make the next run fail closed.

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
4. After any `.pen` change, rerun `penflow map-pencil-context ui.pen semantic-ui-tree.json --out pencil-context-map.json --strict-coverage --contract flow-ui-contract/contract.json --coverage-out semantic-context-coverage.json --json`; only coverage `PASS` permits `validate-pen`.
5. Re-run `validate-pen`, `validate-actual --schema`, and `compare-tree`.
6. Stop with the remaining report if the issue requires a runtime artifact not available locally.

## cc-hub Sync

This skill is project-local under `.agent-sync/skills/penflow/` and is ready for cc-hub/agent-sync symlink management.
