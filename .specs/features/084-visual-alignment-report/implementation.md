---
id: 084-visual-alignment-report
title: Visual alignment report
feature: 084-visual-alignment-report
status: Implemented
spec_ref: spec.md
plan_ref: plan.md
created: 2026-11-24
updated: 2026-11-24
---

# Implementation — Visual alignment report

## Requirement Mapping

<!-- @spec(FR-001) -->
<!-- @spec(FR-002) -->
<!-- @spec(FR-003) -->
<!-- @spec(FR-004) -->
<!-- @spec(FR-005) -->

| Acceptance | Code and evidence |
|---|---|
| AC-001 / FR-001–002 | Read [the evidence evaluator](../../../penflow/visual_alignment.py) and [manifest schema](../../../penflow/schemas/visual-alignment.schema.json) for matching scope, PNG inspection, numeric citations and approval references. Read [the CLI regressions](../../../tests/test_visual_alignment.py) for incompatible and missing cases. |
| AC-002 / FR-003–004 | Read [the Markdown presentation](../../../penflow/visual_alignment_markdown.py) for grouped technical details and unchanged diagnostic labels. The evaluator requires separate PNGs for a repeat and checks the reference bytes and runtime image data. |
| AC-003 / FR-005 | The three consumer cases replay from saved evidence. Read [the operator guide](../../../docs/visual-alignment.md) for the reproducible public input contract. |

## Acceptance Criteria

- AC-001 exercised matching and incompatible capture metadata, truncated and missing inputs, numeric citations and design approvals.
- AC-002 exercised repeatable reports, preserved machine findings, split PNGs and rejection of metadata-only repeats.
- AC-003 replayed the three consumer cases against saved proof, including a separate populated-state probe.

## Independent review

The reviewer reproduced qualification of a truncated PNG and a malformed unobserved report. It also found that a changed combined PNG could qualify a false repeat. The correction rejects those inputs, preserves the legacy diagnostic scope explicitly and has regressions for a metadata-only PNG change. The same reviewer accepted the correction after 45 focused checks and an exact local replay.

## Report and package verification

The local replay uses a saved before/after pair, a composite confirmation and restoration reference, and a separate populated-state probe. The original rendered diagnostic verdicts and counts are preserved. The wheel and source archive built successfully. A fresh environment installed the wheel and produced the same consumer report, byte for byte, from outside the checkout. The checkout reports Penflow 0.2.0.

Full source suite on Python 3.12.13: 1,990 passed, 8 skipped. The targeted implementation, CLI, comparator and export suite passed 139 tests. Ruff, mypy, the dependency lock check, the feature's structural LiveSpec validation and `git diff --check` passed.
