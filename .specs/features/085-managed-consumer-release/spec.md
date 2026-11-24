---
id: 085-managed-consumer-release
title: Managed consumer release
status: Implemented
priority: P1
created: 2026-11-24
updated: 2026-11-24
---

# Managed consumer release

## User Scenarios

A consumer starts its visual replay after a new Penflow version has passed checks on the protected integration branch. The consumer receives the approved Penflow package in an isolated interpreter derived from its pinned LiveSpec Python.

## Functional Requirements

- **FR-001:** A successful checked main build publishes a versioned wheel, a hashed dependency export and a provenance manifest for the checked commit. A version is published once. Pull request jobs never publish releases.
- **FR-002:** A standalone startup command selects the latest published stable release or an explicit release tag, verifies GitHub asset digests, source revision and the pinned Python, then activates the exact wheel in a separate environment.
- **FR-003:** Repeating the selection reuses the verified environment. Concurrent startup and failed installation never replace a valid environment or alter the private runtime.
- **FR-004:** The consumer runner uses the returned interpreter and records the release identity. Actual replay exercises visual-alignment under that interpreter.

## Acceptance Criteria

```gherkin
Scenario: Replay after an approved Penflow release
  Given the consumer has an older installed Penflow and a pinned LiveSpec Python
  When the normal runner starts against the checked published release
  Then it uses the verified wheel without changing that pinned environment
  And a second launch reuses the same activated interpreter
```

- AC-001 covers publication from the checked commit and exact, verified artifact selection.
- AC-002 covers separate environments, retry and repeat, digests and version checks.
- AC-003 covers a real consumer replay and isolated diagnostic execution.

## Edge Cases

- A release is incomplete, withdrawn, malformed or has incompatible artifacts.
- A partial environment or incorrect provenance is found during startup.
- The LiveSpec pin or base interpreter changes.
