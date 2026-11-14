---
name: flow-ui-contract
description: Specify product behavior as a Penflow JSON contract and semantic UI tree before pen.dev design or implementation.
---
# Flow UI contract

Read [the normal review led workflow](../../../docs/review-led-workflow.md) before working. This skill prepares truthful product intent; it does not certify delivery or launch application runtimes.

- Inspect current requirements, accepted decisions and the requested scope. Identify actors, screens, actions, guards, permissions, entities, mutations, validation, states and outcomes. Do not invent network operations, approvals or permission checks for a local state change.
- Author or update `flow-ui-contract/contract.json` as strict v2 JSON. Read [the semantic tree contract](references/semantic-ui-tree.md) when generating the semantic tree. Read [design input guidance](references/design-read.md) when shaping a new visual direction.
- Read project conventions and applicable design/spacing/platform guides. Preserve semantic IDs and behaviors across contract, semantic tree, pen.dev context and runtime. Attach explicit semantic/inherited/decorative classification during authoring; never weaken interactive roles merely to avoid a finding.
- Use existing `validate-flow-contract`, `export-semantic-tree`, `draft-pen-from-tree`, `enrich-pen`, `map-pencil-context`, `export-expected` or `code-ir` commands when their outputs serve the task. Draft generation is wireframe fidelity; use [Mockup Factory](../mockup-factory/SKILL.md) for final visual work. Generated Markdown projections are documentation, not approval prerequisites for independent local checks.
- Run `penflow check --target <workspace> --project <consumer-project-root> --json` when a canvas is available. Preserve actual validator failures and NOT_RUN findings. Before a canvas exists, the explicit contract validator checks the authored contract directly without Doctor hygiene.
- Preserve exact consumer boundaries, actual disk save state and ambiguous-write/deletion protections. Read [the Penflow operator boundary](../penflow/SKILL.md) before pen.dev interaction. Do not install tools or downgrade a consumer as an implicit prerequisite.
- Give the current spec/plan/contract, accepted decisions and actual results to one fresh independent native final reviewer. Fix material defects; report essential missing observations honestly. Update ordinary project documents and deliver within authorization.
- Resolve the product surface/platform and applicable convention sources before choosing control sizes; use explicit contract screen surface metadata or workspace `design-profile.json`. Keep compact desktop visual bounds, mobile hit areas and landing typography distinct. Apply justified, scoped overrides with reasons. Read [the profile and rendered-measurement workflow](../../../docs/review-led-workflow.md#conventions-design-and-rendered-measurements).
- Normal `check` automatically audits the profile and rendered measurements. Capture independent runtime bounds/computed styles with explicit units, coordinates, zoom/DPR and the matching screen/state/viewport; read [the external Web adapter guide](../../../docs/adapters/web-rendered.md). Supply resolved design layout for fill/fit dimensions. Missing measurements remain unobserved, contradictory measurements remain errors, and material size/style/proportion drift needs correction; a structural PASS is insufficient.

Only for an explicit historical certification or legacy migration diagnostic, read [the former workflow](certification.md). Its eight-step pipeline, strict coverage receipts, Doctor receipt requirements and C51 closure are not normal delivery prerequisites.
