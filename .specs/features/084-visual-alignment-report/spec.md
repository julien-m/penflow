---
id: 084-visual-alignment-report
title: Visual alignment report
status: Implemented
priority: P1
created: 2026-11-24
updated: 2026-11-24
---

# Visual alignment report

## User Scenarios

A reviewer checks comparability after capturing a rendered screen, chooses which visual differences to act on, and repeats the comparison after a correction.

## Functional Requirements

- **FR-001:** Produce a read-only Markdown report from one or more paired references and captures. Show screen, state, variant and logical viewport first. Withhold product recommendations for unobserved or incompatible pairs, including composite design boards.
- **FR-002:** Prioritize up to three evidenced review observations per pair. Show the image region, expected and observed behavior, next action and verification. Label visual interpretation and missing observations. Require a readable decision reference for approved divergences.
- **FR-003:** Group repetitive technical diagnostics and keep the individual details, original machine result and evidence links. Report generation leaves existing commands, report formats and exit semantics intact.
- **FR-004:** Present before/after evidence when available. Require the same design frame, screen, state, variant and viewport and a fresh image for follow-up comparison. Preserve the original observation and verdict.
- **FR-005:** Reproduce three reviews from local read-only consumer evidence, covering a layout correction, a composite design board and an unresolved state with a separate functional observation.

## Acceptance Criteria

```gherkin
Scenario: A comparable pair has a reviewed material discrepancy
  Given independent paired images, a detailed rendered report and a cited visual observation
  When I request the alignment report
  Then the prioritized observation shows the region, expectation, observation, action and verification
  And the machine findings are grouped with their individual details retained

Scenario: A pair cannot support product corrections
  Given a missing observation, conflicting pair identities or a multi-state design board
  When I request the alignment report
  Then it explains the missing or conflicting inputs before any review notes
  And the report explains what to clarify or recapture

Scenario: Review an existing correction
  Given two comparable pairs referencing the same design frame and distinct runtime evidence
  When I supply a cited follow-up observation
  Then the report presents both observations and both machine verdicts
```

- AC-001 covers FR-001/002 and incompatibility, absent inputs and invalid citations.
- AC-002 covers FR-003/004 and grouping, preserved verdicts and follow-up matching.
- AC-003 covers FR-005 and replay of the three consumer cases, with a local example.

## Edge Cases

- The design board contains multiple states, or the captured variant or viewport differs.
- A capture, qualified measurement, citation or decision is absent or unreadable.
- Follow-up uses different scope, a changed reference image or the same runtime capture.
