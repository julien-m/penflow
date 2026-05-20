# Web DOM Adapter Guide (Contract C13)

This guide explains how to emit an `actual-ui-tree.json` (contract C12) from a running web app (browser DOM + ARIA + `data-testid` + `getBoundingClientRect`). It is part of **contract C13 — adapter conformance mapping** owned by feature 038.

## Runtime-agnostic boundary

Penflow ships **zero runtime code** for the Web DOM stack. Penflow does **not** launch a browser, does **not** drive Playwright / Selenium / Cypress / Puppeteer, and does **not** execute the reference snippet below. The snippet is **illustrative only** — copy it into your own test runner, your own browser context, your own CI. Penflow's responsibility starts after the JSON file lands on disk, with `penflow validate-actual <file> --schema`.

The only thing Penflow guarantees for the Web stack is the **shape of the JSON** your adapter must produce. That shape is defined by contract C12 ([`actual-ui-tree.schema.json`](../../penflow/schemas/actual-ui-tree.schema.json), feature 037).

## C13 mapping table — Web DOM

The columns follow the canonical C12 field ordering (`id` / `role` / `bbox` / `semantic_id` / `name` / `text` / `children` / `viewport` / `screen_id`). See the spec table in [`spec.md`](../../.specs/features/038-runtime-adapter-guides/spec.md#c13--adapter-conformance-contract-mapping-table) for the cross-stack view.

| C12 field (target) | Web DOM source |
|---|---|
| `id` (required, unique within tree) | `element.getAttribute('data-testid')`, or a stable path-based fallback (e.g. `nthChild`-encoded selector). MUST be unique within the tree. |
| `role` (required, free-form string) | `element.getAttribute('role')` (ARIA), falling back to lowercased `element.tagName` when no ARIA role is set. |
| `bbox.{x,y,width,height}` (required) | `element.getBoundingClientRect()` — copy `x`, `y`, `width`, `height` as plain numbers. |
| `semantic_id` (optional) | Same as `id`, or `element.getAttribute('data-semantic-id')` when a separate semantic identifier is set. Used downstream by `compare-tree` to align actual ↔ expected. |
| `name` (optional) | `element.getAttribute('aria-label')` or `element.getAttribute('name')`. |
| `text` (optional) | `element.textContent` for leaf text nodes. Set to `null` for non-text elements. |
| `children` (optional, recursive) | DOM children walked depth-first. Exclude purely presentational wrappers (`<style>`, `<script>`) and elements with `aria-hidden="true"`. |
| `viewport.{width,height}` | `window.innerWidth` / `window.innerHeight`. |
| `screen_id` | Route path (`location.pathname`), or a developer-chosen identifier (e.g. `"checkout"`). |

This table is normative for the Web stack. The full cross-stack table in [`spec.md`](../../.specs/features/038-runtime-adapter-guides/spec.md#c13--adapter-conformance-contract-mapping-table) is the source of truth for C13.

## Reference snippet (JavaScript — illustrative, not executed by Penflow)

> **Illustrative only.** This snippet is documentation, not a file Penflow imports, compiles, or runs. Adapt it to your own browser harness (Playwright `page.evaluate(...)`, Cypress task, Selenium executeScript, plain devtools console, etc.). Penflow ships no runtime probe for the Web stack.

```js
// Depth-first walk of document.body emitting an actual-ui-tree.json
// matching contract C12. Run inside the browser context.
function walk(element) {
  if (!element || element.getAttribute("aria-hidden") === "true") return null;
  const rect = element.getBoundingClientRect();
  const tag = element.tagName.toLowerCase();
  const role = element.getAttribute("role") || tag;
  const id =
    element.getAttribute("data-testid") ||
    pathBasedFallback(element); // e.g. "form>div:nth-child(2)>button"
  const semanticId =
    element.getAttribute("data-semantic-id") || id;
  const childNodes = Array.from(element.children)
    .map(walk)
    .filter((n) => n !== null);
  return {
    id,
    role,
    bbox: { x: rect.x, y: rect.y, width: rect.width, height: rect.height },
    semantic_id: semanticId,
    name: element.getAttribute("aria-label") || element.getAttribute("name") || null,
    text: childNodes.length === 0 ? (element.textContent || null) : null,
    children: childNodes,
  };
}

function emitActualTree(screenId) {
  return {
    version: 1,
    screens: [
      {
        screen_id: screenId,
        viewport: { width: window.innerWidth, height: window.innerHeight },
        root: walk(document.body),
      },
    ],
  };
}

// Persist with sorted keys + 2-space indent + trailing newline so the file is
// byte-deterministic (matches the Penflow CLI determinism guarantee).
const json = JSON.stringify(emitActualTree("checkout"), Object.keys, 2) + "\n";
// `Object.keys` is shown as a placeholder for a stable sort callback — pick
// the one your runner provides. See examples/adapters/web-dom/actual-ui-tree.json
// for the canonical on-disk shape.
```

Notes:
- `JSON.stringify` does not sort keys by default. Use a stable serializer (e.g. `json-stable-stringify`) or hand-sort before writing.
- Persist the result with UTF-8 + sorted keys + two-space indent + trailing newline so two consecutive runs produce byte-identical files. The Penflow CLI applies the same rule (feature 037).

## Example fixture

A worked example of the JSON shape produced by this guide lives at:

[`../../examples/adapters/web-dom/actual-ui-tree.json`](../../examples/adapters/web-dom/actual-ui-tree.json)

Validate it locally with:

```bash
penflow validate-actual examples/adapters/web-dom/actual-ui-tree.json --schema --json
```

Expected output: exit 0, `"status": "PASS"`, `"issues": []`.

## Contract references

- **C12** — [`actual-ui-tree.schema.json`](../../penflow/schemas/actual-ui-tree.schema.json) (feature 037). Defines the JSON shape your adapter must produce.
- **C13** — adapter conformance mapping (feature 038, this guide).
- **Three Trees** — see the [project README](../../README.md#three-trees) for the role of `actual-ui-tree.json` in the broader Penflow flow.
- **Spec** — [`spec.md`](../../.specs/features/038-runtime-adapter-guides/spec.md) and [`plan.md`](../../.specs/features/038-runtime-adapter-guides/plan.md) own the normative boundary for feature 038.

## What this guide does NOT do

- Does not ship a runnable adapter package on npm.
- Does not start a browser from Penflow.
- Does not add `playwright`, `selenium`, or any browser driver to `pyproject.toml`.
- Does not turn snippet bugs into Penflow regressions — the snippet is documentation.

If you want an end-to-end demo that drives a real running web app, see feature 039 (out of scope for feature 038).
