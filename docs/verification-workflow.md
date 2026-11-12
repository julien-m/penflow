<!-- @spec(FR-001) -->
<!-- @spec(FR-011) -->
<!-- @spec(FR-012) -->
<!-- @spec(FR-015) -->
# Complete verification workflow — C51

C51 is the cumulative verdict for a selected consumer project and workspace. The existing workflow selects `design` after source review and native design production, then `implementation` after the external application runner finishes. Users keep the same planning, design and implementation steps; generated authority files and validation calls are workflow internals.

Read the [closed machine definitions](../penflow/schemas/c51-contracts.schema.json) and use the [public service](../penflow/verification.py). Standalone validators remain useful diagnostics. Their scores, historical C47 reports, warning-tolerant modes and masks do not close C51.

## Source preparation and review

1. Author C20 from actual accepted product behavior. Bind every source requirement that carries a UI-contract obligation to the appropriate obligation, or declare a reviewed delegation for it as described under "Reviewed delegation" below, and preserve expected categories and predicates. Local field changes, navigation, request mutations and native system returns retain their distinct semantics; do not invent requests or permissions for static/local UI. A local state change without any precondition, such as a toggle, declares `"precondition": "none"` instead of a guard. It then has no guarded transition and no `validation` duty, while its action and transition duties stay. A missing guard without that declaration stays invalid; never invent a guard whose `invalid` branch cannot happen.
2. Before the first review, the producer calls `penflow authority prepare <contract.json> --project <caller-root> --json`. This read-only command returns the prepared C20 in the successful envelope's `data`; the producer writes those bytes as its ordinary generated contract. Explicit IDs remain unchanged; missing `test_id` values are deterministic from semantic identity. The reviewer and Pencil boundary run `penflow validate-flow-contract <contract.json> --require-test-ids --project <caller-root> --json`. Validation never repairs an approved source.
3. LiveSpec extracts real FR/AC definitions and reviews the complete cumulative selection. All active features contribute requirements and plans; retiring one preserves the others. Its accepted baseline, prior baselines, exact review output and immutable source snapshots are generated automatically. Brainstorm uses its actual frozen product, view, accepted freeze history and approved change requests; aliases map through explicit bindings and source pointers, never title similarity.
4. The existing workflow generates applicability from the actual reviewed plan/workflow metadata. The closed `penflow_verification_policy` modes are `livespec` and `brainstorm_handoff`; each selected policy contains `version: 1` and exactly `generated_docs`, `native_geometry`, `homologous_references`, `native_export`, each `required` or `not_applicable`. Standard LiveSpec aggregates every active plan, then unions authenticated inherited requirements. A dedicated workflow must itself be archived and reviewed. Missing, duplicate, contradictory or unknown decisions block; artifact absence never proves non-applicability.

The generated policy source binds exact workflow bytes and optional imported authority. LiveSpec records it in its immutable review inputs; Brainstorm writes the workspace's `verification-policy-source.json`. C20 carries the matching policy projection. Neither is a user-maintained ledger. A changed mapping or weaker predicate requires a fresh bound source review.

<!-- @spec FR-008: Document the delegation contract — .specs/features/082-reviewed-requirement-delegation-to-upstream-acceptance/spec.md#fr-008 -->
## Reviewed delegation

A LiveSpec source requirement has exactly one status: bound to at least one outcome expectation, delegated to the upstream acceptance, or uncovered. An uncovered requirement blocks with `requirements.uncovered`.

- Declare a delegation in the reviewed C20 contract under `requirements.delegations`, next to `bindings`. Each record has exactly three fields: `requirement_id` (one source requirement), `acceptance_owner` (the constant `livespec-acceptance`) and `rationale` (a non-blank reason that the contract reviewer judges). The key is optional; when present it holds at least one record.
- A delegation is accepted only from the reviewed contract bytes of the current baseline. Penflow projects it to `projection.delegated`, sorted by `requirement_id`, and the review snapshot binds it through `projection_sha256`. Editing, adding or removing a record after review makes the contract stale; a new review is required.
- A delegation that names an unknown or duplicate requirement, a requirement that is also bound, a retired feature's requirement, an FR whose text references no AC, or a record outside the closed shape fails with `requirements.delegation.invalid`. A Brainstorm contract that carries the key fails with `product.delegation.forbidden`. Inherited (imported) duties are always bound.
- LiveSpec may add `penflow_identity` to the review snapshot, the review approval and the Brainstorm authority import. This field identifies the Penflow CLI that LiveSpec invoked, with exactly `version`, `executable` and `executable_sha256`. Penflow checks only its closed shape. LiveSpec checks that the identity matches. The key is never null, and records without it keep their historical bytes.
- A duty observable on screen, including keyboard and focus behaviour, is bound and not delegated. A duty verifiable by Penflow with typed `storage` or `network` evidence is bound and not delegated.
- A reviewed source is compared with its authenticated archive using one parser on both sides: the `semantic_sha256` recorded at approval is informational, because an earlier normalization may no longer reproduce it. A change of meaning still needs a review.
- **Technical continuity revision.** When LiveSpec delivery continuity accepts a technical change of reviewed sources, LiveSpec republishes the baseline as a revision with the same approval, scope, selection and requirements. The revision has a `previous` link to the archived predecessor and a `continuity` reference to an archived `requirements-continuity` receipt. Penflow trusts no verdict of that receipt; it authenticates every archived byte and re-proves each change:
  - a source keeps its meaning without the `**Evidence:**`, `**Review inputs:**`, `**Static command:**`, `**Static directory:**` and `**Static inputs:**` lines of its `AC-NNN` sections, and exactly the declared criteria changed them, each with its declared levels before and after;
  - each new level is one the approved document already grants:
    - the only level of that criterion in a normative level table (a Markdown table outside fences whose header names the level and the criteria, read row by row, ranges `AC-NNN–AC-MMM` included);
    - or, without a table entry, a move from an explicit inline level that keeps its floor: `execution` and `native` never move, and nothing becomes `review`.
    No level is guessed: without any approved level, or with several table levels for one criterion (an inline line holds one), the change needs a review. Levels written only in free prose are not read; the change is then refused, never accepted;
  - the contract only ADDS `states` or `repeat_model` to nodes that had none, plus the entity fields those new repeat models name, and moves the source digests of a proved source change. It still validates. Removing or changing an existing scope or model, a node, a binding, an order, an action, a guard, a transition or an expectation is refused;
  - the projection equals the approved one except for those moved source digests.
  Anything else, such as criterion text, actions, guards, transitions, expectations, copy, an undeclared criterion, or an altered or missing archive, is refused (`continuity.*`, `input.stale`). Baselines without `continuity` are read as before.
- Contract reviewers: refuse a delegation that removes a persistence expectation or any other duty of the two kinds above. The approval `changes` delta names binding changes only, so read delegation changes in the snapshot `projection.delegated`; a bound requirement that becomes delegated shows its removed binding in `changed_binding_ids`.

The report lists every delegated requirement under `delegated_requirements`, one `{requirement_id, acceptance_owner, certified}` entry each, with `certified: false`. Obligation counts cover the obligations derived from the contract records only; a delegation never satisfies, removes or replaces one of them. With delegated requirements, a `PASS` certifies the UI-contract obligations only and claims no upstream or future application execution. Consumers read `delegated_requirements` from the report whose hash the `PASS` validation wrapper returns, and fail their own closure when a delegated acceptance criterion lacks upstream acceptance. A delegation adds no gate, runner or evidence capability, and artifacts without delegations keep their exact bytes.

## Native design closure

- Preparation before Plan Review is explicitly non-certifying. Reuse unchanged design bytes and current valid receipts after review; do not repeat a complete Mockup Factory run solely because the phase changed.
- Open `ui.pen` in pen.dev and confirm it with `get_app_state` before any MCP call. Capture actual pen.dev persistence (C46) by file copies: copy `ui.pen` before the final mutation batch, mutate through `execute`, run the `pencil-sync` save trigger, copy `ui.pen` again, write the `penflow-pencil-persistence-observation`, then run `verify-pencil-persistence` and `validate-report`. Penflow reads `ui.pen` on disk by design; no rule restricts Penflow to MCP access. Also capture exports, inspected vision evidence (C45) and the complete native layout. `pencil-sync` is only a save trigger. A renderer being installed is not executed evidence.
- When geometry is required, save the raw MCP response of the native layout `execute` call (Penflow skill; it replaces the legacy `snapshot_layout` tool) and a `penflow-native-layout` envelope: `version: 1`, `coordinate_space: parent-relative`, exact `source` and `observation` file hashes, and `children` equal to the decoded native layout: the single printed list, or the tree rebuilt from a printed `penflow-native-get-layout` measurement envelope (`penflow.verification_transport`). The Print transport (`OK`, `## Print output`, one line) and the legacy bare JSON response are both decoded; failed calls, several Print lines and identity/parent/context mismatches block. Its optional `screens` index is derived from the same measurements. Every native node and parent must match the current source; no synthetic layout is accepted.
- C51 accumulates native child offsets and removes the root's canvas origin. The resulting expected coordinates are relative to the logical screen. Native fill-container dimensions use measured values. Native intrinsic text sizing (document version 2.14 or later) uses measured content width; fixed/unmeasured text retains its estimate and parent bounds remain checked.
- Reference fidelity and native export-operation C48 follow reviewed applicability and authenticated inherited duties. C45 and C46 remain required. A pure LiveSpec workflow does not invent a frozen Brainstorm product just to execute C48.

Run automatically from the selected caller:

```bash
penflow run --target penflow --profile design --project . --json
penflow validate-report penflow/run-report.json --schema --required-profile design --project . --json
```

Require both exits 0 and exact-profile `PASS` with empty issues. C51 generates semantic/expected/IR projections from authenticated inputs; do not overwrite its normalized expected tree afterward with a standalone legacy export. `audit-report.json` remains the detailed audit history, not the final cumulative authority.

## Implementation closure

The external runner executes the application and captures C12, its provenance, typed outcome observations and required C44 causal evidence. It independently captures actor/scenario/action identity, real request/response facts, before/after state, and storage readback after restart when required. Observed facts never come from expected predicates. A static screen uses an authentic UI snapshot without an invented actor or action.

C51 removes only inert runtime layout wrappers and exact inherited text labels before comparing source identities. A wrapper's context may contain only consistent classification, ownership and matching-role metadata; any other explicit context field remains observable, including an action, intent, binding, repeat, entity, test identifier or permission with an empty, null or false value. Semantic, unknown or contradictory classifications are retained and fail as undeclared nodes. Layout wrappers with absent or null C12 semantic identity may remain unclassified or simply decorative; they need no new owner metadata. Explicit ownership claims must name the nearest declared ancestor and a nonempty relation or reason; inherited labels additionally require the `content` relation and exact canonical owner text. Removing an inert wrapper preserves its descendants and their measured geometry. This normalization adds no capture or operator step.

The runner writes a `penflow-build-manifest` inside the caller project but outside the Penflow workspace and managed temporary directories. It binds actual executed entrypoint snapshots, served artifacts, source references, raw evidence and observation envelopes. Use `verification_source_references(project_root=..., workspace=...)` from the [snapshot API](../penflow/verification_snapshot.py) before and after capture; no consumer should duplicate authority selection. Session/scenario IDs join the exact referenced facts, not merely separate lists of known IDs.

```bash
penflow run --target penflow --profile implementation --project . --build-manifest <runner-path> --json
penflow validate-report penflow/run-report.json --schema --required-profile implementation --project . --build-manifest <runner-path> --json
```

The caller supplies the manifest independently. A report cannot select its own project or build. Revalidation reads current bytes and reruns the same policy; changing only report status or recomputing its hash cannot make an incomplete run pass. Missing evidence, unknown capabilities, omitted obligations, stale sources and required warnings remain blocking.

The expected tree carries the contract `states` of each screen and node and the contract `repeat_model` of collection templates. When nodes are scoped to states, the runner captures one actual tree per state (`state`, `scenario_id`), each witnessed by an `observed_states` entry; the comparison joins each capture with the nodes of its state and refuses a missing, unknown, unwitnessed or fused state, and matches collection instances only through `instance_id_template` ([state and collection capture](adapters/state-and-collection-capture.md)).

`observed_states` is an index into authenticated UI observations or standalone UI snapshots. Each tuple must join exact screen/state/session/scenario/contract/build facts. Disappearance after a native close is observed absence; unavailable geometry/state may be null only in that closed branch. A guard may declare `"enforcement": "absence"` when the product enforces it by not offering the action (Save is not rendered until the record is read). Its `validation:<guard>:<action>:invalid` duty stays.
- It is proved by UI facts with `"present": false` before and after: `visible: false`, and null `bbox`, `enabled` and `text`.
- An absent control proves only that branch (`outcome.validation.absence_undeclared`), and a guard enforced by absence needs that absence (`outcome.validation.absence_unobserved`).
- The default `refusal` is unchanged. Back navigation joins an actually observed previous URL, plus any source-required destination predicate.

## Consumer transport and lifecycle

The public function is `validate_verification_report(report_path, *, project_root, required_profile, build_manifest_path=None)`. Its CLI equivalent returns `kind: penflow-verification-validation`, `version: 1`, `status`, `required_profile`, actual `profile`, `report_sha256`, `scope`, `build_manifest`, and `issues`. On failure, unknown fields are explicitly null. A design success has a null build manifest.

Consumers hash the report before and after validation and compare the returned report hash, exact caller scope, profile and independently supplied build path/hash. They do not reimplement C51 rules. Lifecycle-only LiveSpec status/updated changes and exact generated finalization markers remain semantically linked to authenticated immutable reviewed snapshots. Free comments, visual requirements, FR/AC, categories and predicates remain significant. Other build or evidence bytes receive no lifecycle exception.

Brainstorm handoff uses the existing automatic bootstrap: `authority collect` first revalidates the source design report; the importer preserves all validated source bytes in a local archive, rechecks the source, and publishes atomically. The fixed `.specs/penflow-brainstorm-authority.json` pointer references an immutable import package. `authority project` recomputes imported product duties against the current C20; source path history never requires accessing a moved original project. The LiveSpec review binds the import and preserves its denominator and required procedure. A loose copied freeze is not inheritance proof.

## Limits and recovery

- `PASS` certifies the complete declared scope and observed capabilities. It cannot prove omitted human intent, all future executions or a compromised trusted runner. Hashes prove identity and consistency, not that an arbitrary producer honestly executed an application.
- Fix the identified source, adapter, application or native design; rerun its affected production step and the cumulative verifier. Never relabel old observations, remove duties to reduce the denominator or turn missing capabilities into non-applicability.
- Existing ungoverned reports and static demo fixtures remain available for inspection/regression. They do not certify C51. Unsupported native variable/theme representations fail explicitly until an adapter can observe and resolve them without ambiguity.
