---
name: penflow
description: Use Penflow for pen.dev contracts, current local checks, semantic/expected/actual trees and structural design/runtime comparison.
---
# Penflow

Read [the normal review led workflow](../../../docs/review-led-workflow.md) before working. It governs delivery; old diagnostic certificates are opt-in only.

- Penflow core validates local files and compares trees. External adapters produce `actual-ui-tree.json`; core never launches browsers, Xcode, simulators, Playwright or app builds.
- `flow-ui-contract/contract.json` is the strict v2 behavior contract; `semantic-ui-tree.json` captures intent, `ui.pen` the design, `expected-ui-tree.json` derived structure, and `actual-ui-tree.json` external runtime structure. Preserve actual actions, guards, permissions, mutations and outcomes.
- Start from current files and the requested scope. Run `penflow check --target <workspace> --project <consumer-project-root> --json`; use relevant existing CLI generators/validators only when their outputs are needed. Do not generate every intermediate merely to obtain a certificate.
- For contract authoring, read [flow-ui-contract](../flow-ui-contract/SKILL.md). For design improvements, read [Mockup Factory](../mockup-factory/SKILL.md). For adoption and CLI examples, read [project integration](../../../docs/project-integration.md).
- Observe real rendered UI/runtime behavior when needed; a structural result is not an interaction or visual observation. Give actual results and unverified essentials to one independent native final reviewer, correct material findings and deliver within authorization.
- Read the real convention sources and platform exclusions, resolve surface/platform from explicit contract screen metadata or workspace `design-profile.json`, then materialize its component/variant rules and exact product `typography.font_size_scale` once; read [the exact-scale contract](../../../docs/theme-contract.md#exact-product-typography-in-normal-check). `sources[]` is provenance, not Markdown interpretation. An absent exact scale keeps legacy behavior; a supplied exact scale excludes default/theme additions and exposes theme conflicts. Keep compact desktop visual bounds, mobile hit areas and landing typography distinct. Apply justified, scoped overrides with reasons. Read [the profile and rendered-measurement workflow](../../../docs/review-led-workflow.md#conventions-design-and-rendered-measurements).
- Normal `check` automatically audits the profile and rendered measurements. Capture independent runtime bounds/computed styles with explicit units, coordinates, zoom/DPR and the matching screen/state/viewport; read [the external Web adapter guide](../../../docs/adapters/web-rendered.md). Supply resolved design layout for fill/fit dimensions. Missing measurements remain unobserved, contradictory measurements remain errors, and material size/style/proportion drift needs correction; a structural PASS is insufficient.

## pen.dev operator boundary

- Prefer the user's requested Pencil/pen.dev plugin. Inspect the exposed tools, current documentation and permissions before use. Naming is pen.dev; retain `pencil` for existing command/server/schema identifiers.
- When using the desktop 1.2 MCP surface, open the exact `ui.pen`, confirm it with `get_app_state`, then read `execute.md` via `read_skill`. Pass `filePath` to `execute`; check the document identity before mutations. Do not infer tool availability from legacy `batch_design` examples.
- Save edited documents through the exposed save mechanism. The legacy desktop transport uses `penflow pencil-sync <workspace>/ui.pen --project <consumer-project-root> --json`, optionally `--app` and `--save-timeout`. Its `persistence_status: UNVERIFIED` is a trigger result; inspect actual disk bytes before checking them. An unchanged digest is not proof that a requested edit was persisted.
- Save-helper setup is explicit: `penflow doctor --install-save-helper --json`. It can require Accessibility/Automation permission; do not silently install or change machine permissions. Report exact tool refusal or missing capability without inventing observation.
- Native `Get`/bounds supply geometry. Preserve `TakeScreenshot` ImageContent bytes as a real local PNG and record image dimensions/scale; reduced overviews are not 1× measurements. An acknowledged `Export` without an observable file is an export limitation, not a required ghost artifact. Synthetic decode fixtures are not aesthetic references.
- Keep visual proof images at their real paths, show Markdown images and clickable file links, and publish annotation links through `visual-preview url --json <absolute-path>` when available. Preview failure is a disclosed limitation, never fabricated evidence.

## Historical diagnostics

Only for an explicit request, read [the former certification workflow](certification.md). It preserves C42/C45/C46/C47/C48/C51 commands and operator details. Its automatic hygiene, certificate and bounded full-chain loops do not apply to normal work.
