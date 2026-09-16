# Third-Party Notices

## Vendored assets

### Inter font

Files:

- `tests/runtime_pilot/inter-regular.woff2`
- `tests/runtime_pilot/inter-semibold.woff2`

Copyright (c) 2016 The Inter Project Authors. Licensed under the SIL Open Font License, Version 1.1. **Read** [the bundled license text](tests/runtime_pilot/inter-license.txt) before redistributing or modifying the fonts.

## Runtime dependencies

Penflow declares PyYAML, jsonschema, referencing, and Mistune in `pyproject.toml`. They are resolved by the installer and are not copied into this repository. Their upstream copyright and license terms apply independently; consult the exact installed distribution metadata for the resolved versions.

Build and development tools such as Hatchling, pytest, Ruff, mypy, and uv are likewise external tools rather than vendored project code.

## Project fixtures

`penflow/demo-assets/checkout-screen.png` and the generated demo contracts/reports are package-owned synthetic fixtures. They are explicitly non-certifying and must not be described as fresh pen.dev, browser, runtime, or model output.
