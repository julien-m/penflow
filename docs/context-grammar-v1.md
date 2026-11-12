<!-- LiveSpec traceability anchors -->
<!-- @spec(FR-006) -->

# Context Grammar V1

`context` can be a JSON object or `key=value; key=value` shorthand.

Allowed keys:
- `classification`: exactly one of `semantic`, `inherited`, or `decorative`.
- `semantic_id`: stable dotted/kebab/snake identifier.
- `role`: semantic role such as `screen`, `text`, `button`, `list`, `icon`.
- `intent`: user action for interactive elements.
- `binding`: `entity.field` data binding.
- `repeat`: collection binding for lists.
- `entity`: domain entity name.
- `variant`: stable variant or `dynamic`/`volatile` mask hint.
- `test_id`: optional external test handle.
- `inherits_from`: semantic owner for an `inherited` node.
- `instance_key`: stable repeat-instance discriminator for inherited content.
- `relation`: semantic relation such as `label` or `content`.
- `decorative_owner`: semantic owner for a `decorative` node.
- `decorative_reason`: non-empty explanation for excluding a decorative node.
- `mask`: skip a volatile node during structural comparison.
- `mask_text`: ignore text drift while still comparing role, hierarchy, bbox, and visual properties.
- `tolerance`: object with comparison tolerances such as `bbox_px`, `radius_px`, `font_px`, `spacing_px`, `order`.

Forbidden: runtime/platform terms such as SwiftUI, React, Xcode, Playwright, Android, Dioxus, or CSS in context values.

## Classification rules

<!-- @spec(FR-001) -->

- `semantic` requires `semantic_id`, `test_id`, and `role`; it forbids inheritance and decorative fields.
- `inherited` requires `inherits_from` and `relation`; it forbids semantic and decorative fields.
- `decorative` requires `decorative_owner` and `decorative_reason`; it forbids semantic and inheritance fields.
- The owner of an `inherited` or `decorative` node is an anchored ancestor, with one exception: `relation=label-for`.
  - A `label-for` text node names a sibling semantic form control (role `input`, `select`, `toggle`, `checkbox` or `radio`), as an HTML `<label for>` names its control.
  - Its content is the control's authored copy when the control has none of its own.
  - The expected tree gives the control that text as `label`, and the comparison requires the runtime to associate the same label (`label` in the actual node, from `<label for>`/`id` or `aria-labelledby`).
  - The label must have text. A control has at most one `label-for` sibling. Any other target is refused (`pencil.label_target_not_control`, `pencil.label_without_copy`, `pencil.label_duplicate`).
- Stable identifiers are exact, case-sensitive, Unicode NFC join keys. Visible text, geometry, styling,
  colors, names, and similarity never imply a classification.

Consumers that opt into strict semantic coverage must classify every id-bearing authored Pencil
node. Omitting `classification` remains accepted only for legacy forward-only context handling.
