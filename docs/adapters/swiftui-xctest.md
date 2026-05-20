# SwiftUI + XCTest Adapter Guide (Contract C13)

This guide explains how to emit an `actual-ui-tree.json` (contract C12) from a running SwiftUI app driven by XCTest (`XCUIApplication`, `XCUIElement`, `accessibilityIdentifier`, `snapshot()`). It is part of **contract C13 — adapter conformance mapping** owned by feature 038.

## Runtime-agnostic boundary

Penflow ships **zero runtime code** for the SwiftUI / iOS stack. Penflow does **not** invoke `xcodebuild`, does **not** boot the iOS Simulator, does **not** drive XCUITest, and does **not** execute the Swift snippet below. The snippet is **illustrative only** — copy it into your own XCTest target, your own simulator, your own CI. Penflow's responsibility starts after the JSON file lands on disk, with `penflow validate-actual <file> --schema`.

The only thing Penflow guarantees for the SwiftUI stack is the **shape of the JSON** your adapter must produce. That shape is defined by contract C12 ([`actual-ui-tree.schema.json`](../../penflow/schemas/actual-ui-tree.schema.json), feature 037).

## C13 mapping table — SwiftUI + XCTest

The columns follow the canonical C12 field ordering (`id` / `role` / `bbox` / `semantic_id` / `name` / `text` / `children` / `viewport` / `screen_id`). See the spec table in [`spec.md`](../../.specs/features/038-runtime-adapter-guides/spec.md#c13--adapter-conformance-contract-mapping-table) for the cross-stack view.

| C12 field (target) | SwiftUI + XCTest source |
|---|---|
| `id` (required, unique within tree) | `XCUIElement.identifier` — i.e. the `accessibilityIdentifier(_:)` set in your SwiftUI view. MUST be unique within the tree; use dotted namespacing (e.g. `Checkout.PayButton`) to make collisions unlikely. |
| `role` (required, free-form string) | `XCUIElement.elementType` mapped to a stable lowercased string. Common mappings: `.button` → `"button"`, `.staticText` → `"staticText"`, `.image` → `"image"`, `.textField` → `"textField"`, `.other` → `"view"`. |
| `bbox.{x,y,width,height}` (required) | `XCUIElement.frame` from `snapshot().frame` — copy `origin.x`, `origin.y`, `size.width`, `size.height` as `Double`. |
| `semantic_id` (optional) | Same as `id` (the `accessibilityIdentifier`) when no separate semantic id exists. Used downstream by `compare-tree` to align actual ↔ expected. |
| `name` (optional) | `XCUIElement.label` (which surfaces SwiftUI `accessibilityLabel(_:)`). |
| `text` (optional) | `XCUIElement.value as? String` (for editable fields) or `label` for static text elements. Set to `nil` (`null` in JSON) when the element has no textual content. |
| `children` (optional, recursive) | `XCUIElement.children(matching: .any).allElementsBoundByIndex` — walk depth-first. Skip elements with `accessibilityElementsHidden == true`. |
| `viewport.{width,height}` | `XCUIApplication().windows.firstMatch.frame.size` (or the device's logical screen size from `UIScreen.main.bounds`). |
| `screen_id` | XCTest test method name, the SwiftUI view name (e.g. `"checkout"`), or a developer-chosen identifier. |

This table is normative for the SwiftUI stack. The full cross-stack table in [`spec.md`](../../.specs/features/038-runtime-adapter-guides/spec.md#c13--adapter-conformance-contract-mapping-table) is the source of truth for C13.

## Reference snippet (Swift / XCTest — illustrative, not executed by Penflow)

> **Illustrative only.** This snippet is documentation, not a file Penflow compiles or runs. Adapt it to your own XCTest target, your own simulator, your own CI. Penflow ships no runtime probe for the SwiftUI stack.

```swift
import XCTest

// Walks XCUIApplication.descendants(matching: .any) and emits an
// actual-ui-tree.json matching contract C12.
struct ActualNode: Encodable {
    let id: String
    let role: String
    let bbox: Bbox
    let semantic_id: String?
    let name: String?
    let text: String?
    let children: [ActualNode]
}

struct Bbox: Encodable {
    let x: Double, y: Double, width: Double, height: Double
}

struct Viewport: Encodable { let width: Double, height: Double }
struct Screen: Encodable { let screen_id: String; let viewport: Viewport; let root: ActualNode }
struct ActualTree: Encodable { let version: Int; let screens: [Screen] }

func roleFor(_ type: XCUIElement.ElementType) -> String {
    switch type {
    case .button: return "button"
    case .staticText: return "staticText"
    case .image: return "image"
    case .textField, .secureTextField: return "textField"
    default: return "view"
    }
}

func walk(_ element: XCUIElement) -> ActualNode {
    let snap = try! element.snapshot()
    let frame = snap.frame
    let children = element.children(matching: .any).allElementsBoundByIndex.map(walk)
    let id = element.identifier.isEmpty
        ? "anon.\(ObjectIdentifier(element).hashValue)"
        : element.identifier
    return ActualNode(
        id: id,
        role: roleFor(element.elementType),
        bbox: Bbox(x: frame.origin.x, y: frame.origin.y,
                   width: frame.size.width, height: frame.size.height),
        semantic_id: id,
        name: element.label.isEmpty ? nil : element.label,
        text: (element.value as? String) ?? (element.label.isEmpty ? nil : element.label),
        children: children
    )
}

func emitActualTree(screenId: String) -> ActualTree {
    let app = XCUIApplication()
    let window = app.windows.firstMatch
    let viewport = Viewport(width: Double(window.frame.size.width),
                            height: Double(window.frame.size.height))
    return ActualTree(
        version: 1,
        screens: [Screen(screen_id: screenId, viewport: viewport, root: walk(window))]
    )
}

// Persist with sorted keys + pretty-print so the file is byte-deterministic
// (matches the Penflow CLI determinism guarantee).
let encoder = JSONEncoder()
encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
let data = try encoder.encode(emitActualTree(screenId: "checkout"))
// Append a trailing newline yourself — JSONEncoder does not add one.
```

Notes:
- `JSONEncoder` with `[.prettyPrinted, .sortedKeys]` uses 2-space indent and sorts keys — matches the Penflow determinism rule. Append `"\n"` to the data before writing to disk for the trailing newline.
- Run the walk **after** the screen under test has stabilised (`app.wait(for: ...)`) to avoid capturing a transient layout.

## Example fixture

A worked example of the JSON shape produced by this guide lives at:

[`../../examples/adapters/swiftui-xctest/actual-ui-tree.json`](../../examples/adapters/swiftui-xctest/actual-ui-tree.json)

Validate it locally with:

```bash
penflow validate-actual examples/adapters/swiftui-xctest/actual-ui-tree.json --schema --json
```

Expected output: exit 0, `"status": "PASS"`, `"issues": []`.

## Contract references

- **C12** — [`actual-ui-tree.schema.json`](../../penflow/schemas/actual-ui-tree.schema.json) (feature 037). Defines the JSON shape your adapter must produce.
- **C13** — adapter conformance mapping (feature 038, this guide).
- **Three Trees** — see the [project README](../../README.md#three-trees) for the role of `actual-ui-tree.json` in the broader Penflow flow.
- **Spec** — [`spec.md`](../../.specs/features/038-runtime-adapter-guides/spec.md) and [`plan.md`](../../.specs/features/038-runtime-adapter-guides/plan.md) own the normative boundary for feature 038.

## What this guide does NOT do

- Does not ship a SwiftPM / CocoaPods adapter package.
- Does not boot the iOS Simulator from Penflow.
- Does not add `xcuitest`, `xcodebuild`, or any iOS-specific dependency to `pyproject.toml`.
- Does not turn snippet bugs into Penflow regressions — the snippet is documentation.

If you want an end-to-end demo that drives a real running iOS app, see feature 039 (out of scope for feature 038).
