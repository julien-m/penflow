# Changelog

All notable public changes will be recorded here. Penflow follows semantic versioning once releases are tagged.

## [Unreleased]

### Added

- Public MIT licensing, contribution, security, provenance, release, and third-party notices.
- Reproducible source installation and wheel/source-distribution build documentation.
- Dependabot configuration for `uv` and GitHub Actions dependencies.

### Changed

- GitHub Actions references are pinned to commit SHAs, and CI builds both distribution formats.
- Local LiveSpec specs, agent tooling, and generated evidence are no longer tracked and were removed from Git history before publication.
- Test helpers read machine-specific runtime paths from environment variables instead of hard-coded absolute paths.
- Feature 045 accepts mutation-free local form submits while preserving strict request duties for mutation-bearing submits.

## [0.1.0] - Unreleased

The package metadata reserves `0.1.0` for the first alpha release. No package-registry publication or signed release is claimed.
