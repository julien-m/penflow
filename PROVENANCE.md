# Provenance and Publication Boundaries

## Current tree

Penflow source, documentation, JSON schemas, synthetic examples, and the bundled checkout demo image are maintained in this repository and distributed under [LICENSE](LICENSE), except for material explicitly listed in [third-party-notices.md](third-party-notices.md). Generated demo reports are fixtures, not fresh runtime or model evidence.

The Inter font files under `tests/runtime_pilot/` are third-party test assets and retain their SIL Open Font License 1.1 notice in `tests/runtime_pilot/inter-license.txt`. Python dependencies are not vendored and retain their upstream licenses.

## History cleanup before publication

Before the repository became public, its Git history was rewritten with `git filter-repo`:

- the maintainer's local LiveSpec working tree (`.specs/`), local agent tooling (`.agent-sync.local/`, `.conventions/`, `AGENTS.md`), and generated run evidence were removed from every commit;
- machine-specific absolute paths were replaced with neutral placeholders in the remaining history.

The full maintainer LiveSpec workspace stays local. Scoped review led feature records and their registry are intentionally versioned as public implementation contracts; they do not include the removed private history or consumer evidence. Code/test traceability comments remain supported.

## Adding assets or evidence

Contributors must record the source, author or producer, applicable license, and whether an artifact is synthetic, generated, or observed. Do not commit private consumer evidence, credentials, personal data, or machine-specific paths. When rights are unknown, omit the artifact and document the unresolved source rather than guessing a license.
