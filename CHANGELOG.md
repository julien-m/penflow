# Changelog

All notable public changes will be recorded here. Penflow follows semantic versioning once releases are tagged.

## [Unreleased]

### Added

- `penflow check`: read-only diagnostics from current local inputs, with explicit missing observations, independent-check continuation and bounded regular-file reads.
- Review led skill/workflow guidance with retained opt-in historical certification instructions and migration/rollback documentation.

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

- Standalone read-only validation no longer depends on unrelated Doctor project hygiene.
- Ordinary producer postflight cleanup refusals remain visible on stderr while preserving the product result/exit; unsafe deletion stays refused.

- C51 compares a documentation board state by state. The expected tree carries the contract `states` of each screen and node; an actual tree may hold one capture per declared state (`state` and `scenario_id`, witnessed by `observed_states`). A declared state without capture (`screen.state_missing`), an unknown (`screen.state_unknown`) or undeclared (`screen.state_undeclared`) state, an unwitnessed capture (`screen.state_unwitnessed`), a node of another state (`node.state_unexpected`) and two captures of one state are refused. A single stateless capture keeps the strict comparison.
- C51 matches collection instances: a contract `repeat_model` reaches the expected template node, and each runtime instance (`semantic_id::instance_id`) must match `instance_id_template` exactly (`node.instance_unexpected`), with repeated descendants in the same instance (`node.instance_mismatch`). Without `repeat_model`, instances stay strict.
- `check-consistency` compares `bbox.height` only between members whose design height is fixed. The expected export records each node's `sizing` (`fixed`, `fill`, `hug`, `unspecified`); trees without it keep the strict comparison, and malformed sizing is refused.
- The expected and actual UI tree schema accepts a native Pencil image paint as `visual.fill` (`type` `image`, non-empty `url`, optional boolean `enabled` and non-empty `mode`, no other key). Before, `export-expected` failed with `... is not of type 'string'` on a frame painted with a reference image. Color fills are unchanged; any other object, an empty string or a malformed image paint is still refused, and a different image still differs in comparison.
- C51 accepts the optional `penflow_identity` (Penflow version text, executable path and executable SHA-256) that LiveSpec writes in its review snapshot, review approval and Brainstorm authority import. Before, `--profile design` blocked `upstream-requirements` with `input.invalid_object: review-approval`. Records without the key validate as before; a present key must hold exactly these three non-empty fields.

## [0.1.0] - Unreleased

The package metadata reserves `0.1.0` for the first alpha release. No package-registry publication or signed release is claimed.
