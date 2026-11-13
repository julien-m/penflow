<!-- LiveSpec traceability anchors -->
<!-- @spec(FR-003) -->
<!-- @spec(FR-004) -->
<!-- @spec(FR-013) -->

# flow-ui-contract

Penflow-local migration of the old specify-flows workflow. It captures behavior around visual mockups and pen.dev `.pen` files, then promotes reviewed behavior into canonical `flow-ui-contract/contract.json` for semantic UI tree export and pen.dev enrichment.

Invoke the installed skill as `flow-ui-contract`. Legacy wording signals such as `specify flows`, `flow specs`, and `spec flows` should route here; no separate `specify-flows` slash command is installed.

## Purpose

Use this skill to author or recover the behavior layer before code. It produces canonical `flow-ui-contract/contract.json`; legacy `flow-ui-contract/flows/*.md` and `flow-ui-contract/screens/*.md` remain documentation or explicit migration inputs. Penflow then exports `semantic-ui-tree.json`, drafts or enriches pen.dev `.pen` files, exports `expected-ui-tree.json`, generates `code-ir.json`, and compares external `actual-ui-tree.json`.

Runtime boundary: Penflow consumes actual trees from external adapters. It does not run browsers, Xcode, simulators, Playwright, React Native, Metro, or app builds.

Before and after the workflow, run `penflow doctor --project <consumer-project-root> --check --json` and retain both read-only receipts. For a new project, a failing receipt may proceed to `doctor --fix` only when every issue code belongs to the exact bootstrap allowlist: `pen.missing`, `gitignore.managed_block_missing`, `gitignore.managed_block_outdated`, or `gitignore.managed_block_duplicate`. Any other finding blocks until manually resolved. Require a passing `doctor --check` after the fix, author the canvas, then require the final read-only Doctor check to pass. The exact selected project is never widened to its enclosing Git worktree; a collective worktree may contain several independent projects. Keep exactly one `ui.pen` per selected project; active/draft/archive revisions are top-level lifecycle regions inside it. Technical intermediates belong under managed, ignored `.penflow-tmp/`, `.penflow-run/`, and `.mockup-validation/` and are cleaned only by safe producer preflight/postflight. Multiple `.pen` candidates and tracked/staged temporary leaks require manual consolidation or Git-index resolution; Doctor never chooses files or rewrites history.

## Design Conventions

Before authoring UI flows or screens, **Read** the project's `.conventions/index.md` (when present) and load the matching design domains. UI specs must use the convention-defined patterns for app shells, dashboards, payments, forms, lists/tables, states, responsiveness, and accessibility; a screen that only lists labels and buttons is incomplete when a richer pattern applies.

## Semantic Tree Formation

The skill does not ask the LLM to hand-write `semantic-ui-tree.json`; Penflow generates it with `export-semantic-tree`. The LLM still needs the formation contract so it writes useful contracts: v2 `contract.json` objects become `flows[]` and `screens[]`; legacy flow specs become `flows[]`; screen specs become `screens[]`; visible hierarchy becomes recursive semantic nodes, and business context becomes `intent`, `binding`, `entity`, `states`, `validations`, `side_effects`, `test_id`, and `source_map`. **Read** [`references/semantic-ui-tree.md`](references/semantic-ui-tree.md) before explaining or debugging tree output.

## Output

```text
<target>/
├── ui.pen
├── mockups/
│   └── manifest.json
└── flow-ui-contract/
    ├── contract.json
    ├── flows/
    │   └── booking.md
    └── screens/
        └── checkout-form.md
```

## Validator

```bash
python3 .agent-sync/skills/flow-ui-contract/validator.py <target>/flow-ui-contract/flows/booking.md
python3 .agent-sync/skills/flow-ui-contract/validator.py --dir <target>/flow-ui-contract
python3 .agent-sync/skills/flow-ui-contract/validator.py booking.md --manifest <target>/mockups/manifest.json
python3 .agent-sync/skills/flow-ui-contract/validator.py --status --target <target>
```

Exit codes: `0` = PASS, `1` = FAIL with at least one blocking error or missing status manifest.

## Forward

```bash
penflow validate-flow-contract <target>/flow-ui-contract/contract.json --project <consumer-project-root> --json
penflow export-semantic-tree <target>/flow-ui-contract/contract.json --project <consumer-project-root> --out <target>/semantic-ui-tree.json --json
penflow validate-semantic-tree <target>/semantic-ui-tree.json --project <consumer-project-root> --json
penflow draft-pen-from-tree <target>/semantic-ui-tree.json --project <consumer-project-root> --out <target>/ui.pen --theme-css <target>/theme.css --json
penflow validate-pen <target>/ui.pen --project <consumer-project-root> --json
penflow export-expected <target>/ui.pen --project <consumer-project-root> --out <target>/expected-ui-tree.json --json
penflow code-ir --from-context <target>/ui.pen --semantic-tree <target>/semantic-ui-tree.json --contract <target>/flow-ui-contract/contract.json --flow-id <flow-id> --flow-name "<Flow name>" --project <consumer-project-root> --out <target>/code-ir.json --json
```

## Enrichment

```bash
penflow enrich-pen <target>/ui.pen <target>/semantic-ui-tree.json --project <consumer-project-root> --out <target>/ui.pen --json
penflow map-pencil-context <target>/ui.pen <target>/semantic-ui-tree.json --project <consumer-project-root> --out <target>/pencil-context-map.json --strict-anchors --json
penflow validate-pen <target>/ui.pen --project <consumer-project-root> --json
penflow export-expected <target>/ui.pen --project <consumer-project-root> --out <target>/expected-ui-tree.json --json
penflow code-ir --from-context <target>/ui.pen --semantic-tree <target>/semantic-ui-tree.json --context-map <target>/pencil-context-map.json --contract <target>/flow-ui-contract/contract.json --flow-id <flow-id> --flow-name "<Flow name>" --project <consumer-project-root> --out <target>/code-ir.json --json
```

## Reverse

```bash
penflow reverse-pen <target>/ui.pen --project <consumer-project-root> --out <target>/reverse-output --enrich --json
penflow validate-semantic-tree <target>/reverse-output/semantic-ui-tree.json --project <consumer-project-root> --json
```

`reverse-pen --out <dir>` writes a directory containing `semantic-ui-tree.json` and `flow-ui-contract/`; validate `<dir>/semantic-ui-tree.json`, not the directory path itself.
Reverse mode marks missing business logic as `[NEEDS CLARIFICATION]`; do not invent rules.

## Post-Implementation Compare

```bash
penflow validate-actual actual-ui-tree.json --schema --json
penflow compare-tree expected-ui-tree.json actual-ui-tree.json --out compare-report.json --json
penflow review-report compare-report.json --out review-report.json --json
penflow fix-report compare-report.json --out fix-report.json --json
```

## Full Demo

```bash
penflow demo --out examples/full --json
```

## Tests

```bash
python3 -m pytest .agent-sync/skills/flow-ui-contract/tests -v
```

The project-level suite also smoke-tests the migrated validator with `python3 -m pytest`.

## Boundaries

- This skill never writes to `.specs/`.
- It prepares flow/screen contracts and documents Penflow commands; Penflow commands generate semantic trees, `.pen` context, expected trees, code IR, and reports.
- It preserves `.pen` visual layout; enrichment adds context without blind overwrite.
- It never runs a UI runtime; external adapters own `actual-ui-tree.json`.
