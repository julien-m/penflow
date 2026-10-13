# SwiftUI + XCTest Adapter Guide (Contract C13)

This guide explains how to emit an `actual-ui-tree.json` (contract C12) from a running SwiftUI app driven by XCTest (`XCUIApplication`, `XCUIElement`, `accessibilityIdentifier`, `snapshot()`). It is part of **contract C13 — adapter conformance mapping** owned by feature 038.

## Runtime-agnostic boundary

Penflow ships **zero runtime code** for the SwiftUI / iOS stack. Penflow does **not** invoke `xcodebuild`, does **not** boot the iOS Simulator, does **not** drive XCUITest, and does **not** execute the Swift snippet below. The snippet is **illustrative only** — copy it into your own XCTest target, your own simulator, your own CI. Penflow's responsibility starts after the JSON file lands on disk, with `penflow validate-actual <file> --schema`.

The C12 boundary validates the **shape of the JSON** your adapter must produce. That shape is defined by contract C12 ([`actual-ui-tree.schema.json`](../../penflow/schemas/actual-ui-tree.schema.json), feature 037).

## C51 certification and coordinates

C12 schema validation proves the shape of an observation. C51 additionally joins it to the independently selected build manifest, approved sources, runner/session/scenario identities and the exact evidence bytes. The runner records actual before/after facts and outcomes; it must not copy expected values or declare a successful assertion in place of observing it. **Read** [the verification workflow](../verification-workflow.md) and [the causal evidence guide](causal-transition-evidence.md) before producing certifying evidence.

For C51, express every bbox in logical units relative to the observed screen origin, including nested nodes. Preserve the original native measurements in the runner evidence, then subtract the measured screen origin; do not consult the expected tree to normalize actual geometry. Missing measurements block capture instead of becoming zero boxes. Penflow independently normalizes its authenticated Pencil layout to the same screen coordinates. Older viewport/local-coordinate exports remain historical C13 examples; do not mix their coordinate conventions in a C51 comparison.

Capture the rendered hierarchy, including additional controls without semantic annotations. Test identifiers join observations to the contract; they do not supply the observed role, text, visibility or value. Unknown or unmapped interactive elements must remain visible to validation. Hidden accessibility metadata alone does not prove an element is absent from the rendered screen. A required property unavailable through a platform adapter blocks that capability rather than being omitted.

## C13 mapping table — SwiftUI + XCTest

The columns follow the canonical C12 field ordering (`id` / `role` / `bbox` / `semantic_id` / `name` / `text` / `children` / `viewport` / `screen_id`). See the cross-stack overview in [README.md](README.md).

| C12 field (target) | SwiftUI + XCTest source |
|---|---|
| `id` (required, unique within tree) | `XCUIElement.identifier` — i.e. the `accessibilityIdentifier(_:)` set in your SwiftUI view. MUST be unique within the tree; use dotted namespacing (e.g. `Checkout.PayButton`) to make collisions unlikely. |
| `role` (required, free-form string) | `XCUIElement.elementType` mapped to a stable lowercased string. Common mappings: `.button` → `"button"`, `.staticText` → `"staticText"`, `.image` → `"image"`, `.textField` → `"textField"`, `.other` → `"view"`. |
| `bbox.{x,y,width,height}` (required) | `snapshot().frame` is absolute. Subtract the independently measured screen frame origin from each node origin for C51; preserve size in logical points and retain raw frames in runner evidence. |
| `semantic_id` (optional) | Same as `id` (the `accessibilityIdentifier`) when no separate semantic id exists. Used downstream by `compare-tree` to align actual ↔ expected. |
| `name` (optional) | `XCUIElement.label` (which surfaces SwiftUI `accessibilityLabel(_:)`). |
| `text` (optional) | `XCUIElement.value as? String` (for editable fields) or `label` for static text elements. Set to `nil` (`null` in JSON) when the element has no textual content. |
| `children` (optional, recursive) | `XCUIElement.children(matching: .any).allElementsBoundByIndex` — walk depth-first. Skip elements with `accessibilityElementsHidden == true`. |
| `viewport.{width,height}` | `XCUIApplication().windows.firstMatch.frame.size` (or the device's logical screen size from `UIScreen.main.bounds`). |
| `screen_id` | XCTest test method name, the SwiftUI view name (e.g. `"checkout"`), or a developer-chosen identifier. |

This table is normative for the SwiftUI stack. The cross-stack overview in [README.md](README.md) lists the other stacks.

## Reference snippet (Swift / XCTest — illustrative, not executed by Penflow)

This accessibility-only example does not collect C51 provenance or every visual property. A certifying adapter must supplement unavailable observations or block the affected capability; it must also detect rendered controls missing accessibility identifiers instead of treating the example fallback as a contract identity.

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

func walk(_ element: XCUIElement, screenOrigin: CGPoint) -> ActualNode {
    let snap = try! element.snapshot()
    let frame = snap.frame
    let children = element.children(matching: .any).allElementsBoundByIndex.map {
        walk($0, screenOrigin: screenOrigin)
    }
    let id = element.identifier.isEmpty
        ? "anon.\(ObjectIdentifier(element).hashValue)"
        : element.identifier
    return ActualNode(
        id: id,
        role: roleFor(element.elementType),
        bbox: Bbox(x: frame.origin.x - screenOrigin.x,
                   y: frame.origin.y - screenOrigin.y,
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
        screens: [Screen(screen_id: screenId, viewport: viewport, root: walk(window, screenOrigin: window.frame.origin))]
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
- **Spec** — the internal feature 038 specification (not published) owns the normative boundary; the [adapter guide overview](README.md) summarizes it.

## What this guide does NOT do

- Does not ship a SwiftPM / CocoaPods adapter package.
- Does not boot the iOS Simulator from Penflow.
- Does not add `xcuitest`, `xcodebuild`, or any iOS-specific dependency to `pyproject.toml`.
- Does not turn snippet bugs into Penflow regressions — the snippet is documentation.

The feature 039 demo uses a static actual-tree fixture. It does not execute an iOS application or certify this illustrative adapter.
