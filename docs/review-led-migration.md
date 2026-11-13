# Migrate to review led checks

## Before adoption

Record the current CLI/SDK revision, Python interpreter, consumer runtime pin and customized skills/agents. Preserve product files, active mission state and historical evidence. Read [the normal workflow](review-led-workflow.md) and identify which current instructions still mandate certification.

Build the reviewed candidate with `uv build` and install its wheel into an isolated environment first. Test CLI startup, `check` against a disposable consumer workspace, and relevant existing diagnostics. The wheel supplies the CLI/core; it does not automatically replace a consumer's skill projections or runtime pin. Verify those separately through their supported selectors.

A consumer ahead of public main must keep its existing fixes. Port only the reviewed simplification delta onto that SDK lineage, test the result, and preserve both base/candidate identities. Do not install an older public lineage merely to obtain shorter skills. A coordinated LiveSpec/Penflow adoption must validate both installed tools together before resuming a consumer.

## Behavior changes

- The primary command is `penflow check --target <workspace> --project <root> --json`. No Git repository, Doctor receipt, approval history, native certificate packet or build manifest is required. Reads are confined to the selected project and regular files up to 64 MiB each, including the final input-stability recheck. No files are written or UI/runtime processes launched.
- Capture actual results, command exits and NOT_RUN observations. A failed input does not suppress independent checks. Top-level exit 1 means executed diagnostics found warnings/errors, 2 means the workspace is unusable, and 0 may still include missing observations. The result is always non-certifying and requires independent review.
- Standalone read-only diagnostics and `export-flow-docs --check` no longer require unrelated project hygiene. Existing producer preflight, ambiguous-write protections and safe cleanup authorization remain. For ordinary producers, a postflight cleanup refusal emits a separate stderr JSON finding and preserves the product result/exit. Consumers that parse stdout should continue to do so; retain stderr findings too.
- Load the three current skill entry points and resolve their linked workflow from the selected source. Historical skill bodies, companion READMEs and the integration guide remain available only for explicitly requested diagnostics. Reuse one fresh native final review and targeted correction follow-up. Do not create another automatic review/certificate chain.
- Existing `run`, C47, C51, `authority` and receipt validators retain their actual diagnostic contracts and exits. No old FAIL/BLOCKED becomes PASS. A `penflow-check-report` is not accepted as a C51 report, and a supplied actual tree alone proves neither runtime interactions, freshness nor build identity.

## Verify and resume

Use a safe checkpoint after current writes finish. Run relevant tests and actual UI/runtime observations for the product change. Give the native reviewer all findings and material missing observations. Reload the consumer's instructions explicitly, preserve missions/decisions/customizations, and observe real continuation; package installation alone is not evidence that a worker adopted the policy.

## Rollback

Select the saved prior wheel/interpreter and runtime through supported selectors. Restore only the owned skill projections changed by adoption. Keep newer product changes, approval history and both diagnostic histories. State which delivery policy now applies. Do not reset mission counters, rewrite old evidence or delete data because cleanup refused it.
