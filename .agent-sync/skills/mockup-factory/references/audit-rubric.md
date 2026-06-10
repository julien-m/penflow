# UX + Contract Audit Rubric

Each checklist item must include severity, evidence, and the best available anchor: `screen_id`, `semantic_id`, and `pencil_node_id`.

## Blocking Contract Criteria

- Missing or invalid `flow-ui-contract` source for a screen.
- Invalid `semantic-ui-tree.json`.
- Invalid `.pen` context or duplicate `semantic_id`.
- Missing expected UI tree for an optimized screen.
- `detect-drift` reports missing semantic nodes, obsolete Pencil context, or unresolved `[NEEDS CLARIFICATION]`.

## UX/UI Criteria

| Category | PASS Requirement |
|---|---|
| Semantic contract | Every visible primary action, state, validation, and data binding maps to the semantic tree. |
| Visual alignment | Shared axes are frame-based and consistently aligned; no accidental overlap or overflow. |
| Hierarchy | Titles, sections, controls, and content density reveal priority without oversized decorative treatment. |
| CTA placement | Primary actions are discoverable, singular per decision zone, and close to the content they affect. |
| Density | Layout is scannable and task-focused; empty/loading/error states are represented when relevant. |
| Accessibility | Text contrast, target size, focus order, labels, and non-color status cues meet WCAG-oriented expectations. |
| Responsive behavior | Desktop, tablet, and mobile/watch frame assumptions are explicit when the product targets them. |
| Modernity | Components follow current SaaS/app conventions without ornamental one-off styling. |
| Polish | Spacing, radius, typography, icons, and borders are consistent with project conventions. |

Critical failures in any category block PASS. Cosmetic issues may remain only as documented warnings.

## Visual Evidence Criteria

Final PASS must be backed by **Read** [`visual-validation.md`](visual-validation.md). The reviewer must inspect the actual Pencil-rendered screen and record:

- screenshot/PNG path for each screen;
- layout snapshot dump (`layout-snapshot.json`) for the deterministic bbox cross-check;
- a `vision-report.json` answering only the five locked vision categories (`visual_balance`, `rendering_artifacts`, `readability`, `perceived_hierarchy`, `imagery_quality`) with one evidence sentence each;
- warnings for sparse density, missing responsive variants, or non-critical polish gaps.

Deterministic facts (contrast, target sizes, overlap/overflow, text fit) come from `penflow audit-visual`, not from the vision pass. The visual evidence verdict is the `penflow validate-visual-evidence` exit code; if no screenshot/export exists, the audit is incomplete even when tree validation passes.
