# @spec(AC-012)
# @spec(FR-009)
# @spec(FR-014)
"""Run the closed Feature 074 quality gates and persist hashed transcripts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import socket
import subprocess
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypeAlias

FEATURE_ID = "074-penflow-doctor-consumer-project-hygiene"
FEATURE_CHECKS = Path(".specs/features") / FEATURE_ID / "checks"
GATE_IDS = ("qg1", "qg2", "qg3", "qg4", "qg5", "qe7")
FEATURE_DIRECTORY = Path(".specs/features") / FEATURE_ID
DEFAULT_TIMEOUT_SECONDS = 90
QE7_TIMEOUT_SECONDS = 45
QE7_FILE_COUNT = 50_000
QE7_LOGICAL_BYTES = 5 << 30
QE7_MAX_ELAPSED_SECONDS = 30.0
QE7_MAX_RSS_BYTES = 256 << 20
QE7_MAX_OPEN_FDS = 32


class GateConfigurationError(ValueError):
    """Raised when a gate or selector is outside the closed registry contract."""


class ReceiptValidationError(ValueError):
    """Raised when a receipt no longer matches its path-backed evidence."""


@dataclass(frozen=True, slots=True)
class CommandResult:
    """Capture raw bytes and exit status for one gate command."""

    returncode: int
    stdout: bytes
    stderr: bytes


@dataclass(frozen=True, slots=True)
class ArtifactSelector:
    """Require one project-relative artifact and optional semantic validator."""

    path: str
    kind: str = "sha256"


@dataclass(frozen=True, slots=True)
class CommandSpec:
    """Define one immutable argv command and its expected evidence selectors."""

    name: str
    argv: tuple[str, ...]
    output_contains: tuple[str, ...] = ()
    artifacts: tuple[ArtifactSelector, ...] = ()
    environment: tuple[tuple[str, str], ...] = ()


CommandRunner: TypeAlias = Callable[..., CommandResult]
# JSON evidence is recursively heterogeneous and validated explicitly at its read boundaries.
JsonReceipt: TypeAlias = dict[str, Any]


def gate_command_specs(
    gate: str,
    project: Path,
    *,
    external_receipt: Path | None = None,
) -> tuple[CommandSpec, ...]:
    """Resolve one gate to the authoritative argv-only command sequence.

    Args:
        gate: One exact identifier from ``GATE_IDS``.
        project: Consumer Penflow source root used as subprocess cwd.
        external_receipt: Independent spec-check receipt required only by QG1.

    Returns:
        The immutable command sequence for the selected gate.

    Raises:
        GateConfigurationError: If the gate or receipt arguments are invalid.
    """
    _require_gate(gate)
    python = sys.executable
    pytest = (python, "-m", "pytest")
    if gate == "qg1":
        if external_receipt is None:
            raise GateConfigurationError("qg1 requires --external-receipt")
        receipt_path = _project_relative(project, external_receipt)
        return (
            CommandSpec(
                name="livespec-validate-feature",
                argv=(
                    "livespec",
                    "validate",
                    FEATURE_DIRECTORY.as_posix(),
                    "--strict",
                    "--format",
                    "json",
                ),
            ),
            CommandSpec(
                name="livespec-finalize-verify",
                argv=(
                    "livespec",
                    "finalize",
                    "verify",
                    "--feature",
                    FEATURE_ID,
                    "--json",
                ),
                artifacts=(ArtifactSelector(receipt_path, kind="complete_spec_check_run"),),
            ),
        )
    if external_receipt is not None:
        raise GateConfigurationError("--external-receipt is accepted only by qg1")
    if gate == "qg2":
        return (
            CommandSpec(
                name="destructive-safety",
                argv=pytest
                + (
                    "tests/test_project_doctor.py",
                    "tests/test_run_lifecycle.py",
                    "-q",
                    "-k",
                    "git or symlink or escape or identity or fault or race or tracked or staged",
                ),
                output_contains=("passed",),
            ),
        )
    if gate == "qg3":
        return (
            CommandSpec(
                name="single-canvas",
                argv=pytest
                + (
                    "tests/test_pen_lifecycle.py",
                    "tests/test_semantic_draft.py",
                    "tests/test_semantic_mapping.py",
                    "tests/test_reverse_pen.py",
                    "tests/test_demo.py",
                    "tests/test_full_demo.py",
                    "-q",
                ),
                output_contains=("passed",),
            ),
        )
    if gate == "qg4":
        return (
            CommandSpec(
                name="run-retention",
                argv=pytest
                + (
                    "tests/test_run_lifecycle.py",
                    "tests/test_run_pipeline.py",
                    "-q",
                    "-k",
                    "retention or owner or cleanup or idempotent or interrupted or repeated",
                ),
                output_contains=("passed",),
            ),
        )
    if gate == "qg5":
        return (
            CommandSpec(
                name="ruff-format",
                argv=(python, "-m", "ruff", "format", "--check", "."),
            ),
            CommandSpec(name="ruff-lint", argv=(python, "-m", "ruff", "check", ".")),
            CommandSpec(name="mypy", argv=(python, "-m", "mypy", ".")),
            CommandSpec(
                name="full-pytest",
                argv=pytest + ("-q",),
                output_contains=("passed",),
            ),
            CommandSpec(
                name="runtime-isolation",
                argv=pytest
                + (
                    "tests/test_skill_docs.py",
                    "tests/test_cli.py",
                    "-q",
                    "-k",
                    "runtime_isolation or forbidden",
                ),
                output_contains=("passed",),
            ),
        )
    measurement_path = FEATURE_CHECKS / "qe7-large-tree-metrics.json"
    return (
        CommandSpec(
            name="large-tree",
            argv=pytest
            + (
                "tests/test_run_lifecycle.py",
                "-q",
                "-k",
                "large_tree",
            ),
            output_contains=("passed",),
            artifacts=(ArtifactSelector(measurement_path.as_posix(), kind="qe7"),),
            environment=(("PENFLOW_QE7_OUT", str((project / measurement_path).resolve())),),
        ),
    )


def run_gate_specs(
    *,
    gate: str,
    project: Path,
    output: Path,
    command_specs: Sequence[CommandSpec],
    command_runner: CommandRunner | None = None,
    commit: str | None = None,
    diagnostics: Mapping[str, str] | None = None,
) -> JsonReceipt:
    """Execute a validated gate sequence and atomically persist its receipt.

    Args:
        gate: Closed gate identifier.
        project: Repository root used for subprocess cwd and evidence containment.
        output: Receipt path under the project root.
        command_specs: Registry-derived specs or explicit test-only contract fixtures.
        command_runner: Injectable argv-only subprocess boundary.
        commit: Optional known commit, otherwise resolved from Git.
        diagnostics: Optional volatile timestamps/host for deterministic tests.

    Returns:
        The schema-1 receipt. A failed command or selector yields a FAIL receipt.

    Raises:
        GateConfigurationError: If gate, paths, argv or selectors are unsafe.
    """
    _require_gate(gate)
    root = project.expanduser().resolve()
    if not root.is_dir():
        raise GateConfigurationError(f"project is not a directory: {project}")
    output_path = output if output.is_absolute() else root / output
    _require_contained(root, output_path)
    transcript_dir = output_path.parent / "transcripts"
    runner = command_runner or _run_command
    timeout = QE7_TIMEOUT_SECONDS if gate == "qe7" else DEFAULT_TIMEOUT_SECONDS
    resolved_commit = commit or _git_commit(root)
    started_at = datetime.now(UTC).isoformat()
    assertions: list[str] = []
    command_rows: list[dict[str, object]] = []
    artifact_rows: dict[str, dict[str, str]] = {}
    for index, command in enumerate(command_specs, start=1):
        _validate_command_spec(root, command)
        stdout_path = transcript_dir / f"{gate}-{index:02d}-{command.name}.out"
        stderr_path = transcript_dir / f"{gate}-{index:02d}-{command.name}.err"
        environment = os.environ.copy()
        environment.update(dict(command.environment))
        try:
            result = runner(command.argv, root, timeout, environment)
            timed_out = False
        except subprocess.TimeoutExpired as error:
            stdout = _timeout_bytes(error.stdout)
            stderr = _timeout_bytes(error.stderr) + f"timeout after {timeout}s\n".encode()
            result = CommandResult(124, stdout, stderr)
            timed_out = True
        except OSError as error:
            result = CommandResult(127, b"", f"{type(error).__name__}: {error}\n".encode())
            timed_out = False
        _atomic_write_bytes(stdout_path, result.stdout)
        _atomic_write_bytes(stderr_path, result.stderr)
        stdout_relative = stdout_path.relative_to(root).as_posix()
        stderr_relative = stderr_path.relative_to(root).as_posix()
        command_rows.append(
            {
                "argv": list(command.argv),
                "exit_code": result.returncode,
                "stdout_path": stdout_relative,
                "stdout_sha256": _sha256_bytes(result.stdout),
                "stderr_path": stderr_relative,
                "stderr_sha256": _sha256_bytes(result.stderr),
            }
        )
        assertions.append(
            f"command:{command.name}:exit_zero:{'PASS' if result.returncode == 0 else 'FAIL'}"
        )
        if timed_out:
            assertions.append(f"command:{command.name}:timeout:FAIL")
        decoded_output = result.stdout.decode("utf-8", errors="replace")
        for expected in command.output_contains:
            assertions.append(
                f"command:{command.name}:stdout_contains:{expected}:"
                f"{'PASS' if expected in decoded_output else 'FAIL'}"
            )
        for selector in command.artifacts:
            artifact_path = root / selector.path
            is_present = artifact_path.is_file() and not artifact_path.is_symlink()
            assertions.append(
                f"artifact:{selector.path}:present:{'PASS' if is_present else 'FAIL'}"
            )
            if not is_present:
                continue
            artifact_hash = _sha256_file(artifact_path)
            artifact_rows[selector.path] = {"path": selector.path, "sha256": artifact_hash}
            selector_pass = _validate_artifact_selector(
                selector,
                artifact_path,
                expected_commit=resolved_commit,
            )
            if selector.kind != "sha256":
                assertions.append(
                    f"artifact:{selector.path}:{selector.kind}-contract:"
                    f"{'PASS' if selector_pass else 'FAIL'}"
                )
    stable_result = {
        "feature": FEATURE_ID,
        "gate": gate,
        "status": "PASS"
        if assertions and all(row.endswith(":PASS") for row in assertions)
        else "FAIL",
        "commit": resolved_commit,
        "commands": command_rows,
        "artifacts": [artifact_rows[path] for path in sorted(artifact_rows)],
        "assertions": assertions,
    }
    volatile = dict(diagnostics) if diagnostics is not None else _diagnostics(started_at)
    receipt: dict[str, object] = {
        "schema_version": 1,
        "stable_result": stable_result,
        "diagnostics": volatile,
    }
    _atomic_write_json(output_path, receipt)
    return receipt


def run_gate(
    *,
    gate: str,
    project: Path,
    output: Path,
    external_receipt: Path | None = None,
) -> JsonReceipt:
    """Execute one gate exclusively through the closed registry."""
    specs = gate_command_specs(gate, project.resolve(), external_receipt=external_receipt)
    return run_gate_specs(
        gate=gate,
        project=project,
        output=output,
        command_specs=specs,
    )


def validate_receipt(receipt_path: Path, project: Path) -> None:
    """Rehash every transcript and artifact referenced by a durable receipt.

    Args:
        receipt_path: Schema-1 receipt to validate.
        project: Repository root used to resolve normalized evidence paths.

    Raises:
        ReceiptValidationError: If shape, containment, presence or a hash is invalid.
    """
    root = project.resolve()
    resolved_receipt = receipt_path if receipt_path.is_absolute() else root / receipt_path
    _require_contained(root, resolved_receipt)
    try:
        payload = json.loads(resolved_receipt.read_text(encoding="utf-8"))
        stable = payload["stable_result"]
        commands = stable["commands"]
        artifacts = stable["artifacts"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as error:
        raise ReceiptValidationError("receipt is unreadable or malformed") from error
    for command in commands:
        for stream in ("stdout", "stderr"):
            path = _validated_receipt_path(root, command[f"{stream}_path"])
            if not path.is_file() or path.is_symlink():
                raise ReceiptValidationError(f"transcript is missing: {path}")
            if _sha256_file(path) != command[f"{stream}_sha256"]:
                raise ReceiptValidationError(f"transcript hash mismatch: {path}")
    for artifact in artifacts:
        path = _validated_receipt_path(root, artifact["path"])
        if not path.is_file() or path.is_symlink():
            raise ReceiptValidationError(f"artifact is missing: {path}")
        if _sha256_file(path) != artifact["sha256"]:
            raise ReceiptValidationError(f"artifact hash mismatch: {path}")


def main(argv: Sequence[str] | None = None) -> int:
    """Parse the closed gate CLI and return zero only for a validated PASS receipt."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("gate", choices=GATE_IDS)
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--external-receipt", type=Path)
    args = parser.parse_args(argv)
    try:
        receipt = run_gate(
            gate=args.gate,
            project=args.project,
            output=args.out,
            external_receipt=args.external_receipt,
        )
        validate_receipt(args.out, args.project)
    except (GateConfigurationError, ReceiptValidationError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    return 0 if receipt["stable_result"]["status"] == "PASS" else 1


def _require_gate(gate: str) -> None:
    if gate not in GATE_IDS:
        raise GateConfigurationError(f"unknown gate: {gate}")


def _validate_command_spec(project: Path, command: CommandSpec) -> None:
    if not command.name or any(
        character not in "abcdefghijklmnopqrstuvwxyz0123456789-" for character in command.name
    ):
        raise GateConfigurationError(f"invalid command name: {command.name!r}")
    if not command.argv or any(
        not isinstance(argument, str) or "\x00" in argument for argument in command.argv
    ):
        raise GateConfigurationError(f"invalid argv for command: {command.name}")
    for selector in command.artifacts:
        _validated_receipt_path(project, selector.path)
        if selector.kind not in {
            "sha256",
            "pass_receipt",
            "complete_spec_check_run",
            "qe7",
        }:
            raise GateConfigurationError(f"unknown artifact selector: {selector.kind}")


def _project_relative(project: Path, path: Path) -> str:
    candidate = path if path.is_absolute() else project / path
    return _require_contained(project, candidate).relative_to(project.resolve()).as_posix()


def _require_contained(project: Path, path: Path) -> Path:
    root = project.resolve()
    candidate = path.resolve(strict=False)
    if candidate != root and root not in candidate.parents:
        raise GateConfigurationError(f"evidence path escapes project: {path}")
    return candidate


def _validated_receipt_path(project: Path, raw_path: object) -> Path:
    if not isinstance(raw_path, str) or not raw_path or Path(raw_path).is_absolute():
        raise GateConfigurationError(f"receipt path must be project-relative: {raw_path!r}")
    return _require_contained(project, project / raw_path)


def _validate_artifact_selector(
    selector: ArtifactSelector,
    path: Path,
    *,
    expected_commit: str | None,
) -> bool:
    if selector.kind == "sha256":
        return True
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(payload, dict):
        return False
    if selector.kind == "pass_receipt":
        status = payload.get("status") or payload.get("result")
        stable = payload.get("stable_result")
        if isinstance(stable, dict):
            status = stable.get("status", status)
        return status == "PASS"
    if selector.kind == "complete_spec_check_run":
        return _validate_complete_spec_check_run(payload)
    return _validate_qe7_payload(payload, expected_commit=expected_commit)


def _validate_complete_spec_check_run(payload: Mapping[str, object]) -> bool:
    """Require a successful, feature-bound spec-check whose archive task is closed."""
    goal = payload.get("goal")
    verify_result = payload.get("verify_result")
    if not isinstance(goal, dict) or not isinstance(verify_result, dict):
        return False
    tasks = goal.get("tasks")
    if not isinstance(tasks, list):
        return False
    archive_rows = [
        row for row in tasks if isinstance(row, dict) and row.get("id") == "archive.run"
    ]
    return (
        payload.get("schema_version") == "2.0"
        and payload.get("command") == "spec-check"
        and payload.get("feature") == FEATURE_ID
        and payload.get("exit_code") == 0
        and goal.get("status") == "complete"
        and len(archive_rows) == 1
        and archive_rows[0].get("status") == "complete"
        and verify_result.get("outcome") == "success"
    )


def _validate_qe7_payload(payload: object, *, expected_commit: str | None) -> bool:
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        return False
    stable = payload.get("stable_result")
    if not isinstance(stable, dict) or stable.get("status") != "PASS":
        return False
    runner = stable.get("runner")
    fixture = stable.get("fixture")
    metrics = stable.get("metrics")
    if (
        not isinstance(runner, dict)
        or not isinstance(fixture, dict)
        or not isinstance(metrics, dict)
    ):
        return False
    required_runner = (
        "image_os",
        "image_version",
        "kernel",
        "architecture",
        "cpu_count",
        "filesystem",
        "python_version",
    )
    if any(runner.get(field) in (None, "") for field in required_runner):
        return False
    if expected_commit is not None and stable.get("commit") != expected_commit:
        return False
    file_count = fixture.get("file_count")
    logical_bytes = fixture.get("logical_bytes")
    elapsed_seconds = metrics.get("elapsed_seconds")
    peak_rss_bytes = metrics.get("peak_rss_bytes")
    peak_open_fds = metrics.get("peak_open_fds")
    reported_bytes = metrics.get("reported_logical_bytes")
    recomputed_bytes = metrics.get("recomputed_logical_bytes")
    if not isinstance(file_count, int) or isinstance(file_count, bool):
        return False
    if not isinstance(logical_bytes, int) or isinstance(logical_bytes, bool):
        return False
    if not isinstance(peak_rss_bytes, int) or isinstance(peak_rss_bytes, bool):
        return False
    if not isinstance(peak_open_fds, int) or isinstance(peak_open_fds, bool):
        return False
    if not isinstance(reported_bytes, int) or isinstance(reported_bytes, bool):
        return False
    if not isinstance(recomputed_bytes, int) or isinstance(recomputed_bytes, bool):
        return False
    if not isinstance(elapsed_seconds, int | float) or isinstance(elapsed_seconds, bool):
        return False
    expected_bytes = QE7_LOGICAL_BYTES
    return (
        fixture.get("seed") == 74
        and file_count == QE7_FILE_COUNT
        and logical_bytes == expected_bytes
        and elapsed_seconds <= QE7_MAX_ELAPSED_SECONDS
        and peak_rss_bytes <= QE7_MAX_RSS_BYTES
        and peak_open_fds <= QE7_MAX_OPEN_FDS
        and reported_bytes == expected_bytes
        and recomputed_bytes == expected_bytes
    )


def _run_command(
    argv: tuple[str, ...],
    cwd: Path,
    timeout: int,
    environment: Mapping[str, str],
) -> CommandResult:
    # Evidence commands are argv-only, bounded, and capture unmodified stdout/stderr bytes.
    completed = subprocess.run(
        list(argv),
        cwd=cwd,
        env=dict(environment),
        check=False,
        capture_output=True,
        timeout=timeout,
    )
    return CommandResult(completed.returncode, completed.stdout, completed.stderr)


def _git_commit(project: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=project,
            check=False,
            capture_output=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "UNAVAILABLE"
    commit = result.stdout.decode(errors="replace").strip()
    return commit if result.returncode == 0 and commit else "UNAVAILABLE"


def _diagnostics(started_at: str) -> dict[str, str]:
    return {
        "started_at": started_at,
        "finished_at": datetime.now(UTC).isoformat(),
        "host": socket.gethostname(),
        "platform": platform.platform(),
    }


def _timeout_bytes(value: str | bytes | None) -> bytes:
    if value is None:
        return b""
    return value if isinstance(value, bytes) else value.encode()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _atomic_write_json(path: Path, payload: Mapping[str, object]) -> None:
    data = (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()
    _atomic_write_bytes(path, data)


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        # Durability order is file bytes, file fsync, replace, then containing-directory fsync.
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
