<!-- LiveSpec traceability anchors -->
<!-- @spec(FR-007) -->

# Semantic UI Tree Formation

Use this reference when an agent must understand how canonical `contract.json` becomes `semantic-ui-tree.json`. Author/review JSON, generate human docs with `penflow export-flow-docs`, then run `penflow export-semantic-tree`. Do not hand-write production semantic trees or generated Markdown.

## Sources

- Canonical source: `<target>/flow-ui-contract/contract.json`
- Generated projections: `<target>/flow-ui-contract/flows/*.md`, `<target>/flow-ui-contract/screens/*.md`, and `generated-docs.json`
- Schema: **Read** [`../../../../penflow/schemas/semantic-ui-tree.schema.json`](../../../../penflow/schemas/semantic-ui-tree.schema.json)
- Example: **Read** [`../../../../examples/demo/semantic-ui-tree.json`](../../../../examples/demo/semantic-ui-tree.json)

## Output Shape

`penflow export-semantic-tree` creates one deterministic JSON object:

```text
semantic-ui-tree
├── source
├── flows[]
│   ├── id, title, priority
│   ├── entry_screen
│   ├── steps[]
│   └── transitions[]
└── screens[]
    ├── id, flow_id, surface, viewport
    ├── root
    ├── states[]
    ├── validations[]
    └── side_effects[]
```

## Formation Rules

- Canonical `contract.json` `flows[]` become semantic-tree `flows[]`: declared ids, titles, priorities, steps, entry screens, and transitions are copied deterministically. Generated `flows/*.md` only document those bytes.
- Canonical `contract.json` `screens[]` become semantic-tree `screens[]`: ids, flow ids, surfaces, viewport hints, and recursive roots are copied deterministically. Generated `screens/*.md` never produce the tree.
- Explicit legacy migration only: `flows/*.md` becomes `flows[]` and `screens/*.md` becomes `screens[]`; this compatibility parser is not a v2 authoring route. Legacy visible hierarchy becomes `root` plus recursive `children` before promotion into canonical JSON.
- Every screen root is a semantic node with `role: "screen"`; nested UI elements become semantic nodes with roles such as `container`, `text`, `button`, `input`, `list`, `modal`, or `alert`.
- Visible labels become `text`; user-facing purpose becomes `intent`; data dependencies become `binding` and `entity`; repeated data regions set `repeat`; stable automation hooks become `test_id`.
- Screen-level and node-level rules become `states[]`, `validations[]`, and `side_effects[]`. Unknown business logic must be written as `[NEEDS CLARIFICATION]`, not invented.
- Each flow, screen, and node carries `source_map` so downstream agents can trace it back to a spec file, pen.dev node, or reverse-engineered source.
- Ordering is stable: files, flows, screens, steps, transitions, and child nodes must be emitted deterministically from source order plus stable sorting where the parser owns ordering.

## .pen Context Propagation

`draft-pen-from-tree` and `enrich-pen` propagate semantic fields into pen.dev `.pen` `context`. Before strict downstream work, explicitly classify every authored node and run `map-pencil-context --strict-coverage --contract ... --coverage-out ...`; forward-only anchor matching is diagnostic, not exhaustive proof.

```text
classification=semantic; semantic_id=checkout-form; test_id=checkout-form-screen; role=screen
classification=semantic; semantic_id=pay-button; test_id=pay-button; role=button; intent=submit_payment
classification=inherited; inherits_from=pay-button; relation=content
classification=decorative; decorative_owner=pay-button; decorative_reason=duplicates-label
```

## Tree Distinctions

| Tree | Producer | Purpose |
|---|---|---|
| `semantic-ui-tree.json` | Penflow from canonical `flow-ui-contract/contract.json` | Before-code product intent and business context. |
| `expected-ui-tree.json` | Penflow from contextualized `.pen` | Design-derived contract used as compare baseline. |
| `actual-ui-tree.json` | External runtime adapter | After-code runtime observation validated and compared by Penflow. |

Penflow compares `expected-ui-tree.json` and `actual-ui-tree.json`; it does not compare runtime output directly against generated flow Markdown.
