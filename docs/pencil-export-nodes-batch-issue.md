# PF-PENCIL-EXPORT-NODES-BATCH-20260701

Status: open upstream/operator-layer issue, historical for pen.dev < 1.2. The `export_nodes`, `get_editor_state` and `batch_get` MCP tools cited below no longer exist in pen.dev 1.2; exports now run through `execute` `Export([...])` and the open document is checked with `get_app_state`. Keep one node per `Export` call if multi-node exports misbehave.

## Evidence

Read [`session-refondre-timeline.txt`](local-session-transcript.txt) before changing this issue.

- Lines 663-668 reproduce the failure: `export_nodes` with eight node IDs on `projects/claude-pilot/handoff/penflow/ui.pen` fails with Pencil error `wrong .pen file`.
- Lines 670-675 qualify the file/ID state: `get_editor_state` confirms the opened document is the expected `.pen` and the eight top-level IDs are present.
- Lines 677-682 prove the single-node fallback: unit export of `kd7bd` succeeds.
- Lines 684-695 isolate batch size/state: a three-node batch succeeds, a four-node batch fails again with the same batch path.
- Lines 697-715 finish through exports unitaires for the remaining screens.

## Qualification

This is treated as a Pencil MCP/app batch-export state issue, not a Penflow core usage bug:

- The same `filePath` and top-level node IDs are accepted by `get_editor_state`.
- At least one unit export succeeds after the failed batch.
- Smaller batches can pass while a later batch fails, which points to MCP/app export state rather than invalid Penflow data.

## Required Fallback

- Do not add Pencil MCP, browser, renderer, or app-control dependencies to Penflow Python core.
- Keep `penflow run` deterministic and file-based.
- Use unit exports at the skill/operator layer when multi-ID `export_nodes` returns `wrong .pen file`.
- Report this issue ID in worker receipts when the fallback is used: `PF-PENCIL-EXPORT-NODES-BATCH-20260701`.
