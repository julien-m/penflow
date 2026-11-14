# Integrating Penflow Into an Existing Project

Read [the normal review led workflow](review-led-workflow.md) for delivery and [migration/rollback](review-led-migration.md) before changing an installed consumer.

## Recommended layout

Select the exact consumer root and keep its `penflow/` workspace local. The current behavior contract lives in `penflow/flow-ui-contract/contract.json`; the design is `penflow/ui.pen`. Semantic/expected trees, context maps and code IR are derived artifacts produced when useful. Runtime adapters own `actual-ui-tree.json`; Penflow never launches the app, browser, Xcode or simulator.

Keep one canonical `.pen` for the product, including subsequent features. Reuse its screens and add journeys/states in that canvas; do not create `feature-name/ui.pen` for every increment. If multiple design files already exist, inspect and consolidate their useful content through the editor, preserving screens and references before removing any source. Read [the editor connection guidance](review-led-workflow.md#existing-canvas-and-editor-connection) before interpreting an opening or connection error.

Automatically distribute ready, independent tasks to available subagents, including disjoint named screens/frames/components in that same canvas. Coordinate shared nodes, variables and components through an integration owner; preserve concurrent edits, reconcile uncertain mutations and verify saves. Give every worker its own complete brief and combine results into one final review. Read [the parallel work rules](review-led-workflow.md#automatic-parallel-work-in-one-canvas); unavailable subagents do not block progress.

## Current checks

```bash
penflow check --target penflow --project . --json
```

This read-only command works without Git/Doctor or certification metadata. It reads current inputs, derives expected structure in memory and continues independent checks after a failure. A missing actual tree stays NOT_RUN; an actual tree without a build manifest can still be structurally checked. Real runtime interactions, appearance, freshness and build identity remain unverified until separately observed. Capture command/exit/findings/limitations for independent review; a zero exit is not delivery approval.

## Authoring and handoff

- For new behavior, read [flow-ui-contract](../.agent-sync/skills/flow-ui-contract/SKILL.md). Use current accepted requirements; preserve actions, guards, permissions, mutations and outcomes.
- For an existing mockup, inspect and enrich the selected canvas without discarding visual edits. For hi-fi design, read [Mockup Factory](../.agent-sync/skills/mockup-factory/SKILL.md).
- Use explicit generators such as `export-semantic-tree`, `map-pencil-context`, `export-expected` and `code-ir` only when their output serves the task. Existing producers still enforce project hygiene and confined writes. Use `doctor --fix --project . --json` explicitly for initialization/unambiguous repair; a read-only diagnostic never needs a Doctor receipt.
- Observe rendered screens and exercise affected application behavior through the external runner. Reuse unchanged results. Send current specs/plan, accepted decisions, full diff and actual results to one fresh native final reviewer; fix material findings and deliver within authorization.
- Keep active/draft/archive regions in the selected canvas. Ambiguous writes or unsafe cleanup require resolution; a cleanup refusal never authorizes deletion. Ordinary producer postflight cleanup findings are separate stderr JSON, while product stdout/exit remain intact.

## Historical diagnostics

Only for an explicit C42/C47/C51 or old workflow request, read [the retained integration guide](project-integration-certification.md) and [C51](verification-workflow.md). Their commands, exit codes and historical interpretations remain intact. Do not automatically re-run approval/certificate chains or relabel an old BLOCKED as PASS.
