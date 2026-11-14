# Implementation — Rendered design conventions

## Requirement and acceptance mapping

| Requirement / acceptance | Implementation | Verification |
|---|---|---|
| FR-001 / AC-001 | design_profile.py + versioned sourced profiles/schema, explicit surface/platform and reasoned scoped overrides | test_design_profile.py; default profile selection/inheritance tests in test_review_measurements.py |
| FR-002 / AC-001 | bounded pen_components.py expansion; diagnostic physical regions; independent lint/metrics after lifecycle error; native variable/theme/dimension resolution | test_pen_components.py; lifecycle, native theme/dimension token and inherited component integration regressions |
| FR-003/004 / AC-002 | rendered_measurements.py composes existing compare, native geometry and styles; strict metadata/viewport/units/state/grouping; fixed vs intrinsic axes, ratios and bounded reasons | test_rendered_measurements.py; test_compare_state_scope.py; real-source variant/mask/default orientation integration |
| FR-005 / AC-003 | external Web DOM/computed-style adapter, authored native frame+text fixture and real bad→corrected normal-check runner | six real-browser tests; ordinary check live demo; independent label typography observations |
| FR-006 / AC-004 | current distributed skills/README/workflow/migration; isolated wheel verified; scoped specs and one final independent native review | doc regressions, skill structural validation, full suite/type/lint/build, isolated wheel and protected PR/CI delivery |

## Executed checks

- Full `.venv/bin/python -m pytest -q`: 1,922 passed, 8 skipped, 95.30 seconds. Six skips require an external browser and were separately run with actual existing tools: 6 passed in 7.38 seconds. Two existing environment-dependent skips remain distinct.
- Ruff check passed; Ruff format check: 281 files already formatted. mypy: 278 source files passed. `git diff --check` passed.
- `uv build`: wheel and source distribution built. Wheel contains profile data, schema, component resolver and rendered comparator. Fresh environment outside the checkout, only runtime dependencies: CLI help passes; observed oversized workspace exits 1/MATERIAL_DRIFT, corrected workspace exits 0/NOT_OBSERVED, both profile audits PASS. Disposable installation removed afterward.
- Final real browser replay (Chrome 157.0.8103.78): observed control 120×121.125/font20/padding32 becomes 120×40/font14/padding8. Bbox, padding and source-label font/line-height defects detected by ordinary check; fresh corrected observation has zero material findings.
- The demo does not fabricate native bounds. Three source auto-layout/intrinsic geometry observations remain NOT_OBSERVED. No freshness, build, interaction or aesthetic certification is claimed.
- One fresh generic native reviewer, without implementer conversation history, independently ran 94 focused tests. All five reproduced material findings were corrected and checked by that same reviewer. Read [the review](review.md).
- Read [skill authority and authoring evidence](skill-authority.md) and [the compatible port guide](../../../docs/review-led-migration.md#minimal-private-lineage-port). No global synchronization or installed consumer/private SDK change.

## Delivery

Public PR/CI publication pending at this checkpoint. The implementation is accepted; publication results are recorded in progress and changelog when observed.
