"""Build and, from qualified CI, publish a Penflow wheel and its locked dependencies."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import tomllib
from collections.abc import Callable
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = "penflow-release.json"
REQUIREMENTS = "penflow-runtime-requirements.txt"
VERSION = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")
SHA = re.compile(r"[0-9a-f]{40}")
DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
RELEASE_READ_ATTEMPTS = 10
RELEASE_READ_INTERVAL = 3
REQUIRED_WORKFLOWS = {
    "CI": ".github/workflows/ci.yml",
    "Security": ".github/workflows/security.yml",
}
# GitHub release payloads are decoded dynamically and checked before use.
JsonObject = dict[str, Any]


def _run(*command: str, cwd: Path = REPO_ROOT, env: dict[str, str] | None = None) -> bytes:
    return subprocess.run(
        command, cwd=cwd, env=env, stdout=subprocess.PIPE, check=True, timeout=180
    ).stdout


def _digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _version() -> str:
    project = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    version = project["version"]
    if (
        project["name"] != "penflow"
        or not isinstance(version, str)
        or not VERSION.fullmatch(version)
    ):
        raise ValueError("expected a stable Penflow version in pyproject.toml")
    return version


def _revision() -> str:
    revision = _run("git", "rev-parse", "HEAD").decode("ascii").strip()
    if not SHA.fullmatch(revision):
        raise ValueError("expected a commit SHA from Git")
    return revision


def _wheel_name(version: str) -> str:
    return f"penflow-{version}-py3-none-any.whl"


def _paths(out: Path, version: str) -> tuple[Path, Path, Path]:
    return out / _wheel_name(version), out / REQUIREMENTS, out / MANIFEST


def _descriptor(version: str, commit: str, digests: dict[str, str]) -> JsonObject:
    return {
        "schema": 1,
        "version": version,
        "commit": commit,
        "wheel": {"name": _wheel_name(version), "sha256": digests[_wheel_name(version)]},
        "requirements": {"name": REQUIREMENTS, "sha256": digests[REQUIREMENTS]},
    }


def _build(out: Path, version: str, commit: str) -> tuple[Path, ...]:
    out.mkdir(parents=True, exist_ok=True)
    wheel, requirements, manifest = _paths(out, version)
    if any(out.iterdir()):
        raise ValueError("release output directory must be empty")
    # Hatchling uses the commit timestamp for repeatable ZIP entry timestamps.
    epoch = _run("git", "show", "-s", "--format=%ct", commit).decode("ascii").strip()
    _run(
        "uv",
        "build",
        "--wheel",
        "--no-create-gitignore",
        "--out-dir",
        str(out),
        env={**os.environ, "SOURCE_DATE_EPOCH": epoch},
    )
    if not wheel.is_file():
        raise ValueError("build did not produce the expected universal Penflow wheel")
    requirements.write_bytes(
        _run(
            "uv",
            "export",
            "--locked",
            "--no-dev",
            "--no-default-groups",
            "--no-emit-project",
            "--no-header",
            "--format",
            "requirements-txt",
        )
    )
    _smoke(wheel, requirements, version)

    # Upload the descriptor only after the isolated installation has passed.
    descriptor = _descriptor(
        version, commit, {path.name: _digest(path) for path in (wheel, requirements)}
    )
    manifest.write_text(json.dumps(descriptor, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return wheel, requirements, manifest


def _smoke(wheel: Path, requirements: Path, version: str) -> None:
    with tempfile.TemporaryDirectory(prefix="penflow-release-smoke-") as temporary:
        outside = Path(temporary).resolve()
        env = outside / "runtime"
        python = str(env / "bin" / "python")
        _run("uv", "venv", "--python", sys.executable, str(env), cwd=outside)
        _run(
            "uv",
            "pip",
            "sync",
            "--python",
            python,
            "--require-hashes",
            "--strict",
            str(requirements),
            cwd=outside,
        )
        _run("uv", "pip", "install", "--python", python, "--no-deps", str(wheel), cwd=outside)
        _run("uv", "pip", "check", "--python", python, cwd=outside)
        cli_version = _run(python, "-I", "-m", "penflow", "--version", cwd=outside).decode().strip()
        if cli_version != f"penflow {version}":
            raise ValueError("installed Penflow CLI version differs from pyproject.toml")
        _run(python, "-I", "-m", "penflow", "visual-alignment", "--help", cwd=outside)


def _release_record(repository: str, tag: str) -> JsonObject | None:
    # The tag-specific endpoint describes published releases. Listing also sees our drafts.
    pages = json.loads(
        _run("gh", "api", "--paginate", "--slurp", f"repos/{repository}/releases?per_page=100")
    )
    matches = [release for page in pages for release in page if release["tag_name"] == tag]
    if len(matches) > 1:
        raise ValueError(f"multiple GitHub releases use {tag}")
    return matches[0] if matches else None


def _wait_for_release(
    repository: str, tag: str, visible: Callable[[JsonObject], bool]
) -> JsonObject:
    # GitHub's release list can lag behind a successful draft, asset or publication write.
    for attempt in range(RELEASE_READ_ATTEMPTS):
        release = _release_record(repository, tag)
        if release is not None and visible(release):
            return release
        if attempt + 1 < RELEASE_READ_ATTEMPTS:
            time.sleep(RELEASE_READ_INTERVAL)
    raise ValueError(f"GitHub did not expose the verified state for {tag} after the release write")


def _assets(release: JsonObject) -> dict[str, str]:
    assets = release["assets"]
    digests = {asset["name"]: asset["digest"] for asset in assets}
    if len(digests) != len(assets):
        raise ValueError("GitHub release contains duplicate asset names")
    if any(
        asset["state"] != "uploaded" or not DIGEST.fullmatch(asset["digest"] or "")
        for asset in assets
    ):
        raise ValueError("GitHub release contains an incomplete asset")
    return digests


def _tag_commit(repository: str, tag: str) -> str:
    # The commits endpoint resolves both lightweight and annotated tags to a commit.
    return json.loads(
        _run("gh", "api", f"repos/{repository}/commits/{tag}", "--jq", "{sha: .sha}")
    )["sha"]


def _verify_published(repository: str, tag: str, version: str, release: JsonObject) -> None:
    if release["draft"] or release["prerelease"]:
        raise ValueError(f"{tag} is not a published stable release")
    available = _assets(release)
    if available.keys() != {MANIFEST, REQUIREMENTS, _wheel_name(version)}:
        raise ValueError(f"{tag} does not contain the complete consumer release")
    raw = _run(
        "gh",
        "release",
        "download",
        tag,
        "--repo",
        repository,
        "--pattern",
        MANIFEST,
        "--output",
        "-",
    )
    if f"sha256:{hashlib.sha256(raw).hexdigest()}" != available[MANIFEST]:
        raise ValueError(f"{tag} descriptor digest differs from GitHub's record")
    if json.loads(raw) != _descriptor(
        version,
        _tag_commit(repository, tag),
        {name: digest[7:] for name, digest in available.items()},
    ):
        raise ValueError(f"{tag} assets do not agree with the tag and release descriptor")


def _verify_preexisting_tag(repository: str, tag: str, sha: str) -> None:
    # ls-remote distinguishes a missing tag from a failed API request and peels annotated tags.
    ref = f"refs/tags/{tag}"
    raw = _run("git", "ls-remote", f"https://github.com/{repository}.git", ref, f"{ref}^{{}}")
    refs = {
        name: revision
        for revision, name in (line.split() for line in raw.decode("ascii").splitlines())
    }
    if refs and refs.get(f"{ref}^{{}}", refs.get(ref)) != sha:
        raise ValueError(f"{tag} already points to another commit")


def _publish(out: Path, version: str, commit: str, repository: str) -> None:
    tag = f"v{version}"
    release = _release_record(repository, tag)
    if release and not release["draft"]:
        _verify_published(repository, tag, version, release)
        print(f"{tag} is already published with all three verified consumer assets")
        return
    if release and (release["target_commitish"] != commit or release["prerelease"]):
        raise ValueError(f"draft {tag} belongs to a different release source")
    _verify_preexisting_tag(repository, tag, commit)

    # The read-only CI job built and ran the wheel. This job validates its output
    # and publishes it without importing code from the artifact.
    paths = _paths(out, version)
    if {entry.name for entry in out.iterdir()} != {path.name for path in paths} or any(
        not path.is_file() or path.is_symlink() for path in paths
    ):
        raise ValueError("the build artifact does not contain exactly three regular release files")
    digests = {path.name: _digest(path) for path in paths}
    if json.loads(paths[2].read_bytes()) != _descriptor(version, commit, digests):
        raise ValueError("the build artifact does not match the qualified source and asset digests")
    if release is None:
        _run(
            "gh",
            "release",
            "create",
            tag,
            "--repo",
            repository,
            "--target",
            commit,
            "--title",
            f"Penflow {version}",
            "--notes",
            f"Consumer wheel built from CI- and Security-qualified commit {commit}.",
            "--draft",
        )
        release = _wait_for_release(repository, tag, lambda record: record["draft"])
    if not release["draft"] or release["target_commitish"] != commit:
        raise ValueError(f"could not establish a draft for {tag} at the qualified commit")

    # A retry may finish a partial draft, provided every existing asset matches byte for byte.
    expected = {name: f"sha256:{digest}" for name, digest in digests.items()}
    actual = _assets(release)
    if any(expected.get(name) != digest for name, digest in actual.items()):
        raise ValueError(f"draft {tag} contains conflicting assets")
    missing = [str(path) for path in paths if path.name not in actual]
    if missing:
        _run("gh", "release", "upload", tag, *missing, "--repo", repository)
    current = _wait_for_release(
        repository,
        tag,
        lambda record: (
            all(asset["state"] == "uploaded" and asset["digest"] for asset in record["assets"])
            and len(record["assets"]) >= len(expected)
        ),
    )
    if (
        not current["draft"]
        or current["target_commitish"] != commit
        or current["prerelease"]
        or _assets(current) != expected
    ):
        raise ValueError(f"GitHub did not verify each of the three staged assets for {tag}")
    _verify_preexisting_tag(repository, tag, commit)
    if not _checks_passed(repository, commit):
        raise ValueError("the staged release lost its CI or Security qualification")
    # Use GitHub's version-aware policy for the latest stable release.
    _run(
        "gh",
        "api",
        "--method",
        "PATCH",
        f"repos/{repository}/releases/{int(current['id'])}",
        "--field",
        "draft=false",
        "--raw-field",
        "make_latest=legacy",
    )
    published = _wait_for_release(repository, tag, lambda record: not record["draft"])
    if _tag_commit(repository, tag) != commit:
        raise ValueError(f"published {tag} did not resolve to the qualified commit")
    _verify_published(repository, tag, version, published)
    print(f"Published {tag} from {commit}")


def _is_main_push(run: JsonObject, repository: str, commit: str, workflow: str) -> bool:
    return (
        run["name"] == workflow
        and run["path"] == REQUIRED_WORKFLOWS[workflow]
        and run["event"] == "push"
        and run["head_branch"] == "main"
        and run["head_sha"] == commit
        and run["head_repository"] is not None
        and run["head_repository"]["full_name"] == repository
    )


def _checks_passed(repository: str, commit: str) -> bool:
    waiting_for: list[str] = []
    for workflow, path in REQUIRED_WORKFLOWS.items():
        endpoint = (
            f"repos/{repository}/actions/workflows/{Path(path).name}/runs"
            f"?head_sha={commit}&branch=main&event=push&per_page=100"
        )
        pages = json.loads(_run("gh", "api", "--paginate", "--slurp", endpoint))
        matching = [
            run
            for page in pages
            for run in page["workflow_runs"]
            if _is_main_push(run, repository, commit, workflow)
        ]
        # A later run or rerun in progress supersedes an earlier success.
        latest = max(
            matching, key=lambda run: (int(run["id"]), int(run["run_attempt"])), default=None
        )
        if latest is None or latest["status"] != "completed" or latest["conclusion"] != "success":
            waiting_for.append(workflow)
    if waiting_for:
        print(
            f"Publication requires successful {', '.join(waiting_for)} for {commit}",
            file=sys.stderr,
        )
    return not waiting_for


def _workflow_repository(commit: str) -> str:
    # workflow_run accepts successful main-push events from exactly our two checks.
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    if (
        os.environ.get("GITHUB_ACTIONS") != "true"
        or os.environ.get("GITHUB_EVENT_NAME") != "workflow_run"
        or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository)
        or _run("git", "status", "--porcelain", "--untracked-files=no")
    ):
        raise ValueError("publication requires a clean GitHub Actions workflow_run checkout")
    run = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))[
        "workflow_run"
    ]
    workflow = run["name"]
    if (
        workflow not in REQUIRED_WORKFLOWS
        or run["status"] != "completed"
        or run["conclusion"] != "success"
        or not _is_main_push(run, repository, commit, workflow)
    ):
        raise ValueError("expected a successful same-repository main-push CI or Security event")
    return repository


def main() -> None:
    """Build and validate release assets, optionally publishing them from protected CI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, help="directory for the three verified assets")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--qualify", action="store_true", help="check CI and Security for this source"
    )
    mode.add_argument(
        "--publish", action="store_true", help="publish prebuilt assets from qualified CI"
    )
    args = parser.parse_args()
    if args.out is None and not args.qualify:
        parser.error("--out is required to build or publish")
    try:
        commit = _revision()
        if args.qualify:
            qualified = _checks_passed(_workflow_repository(commit), commit)
            print("true" if qualified else "false")
        elif args.publish:
            repository = _workflow_repository(commit)
            if not _checks_passed(repository, commit):
                raise ValueError(
                    "this source requires successful CI and Security before publishing"
                )
            _publish(args.out.resolve(), _version(), commit, repository)
        else:
            out, version = args.out.resolve(), _version()
            _build(out, version, commit)
            print(f"Built and verified Penflow {version} assets in {out}")
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        parser.exit(1, f"consumer release: {error}\n")


if __name__ == "__main__":
    main()
