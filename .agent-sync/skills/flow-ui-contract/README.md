# flow-ui-contract

Penflow-local migration of the old specify-flows workflow. It captures behavior around visual mockups and Pencil `.pen` files, then writes validated flow/screen Markdown specs for semantic UI tree export and Pencil enrichment.

Invoke the installed skill as `flow-ui-contract`. Legacy wording signals such as `specify flows`, `flow specs`, and `spec flows` should route here; no separate `specify-flows` slash command is installed.

## Purpose

Use this skill to author or recover the behavior layer before code. It produces `flow-ui-contract/flows/*.md` and `flow-ui-contract/screens/*.md`; Penflow then exports `semantic-ui-tree.json`, drafts or enriches Pencil, exports `expected-ui-tree.json`, generates `code-ir.json`, and compares external `actual-ui-tree.json`.

Runtime boundary: Penflow consumes actual trees from external adapters. It does not run browsers, Xcode, simulators, Playwright, React Native, Metro, or app builds.

## Semantic Tree Formation

The skill does not ask the LLM to hand-write `semantic-ui-tree.json`; Penflow generates it with `export-semantic-tree`. The LLM still needs the formation contract so it writes useful specs: flow specs become `flows[]`, screen specs become `screens[]`, visible hierarchy becomes recursive semantic nodes, and business context becomes `intent`, `binding`, `entity`, `states`, `validations`, `side_effects`, `test_id`, and `source_map`. **Read** [`references/semantic-ui-tree.md`](references/semantic-ui-tree.md) before explaining or debugging tree output.

## Output

```text
<target>/
├── ui.pen
├── mockups/
│   └── manifest.json
└── flow-ui-contract/
    ├── flows/
    │   └── booking.md
    └── screens/
        └── checkout-form.md
```

## Validator

```bash
python .agent-sync/skills/flow-ui-contract/validator.py <target>/flow-ui-contract/flows/booking.md
python .agent-sync/skills/flow-ui-contract/validator.py --dir <target>/flow-ui-contract
python .agent-sync/skills/flow-ui-contract/validator.py booking.md --manifest <target>/mockups/manifest.json
python .agent-sync/skills/flow-ui-contract/validator.py --status --target <target>
```

Exit codes: `0` = PASS, `1` = FAIL with at least one blocking error or missing status manifest.

## Forward

```bash
penflow export-semantic-tree <target>/flow-ui-contract --out semantic-ui-tree.json --json
penflow validate-semantic-tree semantic-ui-tree.json --json
penflow draft-pen-from-tree semantic-ui-tree.json --out ui.pen --json
penflow validate-pen ui.pen --json
penflow export-expected ui.pen --out expected-ui-tree.json --json
penflow code-ir --from-context ui.pen --semantic-tree semantic-ui-tree.json --flow-id <flow-id> --flow-name "<Flow name>" --out code-ir.json --json
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

Reverse mode marks missing business logic as `[NEEDS CLARIFICATION]`; do not invent rules.

## Post-Implementation Compare

```bash
penflow validate-actual actual-ui-tree.json --schema --json
penflow compare-tree expected-ui-tree.json actual-ui-tree.json --out compare-report.json --markdown compare-report.md --json
penflow review-report compare-report.json --out review-report.md
penflow fix-report compare-report.json --out fix-report.md
```

## Full Demo

```bash
penflow demo --out examples/full --json
```

## Tests

```bash
python -m pytest .agent-sync/skills/flow-ui-contract/tests -v
```

The project-level suite also smoke-tests the migrated validator with `python -m pytest`.

## Boundaries

- This skill never writes to `.specs/`.
- It prepares flow/screen contracts and documents Penflow commands; Penflow commands generate semantic trees, Pencil context, expected trees, code IR, and reports.
- It preserves `.pen` visual layout; enrichment adds context without blind overwrite.
- It never runs a UI runtime; external adapters own `actual-ui-tree.json`.
