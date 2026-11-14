# Migrate to review led checks

## Before adoption

Record the current CLI/SDK revision, Python interpreter, consumer runtime pin and customized skills/agents. Preserve product files, active mission state and historical evidence. Read [the normal workflow](review-led-workflow.md) and identify which current instructions still mandate certification.

Build the reviewed candidate with `uv build` and install its wheel into an isolated environment first. Test CLI startup, `check` against a disposable consumer workspace, and relevant existing diagnostics. The wheel supplies the CLI/core; it does not automatically replace a consumer's skill projections or runtime pin. Verify those separately through their supported selectors.

A consumer ahead of public main must keep its existing fixes. Port only the reviewed simplification delta onto that SDK lineage, test the result, and preserve both base/candidate identities. Do not install an older public lineage merely to obtain shorter skills. A coordinated LiveSpec/Penflow adoption must validate both installed tools together before resuming a consumer.

## Behavior changes

- The primary command is `penflow check --target <workspace> --project <root> --json`. No Git repository, Doctor receipt, approval history, native certificate packet or build manifest is required. Reads are confined to the selected project and regular files up to 64 MiB each, including the final input-stability recheck. No files are written or UI/runtime processes launched.
- Capture actual results, command exits and `NOT_RUN`/`NOT_OBSERVED` coverage gaps. A failed input does not suppress independent checks. Top-level exit 1 means executed diagnostics found warnings/errors, 2 means the workspace is unusable, and 0 may still include missing observations. The result is always non-certifying and requires independent review.
- Standalone read-only diagnostics and `export-flow-docs --check` no longer require unrelated project hygiene. Existing canvas-producer preflight, ambiguous-write protections and safe cleanup authorization remain; ordinary contract-only semantic export uses the scoped correction below. For ordinary producers, a postflight cleanup refusal emits a separate stderr JSON finding and preserves the product result/exit. Consumers that parse stdout should continue to do so; retain stderr findings too.
- Load the three current skill entry points and resolve their linked workflow from the selected source. Historical skill bodies, companion READMEs and the integration guide remain available only for explicitly requested diagnostics. Reuse one fresh native final review and targeted correction follow-up. Do not create another automatic review/certificate chain.
- Existing `run`, C47, C51, `authority` and receipt validators retain their actual diagnostic contracts and exits. No old FAIL/BLOCKED becomes PASS. A `penflow-check-report` is not accepted as a C51 report, and a supplied actual tree alone proves neither runtime interactions, freshness nor build identity.

## Adopt profile and rendered measurement diagnostics

- Existing CLI commands and historical certificates keep their contracts. Normal `check` adds automatic profile and rendered-measurement diagnostics. Legacy workspaces can still run structural checks; missing surface context or qualified runtime measurements are unobserved, never a new PASS. Qualified runtime captures use normalized structural comparison inside `compare-rendered`; the raw `compare-tree` diagnostic is not run for those captures. No certificate packet, approval ledger or global skill synchronization is required.
- Select the actual surface/platform once through explicit contract screen surface metadata or workspace `design-profile.json`. Read the resolved convention sources and exclusions; review the bundled policy snapshot against current product rules. Preserve justified product differences as explicit scoped overrides with reasons rather than widening global tolerances. A Tauri WebView uses web/product conventions; mobile hit area and desktop visual control size remain distinct.
- Update the external adapter to emit actual runtime bounds, computed styles and `measurement` metadata (`source`, `method`, `units`, `coordinate_space`, `zoom`, `device_pixel_ratio`). Capture the matching viewport and state; use `design_screen_id` for explicit source-frame selection. Read [the Web rendered adapter guide](adapters/web-rendered.md). Keep optional resolved Pencil layout in `design-layout.json` when source fill/fit geometry cannot be inferred.
- Preserve the single existing product canvas and reconcile revision/variant mappings explicitly. A lifecycle error remains a finding while independent per-region diagnostics continue; do not delete revisions or designate an active frame merely to clear a check.
- For a private consumer ahead of public main, port the reviewed profile/measurement modules and their small tree/check integration delta onto its current SDK lineage, together with matching schemas, package profile data, tests and current workflow instructions. Keep the public source revision and private base revision in the adoption record. Exercise the isolated wheel and the consumer's adapter before changing its pin. Do not replace private SDK fixes with the public wheel, synchronize global skills or upgrade Atlas without coordinated adoption.

## Verify and resume

Use a safe checkpoint after current writes finish. Run relevant tests and actual UI/runtime observations for the product change. Give the native reviewer all findings and material missing observations. Reload the consumer's instructions explicitly, preserve missions/decisions/customizations, and observe real continuation; package installation alone is not evidence that a worker adopted the policy.

## Rollback

Select the saved prior wheel/interpreter and runtime through supported selectors. Restore only the owned skill projections changed by adoption. Keep newer product changes, approval history and both diagnostic histories. State which delivery policy now applies. Do not reset mission counters, rewrite old evidence or delete data because cleanup refused it.

## Minimal private-lineage port

Apply the reviewed delta onto the consumer's existing Penflow lineage, never replace that lineage with the public wheel. Core files: `design_profile.py`, `pen_components.py`, `rendered_measurements.py`, `profiles/design-profiles.json`, `schemas/design-profile.schema.json`; matching integration changes live in `review_checks.py`, `compare.py`, `context.py`, `models.py`, `pen.py`, `tree.py`, `token_lint.py`, `visual_metrics.py`, `verification_styles.py` and the additive actual-tree schema. Include matching regression tests and repository-owned skill/workflow changes. Keep the consumer's SDK fixes, runtime pin and Atlas data unchanged until its supervisor coordinates adoption.

Read [the external adapter](adapters/web-rendered.md) for caller-owned capture code; it is optional for non-Web runtimes, whose adapters must produce equivalent observations. Test the private candidate in isolation before updating its pin. The public PR/commit identifies the port source; the adopter records its actual private base and resulting candidate rather than assuming identical files.

### Exact typography-scale correction after feature 083

Existing consumers without a typography object retain their scale behavior. To use a resolved exact product scale, update the profile schema, `design_profile.py`, `review_checks.py` and `token_lint.py` together, plus their targeted regression test and workflow references. The check resolves the profile once before lint, rejects contradictory theme sizes explicitly and keeps an invalid profile from suppressing independent diagnostics. Read [the exact-scale contract](theme-contract.md#exact-product-typography-in-normal-check) before authoring the product profile.

This delta changes no runtime adapter, actual-tree schema, dependency or private FactsIdentity/SDK code. Port it onto the consumer's existing lineage and test its candidate independently; the public correction does not update an installed private wheel, environment, binding or pin. Reuse unchanged browser evidence while its relevant inputs remain unchanged.

### Contract-only semantic producer correction

A consumer may export a valid strict contract before resolving unrelated canvas revisions. Port `semantic_export.py` plus the narrow CLI handler/governance integration together. Preserve the private project/path resolver, writer lock, contract/semantic validators and atomic writer; do not replace a private SDK module wholesale. Only ordinary `export-semantic-tree` skips canvas/hygiene Doctor preflight and managed-run cleanup. No new opt-in flag is needed.

Existing valid semantic outputs owned by the same selected contract may regenerate. An existing foreign/malformed artifact, source alias, hardlink, symlink or non-JSON destination is refused rather than overwritten; select a legitimate new output when ownership cannot be established. Read [the publication boundary](review-led-workflow.md#contract-only-semantic-export). This correction changes no consumer binding, environment, canvas or private installed package by itself.
