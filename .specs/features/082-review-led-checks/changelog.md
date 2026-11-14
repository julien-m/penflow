# Changelog — Review led checks

## 2026-11-14 — Existing canvas and editor connection

- Restore the single product canvas rule prominently in the normal workflow and integration guide; enrich existing screens across features instead of creating a canvas per feature.
- Separate editor-opening acknowledgements, actual file connection, mutation readback and disk persistence. Document measured background/multiple-document behavior without inventing a one-editor-per-chat limit or a new test gate.
- Read [the operator observations](../../../docs/pen-dev-editor-observations.md) for the bounded live tests and their limits.

## 2026-11-13 — Implemented

- Added non-certifying current-input checks; failures and missing observations remain visible while independent diagnostics continue.
- Removed unrelated Doctor prerequisites from ordinary read-only diagnostics; retained explicit historical C51 governance and existing producer protections.
- Preserved ordinary producer results when postflight cleanup refuses deletion, with separate stderr findings.
- Simplified three skill entries and public guidance; archived historical protocols and documented migration/rollback.
- Corrected the independent review finding: regular-file, nonblocking, 64 MiB bounded reads and rechecks only for the new checker; legacy reads remain unchanged.
- Validation and limitations: read [progress](progress.md). No installation, publication or consumer-runtime change by this source task.

## 2026-11-13 — PR review corrections

- Preserve token warnings from the existing violations field in check issues and nonzero outcomes.
- Normalize the supported single-screen actual envelope before comparison; genuine mismatches still fail.
- Both regressions reproduced before correction and pass afterwards.
