---
id: 082-review-led-checks
name: Review Led Checks
status: Implemented
priority: P1
created: 2026-11-13
---
# Review led checks

User decision: simplify normal Penflow work without manufacturing certification. Keep historical diagnostics explicitly callable, preserve concurrent changes and installed consumers, and deliver after one independent native review. The authorized exception permits direct implementation without the former LiveSpec certificate pipeline.

## Requirements

- **FR-001:** Provide one primary `penflow check --target <workspace> [--project <root>] --json` command. Inspect current local contract, canvas, tokens, consistency, visual metrics and available actual tree without requiring Git, Doctor hygiene, source approval history, native export receipts or a build manifest. Continue independent checks after a failure; record unmet dependencies honestly.
- **FR-002:** Return deterministic, non-certifying results with each check's actual status, exit code, issues and input identity; missing inputs are NOT_RUN, never PASS. Distinguish structural comparison from rendered UI and runtime interactions, which remain unverified. Preserve real failures; a reviewer decides delivery impact.
- **FR-003:** Read-only CLI diagnostics inspect their explicit inputs without unrelated project hygiene vetoes. Explicit C51 authority/profile requests retain their existing governance and interpretation. Protect producer project boundaries, ambiguous writes and unsafe deletion.
- **FR-004:** A refused postflight cleanup on an ordinary producer remains a visible stderr finding and preserves the product exit/result. Historical `run` keeps its existing exit behavior. Never retry a refused deletion or delete unproven data.
- **FR-005:** Route the three canonical skills and public integration guidance through useful checks and one fresh independent native final review; archive former certification instructions for explicit diagnostics. No new automatic certificate chain, silent installation, consumer downgrade or retrospective PASS.
- **FR-006:** Keep migration/rollback instructions, ordinary LiveSpec documents and local commit; do not publish or merge.

## Acceptance

```gherkin
Scenario: Administrative prerequisites are absent
  Given a valid local canvas without Git or approval receipts
  When the operator runs check
  Then available checks run and missing observations remain explicit

Scenario: A real defect and an independent valid input coexist
  Given an invalid contract and a usable canvas and actual tree
  When the operator runs check
  Then the contract fails and independent diagnostics still run

Scenario: Explicit input in an untidy project
  Given multiple canvases or missing ignore metadata
  When a read-only validator inspects an explicit file
  Then its result describes that file without a Doctor prerequisite

Scenario: Cleanup cannot safely complete
  Given an ordinary producer has returned its result
  When postflight cleanup refuses deletion
  Then the original result and exit remain and stderr reports the refusal
```

AC-001 covers FR-001/002: no-Git operation, continued checks, missing/invalid runtime, deterministic output and no workspace writes. AC-002 covers FR-003: read-only input validation with Doctor-incompatible hygiene; explicit C51 regressions remain covered. AC-003 covers FR-004: cleanup refusal preserves both success and failure. AC-004 covers FR-005/006: current guidance selects the review workflow, archived diagnostics remain available, independent review and migration report recorded.
