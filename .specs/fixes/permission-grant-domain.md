# Permission grant domain — scoped correction

User request (2026-11-13): integrate the newer permission correction into public main, test, push and merge. This corrects C51 feature 077's applicable permission duties without changing normal review-led delivery or consumer installations.

## Contract and plan

Port only 669463f onto public 80e3307. For each source permission, retain that grant's own allowed actor. Derive denied only when a declared actor has no grant for the same effective action and entity. Union direct action references with the action's permission pointer; another action/entity never grants authority. Reject undeclared actors, unbound impossible negative expectations and negative observations by granted actors. Existing observation schemas, non-permission duties and source immutability remain.

The shared pure resolver owns grant membership; obligation derivation, expected semantics and observed-outcome validation use that resolver. No database, schema, UI/runtime execution or consumer-pinning change. Python typed boundaries and existing JSON payload contracts remain; fixed test data stays in tests.

## Implementation mapping

| Responsibility | Owning file | Checks |
|---|---|---|
| Action/entity grant domain | Read [resolver](../../penflow/verification_permissions.py) | Cross-action/entity and multiple-grant tests |
| Applicable denied duty | Read [obligations](../../penflow/verification_obligations.py) | Singleton, fully/partially granted actor domains |
| Preserve exact allowed witness | Read [expectations](../../penflow/verification_expectations.py) | Each source grant's actor, missing/unknown/negative predicates |
| Reject contradictory runtime result | Read [outcomes](../../penflow/verification_outcomes.py) | Granted negative, unknown actor, missing observation, non-permission outcomes |
| Historical operator contract | Read [C51 guide](../../docs/verification-workflow.md) | Existing workflow documentation regressions |

## Progress and validation

- Exact source port committed as 3704a9f; no unrelated consumer fixes included.
- Targeted permission/obligation/adversarial/guard/docs tests: 98 passed in 6.91s.
- Whole-repo Ruff, format and mypy: passed (269 Python files).
- One fresh independent native final review: accepted, no material findings. The reviewer independently reran the 98 scoped tests and checked the pointer-only/action-binding union edge.
- Full-suite and CI results are retained on the delivery PR; merge requires observing their actual result. No runtime application observation is claimed.
- User authorized publication and merge; no changes to Atlas or installed consumers are implied.

## Changelog

- 2026-11-13: ported the reviewed source variant; one common resolver replaces single-actor authorization assumptions in all three consumers. Explicit historical diagnostics retain real fail results, including missing required denials. Test packets are synthetic local validator coverage, not application-runtime observations.

## Independent native review record

Accepted: no material findings in 80e3307..3704a9f. The shared resolver unions both action bindings within the exact entity; denied duties omit impossible negatives and each grant retains its own positive actor. Outcome validation uses the source permission entity and preserves unknown-actor rejection. Architecture remains stateless and runtime independent with no new persistence/network dependency. The reviewer independently reran all five scoped test files (98 passed) and an in-memory pointer-only grant check. No corrections required. Synthetic protocol validation does not establish live application behavior.
