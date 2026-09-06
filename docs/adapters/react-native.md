# React Native Adapter Guide (Contract C13)

This guide explains how to emit an `actual-ui-tree.json` (contract C12) from a running React Native app (`testID`, `accessibilityRole`, `accessibilityLabel`, `onLayout`). It is part of **contract C13 — adapter conformance mapping** owned by feature 038.

## Runtime-agnostic boundary

Penflow ships **zero runtime code** for the React Native stack. Penflow does **not** start the Metro bundler, does **not** drive the iOS Simulator or Android Emulator, does **not** run Detox / Appium / Maestro, and does **not** execute the JS/TS snippet below. The snippet is **illustrative only** — copy it into your own RN test harness, your own bundler, your own CI. Penflow's responsibility starts after the JSON file lands on disk, with `penflow validate-actual <file> --schema`.

The C12 boundary validates the **shape of the JSON** your adapter must produce. That shape is defined by contract C12 ([`actual-ui-tree.schema.json`](../../penflow/schemas/actual-ui-tree.schema.json), feature 037).

## C51 certification and coordinates

C12 schema validation proves the shape of an observation. C51 additionally joins it to the independently selected build manifest, approved sources, runner/session/scenario identities and the exact evidence bytes. The runner records actual before/after facts and outcomes; it must not copy expected values or declare a successful assertion in place of observing it. **Read** [the verification workflow](../verification-workflow.md) and [the causal evidence guide](causal-transition-evidence.md) before producing certifying evidence.

For C51, express every bbox in logical units relative to the observed screen origin, including nested nodes. Preserve the original native measurements in the runner evidence, then subtract the measured screen origin; do not consult the expected tree to normalize actual geometry. Missing measurements block capture instead of becoming zero boxes. Penflow independently normalizes its authenticated Pencil layout to the same screen coordinates. Older viewport/local-coordinate exports remain historical C13 examples; do not mix their coordinate conventions in a C51 comparison.

Capture the rendered hierarchy, including additional controls without semantic annotations. Test identifiers join observations to the contract; they do not supply the observed role, text, visibility or value. Unknown or unmapped interactive elements must remain visible to validation. Hidden accessibility metadata alone does not prove an element is absent from the rendered screen. A required property unavailable through a platform adapter blocks that capability rather than being omitted.

## C13 mapping table — React Native

The columns follow the canonical C12 field ordering (`id` / `role` / `bbox` / `semantic_id` / `name` / `text` / `children` / `viewport` / `screen_id`). See the spec table in [`spec.md`](../../.specs/features/038-runtime-adapter-guides/spec.md#c13--adapter-conformance-contract-mapping-table) for the cross-stack view.

| C12 field (target) | React Native source |
|---|---|
| `id` (required, unique within tree) | `props.testID`. MUST be unique within the tree; use dotted namespacing (e.g. `checkout.pay`) to make collisions unlikely. |
| `role` (required, free-form string) | `props.accessibilityRole` (e.g. `"button"`, `"text"`, `"image"`) when set, falling back to the component's display name (e.g. `View`, `Text`, `Pressable`). |
| `bbox.{x,y,width,height}` (required) | `onLayout.nativeEvent.layout` is parent-relative. Accumulate every measured ancestor offset for an untransformed/unscrolled hierarchy, or use actual native window measurements and subtract the measured screen origin. Observe scroll/transform offsets; never copy local `x/y` directly into C51. |
| `semantic_id` (optional) | Same value as `testID` when no separate semantic id is needed. Used downstream by `compare-tree` to align actual ↔ expected. |
| `name` (optional) | `props.accessibilityLabel`. |
| `text` (optional) | `props.children` when it is a string (e.g. `<Text>{label}</Text>`), or the joined rendered text of nested `<Text>` children for leaf text nodes. Set to `null` for non-text components. |
| `children` (optional, recursive) | React children of the component — walked depth-first. Skip components with `props.accessibilityElementsHidden === true` or `props.importantForAccessibility === "no-hide-descendants"`. |
| `viewport.{width,height}` | `Dimensions.get('window')` — both `width` and `height` as numbers. |
| `screen_id` | React Navigation route name (`route.name`) or a developer-chosen identifier (e.g. `"checkout"`). |

This table is normative for the React Native stack. The full cross-stack table in [`spec.md`](../../.specs/features/038-runtime-adapter-guides/spec.md#c13--adapter-conformance-contract-mapping-table) is the source of truth for C13.

## Reference snippet (JS / TS — illustrative, not executed by Penflow)

The offset accumulation below assumes an unscrolled, untransformed hierarchy containing every measured host ancestor. A production adapter must use native measurements when those assumptions do not hold. The declared virtual tree and react-test-renderer alone are not evidence of a rendered native application.

> **Illustrative only.** This snippet is documentation, not a file Penflow imports or bundles. Adapt it to your own RN test harness, your own bundler, your own CI. Penflow ships no runtime probe for the React Native stack.

```tsx
import React, { useRef } from "react";
import { View, Text, Pressable, Dimensions, LayoutChangeEvent } from "react-native";

// Per-node layout cache keyed by testID. Populated by onLayout callbacks.
const layouts = new Map<string, { x: number; y: number; width: number; height: number }>();

function trackLayout(testID: string) {
  return (event: LayoutChangeEvent) => {
    const { x, y, width, height } = event.nativeEvent.layout;
    layouts.set(testID, { x, y, width, height });
  };
}

// Walks a virtual representation of the tree (React does not expose a live
// host-tree API for production — wire the same metadata through your component
// declarations, or use a probing library like react-test-renderer / Detox /
// Maestro that exposes the rendered host tree in your harness).
type Node = {
  id: string;
  role: string;
  semantic_id?: string;
  name?: string | null;
  text?: string | null;
  children: Node[];
};

function emitNode(node: Node, parentX = 0, parentY = 0): unknown {
  const local = layouts.get(node.id);
  if (!local) throw new Error(`Missing measured layout: ${node.id}`);
  const bbox = { ...local, x: parentX + local.x, y: parentY + local.y };
  return {
    id: node.id,
    role: node.role,
    bbox,
    semantic_id: node.semantic_id ?? node.id,
    name: node.name ?? null,
    text: node.text ?? null,
    children: node.children.map((child) => emitNode(child, bbox.x, bbox.y)),
  };
}

function emitActualTree(screenId: string, root: Node) {
  const { width, height } = Dimensions.get("window");
  return {
    version: 1,
    screens: [
      {
        screen_id: screenId,
        viewport: { width, height },
        root: emitNode(root, -(layouts.get(root.id)?.x ?? 0),
                       -(layouts.get(root.id)?.y ?? 0)),
      },
    ],
  };
}

// Persist with sorted keys + 2-space indent + trailing newline so the file is
// byte-deterministic. JSON.stringify does not sort keys natively — use a
// stable serializer (e.g. `safe-stable-stringify`) or hand-sort before writing.
// See examples/adapters/react-native/actual-ui-tree.json for the canonical shape.
```

Notes:
- Persist the result with UTF-8 + sorted keys + two-space indent + trailing newline so two consecutive runs produce byte-identical files. The Penflow CLI applies the same rule (feature 037).
- React Native does not expose a live "host tree dump" API in production builds. In tests, either declare the tree explicitly alongside the component, or use a tool that exposes the rendered host tree (Detox, Maestro, react-test-renderer).
- Always wait for the last `onLayout` callback before serialising — bounding boxes for off-screen or animating views are not stable.

## Example fixture

A worked example of the JSON shape produced by this guide lives at:

[`../../examples/adapters/react-native/actual-ui-tree.json`](../../examples/adapters/react-native/actual-ui-tree.json)

Validate it locally with:

```bash
penflow validate-actual examples/adapters/react-native/actual-ui-tree.json --schema --json
```

Expected output: exit 0, `"status": "PASS"`, `"issues": []`.

## Contract references

- **C12** — [`actual-ui-tree.schema.json`](../../penflow/schemas/actual-ui-tree.schema.json) (feature 037). Defines the JSON shape your adapter must produce.
- **C13** — adapter conformance mapping (feature 038, this guide).
- **Three Trees** — see the [project README](../../README.md#three-trees) for the role of `actual-ui-tree.json` in the broader Penflow flow.
- **Spec** — [`spec.md`](../../.specs/features/038-runtime-adapter-guides/spec.md) and [`plan.md`](../../.specs/features/038-runtime-adapter-guides/plan.md) own the normative boundary for feature 038.

## What this guide does NOT do

- Does not ship an npm adapter package.
- Does not start the Metro bundler from Penflow.
- Does not add `react-native`, `node`, `npm`, or `metro` to `pyproject.toml`.
- Does not turn snippet bugs into Penflow regressions — the snippet is documentation.

The feature 039 demo uses a static actual-tree fixture. It does not execute a React Native application or certify this illustrative adapter.
