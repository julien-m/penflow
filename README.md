<!-- LiveSpec traceability anchors -->
<!-- @spec(FR-001) -->
<!-- @spec(FR-002) -->
<!-- @spec(FR-003) -->
<!-- @spec(FR-006) -->
<!-- @spec(FR-007) -->
<!-- @spec(FR-008) -->
<!-- @spec(FR-012) -->
<!-- @spec(FR-013) -->
<!-- @spec(FR-014) -->

# Penflow

Penflow is a deterministic Python CLI for pen.dev `.pen` design contracts. It parses `.pen` JSON, validates `context`, exports expected UI trees, validates external actual UI trees, compares both trees structurally, writes JSON reports, and generates simple screen/code artifacts. Penflow remains runtime-agnostic: browsers, simulators, application runtimes, and pen.dev itself stay outside the Python core.

The project is licensed under the [MIT License](LICENSE). Before contributing or reporting a vulnerability, **read** [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md). Release status and provenance limits are recorded in [CHANGELOG.md](CHANGELOG.md), [RELEASE.md](RELEASE.md), and [PROVENANCE.md](PROVENANCE.md).

## Consumer Project Hygiene

Run Penflow against the exact consumer project, never the Penflow source checkout. At the start and end of every Penflow task, capture a read-only Doctor receipt:

```bash
penflow doctor --project . --check --json
```

`--project` selects that exact directory (or an existing file's parent); without it, the exact CWD is selected. Doctor never widens the boundary to the enclosing repository. A collective Git worktree may therefore contain several independent Penflow projects, but each selected project must contain exactly one regular, case-sensitive `ui.pen`. Keep every logical screen revision inside that infinite canvas as a top-level frame with `penflow.lifecycle` schema 1: one `active` revision per `logical_screen_id`, plus any `draft` and `archive` revisions. Unmarked legacy top-level frames remain active for compatibility; downstream exports consume active regions only. The internal `git_root` is used only for scoped Git interrogation and transient Git metadata coordination; `.pen` discovery, ignore ownership, temporary inventory, repair and cleanup remain below `<consumer-project-root>`.

Technical working data belongs only below ignored `.penflow-tmp/`, `.penflow-run/`, and `.mockup-validation/`. Producer preflight reconciles eligible completed, failed, or proven-dead runs; postflight removes successful working payload after durable outputs are finalized. Live owners, unknown files, symlinks, escaped paths, tracked/staged data, referenced evidence, and `ui.pen` are preserved and block unsafe cleanup.

`penflow doctor --project . --fix --json` may initialize `penflow/ui.pen` when none exists and install the managed `.gitignore` block. It never chooses among multiple `.pen` files or rewrites Git history/index state. Resolve `multiple_pen_files` manually by consolidating the intended screen revisions into the canonical canvas, then deliberately remove or migrate the extra files. For tracked or staged temporary paths, review them and manually unstage/untrack them before rerunning Doctor.

Exit codes are `0` PASS, `1` project-health block, `2` usage error, `3` untrustworthy I/O/schema result, and `4` cleanup safety block.

## JSON-Only Contract v2

Local form submits use `kind: state_change`, `event: submit`, a guard and a same-screen
success transition. They require no invented network mutation or permission; mutation-bearing
actions keep all request checks. C51 still requires the action, both guard outcomes and the
transition to be observed. Read the [local submit contract](.specs/features/045-penflow-json-only-strict-contract-v2/spec.md#local-submit-clarification--2026-09-06).

`flow-ui-contract/contract.json` is the canonical strict v2 business contract. Flow/screen Markdown is a deterministic, hash-bound projection produced by `export-flow-docs`; legacy Markdown is accepted only through explicit migration. Strict coverage is bidirectional: every contract node has one Pencil anchor and every authored Pencil node is explicitly semantic, inherited, or decorative.

## Complete Verification (C51)

The normal workflow produces one versioned `run-report.json` and revalidates it at the consumer's final transition. Its profile comes from the requested deliverable: `design` checks the approved contract and native design; `implementation` adds the actual application build, executed scenarios and observed outcomes. Missing runtime evidence never changes an implementation request into a design request.

The workflow supplies these inputs automatically; the equivalent CLI calls are:

```bash
penflow run --target penflow --profile implementation --build-manifest "$RUNNER_BUILD_MANIFEST" --project . --json
penflow validate-report penflow/run-report.json --schema --required-profile implementation --build-manifest "$RUNNER_BUILD_MANIFEST" --project . --json
```

For design closure, the workflow selects `design` and omits the build manifest. `--project` is the exact consumer project, while the workspace may be its `penflow/` or `handoff/penflow/` directory. The manifest is produced by the external runner for the build actually exercised; a Git revision, static fixture or file hash alone is not runtime evidence.

C51 derives requirements and applicability from reviewed LiveSpec sources or an authenticated frozen Brainstorm contract. It joins those requirements to contract obligations, native evidence and typed observations. Every required gate and obligation must pass: missing, skipped, stale or unknown evidence blocks closure. Revalidation checks current inputs and caller identities instead of trusting a stored `PASS`. Historical reports and the opt-in C47 `--strict-closure` path remain readable but do not certify C51.

The public Python boundary is `penflow.verification.produce_verification_report(...)` and `validate_verification_report(...)`. The latter returns `penflow-verification-validation` version 1 with the checked report hash, exact project/workspace, profile and build-manifest identity. **Read** [the verification workflow](docs/verification-workflow.md) for the schemas, automatic producer steps and integration contract; **read** [the adapter guides](docs/adapters/README.md) for the external runtime boundary. Generated code remains a scaffold until these implementation checks pass.

## Strict by Default (Breaking Change, Feature 049 / C24)

Penflow exits non-zero on **warning-severity issues by default**. Errors always fail; warnings fail unless you pass the global `--lenient` flag (accepted before or after the subcommand on every validating command):

- Applies to `validate-pen`, `validate-flow-specs`, `validate-flow-contract`, `validate-semantic-tree`, `validate-actual`, `validate-flow`, `validate-screen`, `validate-code-ir`, `validate-report`, `validate-visual-evidence`, `compare-tree`, `detect-drift`, `lint-tokens`, `check-consistency`, `audit-visual`, `export-expected`, `ci`.
- `compare-tree` and `ci` default threshold is **0.98** (was 0.9). `--lenient` restores the 0.9 default; an explicit `--threshold` always wins.
- `export-semantic-tree`, `reverse-pen`, and `extract-tokens` now report issues and exit 1 on them (previously always exit 0). `reverse-pen` flags every generated artifact still containing `[NEEDS CLARIFICATION]` as `reverse.clarification_needed`; `extract-tokens` flags uninterpretable values as `tokens.value.unparsed`.
- `detect-drift` carries blocking data: each issue has a `blocking` boolean (`BLOCKING_DRIFT_CODES` = `drift.semantic_tree_invalid`, `drift.semantic_node_missing_in_pen`, `drift.pencil_context_obsolete`, `drift.clarification_marker`), the summary has a `blocking` count, and the report status gains `BLOCKED`. **Blocking issues exit 1 even with `--lenient`.**
- Silent coercions now warn: non-keyword string bbox values emit `pen.bbox.invalid` (via `validate-pen`/`inspect`; Pencil sizing keywords `fill_container`/`fit_content(...)` are exempt), and unparsable theme dimensions emit `theme.value.unparsed` (via `lint-tokens`).
- `jsonschema>=4` is a hard dependency; the minimal fallback validators were removed.

Migration: append `--lenient` to any pipeline that tolerated warnings, or fix the warnings (recommended).

## Install

Penflow requires Python 3.12 or newer. The repository is the current distribution source; no PyPI release is claimed.

For a command available outside a checkout after the repository is public:

```bash
uv tool install "git+https://github.com/julien-m/penflow.git"
penflow --help
```

For development from a clone:

```bash
git clone https://github.com/julien-m/penflow.git
cd penflow
uv sync --extra dev --locked
uv run penflow --help
uv run python -m pytest
```

To build the same wheel and source archive checked by CI:

```bash
uv build
python3 -m venv /tmp/penflow-release-check
/tmp/penflow-release-check/bin/python -m pip install dist/penflow-0.1.0-py3-none-any.whl
/tmp/penflow-release-check/bin/penflow --help
```

The release checklist in [RELEASE.md](RELEASE.md) defines the version/tag/build order. Do not publish an artifact whose version differs between `pyproject.toml`, `penflow.__version__`, and the tag.

## Core Commands

In this block, `<workspace>` is `<consumer-project-root>/penflow`; every
canonical artifact stays below that workspace while Doctor governs the exact
consumer project root.

```bash
penflow doctor --project <consumer-project-root> --check --json
penflow run --target <workspace> --project <consumer-project-root> --theme-css <workspace>/theme.css --references <workspace>/references --strict --json
penflow doctor --project <consumer-project-root> --check --json
penflow inspect <workspace>/ui.pen --project <consumer-project-root>
penflow pencil-sync <workspace>/ui.pen --project <consumer-project-root> --expect-screens 8 --json
penflow verify-pencil-persistence <workspace>/observation.json --document <workspace>/ui.pen --run-id run-001 --operation save-current-pencil-document --out <workspace>/persistence-receipt.json --project <consumer-project-root> --json
penflow validate-pen <workspace>/ui.pen --project <consumer-project-root>
penflow export-expected <workspace>/ui.pen -o <workspace>/expected-ui-tree.json --project <consumer-project-root>
penflow check-consistency <workspace>/expected-ui-tree.json --out <workspace>/consistency-report.json --project <consumer-project-root> [--group-by role|role+intent|role+intent+variant|role+intent+variant+size-class]
penflow audit-visual <workspace>/expected-ui-tree.json --theme-css <workspace>/theme.css [--layout-snapshot <workspace>/.mockup-validation/visual-evidence/layout-snapshot.json] --out <workspace>/visual-metrics-report.json --project <consumer-project-root>
penflow theme-fingerprint <workspace>/theme.css --project <consumer-project-root> --json
penflow validate-visual-evidence <workspace>/.mockup-validation/visual-evidence --expected <workspace>/expected-ui-tree.json --theme-css <workspace>/theme.css --project <consumer-project-root> --json
penflow validate-reference-fidelity <workspace>/.mockup-validation/visual-evidence --references <workspace>/references --project <consumer-project-root> --json
penflow validate-actual <workspace>/actual-ui-tree.json --project <consumer-project-root> [--schema]
penflow validate-flow-contract <workspace>/flow-ui-contract/contract.json --project <consumer-project-root> --json
penflow validate-causal-evidence <workspace>/flow-ui-contract/contract.json <workspace>/evidence/causal-evidence.json --project <consumer-project-root> --json
penflow export-semantic-tree <workspace>/flow-ui-contract/contract.json --out <workspace>/semantic-ui-tree.json --project <consumer-project-root>
penflow validate-semantic-tree <workspace>/semantic-ui-tree.json --project <consumer-project-root> --json
penflow draft-pen-from-tree <workspace>/semantic-ui-tree.json --out <workspace>/ui.pen --theme-css <workspace>/theme.css --project <consumer-project-root> --json
penflow lint-tokens <workspace>/ui.pen --theme-css <workspace>/theme.css --out <workspace>/token-lint-report.json --project <consumer-project-root> --json
penflow enrich-pen <workspace>/ui.pen <workspace>/semantic-ui-tree.json --out <workspace>/ui.pen --project <consumer-project-root> --json
penflow map-pencil-context <workspace>/ui.pen <workspace>/semantic-ui-tree.json --out <workspace>/pencil-context-map.json --project <consumer-project-root> --strict-coverage --contract <workspace>/flow-ui-contract/contract.json --coverage-out <workspace>/semantic-context-coverage.json --json
penflow audit-context-coverage <workspace>/ui.pen --contract <workspace>/flow-ui-contract/contract.json --out <workspace>/semantic-context-coverage.json --project <consumer-project-root> --json
penflow export-flow-docs <workspace>/flow-ui-contract/contract.json --out <workspace>/flow-ui-contract --project <consumer-project-root> --json
penflow export-flow-docs <workspace>/flow-ui-contract/contract.json --out <workspace>/flow-ui-contract --check --project <consumer-project-root> --json
penflow migrate-flow-md-to-contract-json <workspace>/flow-ui-contract --out <workspace>/flow-ui-contract/contract.json --project <consumer-project-root> --json
penflow reverse-pen <workspace>/ui.pen --out <workspace>/reverse-output --project <consumer-project-root> --json
penflow detect-drift <workspace>/flow-ui-contract/contract.json <workspace>/semantic-ui-tree.json <workspace>/ui.pen --out <workspace>/drift-report.json --project <consumer-project-root> --json
penflow checklist-from-drift <workspace>/drift-report.json --out <workspace>/checklist.json --project <consumer-project-root> [--group <name>] --json
penflow code-ir --from-context <workspace>/ui.pen --contract <workspace>/flow-ui-contract/contract.json --flow-id checkout --flow-name "Checkout flow" --out <workspace>/code-ir.json --project <consumer-project-root>
penflow validate-code-ir <workspace>/code-ir.json --project <consumer-project-root> --json
penflow compare-tree <workspace>/expected-ui-tree.json <workspace>/actual-ui-tree.json --out <workspace>/compare-report.json --project <consumer-project-root> --json
penflow review-report <workspace>/compare-report.json --out <workspace>/review-report.json --project <consumer-project-root> --json
penflow fix-report <workspace>/compare-report.json --out <workspace>/fix-report.json --project <consumer-project-root> --json
penflow validate-report <workspace>/review-report.json --schema --project <consumer-project-root> --json
penflow demo --out <workspace> --project <consumer-project-root>
```

`penflow run --target <workspace> [--theme-css f] [--references dir] [--strict] --json` is the single-command CI/operator wrapper for an existing Penflow workspace. Its summary and every gate carry the same `runId`, identity `version`, current-run provenance, and SHA-256 lineage for `ui.pen`, contract, expected/actual trees, theme, references, renderer, and export timestamp. Missing required inputs, explicitly requested missing optional paths, source mutation, or citation/provenance divergence make the run nonzero; unarmed absent theme/reference inputs receive deterministic `not-provided` receipts. The command preserves Penflow's runtime-agnostic boundary: no browser, simulator, Playwright, or Pencil MCP control is added to core; the optional `pencil-sync` trigger only runs when explicitly armed with `PENFLOW_RUN_PENCIL_SYNC=1`, otherwise it is reported as `SKIP`. That trigger never substitutes for the separate C46 persistence receipt.

`penflow run --target <workspace> --references <workspace>/references --strict-closure --json`
is the explicit C47 closure check. It does not run the mutating pipeline: it revalidates the
existing `.penflow-run/pencil-persistence-receipt.json`, requires a fresh
`runtime-capture` actual receipt with `sessionId`, validates the declared homologous
references and PASS-only structured blocking visual proof, and requires every artifact to
share one run id. It writes only `.penflow-run/strict-closure.json`, whose schema and
integrity bind all workspace input bytes. Missing, `BLOCKED_VISUAL_NOT_RUN`,
`PASSED_WITH_WARNINGS`, stale, replayed, mismatched, non-blocking, generic, duplicated, or
tampered evidence exits 1 with structured issues. Without `--strict-closure`, existing
`penflow run` behavior is unchanged.

For dense multi-screen mockups, prefer `penflow check-consistency expected-ui-tree.json --group-by role+intent+variant+size-class --out consistency-report.json --json`. The size class buckets node height so compact headers are not compared with full-height panels; anonymous containers without stable intent, variant, or human name are skipped, and repeated divergences are aggregated per group.

### Theme Token Contract

**Read** [`docs/theme-contract.md`](docs/theme-contract.md) before generating `theme.css` for `draft-pen-from-tree`, `lint-tokens`, or Brander-style handoff. The stable contract accepts canonical and `--pf-*` aliases for core colors, `panel`/`panel-2`, `success`/`warning`/`info`, `font-sans`/`font-mono`, `font-size-xs` through `font-size-xl`, plus dynamic `palette-*` color slots and `radius-*` numeric slots. `lint-tokens` records the effective `spacing_scale`, `radius_scale`, and `fontsize_scale` in the strict report inputs; theme-declared font sizes and radii extend defaults unless the matching CLI override is passed.

### Pencil Editor Sync

Run `penflow pencil-sync <ui.pen> [--expect-min-nodes N] [--expect-screens N] --json` after any Pencil editor or MCP mutation. It is only an operator trigger: it reports pre/post SHA-256 plus inspection, always declares `persistence_status: UNVERIFIED` and `closes_persistence: false`, and never uses mtime, pane text, or trigger success to close persistence.

The operator must preserve distinct pre/post snapshot files and write a `penflow-pencil-persistence-observation` containing the exact `run_id`, document path, requested `operation`, trigger provider/status, snapshot paths, and claimed SHA-256 values. Then run `penflow verify-pencil-persistence observation.json --document ui.pen --run-id <exact-run> --operation <exact-operation> --out persistence-receipt.json --json` followed by `penflow validate-report persistence-receipt.json --schema --json`. The verifier independently re-reads observation, pre/post/current bytes; only a PASS receipt with `closes_persistence: true` closes the gate. No-op/same-digest, trigger-only, stale, replayed, tampered, missing, or mismatched evidence exits nonzero.

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

Adapter conformance docs live under [`docs/adapters/`](docs/adapters/). The C13 guides tell external producers in three target stacks — [Web DOM](docs/adapters/web-dom.md), [SwiftUI + XCTest](docs/adapters/swiftui-xctest.md), and [React Native](docs/adapters/react-native.md) — how to emit an `actual-ui-tree.json` (contract C12) that `penflow validate-actual --schema` accepts on the first try. [Causal transition evidence](docs/adapters/causal-transition-evidence.md) defines the C44 pre/action/post, identity, receipt, and independent-outcome packet accepted by `validate-causal-evidence`. Penflow ships **zero runtime code** for these stacks — it never launches a browser, simulator, or application runtime.

### Full Demo

Run `penflow demo --out examples/full` to regenerate the contract **C14/C20** fixture. Use [`examples/full/`](examples/full/) to inspect the complete chain: `contract.json`, documentation flow specs, semantic tree, enriched Pencil file, expected tree, code IR, actual-tree fixture, compare report, review report, and fix report.

To prove the default Stage C1 bootstrap from an empty directory:

```bash
fresh=$(mktemp -d)
penflow demo --out "$fresh" --json
penflow run --target "$fresh" --json
```

`penflow demo` derives `actual-ui-tree.json` deterministically from its generated expected tree and installs package-owned synthetic example data labeled `static-demo-fixture`. This immutable packet is not a fresh runtime, renderer, or model verdict. The command does not launch or copy from a browser, simulator, runtime adapter, test helper, or `examples/full`; `penflow run` fails closed if the generated actual tree or load-bearing visual evidence is removed or corrupted.

### Existing Project Integration

**Read** [`docs/project-integration.md`](docs/project-integration.md) when adding Penflow to an existing app repository. It explains the recommended `penflow/` workspace layout, forward adoption, Pencil enrichment, legacy reverse migration, implementation handoff through `code-ir.json`, runtime `actual-ui-tree.json` verification, and a minimal CI gate.

### Guided Mockup Optimization

**Read** [`.agent-sync/skills/mockup-factory/SKILL.md`](.agent-sync/skills/mockup-factory/SKILL.md) when generating, auditing, or optimizing Pencil mockups. The Penflow-local Mockup Factory uses `flow-ui-contract`, `semantic-ui-tree.json`, `.pen`, `pencil-context-map.json`, `expected-ui-tree.json`, and `detect-drift` reports as deterministic anchors. Since feature 052 the audit rubric is prescriptive: every category maps to a scripted gate (`lint-tokens`, `check-consistency`, `audit-visual`, `detect-drift`, `compare-tree`, `validate-visual-evidence`), Critical is exactly any error-severity gate issue or `blocking: true` item, and fixes run in a bounded fix-re-audit loop (max 3 iterations, full chain rerun, no PASS without a final clean run; residual criticals escalate). The design audit verdict is the strict `audit-report.json` (`kind: penflow-mockup-audit`, with `iterations`, per-gate `{gate, command, exit_code, report_path, result}`, and `residual_issues[]`) — `penflow validate-report audit-report.json --schema` checks that audit. C51 `run-report.json` production and fresh revalidation close the complete design workflow afterward.

Since feature 068, **Read** [`.agent-sync/skills/flow-ui-contract/references/design-read.md`](.agent-sync/skills/flow-ui-contract/references/design-read.md) for the landing/showcase `<target>/design-read.json` artifact: a design-read-protocol one-liner plus integer `variance`, `motion`, and `density` dials. Mockup Factory reads that artifact when present; **Read** [`.agent-sync/skills/mockup-factory/references/design-taste-advisory.md`](.agent-sync/skills/mockup-factory/references/design-taste-advisory.md) for the `.mockup-validation/design-taste-advisory.md` anti-default and AI-tell review report. The report is advisory only: it never changes gate status, `audit-report.json` status, schemas, or exit-code policy.

Since feature 055 the contract-gate checklist is machine-seeded: `penflow checklist-from-drift drift-report.json --out checklist.json [--group <name>] --json` maps every drift issue to one anchored open `gate: contract` item (id `drift-<code>-<NNN>` in `_issue_sort_key` order, copied `severity`/`blocking`, `screen_id` derived from `semantic_id`/path with a `_workspace` fallback so nothing is dropped). The command is deterministic (byte-identical reruns, no timestamps, top-level `sourceReport` traceability) and fail-closed (malformed JSON, wrong `kind`, or a schema-invalid report exits 1 without creating or modifying `--out`); items for the other five gates are appended at the skill layer after seeding.

Before final PASS, Mockup Factory also runs the Visual Evidence Gate. **Read** [`.agent-sync/skills/mockup-factory/references/visual-validation.md`](.agent-sync/skills/mockup-factory/references/visual-validation.md) before applying it. When Pencil rendering is available, the gate must export PNGs, show every exported screen as a Markdown image with its absolute path, run `visual-preview url <absolute-path>` when available for browser annotation, dump a layout snapshot to `layout-snapshot.json`, run `audit-visual` with `--layout-snapshot` so overlap/overflow uses real Pencil bboxes, run a vision pass answering ONLY the five locked categories (`visual_balance`, `rendering_artifacts`, `readability`, `perceived_hierarchy`, `imagery_quality`), and write `.mockup-validation/visual-evidence/manifest.json` plus `vision-report.json` (`kind: penflow-vision-report`; legacy `visual-report.json` is deprecated). The verdict is `penflow validate-visual-evidence <dir> --expected expected-ui-tree.json` exiting 0 — the gate is the exit code, not prose; preview URLs are annotation-only and not canonical proof. The schema rejects deterministic categories (contrast, touch targets, overflow belong to `audit-visual`), so vision cannot hand-wave computable facts. Since feature 053, multi-screen sets also require a cross-mockup coherence pass: export all audited screens at a uniform scale, capture one `contact-sheet.png`, expose it through the same Markdown image + `visual-preview url` channels, and answer ONLY the four coherence categories (`cross_screen_rhythm`, `palette_coherence`, `typography_coherence`, `component_recognition`) in the vision report's `coherence` section — required when the expected tree has ≥ 2 screens (`evidence.coherence.missing`), with a non-empty contact-sheet PNG on disk; the numeric cross-screen anchor stays the feature 047 `check-consistency` report. If `visual-preview` is unavailable, operators keep the Markdown image and record browser preview unavailable without changing the deterministic evidence packet by itself. Without a renderer the status is `BLOCKED_VISUAL_NOT_RUN` or escalated rather than silently passing structural-only validation.

When a workspace has `references/references-manifest.json`, each reference entry is `{screen_id, file, sha256, source, mapping: {surface, screen_id, region_id, state, crop}}` and files resolve relative to `references/`. The evidence manifest declares that file via `references_manifest`; `vision-report.json` must add `reference_fidelity` entries for every referenced screen with the locked categories `layout_match`, `palette_match`, `component_parity`, and `density_match`, citing both reference and export files. The additional gate is `penflow validate-reference-fidelity .mockup-validation/visual-evidence --references references --json`: copied exports fail as `reference.evidence_is_reference_copy`, and strong deterministic-vs-LLM disagreement fails as `reference.llm_metric_disagreement`.

Since feature 070 (contract C45), `manifest.json` and `vision-report.json` must share one exact `runId`; every required screen, coherence, and reference criterion is `blocking: true`, has `result: pass`, and carries structured `proof` for surface, screen, hierarchical region, state, assertion, measurement, and hashed artifacts with in-bounds crops. Reference entries add an explicit homologous mapping. Narrative-only evidence, warning/SKIP status, invalid or stretched crops, reference bytes copied as actual, region drift, and one actual/reference SHA reused across non-homologous mappings all exit nonzero.

Since feature 056 (contract C31), evidence packets are bindable to the exact theme bytes they were rendered against. `penflow theme-fingerprint theme.css --json` emits `{path, sha256}` — the SHA-256 of the file's raw bytes (no normalization, reproducible via `shasum -a 256`; missing/unreadable file exits 2). The skill layer writes that block plus an opaque `runId` (ISO-8601 timestamp + short slug recommended) into `manifest.json` — both fields are optional and backward compatible. Arming the gate with `penflow validate-visual-evidence <dir> --theme-css theme.css` requires the manifest stamp to match the current file: a missing stamp emits `evidence.theme.missing`, a mismatching one emits `evidence.theme.stale` (both error severity, exit 1), so any theme edit deterministically invalidates stale evidence and forces a re-run of the bounded loop; a `--theme-css` path missing on disk is a boundary error (exit 2). Without the flag, behavior and output are byte-identical to before — stamps stay inert.

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

`draft-pen-from-tree` is a structural draft stage. If its JSON output is saved as `draft-report.json`, the report includes `fidelity: "wireframe"`: draft = structure / wireframe, PAS un mockup final ; le hi-fi passe par mockup-factory.

Legacy Markdown-only docs may still mention `penflow export-semantic-tree examples/full/flow-ui-contract --out semantic-ui-tree.json --json`; strict v2 uses `contract.json`.

#### Enrichment

Start from an existing visual `.pen`, inject semantic context, preserve layout, validate, and generate expected/code IR artifacts.

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
penflow export-semantic-tree "$consumer/flow-ui-contract/contract.json" --project "$consumer" --out "$consumer/semantic-ui-tree.json" --json
penflow validate-semantic-tree "$consumer/semantic-ui-tree.json" --project "$consumer" --json
penflow enrich-pen "$consumer/ui.pen" "$consumer/semantic-ui-tree.json" --project "$consumer" --out "$consumer/ui.pen" --json
penflow map-pencil-context "$consumer/ui.pen" "$consumer/semantic-ui-tree.json" --project "$consumer" --out "$consumer/pencil-context-map.json" --strict-anchors --json
penflow validate-pen "$consumer/ui.pen" --project "$consumer" --json
penflow export-expected "$consumer/ui.pen" --project "$consumer" --out "$consumer/expected-ui-tree.json" --json
penflow code-ir --from-context "$consumer/ui.pen" --semantic-tree "$consumer/semantic-ui-tree.json" --context-map "$consumer/pencil-context-map.json" --contract "$consumer/flow-ui-contract/contract.json" --flow-id checkout --flow-name "Checkout flow" --project "$consumer" --out "$consumer/code-ir.json" --json
penflow doctor --project "$consumer" --check --json
```

#### Reverse

Start from legacy Pencil, recover flow/screen specs and a semantic tree, then validate the recovered contract.

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
penflow validate-semantic-tree "$consumer/reverse-output/semantic-ui-tree.json" --project "$consumer" --json
penflow validate-pen "$consumer/ui.pen" --project "$consumer" --json
penflow doctor --project "$consumer" --check --json
```

`reverse-pen --out <dir>` writes a directory containing `semantic-ui-tree.json` and `flow-ui-contract/`; validate `<dir>/semantic-ui-tree.json`, not the directory path itself.
Reverse output marks missing business logic as `[NEEDS CLARIFICATION]`; do not invent unknown validations, side effects, or state transitions.
Strict default: `reverse-pen` exits 1 while clarification markers remain (`reverse.clarification_needed`); pass `--lenient` to keep scripted chains green, then resolve the markers.

#### Post-Implementation Compare

After implementation, an external runtime adapter writes `actual-ui-tree.json`. Penflow validates and compares that file; it does not launch or inspect the running app.

`compare-tree` checks presence, role, text, hierarchy, order, bbox (±`bbox_px`), colors, radius (±`radius_px`), typography (±`font_px`), and — feature 048 — layout properties: `layout` and `alignItems` exact-match (`node.visual.layout`, `node.visual.alignItems`), `gap` and `padding` within ±`spacing_px` (default 2; `node.visual.gap`, `node.visual.padding`). Padding forms are normalized (`16` ≡ `[16, 16]` ≡ `[16, 16, 16, 16]`). Tolerances are overridable per node via `context.tolerance` (e.g. `tolerance: {spacing_px: 4}`); absent keys are never compared, so pre-048 trees stay green.

```bash
penflow validate-actual actual-ui-tree.json --schema --json
penflow validate-actual-provenance <workspace> --expected expected-ui-tree.json --surface web --json
penflow compare-tree expected-ui-tree.json actual-ui-tree.json --out compare-report.json --json
penflow review-report compare-report.json --out review-report.json --json
penflow fix-report compare-report.json --out fix-report.json --json
penflow validate-report compare-report.json --schema --json
```

Since P0-2 (contract C2), the adapter also writes a content-bound sidecar `actual-ui-tree.provenance.json` (`kind: penflow-actual-provenance`) next to the actual tree, and `validate-actual-provenance` is the final `penflow run` gate. The receipt records `sourceKind` (`runtime-capture` for a fresh capture/export, `static-demo-fixture` for explicitly qualified frozen example data), `producer`, `capturedAt` (ISO-8601 UTC), `target.surface`, and `content.sha256` (SHA-256 of the actual-tree bytes). Penflow never captures a runtime — it only validates this receipt from local files and rejects, fail-closed, a missing/incomplete receipt (`provenance.receipt.missing`/`.invalid`), a forged digest (`provenance.digest.mismatch`), a `content.path` naming another file (`provenance.content.path_mismatch`), a stale/future/unparseable `runtime-capture` timestamp (`provenance.timestamp.stale`/`.future`/`.invalid`; fixtures are exempt), an inadmissible source kind under `--require-fresh` (`provenance.source_kind.inadmissible`), an incompatible `--surface` (`provenance.target.incompatible`), and a `runtime-capture` whose root is byte-identical to the design-derived expected tree (`provenance.actual.derived_from_expected`). A qualified `static-demo-fixture` may reuse expected bytes but can never masquerade as fresh. The `penflow run` gate arms the runtime-capture freshness policy against the current run's export boundary with a documented default window of 86400s (24h), overridable via `penflow run --actual-max-age-seconds N`; a `static-demo-fixture` is exempt and that exemption is unreachable with `sourceKind=runtime-capture`. Any explicit max-age (`--actual-max-age-seconds`, `--max-age-seconds`, or programmatic) must be finite and strictly positive — `nan`, `inf`, `-inf`, overflowing `1e999`, `0`, and negatives are rejected fail-closed with a structured error and non-zero exit before any report is written (`allow_nan=False` guarantees no `NaN`/`Infinity` JSON), and an unparseable internal run boundary fails explicitly. `content.path` must be a relative name without `..` traversal (`provenance.content.path_invalid`); the `content.sha256` digest is the authority over the bytes.

#### Regression

Run the contract **C16** regression proof with pytest, then reproduce the final CLI chain on the stable fixtures.

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
penflow export-semantic-tree "$consumer/flow-ui-contract/contract.json" --project "$consumer" --out "$consumer/semantic-ui-tree.json" --json
penflow validate-semantic-tree "$consumer/semantic-ui-tree.json" --project "$consumer" --json
penflow draft-pen-from-tree "$consumer/semantic-ui-tree.json" --project "$consumer" --out "$consumer/penflow/ui.pen" --theme-css "$consumer/theme.css" --json
penflow validate-pen "$consumer/penflow/ui.pen" --project "$consumer" --json
penflow export-expected "$consumer/penflow/ui.pen" --project "$consumer" -o "$consumer/expected-ui-tree.json" --json
penflow enrich-pen "$consumer/penflow/ui.pen" "$consumer/semantic-ui-tree.json" --project "$consumer" --out "$consumer/penflow/ui.pen" --json
penflow validate-pen "$consumer/penflow/ui.pen" --project "$consumer" --json
penflow reverse-pen "$consumer/penflow/ui.pen" --project "$consumer" --out "$consumer/reverse-output" --lenient --json
penflow validate-semantic-tree "$consumer/reverse-output/semantic-ui-tree.json" --project "$consumer" --json
penflow validate-actual "$consumer/actual-ui-tree.json" --schema --project "$consumer" --json
penflow compare-tree "$consumer/expected-ui-tree.json" "$consumer/actual-ui-tree.json" --project "$consumer" --out "$consumer/compare.json" --json
penflow review-report "$consumer/compare.json" --project "$consumer" --out "$consumer/review.json" --json
penflow fix-report "$consumer/compare.json" --project "$consumer" --out "$consumer/fix.json" --json
penflow doctor --project "$consumer" --check --json
```

`$consumer/reverse-output` is a reverse output directory; its semantic tree lives at `$consumer/reverse-output/semantic-ui-tree.json` and recovered flow specs live under `$consumer/reverse-output/flow-ui-contract/`. Penflow-owned working snapshots and run payloads stay below `$consumer/.penflow-tmp/` and are reconciled by preflight/postflight.

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
- Pencil `context` is written as `key=value` pairs separated by `;` (`semantic_id=cockpit-live.git; role=container`). Attach it during `batch_design` insertion for screen frames, sections, interactive components, and lists. Run `map-pencil-context --strict-anchors` before downstream `.pen` readers; use `--create-placeholders` only as explicit repair scaffolding because it reports `PARTIAL`.
- Semantic anti-gaming is fail-closed: `validate-semantic-tree` rejects repeated list-like containers without `repeat`, and `validate-flow-contract --json` reports per-screen `interactive_coverage` while rejecting unbound interactive nodes.
- Runtime frameworks provide actual UI trees; Penflow validates and compares those trees.
- The primary validation is structural and semantic, not pixel-perfect.
- Demo `.pen` files use Pencil document schema `2.11` with context shorthand strings so they can be opened in Pencil and parsed by Penflow.

## Local Skill

**Read** [`.agent-sync/skills/penflow/SKILL.md`](.agent-sync/skills/penflow/SKILL.md) to use the project-local skill interface. It is stored under `.agent-sync/skills/` so cc-hub/agent-sync can symlink it when requested.

**Read** [`.agent-sync/skills/flow-ui-contract/SKILL.md`](.agent-sync/skills/flow-ui-contract/SKILL.md) to capture flow/screen behavior around Pencil artifacts. Invoke the installed skill as `flow-ui-contract`; legacy wording such as `specify flows` should route there, but no separate `specify-flows` slash command is installed. It writes validated `flow-ui-contract/flows/*.md` and `flow-ui-contract/screens/*.md` files, and reports `fresh` / `stale` / `unspecified` coverage with `python3 .agent-sync/skills/flow-ui-contract/validator.py --status --target <target>`.

**Read** [`.agent-sync/skills/mockup-factory/SKILL.md`](.agent-sync/skills/mockup-factory/SKILL.md) to run the tree-aware guided UX/UI optimizer for Pencil mockups. The skill can orchestrate external Pencil/audit tooling, but Penflow Python core stays runtime-agnostic.

The pre-Pencil semantic contract is defined in [`penflow/schemas/semantic-ui-tree.schema.json`](penflow/schemas/semantic-ui-tree.schema.json), with a deterministic example at [`examples/demo/semantic-ui-tree.json`](examples/demo/semantic-ui-tree.json). Export it from `flow-ui-contract/contract.json` with `penflow export-semantic-tree path/to/flow-ui-contract/contract.json --out semantic-ui-tree.json`, validate it with `penflow validate-semantic-tree semantic-ui-tree.json --json`, then create a theme-aware Pencil draft with `penflow draft-pen-from-tree semantic-ui-tree.json --out ui.pen --theme-css theme.css --json`, enrich the canonical Pencil file in place with `penflow enrich-pen ui.pen semantic-ui-tree.json --out ui.pen --json`, emit an explicit mapping artifact with `penflow map-pencil-context ui.pen semantic-ui-tree.json --out pencil-context-map.json --strict-anchors --json`, reverse `ui.pen` with `penflow reverse-pen ui.pen --out reverse-output --json`, or report drift with `penflow detect-drift path/to/flow-ui-contract/contract.json semantic-ui-tree.json ui.pen --out drift-report.json --json`. `validate-flow-contract --json` includes `interactive_coverage`, and static screens without interactive actions must declare `static: true` plus `static_reason`. This schema is distinct from post-implementation actual UI trees.

`detect-drift` selects canonical C20 when its first argument is `contract.json` or a directory containing it. It checks the complete stored semantic projection and exhaustive C20/Pencil coverage before canonical drift. Relative and absolute provenance paths may differ only when they resolve to the same selected contract; JSON pointers and all semantic fields remain exact. Invalid C20, changed projections and mismatched Pencil context block even with `--lenient`. Directories without C20 keep legacy Markdown behavior. This preparation diagnostic does not require or certify a C51 report; after moving a workspace, use the existing export/enrichment steps to refresh stale generated artifacts.

## Conventions

Project conventions are generated from the LiveSpec stack in [`.conventions/index.md`](.conventions/index.md) and [`.conventions/manifest.yaml`](.conventions/manifest.yaml).
The stack refresh also installs the generated Python pre-commit hook in [`.githooks/pre-commit`](.githooks/pre-commit) and GitHub Actions workflows in [`.github/workflows/ci.yml`](.github/workflows/ci.yml) and [`.github/workflows/security.yml`](.github/workflows/security.yml).
