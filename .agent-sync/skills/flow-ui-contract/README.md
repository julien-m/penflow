# flow-ui-contract

Penflow-local migration of the old specify-flows workflow. It captures behavior around visual mockups and Pencil `.pen` files, then promotes reviewed behavior into canonical `flow-ui-contract/contract.json` for semantic UI tree export and Pencil enrichment.

Invoke the installed skill as `flow-ui-contract`. Legacy wording signals such as `specify flows`, `flow specs`, and `spec flows` should route here; no separate `specify-flows` slash command is installed.

## Purpose

Use this skill to author or recover the behavior layer before code. It produces canonical `flow-ui-contract/contract.json`; legacy `flow-ui-contract/flows/*.md` and `flow-ui-contract/screens/*.md` remain documentation or explicit migration inputs. Penflow then exports `semantic-ui-tree.json`, drafts or enriches Pencil, exports `expected-ui-tree.json`, generates `code-ir.json`, and compares external `actual-ui-tree.json`.

Runtime boundary: Penflow consumes actual trees from external adapters. It does not run browsers, Xcode, simulators, Playwright, React Native, Metro, or app builds.

## Design Conventions

Before authoring UI flows or screens, **Read** [`../../../.conventions/index.md`](../../../.conventions/index.md) and load the matching design domains. UI specs must use the convention-defined patterns for app shells, dashboards, payments, forms, lists/tables, states, responsiveness, and accessibility; a screen that only lists labels and buttons is incomplete when a richer pattern applies.

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
penflow validate-flow-contract <target>/flow-ui-contract/contract.json --json
penflow export-semantic-tree <target>/flow-ui-contract/contract.json --out semantic-ui-tree.json --json
penflow validate-semantic-tree semantic-ui-tree.json --json
penflow draft-pen-from-tree semantic-ui-tree.json --out ui.pen --theme-css <target>/theme.css --json
penflow validate-pen ui.pen --json
penflow export-expected ui.pen --out expected-ui-tree.json --json
penflow code-ir --from-context ui.pen --semantic-tree semantic-ui-tree.json --contract <target>/flow-ui-contract/contract.json --flow-id <flow-id> --flow-name "<Flow name>" --out code-ir.json --json
```

## Enrichment

```bash
penflow enrich-pen <target>/ui.pen semantic-ui-tree.json --out ui.enriched.pen --json
penflow map-pencil-context ui.enriched.pen semantic-ui-tree.json --out pencil-context-map.json --json
penflow validate-pen ui.enriched.pen --json
penflow export-expected ui.enriched.pen --out expected-ui-tree.json --json
```

## Reverse

```bash
penflow reverse-pen <target>/ui.pen --out reverse-output --enrich --json
penflow validate-semantic-tree reverse-output/semantic-ui-tree.json --json
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
- It prepares flow/screen contracts and documents Penflow commands; Penflow commands generate semantic trees, Pencil context, expected trees, code IR, and reports.
- It preserves `.pen` visual layout; enrichment adds context without blind overwrite.
- It never runs a UI runtime; external adapters own `actual-ui-tree.json`.
