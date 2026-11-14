---
id: 083-rendered-design-conventions
name: Rendered design conventions
status: Implemented
priority: P1
created: 2026-11-14
---
# Rendered design conventions

Normal delivery follows feature 082 review led policy. User authorizes implementation, one independent final review, publication and protected merge. No new goal/certification. Scope Penflow and owned adapters/demo; never change Atlas/private SDK/runtime.

## Requirements

- **FR-001:** Automatically audit resolved surface/platform convention profiles in check. Record source references and reasoned overrides; unknown context is unobserved. Distinguish desktop visual controls, landing hierarchy and mobile hit areas.
- **FR-002:** Reuse token/consistency/visual metrics for measurable Pencil dimensions, spacing, typography and proportions. Preserve independent findings despite ambiguous lifecycle metadata without guessing active revisions.
- **FR-003:** Compare independent runtime geometry/computed styles through the existing engine, validating viewport/state/source frame/units/coordinates/zoom/DPR. Distinguish fixed from fill/hug, missing design geometry from zero, and real observations from expected copies.
- **FR-004:** Distinguish conforming, material drift, measurement error, unobserved. Masks/overrides require reasons; no score/tolerance hides material drift. Capture metadata does not authenticate observation.
- **FR-005:** Supply reusable external DOM capture and real owned demo detecting oversized controls then observing correction. No browser dependency/execution in core.
- **FR-006:** Compatible migration, current skills/README/specs, isolated wheel validation, CI and protected publication. Prepare minimal private port without installation/global synchronization.

## Acceptance

```gherkin
Scenario: Material rendered drift
  Given a Pencil source and independent live DOM capture at the same viewport
  When a control is oversized or has wrong font or padding
  Then check reports material drift
  And a fresh corrected observation conforms to measured assertions

Scenario: Missing and contradictory observations
  Given absent runtime or inconsistent measurement metadata
  When check executes
  Then absence is unobserved and contradiction is measurement error
  And independent source diagnostics continue

Scenario: Responsive and source revision selection
  Given explicit variants or ambiguous active revisions
  When capture identifies its source frame and viewport
  Then only that homologous frame is compared
  And no active revision is guessed

Scenario: Applicable conventions
  Given explicit surface/platform rules and reasoned component overrides
  When source is audited
  Then applicable rules and overrides are reported
  And desktop visual sizes are distinct from mobile hit minimums
```

AC-001: FR-001/002 profiles, reasoned overrides, malformed/contradictory data and independent source checks.
AC-002: FR-003/004 sizes/fonts/padding/viewport/ratios/no-runtime/responsive/masks/units/fill-hug.
AC-003: FR-005 live bad→corrected independent DOM observation.
AC-004: FR-006 full regression, isolated wheel, final independent review, CI and protected merge.

## Typography handoff correction

FR-001/002 and AC-001 include the resolved product typography used by normal token lint. A supplied profile typography scale is exact; conflicting theme declarations remain explicit findings. Absence preserves legacy scale behavior, while invalid policy input cannot suppress independent diagnostics. Source provenance does not imply automatic interpretation of Markdown.
