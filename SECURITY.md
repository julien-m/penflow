# Security Policy

## Supported versions

Security fixes target the latest commit on `main` until versioned releases are published. The `0.1.0` package metadata currently describes an alpha source distribution, not a support promise for a published registry artifact.

## Report a vulnerability

Use GitHub's private vulnerability reporting or open a private draft security advisory for this repository. Do not include credentials, personal data, exploit details, or unredacted evidence in a public issue.

Include the affected revision, impact, minimal reproduction, and any suggested mitigation. Maintainers will coordinate disclosure after validating the report; no response or remediation deadline is guaranteed.

For ordinary bugs without security impact, use the public issue tracker after removing secrets and private paths.

## Security boundaries

Penflow validates local contract and evidence files. It does not run browsers, simulators, application runtimes, or pen.dev. Treat every imported JSON, Markdown, `.pen`, report, and path as untrusted input.

CI runs a SHA-pinned Gitleaks action on every push and pull request. Publication boundaries and the history cleanup performed before the repository became public are documented in [PROVENANCE.md](PROVENANCE.md).
