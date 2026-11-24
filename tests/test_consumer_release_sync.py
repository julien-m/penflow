"""Exercise consumer release selection and isolated installation using local test data."""

from __future__ import annotations

import base64
import csv
import hashlib
import importlib.util
import io
import json
import runpy
import shutil
import subprocess
import sys
import venv
import zipfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "sync-consumer-penflow.py"
MANIFEST = "penflow-release.json"
REQUIREMENTS = "penflow-runtime-requirements.txt"


def _json_bytes(data: object) -> bytes:
    return json.dumps(data).encode()


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _wheel(version: str) -> bytes:
    """Build a tiny standards-compliant fixture for uv without publishing a package."""
    dist_info = f"penflow-{version}.dist-info"
    files = {
        "penflow/__init__.py": f"__version__ = {version!r}\n".encode(),
        "penflow/__main__.py": (
            "import argparse\n"
            "from . import __version__\n"
            "parser = argparse.ArgumentParser(prog='penflow')\n"
            "parser.add_argument('--version', action='version', version=f'penflow {__version__}')\n"
            "parser.add_subparsers(dest='command').add_parser('visual-alignment')\n"
            "parser.parse_args()\n"
        ).encode(),
        f"{dist_info}/METADATA": (
            f"Metadata-Version: 2.1\nName: penflow\nVersion: {version}\nRequires-Python: >=3.12\n\n"
        ).encode(),
        f"{dist_info}/WHEEL": (
            b"Wheel-Version: 1.0\nGenerator: consumer-test\n"
            b"Root-Is-Purelib: true\nTag: py3-none-any\n"
        ),
    }
    record = io.StringIO()
    writer = csv.writer(record)
    for path, data in files.items():
        digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
        writer.writerow([path, f"sha256={digest}", len(data)])
    writer.writerow([f"{dist_info}/RECORD", "", ""])
    files[f"{dist_info}/RECORD"] = record.getvalue().encode()

    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as wheel:
        for path, data in files.items():
            wheel.writestr(zipfile.ZipInfo(path), data)
    return output.getvalue()


@dataclass
class Release:
    """Test release transport data independent of the validator under test."""

    version: str
    commit: str
    assets: dict[str, bytes]
    manifest: dict[str, object]

    @property
    def tag(self) -> str:
        return f"v{self.version}"

    @property
    def wheel_name(self) -> str:
        return f"penflow-{self.version}-py3-none-any.whl"


def _release(version: str) -> Release:
    wheel_name = f"penflow-{version}-py3-none-any.whl"
    wheel = _wheel(version)
    requirements = b"# This fixture has no third-party requirements.\n"
    commit = hashlib.sha1(f"fixture release {version}".encode(), usedforsecurity=False).hexdigest()
    manifest = {
        "schema": 1,
        "version": version,
        "commit": commit,
        "wheel": {"name": wheel_name, "sha256": _sha(wheel)},
        "requirements": {"name": REQUIREMENTS, "sha256": _sha(requirements)},
    }
    return Release(
        version,
        commit,
        {wheel_name: wheel, REQUIREMENTS: requirements, MANIFEST: _json_bytes(manifest)},
        manifest,
    )


@dataclass(frozen=True)
class PinnedRuntime:
    """Paths for a throwaway LiveSpec pin and its unchanged base environment."""

    executable: Path
    lock: Path
    lock_bytes: bytes
    marker: Path


@pytest.fixture
def bootstrap(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    assert (spec := importlib.util.spec_from_file_location("consumer_release_sync", SCRIPT))
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def pinned_runtime(tmp_path: Path) -> PinnedRuntime:
    commit = hashlib.sha1(b"fixture LiveSpec runtime", usedforsecurity=False).hexdigest()
    protocol = 23
    runtime_id = f"{protocol}-{commit[:12]}"
    runtime = tmp_path / f"pinned-{runtime_id}"
    venv.EnvBuilder(symlinks=True).create(runtime)
    marker = runtime / "private-sdk-marker"
    marker.write_bytes(b"private runtime")
    lock_bytes = _json_bytes(
        {
            "schema": 1,
            "mode": "pinned",
            "commit": commit,
            "livespec_version": protocol,
            "runtime_id": runtime_id,
        }
    )
    lock = tmp_path / "livespec.lock"
    lock.write_bytes(lock_bytes)
    return PinnedRuntime(runtime / "bin" / "python", lock, lock_bytes, marker)


@pytest.fixture
def uv() -> str:
    if (uv := shutil.which("uv")) is None:
        pytest.skip("uv is required to verify the actual consumer installer")
    return uv


class Registry:
    """Serve the GitHub wire contract without using the network."""

    api = "https://api.github.com/repos/julien-m/penflow"
    download = "https://github.com/julien-m/penflow/releases/download"

    def __init__(self, latest: Release) -> None:
        self.latest = latest
        self.releases = {latest.tag: latest}
        self.overrides: dict[str, bytes] = {}
        self.calls: list[str] = []

    def publish(self, release: Release) -> None:
        self.releases[release.tag] = release
        self.latest = release

    def asset_url(self, release: Release, name: str) -> str:
        return f"{self.download}/{release.tag}/{name}"

    def metadata(self, release: Release) -> dict[str, object]:
        return {
            "tag_name": release.tag,
            "draft": False,
            "prerelease": False,
            "assets": [
                {
                    "name": name,
                    "digest": f"sha256:{_sha(data)}",
                    "size": len(data),
                    "browser_download_url": self.asset_url(release, name),
                }
                for name, data in release.assets.items()
            ],
        }

    def fetch(self, url: str) -> bytes:
        self.calls.append(url)
        if url in self.overrides:
            return self.overrides[url]
        if url == f"{self.api}/releases/latest":
            return _json_bytes(self.metadata(self.latest))
        for release in self.releases.values():
            if url == f"{self.api}/releases/tags/{release.tag}":
                return _json_bytes(self.metadata(release))
            if url == f"{self.api}/commits/{release.tag}":
                return _json_bytes({"sha": release.commit})
            if url == f"{self.api}/compare/{release.commit}...main":
                return _json_bytes(
                    {"status": "ahead", "merge_base_commit": {"sha": release.commit}}
                )
            for name, data in release.assets.items():
                if url == self.asset_url(release, name):
                    return data
        pytest.fail(f"unexpected GitHub fetch: {url}")


def _select(
    bootstrap: ModuleType,
    runtime: PinnedRuntime,
    cache: Path,
    registry: Registry,
    tag: str | None = None,
) -> dict[str, str]:
    return bootstrap.select_runtime(
        runtime.lock, cache, tag, fetch=registry.fetch, base_python=runtime.executable
    )


def _run_penflow(receipt: dict[str, str], *args: str) -> str:
    completed = subprocess.run(
        [receipt["python"], "-I", "-m", "penflow", *args],
        capture_output=True,
        check=True,
        text=True,
        timeout=20,
    )
    return completed.stdout


def test_selects_new_release_and_reuses_its_verified_interpreter(
    bootstrap: ModuleType, pinned_runtime: PinnedRuntime, tmp_path: Path, uv: str
) -> None:
    cache = tmp_path / "managed environments"
    first = _release("1.2.3")
    registry = Registry(first)
    before = _select(bootstrap, pinned_runtime, cache, registry)
    assert before["status"] == "installed"
    assert _run_penflow(before, "--version").strip() == f"penflow {first.version}"

    second = _release("1.3.0")
    registry.publish(second)
    installed = _select(bootstrap, pinned_runtime, cache, registry)
    assert installed["status"] == "installed"
    assert installed["version"] == second.version
    assert installed["commit"] == second.commit
    assert installed["wheel_sha256"] == _sha(second.assets[second.wheel_name])
    assert installed["tag"] == second.tag
    assert installed["python"] != before["python"]
    assert Path(installed["python"]).is_relative_to(cache)
    assert "visual-alignment" in _run_penflow(installed, "visual-alignment", "--help")

    current = _select(bootstrap, pinned_runtime, cache, registry)
    assert current == {**installed, "status": "current"}
    assert registry.calls.count(registry.asset_url(second, second.wheel_name)) == 1
    assert registry.calls.count(registry.asset_url(second, REQUIREMENTS)) == 1

    previous = _select(bootstrap, pinned_runtime, cache, registry, first.tag)
    assert previous == {**before, "status": "current"}
    assert _run_penflow(previous, "--version").strip() == f"penflow {first.version}"
    assert pinned_runtime.lock.read_bytes() == pinned_runtime.lock_bytes
    assert pinned_runtime.marker.read_bytes() == b"private runtime"


def test_corrupt_download_preserves_the_previous_release_and_allows_retry(
    bootstrap: ModuleType, pinned_runtime: PinnedRuntime, tmp_path: Path, uv: str
) -> None:
    cache = tmp_path / "managed"
    first = _release("1.2.3")
    registry = Registry(first)
    before = _select(bootstrap, pinned_runtime, cache, registry)
    second = _release("1.3.0")
    registry.publish(second)

    wheel_url = registry.asset_url(second, second.wheel_name)
    wheel = second.assets[second.wheel_name]
    registry.overrides[wheel_url] = bytes([wheel[0] ^ 1]) + wheel[1:]
    with pytest.raises(bootstrap.SyncError):
        _select(bootstrap, pinned_runtime, cache, registry)
    assert _run_penflow(before, "--version").strip() == f"penflow {first.version}"
    assert _select(bootstrap, pinned_runtime, cache, registry, first.tag)["status"] == "current"

    del registry.overrides[wheel_url]
    recovered = _select(bootstrap, pinned_runtime, cache, registry)
    assert recovered["status"] == "installed"
    assert recovered["version"] == second.version
    assert _run_penflow(recovered, "--version").strip() == f"penflow {second.version}"


@pytest.mark.parametrize(
    "mismatch", ["manifest-version", "duplicate-field", "asset-digest", "tag", "main-ancestor"]
)
def test_rejects_unqualified_release_metadata_before_downloading_the_wheel(
    bootstrap: ModuleType, pinned_runtime: PinnedRuntime, tmp_path: Path, mismatch: str
) -> None:
    release = _release("1.3.0")
    registry = Registry(release)
    unrelated = _release("1.2.3")
    if mismatch == "manifest-version":
        release.assets[MANIFEST] = _json_bytes({**release.manifest, "version": unrelated.version})
    elif mismatch == "duplicate-field":
        release.assets[MANIFEST] = b'{"schema": 1,' + release.assets[MANIFEST][1:]
    elif mismatch == "asset-digest":
        release.assets[MANIFEST] = _json_bytes(
            {**release.manifest, "wheel": {"name": release.wheel_name, "sha256": "0" * 64}}
        )
    elif mismatch == "tag":
        registry.overrides[f"{registry.api}/commits/{release.tag}"] = _json_bytes(
            {"sha": unrelated.commit}
        )
    else:
        registry.overrides[f"{registry.api}/compare/{release.commit}...main"] = _json_bytes(
            {"status": "diverged", "merge_base_commit": {"sha": unrelated.commit}}
        )

    with pytest.raises(bootstrap.SyncError):
        _select(bootstrap, pinned_runtime, tmp_path / "managed", registry)
    assert registry.asset_url(release, release.wheel_name) not in registry.calls


def test_refuses_python_outside_the_locked_runtime_before_network(
    bootstrap: ModuleType, pinned_runtime: PinnedRuntime, tmp_path: Path
) -> None:
    registry = Registry(_release("1.3.0"))
    with pytest.raises(bootstrap.SyncError):
        bootstrap.select_runtime(
            pinned_runtime.lock,
            tmp_path / "managed",
            fetch=registry.fetch,
            base_python=Path(sys.executable),
        )
    assert registry.calls == []


def test_refuses_lock_with_runtime_id_inconsistent_with_commit(
    bootstrap: ModuleType, pinned_runtime: PinnedRuntime, tmp_path: Path
) -> None:
    registry = Registry(_release("1.3.0"))
    group = json.loads(pinned_runtime.lock_bytes)
    group["runtime_id"] = f"{group['livespec_version']}-{'0' * 12}"
    pinned_runtime.lock.write_bytes(_json_bytes(group))

    with pytest.raises(bootstrap.SyncError):
        _select(bootstrap, pinned_runtime, tmp_path / "managed", registry)
    assert registry.calls == []


def test_rejects_changed_asset_identity_for_an_already_installed_tag(
    bootstrap: ModuleType, pinned_runtime: PinnedRuntime, tmp_path: Path, uv: str
) -> None:
    cache = tmp_path / "managed"
    original = _release("1.3.0")
    registry = Registry(original)
    installed = _select(bootstrap, pinned_runtime, cache, registry)

    replacement = _release(original.version)
    replacement.assets[REQUIREMENTS] += b"# Revised release bytes under the same tag.\n"
    replacement.manifest["requirements"] = {
        "name": REQUIREMENTS,
        "sha256": _sha(replacement.assets[REQUIREMENTS]),
    }
    replacement.assets[MANIFEST] = _json_bytes(replacement.manifest)
    registry.publish(replacement)

    with pytest.raises(bootstrap.SyncError):
        _select(bootstrap, pinned_runtime, cache, registry)
    assert registry.calls.count(registry.asset_url(original, REQUIREMENTS)) == 1
    assert _run_penflow(installed, "--version").strip() == f"penflow {original.version}"


def test_concurrent_selections_activate_one_environment(
    bootstrap: ModuleType, pinned_runtime: PinnedRuntime, tmp_path: Path, uv: str
) -> None:
    cache = tmp_path / "managed"
    release = _release("1.3.0")
    registry = Registry(release)
    # Separate calls share the cache slot and contend for the real installation lock.
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(_select, bootstrap, pinned_runtime, cache, registry)
        second = executor.submit(_select, bootstrap, pinned_runtime, cache, registry)
        results = first.result(timeout=20), second.result(timeout=20)

    assert {item["status"] for item in results} == {"installed", "current"}
    assert results[0]["python"] == results[1]["python"]
    assert registry.calls.count(registry.asset_url(release, release.wheel_name)) == 1


def test_refuses_to_use_the_pinned_environment_as_install_cache(
    bootstrap: ModuleType, pinned_runtime: PinnedRuntime
) -> None:
    registry = Registry(_release("1.3.0"))
    cache = pinned_runtime.marker.parent / "managed"
    with pytest.raises(bootstrap.SyncError):
        _select(bootstrap, pinned_runtime, cache, registry)
    assert not cache.exists()
    assert registry.calls == []
    assert pinned_runtime.marker.read_bytes() == b"private runtime"


def test_refuses_escaping_cache_symlink_before_creating_release_directory(
    bootstrap: ModuleType, pinned_runtime: PinnedRuntime, tmp_path: Path, uv: str
) -> None:
    original_cache = tmp_path / "normal-cache"
    release = _release("1.3.0")
    registry = Registry(release)
    installed = _select(bootstrap, pinned_runtime, original_cache, registry)
    pinned_slot = Path(installed["python"]).relative_to(original_cache).parts[0]

    cache = tmp_path / "linked-cache"
    cache.mkdir()
    external = tmp_path / "external"
    external.mkdir()
    (cache / pinned_slot).symlink_to(external, target_is_directory=True)

    with pytest.raises(bootstrap.SyncError):
        _select(bootstrap, pinned_runtime, cache, registry)
    assert list(external.iterdir()) == []
    assert _run_penflow(installed, "--version").strip() == f"penflow {release.version}"


@pytest.mark.parametrize("security", ["success", "failure", "foreign-sha", "pending-rerun"])
def test_publication_requires_both_current_workflows_on_the_exact_commit(
    monkeypatch: pytest.MonkeyPatch, security: str
) -> None:
    publisher = runpy.run_path(str(SCRIPT.with_name("build-consumer-release.py")))
    checks_passed = publisher["_checks_passed"]
    repo = "example/penflow"
    commit = hashlib.sha1(b"candidate", usedforsecurity=False).hexdigest()

    def run(state: str, workflow: str, path: str, attempt: int = 1) -> dict[str, object]:
        return {
            "name": workflow,
            "path": path,
            "event": "push",
            "head_branch": "main",
            "head_sha": commit,
            "head_repository": {"full_name": repo},
            "id": 10,
            "run_attempt": attempt,
            "status": "in_progress" if state == "pending" else "completed",
            "conclusion": None if state == "pending" else state,
        }

    ci_path, security_path = ".github/workflows/ci.yml", ".github/workflows/security.yml"
    ci = [run("success", "CI", ci_path)]
    security_runs = [run("success", "Security", security_path)]
    if security == "failure":
        security_runs = [run("failure", "Security", security_path)]
    elif security == "foreign-sha":
        security_runs[0]["head_sha"] = hashlib.sha1(b"other", usedforsecurity=False).hexdigest()
    elif security == "pending-rerun":
        security_runs.append(run("pending", "Security", security_path, attempt=2))

    def query(*command: str) -> bytes:
        endpoint = command[-1]
        assert f"head_sha={commit}" in endpoint
        assert "branch=main&event=push" in endpoint
        rows = ci if "/ci.yml/" in endpoint else security_runs
        return _json_bytes([{"workflow_runs": rows}])

    monkeypatch.setitem(checks_passed.__globals__, "_run", query)
    assert checks_passed(repo, commit) == (security == "success")


@pytest.mark.parametrize("available", [True, False])
def test_publisher_waits_for_read_after_write_visibility(
    monkeypatch: pytest.MonkeyPatch, available: bool
) -> None:
    publisher = runpy.run_path(str(SCRIPT.with_name("build-consumer-release.py")))
    wait_for_release = publisher["_wait_for_release"]
    scope = wait_for_release.__globals__
    expected = {"draft": True}
    records = [None, {"draft": False}, expected if available else None]
    pauses: list[float] = []
    monkeypatch.setitem(scope, "RELEASE_READ_ATTEMPTS", len(records))
    monkeypatch.setitem(scope, "_release_record", lambda repo, tag: records.pop(0))
    monkeypatch.setattr(scope["time"], "sleep", pauses.append)

    if available:
        assert (
            wait_for_release("example/penflow", "v3.2.1", lambda release: release["draft"])
            == expected
        )
    else:
        with pytest.raises(ValueError, match="after the release write"):
            wait_for_release("example/penflow", "v3.2.1", lambda release: release["draft"])
    assert len(pauses) == 2
