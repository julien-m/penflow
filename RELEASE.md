# Release Process

`main` is the protected integration branch. A new stable package version becomes available to managed consumers after the exact commit passes the main push CI and Security checks. The [consumer release workflow](.github/workflows/publish-consumer-release.yml) builds and publishes the approved payload as a GitHub release.

1. Match the semantic version in `pyproject.toml`, `penflow.__version__`, the dependency lock and changelog. Plan a new version whenever consumers should adopt a change.
2. Run the checks from [CONTRIBUTING.md](CONTRIBUTING.md), review [PROVENANCE.md](PROVENANCE.md) and [third-party-notices.md](third-party-notices.md), then merge through the protected branch.
3. Inspect the `Publish consumer release` workflow for that exact main commit. The read-only build job exports locked requirements and smoke-tests the installed wheel. The publisher verifies the draft assets before making the release visible.
4. Verify the release tag, commit and digests. Use [the consumer runtime guide](docs/consumer-runtime.md) to verify acquisition and installed CLI identity.

A subsequent main commit with an already published version preserves the original tag and release assets. If publishing fails, rerun the failed workflow for the original qualified commit. A partial draft can resume when its recorded source and existing assets agree. Registry publication outside GitHub requires separate authorization. Keep release credentials outside source and logs.
