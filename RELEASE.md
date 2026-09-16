# Release Process

`main` is the integration branch. A release is complete only after an authorized maintainer performs every step below; this document does not claim that `0.1.0` has been published.

1. Confirm the version matches in `pyproject.toml`, `penflow.__version__`, the changelog, and the intended `v<version>` tag.
2. Run the checks from [CONTRIBUTING.md](CONTRIBUTING.md) on a clean checkout.
3. Build with `uv build`; inspect the wheel and source archive for `LICENSE`, schemas, and `penflow/demo-assets/checkout-screen.png`.
4. Install the wheel into a fresh Python 3.12 environment outside the checkout and run `penflow --help` plus a disposable `penflow demo` smoke test.
5. Review [PROVENANCE.md](PROVENANCE.md) and [third-party-notices.md](third-party-notices.md). Stop if source rights, generated evidence, secrets, or private paths are unresolved.
6. Commit the changelog date, create an annotated `v<version>` tag, and push the commit and tag without rewriting history.
7. Publish only through an explicitly authorized registry/release workflow, then verify the public artifact digest and installation path.

Release credentials must remain outside the repository and logs. A local `uv build` proves buildability only; it does not prove registry publication, signature, provenance clearance, or runtime certification.
