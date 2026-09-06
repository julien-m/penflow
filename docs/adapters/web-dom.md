# Web DOM Adapter Guide (Contract C13)

This guide explains how to emit an `actual-ui-tree.json` (contract C12) from a running web app (browser DOM + ARIA + `data-testid` + `getBoundingClientRect`). It is part of **contract C13 — adapter conformance mapping** owned by feature 038.

## Runtime-agnostic boundary

Penflow ships **zero runtime code** for the Web DOM stack. Penflow does **not** launch a browser, does **not** drive Playwright / Selenium / Cypress / Puppeteer, and does **not** execute the reference snippet below. The snippet is **illustrative only** — copy it into your own test runner, your own browser context, your own CI. Penflow's responsibility starts after the JSON file lands on disk, with `penflow validate-actual <file> --schema`.

The C12 boundary validates the **shape of the JSON** your adapter must produce. That shape is defined by contract C12 ([`actual-ui-tree.schema.json`](../../penflow/schemas/actual-ui-tree.schema.json), feature 037).

## C51 certification and coordinates

C12 schema validation proves the shape of an observation. C51 additionally joins it to the independently selected build manifest, approved sources, runner/session/scenario identities and the exact evidence bytes. The runner records actual before/after facts and outcomes; it must not copy expected values or declare a successful assertion in place of observing it. **Read** [the verification workflow](../verification-workflow.md) and [the causal evidence guide](causal-transition-evidence.md) before producing certifying evidence.

For C51, express every bbox in logical units relative to the observed screen origin, including nested nodes. Preserve the original native measurements in the runner evidence, then subtract the measured screen origin; do not consult the expected tree to normalize actual geometry. Missing measurements block capture instead of becoming zero boxes. Penflow independently normalizes its authenticated Pencil layout to the same screen coordinates. Older viewport/local-coordinate exports remain historical C13 examples; do not mix their coordinate conventions in a C51 comparison.

Capture the rendered hierarchy, including additional controls without semantic annotations. Test identifiers join observations to the contract; they do not supply the observed role, text, visibility or value. Unknown or unmapped interactive elements must remain visible to validation. Hidden accessibility metadata alone does not prove an element is absent from the rendered screen. A required property unavailable through a platform adapter blocks that capability rather than being omitted.

## C13 mapping table — Web DOM

The columns follow the canonical C12 field ordering (`id` / `role` / `bbox` / `semantic_id` / `name` / `text` / `children` / `viewport` / `screen_id`). See the spec table in [`spec.md`](../../.specs/features/038-runtime-adapter-guides/spec.md#c13--adapter-conformance-contract-mapping-table) for the cross-stack view.

| C12 field (target) | Web DOM source |
|---|---|
| `id` (required, unique within tree) | `element.getAttribute('data-testid')`, or a stable path-based fallback (e.g. `nthChild`-encoded selector). MUST be unique within the tree. |
| `role` (required, free-form string) | `element.getAttribute('role')` (ARIA), falling back to lowercased `element.tagName` when no ARIA role is set. |
| `bbox.{x,y,width,height}` (required) | `element.getBoundingClientRect()` — preserve the viewport rect, then subtract the measured screen rect origin from `x` and `y` for C51; preserve width/height in CSS pixels. |
| `semantic_id` (optional) | Same as `id`, or `element.getAttribute('data-semantic-id')` when a separate semantic identifier is set. Used downstream by `compare-tree` to align actual ↔ expected. |
| `name` (optional) | `element.getAttribute('aria-label')` or `element.getAttribute('name')`. |
| `text` (optional) | `element.textContent` for leaf text nodes. Set to `null` for non-text elements. |
| `children` (optional, recursive) | DOM children walked depth-first. Exclude purely presentational wrappers (`<style>`, `<script>`) and elements with `aria-hidden="true"`. |
| `viewport.{width,height}` | `window.innerWidth` / `window.innerHeight`. |
| `screen_id` | Route path (`location.pathname`), or a developer-chosen identifier (e.g. `"checkout"`). |

This table is normative for the Web stack. The full cross-stack table in [`spec.md`](../../.specs/features/038-runtime-adapter-guides/spec.md#c13--adapter-conformance-contract-mapping-table) is the source of truth for C13.

## Reference snippet (JavaScript — illustrative, not executed by Penflow)

This minimal tree walker omits C51 provenance, styles and a complete accessibility-role mapping. A certifying adapter must also inspect rendered controls excluded from an accessibility-only walk; ARIA values and tag names require a validated mapping to the canonical observed roles.

> **Illustrative only.** This snippet is documentation, not a file Penflow imports, compiles, or runs. Adapt it to your own browser harness (Playwright `page.evaluate(...)`, Cypress task, Selenium executeScript, plain devtools console, etc.). Penflow ships no runtime probe for the Web stack.

```js
// Depth-first walk of document.body emitting an actual-ui-tree.json
// matching contract C12. Run inside the browser context.
function walk(element, screenRect) {
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
    .map((child) => walk(child, screenRect))
    .filter((n) => n !== null);
  return {
    id,
    role,
    bbox: { x: rect.x - screenRect.x, y: rect.y - screenRect.y,
            width: rect.width, height: rect.height },
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
        root: walk(document.body, document.body.getBoundingClientRect()),
      },
    ],
  };
}

// Serialize with two-space indentation and a trailing newline.
const json = JSON.stringify(emitActualTree("checkout"), null, 2) + "\n";
// A production runner may sort object keys before this serialization.
```

Notes:
- `JSON.stringify` does not sort keys by default. Use a stable serializer (e.g. `json-stable-stringify`) or hand-sort before writing.
- Persist the result as UTF-8 with two-space indentation and a trailing newline. This example does not sort object keys or guarantee identical bytes across changing runtime observations; canonical key sorting belongs to the production runner when required.

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

The feature 039 demo is a static fixture, not an application run. **Read** [the bounded runtime pilot](../../tests/runtime_pilot/README.md) for the separately executed HTTP/SQLite/browser test application; it is not a general-purpose runtime adapter.
