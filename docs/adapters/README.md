# Runtime Adapter Guides — Contract C13

This directory documents **contract C13 — the adapter conformance mapping** owned by feature 038. It tells external producers (in Web, SwiftUI, React Native) how to emit an `actual-ui-tree.json` (contract C12, feature 037) that `penflow validate-actual --schema` accepts on the first try.

## Runtime-agnostic boundary

Penflow ships **zero runtime code** for these stacks. Penflow does **not** launch a browser, does **not** boot the iOS Simulator, does **not** start the Metro bundler, does **not** run Playwright / XCUITest / Detox / Maestro. Each guide's reference snippet is **illustrative only** — Penflow does not compile, import, or execute it. Penflow's responsibility starts after the JSON file lands on disk.

## Guides

| Stack | Guide | Example fixture |
|---|---|---|
| Web DOM (browser + ARIA + `data-testid` + `getBoundingClientRect`) | [`web-dom.md`](web-dom.md) | [`../../examples/adapters/web-dom/actual-ui-tree.json`](../../examples/adapters/web-dom/actual-ui-tree.json) |
| SwiftUI + XCTest (`accessibilityIdentifier`, `XCUIElement`, `snapshot()`) | [`swiftui-xctest.md`](swiftui-xctest.md) | [`../../examples/adapters/swiftui-xctest/actual-ui-tree.json`](../../examples/adapters/swiftui-xctest/actual-ui-tree.json) |
| React Native (`testID`, `accessibilityRole`, `onLayout`) | [`react-native.md`](react-native.md) | [`../../examples/adapters/react-native/actual-ui-tree.json`](../../examples/adapters/react-native/actual-ui-tree.json) |

Each guide repeats the C13 mapping table for its stack with the canonical C12 field ordering (`id` / `role` / `bbox` / `semantic_id` / `name` / `text` / `children` / `viewport` / `screen_id`).

## Contract references

- **C12** — [`actual-ui-tree.schema.json`](../../penflow/schemas/actual-ui-tree.schema.json) (feature 037). The JSON shape your adapter must produce.
- **C13** — adapter conformance mapping (feature 038, this directory). Per-stack mapping onto C12 — no new schema, no new node fields.
- **Three Trees** — see the [project README](../../README.md#three-trees) for the role of `actual-ui-tree.json` in the broader Penflow flow.
- **Spec** — the internal feature 038 specification (not published) owns the normative boundary; this guide summarizes it.

## Out of scope

- End-to-end demo wiring that drives a real Web / iOS / RN app (feature 039).
- Installable adapter packages (npm, SwiftPM, CocoaPods, PyPI).
- Pixel-perfect comparison or screenshot diffing.
- LLM enrichment of the example trees.
