# React Native Adapter Guide (Contract C13)

This guide explains how to emit an `actual-ui-tree.json` (contract C12) from a running React Native app (`testID`, `accessibilityRole`, `accessibilityLabel`, `onLayout`). It is part of **contract C13 — adapter conformance mapping** owned by feature 038.

## Runtime-agnostic boundary

Penflow ships **zero runtime code** for the React Native stack. Penflow does **not** start the Metro bundler, does **not** drive the iOS Simulator or Android Emulator, does **not** run Detox / Appium / Maestro, and does **not** execute the JS/TS snippet below. The snippet is **illustrative only** — copy it into your own RN test harness, your own bundler, your own CI. Penflow's responsibility starts after the JSON file lands on disk, with `penflow validate-actual <file> --schema`.

The only thing Penflow guarantees for the React Native stack is the **shape of the JSON** your adapter must produce. That shape is defined by contract C12 ([`actual-ui-tree.schema.json`](../../penflow/schemas/actual-ui-tree.schema.json), feature 037).

## C13 mapping table — React Native

The columns follow the canonical C12 field ordering (`id` / `role` / `bbox` / `semantic_id` / `name` / `text` / `children` / `viewport` / `screen_id`). See the spec table in [`spec.md`](../../.specs/features/038-runtime-adapter-guides/spec.md#c13--adapter-conformance-contract-mapping-table) for the cross-stack view.

| C12 field (target) | React Native source |
|---|---|
| `id` (required, unique within tree) | `props.testID`. MUST be unique within the tree; use dotted namespacing (e.g. `checkout.pay`) to make collisions unlikely. |
| `role` (required, free-form string) | `props.accessibilityRole` (e.g. `"button"`, `"text"`, `"image"`) when set, falling back to the component's display name (e.g. `View`, `Text`, `Pressable`). |
| `bbox.{x,y,width,height}` (required) | `onLayout` event's `nativeEvent.layout` — copy `x`, `y`, `width`, `height` as plain numbers. Store the last seen layout per node. |
| `semantic_id` (optional) | Same value as `testID` when no separate semantic id is needed. Used downstream by `compare-tree` to align actual ↔ expected. |
| `name` (optional) | `props.accessibilityLabel`. |
| `text` (optional) | `props.children` when it is a string (e.g. `<Text>{label}</Text>`), or the joined rendered text of nested `<Text>` children for leaf text nodes. Set to `null` for non-text components. |
| `children` (optional, recursive) | React children of the component — walked depth-first. Skip components with `props.accessibilityElementsHidden === true` or `props.importantForAccessibility === "no-hide-descendants"`. |
| `viewport.{width,height}` | `Dimensions.get('window')` — both `width` and `height` as numbers. |
| `screen_id` | React Navigation route name (`route.name`) or a developer-chosen identifier (e.g. `"checkout"`). |

This table is normative for the React Native stack. The full cross-stack table in [`spec.md`](../../.specs/features/038-runtime-adapter-guides/spec.md#c13--adapter-conformance-contract-mapping-table) is the source of truth for C13.

## Reference snippet (JS / TS — illustrative, not executed by Penflow)

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

function emitNode(node: Node) {
  const bbox = layouts.get(node.id) ?? { x: 0, y: 0, width: 0, height: 0 };
  return {
    id: node.id,
    role: node.role,
    bbox,
    semantic_id: node.semantic_id ?? node.id,
    name: node.name ?? null,
    text: node.text ?? null,
    children: node.children.map(emitNode),
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
        root: emitNode(root),
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

If you want an end-to-end demo that drives a real running RN app, see feature 039 (out of scope for feature 038).
