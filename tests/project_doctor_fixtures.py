"""Hermetic Git and filesystem tests for the consumer-project Doctor."""

from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest

from penflow.project_doctor import (
    DoctorResult,
)
from penflow.doctor_context import GitCommandResult, SubprocessGitGateway


EMPTY_PEN_BYTES = b'{"children":[],"version":"1.0"}\n'
MANAGED_IGNORE_BLOCK = (
    "# >>> Penflow managed temporary artifacts v1 >>>\n"
    ".penflow-tmp/\n"
    ".penflow-run/\n"
    ".mockup-validation/\n"
    "# <<< Penflow managed temporary artifacts v1 <<<\n"
)


def _git(repository: Path, *arguments: str, input_bytes: bytes | None = None) -> bytes:
    """Run deterministic Git fixture setup and return stdout bytes.

    Git is the real integration boundary under test. Calls are local-only, bounded,
    non-interactive, and fail the test immediately on any nonzero exit.
    """

    environment = {**os.environ, "LC_ALL": "C", "GIT_TERMINAL_PROMPT": "0"}
    completed = subprocess.run(
        ["git", "-C", os.fspath(repository), *arguments],
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=10,
        env=environment,
    )
    if completed.returncode != 0:
        pytest.fail(completed.stderr.decode("utf-8", errors="replace"))
    return completed.stdout


def _repository(tmp_path: Path) -> Path:
    """Create an isolated non-bare Git worktree."""

    repository = tmp_path / "consumer"
    repository.mkdir()
    _git(repository, "init", "-q")
    _git(repository, "config", "user.email", "penflow@example.test")
    _git(repository, "config", "user.name", "Penflow Tests")
    return repository


def _write_valid_pen(path: Path) -> None:
    """Write the smallest structurally valid Pencil document."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(EMPTY_PEN_BYTES)


def _index_digest(repository: Path) -> str | None:
    """Hash the Git index without creating it when the repository is empty."""

    index_path = repository / ".git" / "index"
    return hashlib.sha256(index_path.read_bytes()).hexdigest() if index_path.exists() else None


def _finding_codes(result: DoctorResult) -> set[str]:
    """Extract stable finding codes from a Doctor result."""

    return {finding.code for finding in result.report.stable_result.findings}


class _RecordingGitGateway:
    """Record exact Git argv while delegating to the bounded real gateway."""

    def __init__(self) -> None:
        self.calls: list[tuple[Path, tuple[str, ...], bytes | None]] = []
        self._delegate = SubprocessGitGateway()

    def run(
        self,
        directory: Path,
        arguments: tuple[str, ...],
        *,
        input_bytes: bytes | None = None,
    ) -> Any:
        self.calls.append((directory, arguments, input_bytes))
        return self._delegate.run(directory, arguments, input_bytes=input_bytes)


class _ScopeEscapeGitGateway(_RecordingGitGateway):
    """Inject one impossible sibling record into a scoped Git response."""

    def run(
        self,
        directory: Path,
        arguments: tuple[str, ...],
        *,
        input_bytes: bytes | None = None,
    ) -> Any:
        if arguments[:2] == ("ls-files", "--stage"):
            return GitCommandResult(
                stdout=(
                    b"100644 0000000000000000000000000000000000000000 0\t"
                    b"packages/sibling/.penflow-run/escape.bin\0"
                ),
                stderr=b"",
            )
        return super().run(directory, arguments, input_bytes=input_bytes)
