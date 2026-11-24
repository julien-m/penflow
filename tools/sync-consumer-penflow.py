"""Select a checked Penflow release for a separate LiveSpec consumer interpreter."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

API = "https://api.github.com/repos/julien-m/penflow"
DOWNLOADS = "https://github.com/julien-m/penflow/releases/download"
MANIFEST = "penflow-release.json"
REQUIREMENTS = "penflow-runtime-requirements.txt"
# A release index, locked dependency list and pure Python wheel are small.
MAX_DOWNLOAD = 32 * 1024 * 1024
HTTP_TIMEOUT = 25
COMMAND_TIMEOUT = 180
TAG = re.compile(r"v(?:0|[1-9][0-9]*)(?:\.(?:0|[1-9][0-9]*)){2}")
COMMIT = re.compile(r"[a-f0-9]{40}")
DIGEST = re.compile(r"[a-f0-9]{64}")


class SyncError(RuntimeError):
    """The selected release or interpreter cannot be verified."""


@dataclass(frozen=True)
class Asset:
    """One verified registry asset and its expected byte identity."""

    name: str
    sha256: str
    url: str
    size: int

    def read(self, fetch: Callable[[str], bytes]) -> bytes:
        """Read and verify this exact asset before interpreting or installing it."""
        data = fetch(self.url)
        if len(data) != self.size or _digest(data) != self.sha256:
            raise SyncError(f"Release asset failed size or SHA-256 verification: {self.name}")
        return data


@dataclass(frozen=True)
class Release:
    """Published stable release bound to a main commit and two exact payloads."""

    tag: str
    commit: str
    wheel: Asset
    requirements: Asset

    @property
    def receipt(self) -> dict[str, str]:
        """Return the stable release identity recorded by the runtime and the runner."""
        return {
            "version": self.tag[1:],
            "tag": self.tag,
            "commit": self.commit,
            "wheel_sha256": self.wheel.sha256,
            "requirements_sha256": self.requirements.sha256,
        }


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _get(url: str) -> bytes:
    """Fetch public GitHub content with a fixed size limit, timeout and no credentials."""
    request = Request(url, headers={"User-Agent": "penflow-release-sync/1"})
    try:
        with urlopen(request, timeout=HTTP_TIMEOUT) as response:
            data = response.read(MAX_DOWNLOAD + 1)
    except (URLError, TimeoutError) as error:
        code = getattr(error, "code", None)
        reason = f"HTTP {code}" if isinstance(code, int) else type(error).__name__
        raise SyncError(f"GitHub release request failed ({reason})") from error
    if len(data) > MAX_DOWNLOAD:
        raise SyncError("GitHub release response exceeds the supported size")
    return data


def _unique_items(pairs: list[tuple[str, object]]) -> dict[str, object]:
    values: dict[str, object] = {}
    for key, value in pairs:
        if key in values:
            raise SyncError("Release or runtime JSON contains a duplicate field")
        values[key] = value
    return values


def _object(raw: bytes) -> dict[str, object]:
    value = json.loads(raw, object_pairs_hook=_unique_items)
    if not isinstance(value, dict):
        raise SyncError("Expected a release or runtime JSON object")
    return value


def _match(value: object, pattern: re.Pattern[str], error: str) -> str:
    if not isinstance(value, str) or len(value) > 70 or not pattern.fullmatch(value):
        raise SyncError(error)
    return value


def _asset(registry_assets: object, tag: str, name: str) -> Asset:
    if not isinstance(registry_assets, list):
        raise SyncError("GitHub release has no asset list")
    entries = [
        asset for asset in registry_assets if isinstance(asset, dict) and asset.get("name") == name
    ]
    if len(entries) != 1:
        raise SyncError(f"GitHub release must have one {name} asset")
    raw = entries[0]
    digest = raw.get("digest")
    if not isinstance(digest, str) or not digest.startswith("sha256:"):
        raise SyncError("GitHub asset has no SHA-256 digest")
    sha = _match(digest.removeprefix("sha256:"), DIGEST, "Invalid GitHub asset digest")
    size = raw.get("size")
    url = f"{DOWNLOADS}/{tag}/{name}"
    if (
        type(size) is not int
        or not 0 < size <= MAX_DOWNLOAD
        or raw.get("browser_download_url") != url
    ):
        raise SyncError(f"Invalid GitHub asset metadata: {name}")
    return Asset(name, sha, url, size)


def _load_release(fetch: Callable[[str], bytes], tag: str | None) -> Release:
    endpoint = "latest"
    if tag is not None:
        endpoint = f"tags/{_match(tag, TAG, 'Expected a stable vMAJOR.MINOR.PATCH tag')}"
    release = _object(fetch(f"{API}/releases/{endpoint}"))
    actual_tag = _match(release.get("tag_name"), TAG, "GitHub returned an invalid release tag")
    if (
        release.get("draft") is not False
        or release.get("prerelease") is not False
        or (tag is not None and tag != actual_tag)
    ):
        raise SyncError("Expected the selected published stable release")
    assets = release.get("assets")
    manifest = _object(_asset(assets, actual_tag, MANIFEST).read(fetch))
    wheel = _asset(assets, actual_tag, f"penflow-{actual_tag[1:]}-py3-none-any.whl")
    requirements = _asset(assets, actual_tag, REQUIREMENTS)
    commit = _match(manifest.get("commit"), COMMIT, "Release manifest contains an invalid commit")
    expected = {
        "schema": 1,
        "version": actual_tag[1:],
        "commit": commit,
        "wheel": {"name": wheel.name, "sha256": wheel.sha256},
        "requirements": {"name": requirements.name, "sha256": requirements.sha256},
    }
    if type(manifest.get("schema")) is not int or manifest != expected:
        raise SyncError("Release manifest disagrees with published asset metadata")
    # Independently resolve the tag and prove the checked revision belongs to main.
    tagged = _object(fetch(f"{API}/commits/{actual_tag}"))
    comparison = _object(fetch(f"{API}/compare/{commit}...main"))
    merge_base = comparison.get("merge_base_commit")
    if (
        tagged.get("sha") != commit
        or comparison.get("status") not in ("ahead", "identical")
        or not isinstance(merge_base, dict)
        or merge_base.get("sha") != commit
    ):
        raise SyncError("Release provenance does not match its Git tag and main history")
    return Release(actual_tag, commit, wheel, requirements)


def _run(args: list[str | Path], label: str) -> str:
    # stdout is reserved for Python/receipt JSON. Keep uv failures bounded and omit raw output.
    result = subprocess.run(
        args, capture_output=True, text=True, timeout=COMMAND_TIMEOUT, check=False
    )
    if result.returncode:
        raise SyncError(f"{label} failed (exit {result.returncode})")
    return result.stdout


def _base_identity(lock_path: Path, python: Path) -> dict[str, str]:
    lock_bytes = lock_path.read_bytes()
    pin = _object(lock_bytes)
    commit = _match(pin.get("commit"), COMMIT, "LiveSpec lock contains an invalid commit")
    version = pin.get("livespec_version")
    runtime_id = pin.get("runtime_id")
    if (
        pin.get("mode") != "pinned"
        or type(pin.get("schema")) is not int
        or pin["schema"] != 1
        or type(version) is not int
        or version < 1
        or runtime_id != f"{version}-{commit[:12]}"
        or commit[:8] not in python.parent.parent.name
        or not (python.parent.parent / "pyvenv.cfg").is_file()
    ):
        raise SyncError("The base Python must belong to the locked LiveSpec runtime")
    snippet = (
        "import json, sys; from pathlib import Path; "
        "print(json.dumps({'prefix': str(Path(sys.prefix).resolve()), "
        "'binary': str(Path(sys._base_executable).resolve()), "
        "'python_version': '.'.join(map(str, sys.version_info[:3]))}))"
    )
    observed = _object(_run([python, "-I", "-c", snippet], "Base Python verification").encode())
    expected_prefix = python.parent.parent.resolve()
    binary, python_version = observed.get("binary"), observed.get("python_version")
    if (
        observed.get("prefix") != str(expected_prefix)
        or not isinstance(binary, str)
        or not isinstance(python_version, str)
    ):
        raise SyncError("The base Python does not execute inside its pinned environment")
    return {
        "livespec_runtime": str(runtime_id),
        "livespec_lock_sha256": _digest(lock_bytes),
        "base_python": str(python),
        "base_prefix": str(expected_prefix),
        "base_binary": binary,
        "python_version": python_version,
    }


_PROBE = """
import importlib.metadata
import json
import sys
from pathlib import Path
import penflow

dist = importlib.metadata.distribution("penflow")
origin = json.loads(dist.read_text("direct_url.json") or "{}")
prefix = Path(sys.prefix).resolve()
assert Path(penflow.__file__).resolve().is_relative_to(prefix)
assert Path(dist.locate_file("")).resolve().is_relative_to(prefix)
print(json.dumps({
    "version": dist.version,
    "module_version": penflow.__version__,
    "prefix": str(prefix),
    "base_binary": str(Path(sys._base_executable).resolve()),
    "python_version": ".".join(map(str, sys.version_info[:3])),
    "origin": origin,
}))
"""


def _verify_runtime(python: Path, wheel: Path, identity: dict[str, str]) -> None:
    if python.parent.parent.resolve() != python.parent.parent:
        raise SyncError("Consumer interpreter directory must stay inside the selected cache")
    observed = _object(
        _run([python, "-I", "-c", _PROBE], "Installed Penflow verification").encode()
    )
    if any(
        observed.get(key) != identity[key] for key in ("version", "base_binary", "python_version")
    ):
        raise SyncError("Installed Penflow version or Python provenance disagrees with the receipt")
    if observed.get("module_version") != identity["version"] or observed.get("prefix") != str(
        python.parent.parent
    ):
        raise SyncError("Imported Penflow does not belong to the selected environment")
    origin = observed.get("origin")
    if not isinstance(origin, dict) or origin.get("url") != wheel.as_uri():
        raise SyncError("The installed package did not originate from the verified local wheel")
    if _digest(wheel.read_bytes()) != identity["wheel_sha256"]:
        raise SyncError("Cached wheel bytes no longer match the published SHA-256")
    _run(
        [python, "-I", "-m", "penflow", "visual-alignment", "--help"], "Visual alignment CLI probe"
    )


def _install(
    directory: Path,
    base: Path,
    release: Release,
    fetch: Callable[[str], bytes],
) -> None:
    uv = shutil.which("uv")
    if uv is None:
        raise SyncError("Installing a new consumer release requires uv on PATH")
    wheel = directory / release.wheel.name
    wheel.write_bytes(release.wheel.read(fetch))
    dependencies = release.requirements.read(fetch)
    requirements = directory / REQUIREMENTS
    line = f"\npenflow @ {wheel.as_uri()} --hash=sha256:{release.wheel.sha256}\n"
    requirements.write_bytes(dependencies + line.encode())
    venv = directory / "venv"
    _run(
        [
            uv,
            "--no-config",
            "venv",
            "--no-project",
            "--no-python-downloads",
            "--python",
            base,
            venv,
        ],
        "Consumer environment creation",
    )
    python = venv / "bin" / "python"
    _run(
        [
            uv,
            "--no-config",
            "pip",
            "sync",
            "--strict",
            "--require-hashes",
            "--only-binary",
            ":all:",
            "--python",
            python,
            requirements,
        ],
        "Locked consumer installation",
    )
    _run([uv, "--no-config", "pip", "check", "--python", python], "Consumer dependency check")


def select_runtime(
    lock_path: Path,
    cache: Path,
    tag: str | None = None,
    *,
    fetch: Callable[[str], bytes] = _get,
    base_python: Path = Path(sys.executable),
) -> dict[str, str]:
    """Verify the selected release and return a checked, independently installed interpreter.

    Uses the specified pinned base Python only for creating a separate environment.
    A successful installation is published after its runtime probe. Repeat calls verify
    the receipt and existing interpreter before skipping installation.
    """
    base = base_python.absolute()
    pin = _base_identity(lock_path, base)
    cache = cache.resolve()
    if cache.is_relative_to(Path(pin["base_prefix"])):
        raise SyncError("The Penflow cache must be outside the pinned LiveSpec environment")
    release = _load_release(fetch, tag)
    identity = pin | release.receipt
    # One cache slot per pin and version. The stored release identity catches an upstream
    # replacement of assets for an already installed version.
    pin_key = _digest(json.dumps(pin, sort_keys=True).encode())[:16]
    slot = cache / f"{pin['livespec_runtime']}-{pin_key}" / release.tag
    if not slot.resolve().is_relative_to(cache):
        raise SyncError("Consumer cache slot resolves outside the cache root")
    slot.mkdir(parents=True, exist_ok=True)
    activation = slot / "active.json"
    with (slot / "install.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if activation.exists():
            saved = _object(activation.read_bytes())
            name = saved.get("directory")
            if (
                saved.get("identity") != identity
                or not isinstance(name, str)
                or re.fullmatch(r"env-[a-z0-9_]+", name) is None
                or (slot / name).resolve() != slot.resolve() / name
            ):
                raise SyncError("Cached activation disagrees with the checked release or runtime")
            directory = slot / name
            python = directory / "venv" / "bin" / "python"
            _verify_runtime(python, directory / release.wheel.name, identity)
            return identity | {"python": str(python), "status": "current"}

        # Keep environments at their final path so their console entry point shebangs stay valid.
        directory = Path(tempfile.mkdtemp(prefix="env-", dir=slot))
        try:
            _install(directory, base, release, fetch)
            python = directory / "venv" / "bin" / "python"
            _verify_runtime(python, directory / release.wheel.name, identity)
            staged = directory / "activation.json"
            staged.write_text(
                json.dumps({"identity": identity, "directory": directory.name}) + "\n"
            )
            os.replace(staged, activation)
        finally:
            # Only remove the newly reserved attempt if activation was never published.
            if not activation.exists():
                shutil.rmtree(directory)
        return identity | {"python": str(python), "status": "installed"}


def main() -> int:
    """Parse operator arguments and emit the selected interpreter or an error."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, required=True, help="project's pinned LiveSpec lock")
    parser.add_argument(
        "--cache", type=Path, default=Path.home() / ".cache/penflow/consumer-runtime"
    )
    parser.add_argument("--tag", help="choose an exact stable release tag")
    args = parser.parse_args()
    try:
        receipt = select_runtime(args.lock, args.cache, args.tag)
    except (SyncError, OSError, ValueError, subprocess.TimeoutExpired) as error:
        print(f"penflow release sync: {error}", file=sys.stderr)
        return 1
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
