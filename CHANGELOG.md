# Changelog

All notable public changes will be recorded here. Penflow follows semantic versioning once releases are tagged.

## [Unreleased]

### Added

- Public MIT licensing, contribution, security, provenance, release, and third-party notices.
- Reproducible source installation and wheel/source-distribution build documentation.
- Dependabot configuration for `uv` and GitHub Actions dependencies.
- C51 reviewed requirement delegation: optional `requirements.delegations` in the contract, `projection.delegated` and report `delegated_requirements` (always `certified: false`), with the diagnostics `requirements.delegation.invalid` and `product.delegation.forbidden`. Artifacts without delegations keep their exact bytes.

### Changed

- GitHub Actions references are pinned to commit SHAs, and CI builds both distribution formats.
- Local LiveSpec specs, agent tooling, and generated evidence are no longer tracked and were removed from Git history before publication.
- Test helpers read machine-specific runtime paths from environment variables instead of hard-coded absolute paths.
- Feature 045 accepts mutation-free local form submits while preserving strict request duties for mutation-bearing submits.

### Fixed

- C51 accepts the optional `penflow_identity` (Penflow version text, executable path and executable SHA-256) that LiveSpec writes in its review snapshot, review approval and Brainstorm authority import. Before, `--profile design` blocked `upstream-requirements` with `input.invalid_object: review-approval`. Records without the key validate as before; a present key must hold exactly these three non-empty fields.

## [0.1.0] - Unreleased

The package metadata reserves `0.1.0` for the first alpha release. No package-registry publication or signed release is claimed.
