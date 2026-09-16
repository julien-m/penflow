# Provenance and Publication Boundaries

## Current tree

Penflow source, documentation, JSON schemas, synthetic examples, and the bundled checkout demo image are maintained in this repository and distributed under [LICENSE](LICENSE), except for material explicitly listed in [third-party-notices.md](third-party-notices.md). Generated demo reports are fixtures, not fresh runtime or model evidence.

The Inter font files under `tests/runtime_pilot/` are third-party test assets and retain their SIL Open Font License 1.1 notice in `tests/runtime_pilot/inter-license.txt`. Python dependencies are not vendored and retain their upstream licenses.

LiveSpec `run/` directories contain generated operator receipts. They are ignored and removed from the current Git index so local evidence is preserved without publishing new archives. This does not delete local evidence and does not remove bytes already present in Git history.

Some tracked LiveSpec `checks/` artifacts remain because feature documents use them as historical traceability. A bounded current-tree pattern audit found no common private-key, GitHub-token, or AWS access-key forms, but it did find machine-specific absolute paths. Gitleaks was not installed for this local cleanup, so only the SHA-pinned CI action can perform that repository scan. Review and curate these retained artifacts before any visibility change; do not treat the bounded pattern audit as privacy clearance.

## Historical limitations

The repository history contains generated run receipts, machine-specific absolute paths, and references to Fable-derived review material. The current tree does not claim redistribution rights for historical third-party material, and this cleanup does not rewrite history. Existing clones, forks, caches, and historical commits may still expose those bytes.

Removing or sanitizing historical objects requires a separately authorized history-rewrite or clean-history publication decision, coordinated with collaborators and hosting caches. Until that happens, a public release must describe history as not provenance-cleared. A successful current-tree scan or CI Gitleaks job must not be represented as full-history clearance.

## Adding assets or evidence

Contributors must record the source, author or producer, applicable license, and whether an artifact is synthetic, generated, or observed. Do not commit private consumer evidence, credentials, personal data, or machine-specific paths. When rights are unknown, omit the artifact and document the unresolved source rather than guessing a license.
