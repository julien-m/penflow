# Changelog — Review led checks

## 2026-11-13 — Implemented

- Added non-certifying current-input checks; failures and missing observations remain visible while independent diagnostics continue.
- Removed unrelated Doctor prerequisites from ordinary read-only diagnostics; retained explicit historical C51 governance and existing producer protections.
- Preserved ordinary producer results when postflight cleanup refuses deletion, with separate stderr findings.
- Simplified three skill entries and public guidance; archived historical protocols and documented migration/rollback.
- Corrected the independent review finding: regular-file, nonblocking, 64 MiB bounded reads and rechecks only for the new checker; legacy reads remain unchanged.
- Validation and limitations: read [progress](progress.md). No installation, publication or consumer-runtime change by this source task.
