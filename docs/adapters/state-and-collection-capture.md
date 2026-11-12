# State and collection capture — consumer interface (C51)

This guide tells a runtime adapter how to capture a design board that documents several mutually exclusive states, and how to emit the rows of a collection. Penflow only reads the files the adapter writes; the adapter runs the application.

## What the expected tree declares

`penflow run` builds the expected tree from the `.pen` board and copies two contract facts onto it, by semantic id:

- each screen gets `states`, the ids of its contract screen states;
- a contract node with `states` (the states in which it exists) gets the same list, and a contract node with `repeat_model` (`collection`, `item_model`, `item_key`, `instance_id_template`) gets that model.

A node without `states` exists in every state of its screen, within its ancestors' states. Nothing else is inferred: the adapter never adds `states` or `repeat_model` to the actual tree, and a missing contract declaration stays missing.

The expected export also records each node's design sizing (`sizing.width`, `sizing.height`: `fixed`, `fill`, `hug` or `unspecified`). `check-consistency` compares heights only between members whose height is `fixed`.

## One capture per state

When a screen declares states that its nodes are scoped to, capture one tree per state instead of one tree per screen:

```json
{
  "version": 1,
  "screens": [
    {"screen_id": "task_detail", "state": "todo", "scenario_id": "open-todo-task", "root": {"id": "task_detail", "role": "screen", "bbox": {"x": 0, "y": 0, "width": 1280, "height": 800}}},
    {"screen_id": "task_detail", "state": "done", "scenario_id": "open-done-task", "root": {"id": "task_detail", "role": "screen", "bbox": {"x": 0, "y": 0, "width": 1280, "height": 800}}}
  ],
  "observed_states": [
    {"screen_id": "task_detail", "state": "todo", "scenario_id": "open-todo-task", "session_id": "s1", "evidence": {"path": "ui/todo.json", "sha256": "<sha256>"}},
    {"screen_id": "task_detail", "state": "done", "scenario_id": "open-done-task", "session_id": "s1", "evidence": {"path": "ui/done.json", "sha256": "<sha256>"}}
  ]
}
```

Rules the comparison enforces:

| Situation | Result |
|---|---|
| Each capture holds the nodes of its state | compared node by node, sibling order counted among that state's nodes |
| A state some expected node is scoped to has no capture | `screen.state_missing` (its nodes are unobserved; never a PASS for lack of captures) |
| A capture names a state the contract does not declare | `screen.state_unknown` |
| The expected screen declares no states but captures carry one | `screen.state_undeclared` |
| A capture has no `observed_states` entry with the same screen, state and scenario | `screen.state_unwitnessed` (the runtime gate also checks the witness itself) |
| A node of another state is present in a capture (two exclusive buttons fused) | `node.state_unexpected` |
| Two captures of the same state, or a stateless capture beside state captures | refused by `validate-actual` |
| A single stateless capture | the strict comparison: every expected node is required in it |

Each capture must come from one declared state witness: record its `state` and `scenario_id` beside the tree, and refuse a second capture of the same screen state instead of overwriting the first.

## Collection instances

For a node whose contract declares `repeat_model`, emit one node per real item, with the template's `semantic_id` and an `instance_id` built from `instance_id_template` (for example `tache-{task.id}` gives `tache-1f2e`). Descendants of a row that repeat with it carry the same `instance_id`.

| Situation | Result |
|---|---|
| Every instance matches the template exactly | each instance is compared with the template (role, text, geometry, style) |
| An `instance_id` does not match the template (another collection, an empty or extra token) | `node.instance_unexpected` |
| A repeated descendant names an instance its row does not have | `node.instance_mismatch` |
| No instance in a capture where the node applies | `node.missing` (use contract `states` for an empty state; no cardinality is assumed) |
| Two nodes with the same `semantic_id::instance_id` or `id` | refused by `validate-actual` |
| An `instance_id` on a node without `repeat_model` | strict: the template is missing and the instance is unexpected |

## Not covered by Penflow

Running the application, reaching each state, choosing scenarios and writing the UI snapshots stay the adapter's job. A field annotated on the wrong `.pen` node (for example a field group annotated as the select it contains) is a design-source correction, not a comparison rule.
