# Theme Token Contract

This contract is the stable input surface for generators that write `theme.css` before running Penflow token gates.

## Accepted CSS Names

`penflow.theme.load_theme()` accepts both canonical `--name` and prefixed `--pf-name` custom properties, then exports every known token as a `$pf-*` pen variable. **Read** [`../penflow/theme.py`](../penflow/theme.py) for the executable map.

Core color tokens: `background`, `foreground`, `card`, `card-foreground`, `primary`, `primary-foreground`, `border`, `input`, `muted`, `muted-foreground`, `accent`, `destructive`, `ring`.

Extended color tokens: `panel`, `panel-2`, `success`, `warning`, `info`.

Typography tokens: `font-sans`, `font-mono`, `font-size-xs`, `font-size-sm`, `font-size-base`, `font-size-lg`, `font-size-xl`.

Radius token: `radius`.

Project-specific color slots: any `palette-*` or `pf-palette-*` custom property with a parseable color value. These become `$pf-palette-*` variables and are included in `lint-tokens` palette checks, but do not alter the stable `style` object.

Project-specific radius slots: any `radius-*` or `pf-radius-*` numeric custom property. These become `$pf-radius-*` variables and extend the effective `lint-tokens` radius scale, but do not alter the base `radius` style field.

## Lint Behavior

`penflow lint-tokens <ui.pen> --theme-css theme.css --out token-lint-report.json --json` loads the theme and checks:

- Colors: every `fill`/`stroke.fill` must resolve to a color declared by known theme tokens or `palette-*` slots.
- Fonts: `fontFamily` must match exactly one declared theme font. Declaring `font-sans` and `font-mono` allows only those two families; random families still fail.
- Font sizes: the effective scale is the documented default plus declared `font-size-*` values unless `--fontsize-scale` is passed.
- Radius: the effective scale is the documented default plus `radius` and declared `radius-*` values unless `--radius-scale` is passed.
- Spacing: the effective scale remains the documented default unless `--spacing-scale` is passed.

The strict report schema is unchanged. **Read** [`../penflow/schemas/token-lint-report.schema.json`](../penflow/schemas/token-lint-report.schema.json) for the output shape.

## Report Inputs

The report `inputs` block records:

- `pen`: linted `.pen` path.
- `theme_css`: theme CSS path, or `null`.
- `spacing_scale`: effective spacing values.
- `radius_scale`: effective radius values after theme extension or CLI override.
- `fontsize_scale`: effective type-scale values after theme extension or CLI override.

Generators should write a complete `theme.css`, then gate the generated `.pen` with `lint-tokens`; a PASS report is the portable handoff proof for downstream orchestration.
