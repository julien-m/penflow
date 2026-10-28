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

## Historical Mistune table reader

Read [the compatibility reader](penflow/requirement_legacy_tables.py). Its table grammar and parsing routines are adapted from Mistune3.2.0 to authenticate existing source projections without rewriting approval archives. New source parsing continues to use the declared runtime dependency.

Copyright (c) 2014, Hsiaoming Yang

All rights reserved.

Redistribution and use in source and binary forms, with or without modification, are permitted provided that the following conditions are met:

* Redistributions of source code must retain the above copyright notice, this list of conditions and the following disclaimer.

* Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following disclaimer in the documentation and/or other materials provided with the distribution.

* Neither the name of the creator nor the names of its contributors may be used to endorse or promote products derived from this software without specific prior written permission.


THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
