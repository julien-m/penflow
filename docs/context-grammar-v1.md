# Context Grammar V1

`context` can be a JSON object or `key=value; key=value` shorthand.

Allowed keys:
- `semantic_id`: stable dotted/kebab/snake identifier.
- `role`: semantic role such as `screen`, `text`, `button`, `list`, `icon`.
- `intent`: user action for interactive elements.
- `binding`: `entity.field` data binding.
- `repeat`: collection binding for lists.
- `entity`: domain entity name.
- `variant`: stable variant or `dynamic`/`volatile` mask hint.
- `test_id`: optional external test handle.
- `tolerance`: object with comparison tolerances such as `bbox_px`, `radius_px`, `font_px`, `order`.

Forbidden: runtime/platform terms such as SwiftUI, React, Xcode, Playwright, Android, Dioxus, or CSS in context values.

