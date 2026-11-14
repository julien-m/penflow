# Rendered Web adapter

Use the external [DOM adapter](../../examples/adapters/web-rendered/dom-capture.mjs) to observe a browser or WebView. Penflow core consumes its JSON; it does not launch a browser or depend on Playwright.

- Annotate one visible screen root with `data-penflow-screen="logical-screen-id"` and `data-semantic="semantic-id"`. Annotate the semantic descendants with `data-semantic`. Nested layout containers keep their semantic hierarchy; visible interactive controls without an annotation reject capture. Hidden nodes remain absent and can therefore produce comparison findings.
- Native `h1`–`h6` and ARIA headings retain the canonical `heading` role; native `nav` and ARIA navigation regions retain `navigation`. This preserves landing-page hierarchy/profile rules instead of downgrading headings to plain text.
- Add `data-design-screen-id="pencil-frame-id"` when selecting one explicit design revision or breakpoint. Otherwise the logical screen identity must select exactly one design. Optional `data-penflow-variant` must correspond to an explicitly declared design variant; viewport dimensions never silently pick a design.
- Execute `captureRenderedDocument()` inside the real target after fonts and images settle. The adapter reads `getBoundingClientRect()` border boxes, computed font/spacing/layout styles and image natural dimensions. It never accepts an expected tree or declared CSS as a substitute for an observation.
- Measurements use CSS pixels and screen-relative coordinates, subtracting the root's viewport origin. The tree records the layout viewport, device pixel ratio and visual viewport scale separately. `line-height: normal` remains unavailable as a numeric metric. Image `object-fit: contain`/`cover` preserves the intrinsic ratio while allowing letterboxing/cropping; `fill` can stretch it.
- Block, inline, inline-block and flow-root layout report `visual.layout: "none"`; Flexbox reports its horizontal/vertical axis. Grid and table layout remain unrepresented instead of claiming equivalence with `none`.
- Metadata describes the capture method. It does not authenticate execution, prove font glyph selection, establish freshness/build identity, or prove interactions. Stateful callers must attach their actual scenario and `observed_states` evidence after exercising the real transition; adding a state label is insufficient.

Read the browser contracts for [DOMRect border boxes and viewport coordinates](https://developer.mozilla.org/en-US/docs/Web/API/Element/getBoundingClientRect), [computed styles](https://developer.mozilla.org/en-US/docs/Web/API/Window/getComputedStyle), [visual viewport zoom](https://developer.mozilla.org/en-US/docs/Web/API/VisualViewport/scale), and [device pixel ratio](https://developer.mozilla.org/en-US/docs/Web/API/Window/devicePixelRatio).

## External runner

Install Playwright and its browser in the caller's runner environment, or select an existing Chromium-compatible executable. No runner dependency is installed by this example. Run from the consumer's Node environment:

```bash
node /path/to/penflow/examples/adapters/web-rendered/capture.mjs \
  https://your-local-app.example/screen /path/to/workspace/actual-ui-tree.json \
  1440 900 playwright /path/to/chromium
penflow check --target /path/to/workspace --project /path/to/project --json
```

The last two arguments are optional: the module defaults to `playwright` resolved from the caller's working directory; omitting the executable uses that Playwright installation's managed browser. The runner creates an isolated headless context, waits for font/image readiness, captures, and closes its browser in `finally`. It does not use the user's browsing profile. A browser failure or timeout leaves the observation unverified.

## Live bad-to-corrected example

Run the independent authored [Pencil fixture](../../examples/adapters/web-rendered/ui.pen) and [HTML fixture](../../examples/adapters/web-rendered/index.html) through a real browser:

```bash
python examples/adapters/web-rendered/run_demo.py --out /tmp/penflow-rendered-demo \
  --playwright /path/to/playwright/index.mjs --browser /path/to/chromium
```

The canonical fixture follows the [native Pencil format](https://docs.pen.dev/for-developers/the-pen-format): the button is a layout frame with a child text label. Typography belongs to that text node; its native line height is a font-size multiplier, resolved to logical pixels before comparison. The HTML uses the corresponding semantic span, so the oversized font is detected on the actual label rather than invented frame typography.

The example uses a file URL and starts no server. It captures the deliberately oversized control, then captures the corrected control from the same HTML with the fault injection disabled. Both actual trees come only from DOM observations. Each capture workspace receives the authored Pencil source and profile selection, then runs ordinary `check_workspace` with no optional comparison flag. It writes each workspace's `actual-ui-tree.json` and `check-report.json`, plus a compact `demo-result.json` to the selected output directory. Keep or delete those generated outputs according to the caller's working-data policy.

Observed in Chrome 157.0.8103.78 at a 640 × 400 CSS-pixel viewport: the oversized button measured 120 × 121.125, font size 20 and vertical padding 32; the corrected button measured 120 × 40, font size 14 and vertical padding 8. The default check's rendered comparison detected height, label font size, label line height and padding differences, then found no material findings after correction. Its aggregate remains `NOT_OBSERVED` because this fixture does not supply independently rendered Pencil auto-layout positions or the content-sized label's native bounds; those gaps do not become a false `CONFORMING` claim. Numeric `.pen` button dimensions and independent runtime measurements prove the size/style correction within that stated scope.
