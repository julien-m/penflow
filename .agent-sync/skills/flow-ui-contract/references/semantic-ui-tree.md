# Semantic UI Tree Formation

Use this reference when an agent must understand how flow/screen specs become `semantic-ui-tree.json`. The normal workflow is still command-driven: author flow/screen Markdown, then run `penflow export-semantic-tree`. Do not hand-write `semantic-ui-tree.json` except for fixtures, tests, or debugging.

## Sources

- Flow specs: `<target>/flow-ui-contract/flows/*.md`
- Screen specs: `<target>/flow-ui-contract/screens/*.md`
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

- `flows/*.md` becomes `flows[]`: frontmatter and headings provide `id`, `title`, `priority`; declared screen order becomes `steps[]`; declared navigation becomes `transitions[]`; the first canonical screen becomes `entry_screen`.
- `screens/*.md` becomes `screens[]`: frontmatter provides `id`, `flow_id`, `surface`, and viewport hints; visible hierarchy becomes `root` plus recursive `children`.
- Every screen root is a semantic node with `role: "screen"`; nested UI elements become semantic nodes with roles such as `container`, `text`, `button`, `input`, `list`, `modal`, or `alert`.
- Visible labels become `text`; user-facing purpose becomes `intent`; data dependencies become `binding` and `entity`; repeated data regions set `repeat`; stable automation hooks become `test_id`.
- Screen-level and node-level rules become `states[]`, `validations[]`, and `side_effects[]`. Unknown business logic must be written as `[NEEDS CLARIFICATION]`, not invented.
- Each flow, screen, and node carries `source_map` so downstream agents can trace it back to a spec file, Pencil node, or reverse-engineered source.
- Ordering is stable: files, flows, screens, steps, transitions, and child nodes must be emitted deterministically from source order plus stable sorting where the parser owns ordering.

## Pencil Context Propagation

`draft-pen-from-tree` creates Pencil nodes from semantic nodes and writes the semantic fields into Pencil `context`. `enrich-pen` preserves existing layout, matches semantic nodes to existing Pencil nodes, and writes the same context. `map-pencil-context` records any ambiguous or missing mapping for review.

## Tree Distinctions

| Tree | Producer | Purpose |
|---|---|---|
| `semantic-ui-tree.json` | Penflow from `flow-ui-contract/*.md` | Before-code product intent and business context. |
| `expected-ui-tree.json` | Penflow from contextualized `.pen` | Design-derived contract used as compare baseline. |
| `actual-ui-tree.json` | External runtime adapter | After-code runtime observation validated and compared by Penflow. |

Penflow compares `expected-ui-tree.json` and `actual-ui-tree.json`; it does not compare runtime output directly against flow Markdown.
