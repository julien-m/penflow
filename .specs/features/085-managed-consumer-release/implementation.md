---
id: 085-managed-consumer-release
title: Managed consumer release
feature: 085-managed-consumer-release
status: Implemented
created: 2026-11-24
updated: 2026-11-24
---

# Implementation — Managed consumer release

<!-- @spec(FR-001,FR-002,FR-003,FR-004) -->

## Requirement Mapping

| Requirement | Evidence |
|---|---|
| FR-001 | Inspect [the publication workflow](../../../.github/workflows/publish-consumer-release.yml) and [builder](../../../tools/build-consumer-release.py) for exact-SHA qualification, isolated build and resumable publication. |
| FR-002 / FR-003 | Read [the bootstrap](../../../tools/sync-consumer-penflow.py) and [its regression tests](../../../tests/test_consumer_release_sync.py) for pin validation, reviewed assets, isolated installation and repeat selection. |
| FR-004 | Read [the startup contract](../../../docs/consumer-runtime.md) for the interpreter and release receipt passed to each consumer replay. No consumer artifacts are distributed here. |

## Acceptance Criteria

- AC-001 checks exact-SHA workflow qualification and artifact metadata. The local release build and isolated package smoke have passed on Python 3.12 and 3.14.
- AC-002 checks genuine uv installation with controlled registry inputs, including reuse, conflicts, write confinement and independent version environments.
- AC-003 is checked on the Mac using the normal runner, with the resulting release and interpreter recorded locally.

The full Penflow suite passed 2,005 tests with 8 skipped. The final independent review checked the same-SHA CI and Security gate, queueing, and isolated Python imports. The consumer bridge passed 20 local runner tests. The protected main workflow published v0.3.0 with verifiable SHA-256 for all three assets. The consumer used its normal runner twice, reporting installed then current with the same interpreter. Both runs produced the Markdown visual report and preserved the baseline machine findings.

The initial publish recovered by rerunning after the draft became readable. The publisher now waits for GitHub to reflect create, upload and publication writes before verifying the state. The 19 focused regressions cover the bounded wait and timeout.
