---
id: 085-managed-consumer-release
updated: 2026-11-24
---

# Managed consumer release changelog

## 2026-11-24 — [Feature]: Verified Penflow release at startup

- Added checked versioned consumer wheel publication on GitHub.
- Added an idempotent bootstrap that selects and verifies the release using a separate environment derived from the pinned LiveSpec Python.
- Read [the rollout guide](../../../docs/consumer-runtime.md) for the runner contract and exact-tag replay.
- Allow GitHub time to expose new draft, upload and publication records before verifying their identity.
