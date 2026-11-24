# Managed consumer runtime

The consumer release workflow publishes a new Penflow version from the exact commit that passed CI and Security on protected `main`. The release carries the universal wheel, dependencies exported with hashes from the checkout's lock, and a small manifest with the version, commit and asset SHA-256. Each version is published once.

## Resolve the interpreter at runner startup

Run the bootstrap from a trusted checkout of Penflow with the consumer's pinned LiveSpec Python. Run on macOS or Linux with `uv` on PATH.

```bash
"$PENFLOW_PYTHON" -I "$PENFLOW_SOURCE/tools/sync-consumer-penflow.py" \
  --lock .specs/livespec.lock
```

Read `python` from the JSON receipt and pass that path to the runner and to every Penflow operation of the replay. Save the receipt in the run record. It includes `status` (`installed` or `current`), the release version and tag, the source commit, the wheel and requirements digests, and the LiveSpec pin/base identity.

The bootstrap verifies the tag revision against main history and checks the bytes against the release registry before installation. It derives an independent virtual environment from the base Python and checks which wheel and module that interpreter actually uses. The LiveSpec runtime's site-packages are outside this operation. Repeating startup queries the release and reuses a matching checked environment without installing packages again.

Use `--tag vMAJOR.MINOR.PATCH` to replay against an exact published version. Set `--cache` to choose the local cache directory. By default it is `~/.cache/penflow/consumer-runtime`. Each published version keeps its own environment so an ongoing run or historical replay can continue to use its selected Python.

If startup reports a GitHub, digest, pin or package error, stop before opening the capture run. Existing valid environments and historical evidence stay available for an explicit replay with their published tag and verified cache.
