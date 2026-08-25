# @spec FR-009 FR-010 AC-010 AC-011 AC-012
"""Run Feature 075's closed quality gates and bind durable evidence hashes."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypeAlias

FEATURE_ID = "075-penflow-doctor-monorepo-project-boundary"
FEATURE_DIRECTORY = Path(".specs/features") / FEATURE_ID
CHECKS_DIRECTORY = FEATURE_DIRECTORY / "checks"
FEATURE_075_GATE_RECEIPTS: Mapping[str, Path] = {
    "qg1": CHECKS_DIRECTORY / "qg1-contract.json",
    "qg2": CHECKS_DIRECTORY / "qg2-root-pathspec.json",
    "qg3": CHECKS_DIRECTORY / "qg3-destructive-isolation.json",
    "qg4": CHECKS_DIRECTORY / "qg4-project-brainstorm.json",
    "qg5": CHECKS_DIRECTORY / "qg5-feature-074.json",
    "qg6": CHECKS_DIRECTORY / "qg6-consumer-proof.json",
    "qe7": CHECKS_DIRECTORY / "qe7-regression.json",
}
DEFAULT_TIMEOUT_SECONDS = 120
QE7_TIMEOUT_SECONDS = 120
PROJECT_BRAINSTORM_PROOF = CHECKS_DIRECTORY / "project-brainstorm-proof.json"
CONSUMER_PROOF = CHECKS_DIRECTORY / "consumer-proof.json"
FEATURE_074_CHECKS = Path(".specs/features/074-penflow-doctor-consumer-project-hygiene/checks")


class GateConfigurationError(ValueError):
    """Report a feature, gate, argv or output outside the closed registry."""


class ReceiptValidationError(ValueError):
    """Report missing or changed path-backed receipt evidence."""


@dataclass(frozen=True, slots=True)
class CommandResult:
    """Capture one bounded command's raw byte channels."""

    returncode: int
    stdout: bytes
    stderr: bytes


@dataclass(frozen=True, slots=True)
class ArtifactSelector:
    """Require one project-relative regular evidence file."""

    path: Path
    require_pass: bool = False
    expected_feature: str | None = None


@dataclass(frozen=True, slots=True)
class CommandSpec:
    """Define one immutable argv-only gate command."""

    name: str
    argv: tuple[str, ...]
    artifacts: tuple[ArtifactSelector, ...] = ()


CommandRunner: TypeAlias = Callable[[tuple[str, ...], Path, int], CommandResult]
JsonObject: TypeAlias = dict[str, Any]


def gate_command_specs(gate: str) -> tuple[CommandSpec, ...]:
    """Return the closed command sequence for one Feature 075 gate."""

    _require_gate(gate)
    python = sys.executable
    pytest = (python, "-m", "pytest")
    if gate == "qg1":
        return _qg1_specs()
    if gate == "qg2":
        return _qg2_specs(pytest)
    if gate == "qg3":
        return _qg3_specs(pytest)
    if gate == "qg4":
        return _qg4_specs(python)
    if gate == "qg5":
        return _qg5_specs(pytest)
    if gate == "qg6":
        return _qg6_specs(python, pytest)
    return (
        CommandSpec("ruff", (python, "-m", "ruff", "check", ".")),
        CommandSpec("mypy", (python, "-m", "mypy", ".")),
        CommandSpec("full-pytest", pytest + ("-q",)),
    )


def _qg1_specs() -> tuple[CommandSpec, ...]:
    return (
        CommandSpec(
            "livespec-validate",
            (
                "livespec",
                "validate",
                FEATURE_DIRECTORY.as_posix(),
                "--strict",
                "--format",
                "json",
            ),
        ),
    )


def _qg2_specs(pytest: tuple[str, ...]) -> tuple[CommandSpec, ...]:
    return (
        CommandSpec(
            "root-pathspec",
            pytest
            + (
                "tests/test_project_doctor.py",
                "tests/test_monorepo_project_boundary.py",
                "-q",
            ),
        ),
    )


def _qg3_specs(pytest: tuple[str, ...]) -> tuple[CommandSpec, ...]:
    return (
        CommandSpec(
            "destructive-isolation",
            pytest
            + (
                "tests/test_run_lifecycle.py",
                "tests/test_monorepo_project_boundary.py",
                "-q",
            ),
        ),
    )


def _qg4_specs(python: str) -> tuple[CommandSpec, ...]:
    return (
        CommandSpec(
            "project-brainstorm-proof",
            (
                python,
                "tests/monorepo_project_boundary_proof.py",
                "--live-project",
                "~/projects/project-brainstorm/projects/routempo",
                "--sibling",
                "~/projects/project-brainstorm/projects/ylune",
                "--out",
                PROJECT_BRAINSTORM_PROOF.as_posix(),
            ),
            (
                ArtifactSelector(
                    PROJECT_BRAINSTORM_PROOF,
                    require_pass=True,
                    expected_feature=FEATURE_ID,
                ),
            ),
        ),
    )


def _qg5_specs(pytest: tuple[str, ...]) -> tuple[CommandSpec, ...]:
    receipt_names = (
        "qg1-contract.json",
        "qg2-destructive-safety.json",
        "qg3-single-canvas.json",
        "qg4-run-retention.json",
        "qg5-regression.json",
        "qg6-consumer-proof.json",
        "qe7-large-tree.json",
    )
    receipts = tuple(
        ArtifactSelector(
            FEATURE_074_CHECKS / name,
            require_pass=True,
            expected_feature="074-penflow-doctor-consumer-project-hygiene",
        )
        for name in receipt_names
    )
    return (
        CommandSpec(
            "feature-074-focused",
            pytest
            + (
                "tests/test_consumer_project_hygiene.py",
                "tests/test_quality_gate_receipt.py",
                "-q",
            ),
            receipts,
        ),
    )


def _qg6_specs(python: str, pytest: tuple[str, ...]) -> tuple[CommandSpec, ...]:
    feature_074 = "074-penflow-doctor-consumer-project-hygiene"
    authoritative = FEATURE_074_CHECKS / "qg6-consumer-proof.json"
    return (
        CommandSpec(
            "exact-consumer-identities",
            pytest + ("tests/test_consumer_project_hygiene.py", "-q"),
        ),
        CommandSpec(
            "consumer-live-copy-proof",
            (
                python,
                "tests/consumer_project_hygiene_probe.py",
                "--search-root",
                "~/projects",
                "--expected-inventory-receipt",
                authoritative.as_posix(),
                "--out",
                CONSUMER_PROOF.as_posix(),
            ),
            (
                ArtifactSelector(CONSUMER_PROOF, True, feature_074),
                ArtifactSelector(authoritative, True, feature_074),
            ),
        ),
    )


def run_gate(
    *,
    feature: str,
    gate: str,
    project: Path,
    output: Path,
    command_runner: CommandRunner | None = None,
) -> JsonObject:
    """Execute one validated registry gate and persist its schema-1 receipt."""

    root, output_path = _validate_invocation(feature, gate, project, output)
    specs = gate_command_specs(gate)
    runner = command_runner or _run_command
    timeout = QE7_TIMEOUT_SECONDS if gate == "qe7" else DEFAULT_TIMEOUT_SECONDS
    transcript_directory = output_path.parent / "transcripts"
    assertions, commands, artifacts = _execute_specs(
        specs,
        root=root,
        transcript_directory=transcript_directory,
        gate=gate,
        runner=runner,
        timeout=timeout,
    )
    status = "PASS" if assertions and all(row.endswith(":PASS") for row in assertions) else "FAIL"
    receipt: JsonObject = {
        "schema_version": 1,
        "stable_result": {
            "feature": FEATURE_ID,
            "gate": gate,
            "status": status,
            "commands": commands,
            "artifacts": [artifacts[path] for path in sorted(artifacts)],
            "assertions": assertions,
        },
        "diagnostics": {"observed_at": datetime.now(UTC).isoformat()},
    }
    _atomic_write_json(output_path, receipt)
    return receipt


def _execute_specs(
    specs: Sequence[CommandSpec],
    *,
    root: Path,
    transcript_directory: Path,
    gate: str,
    runner: CommandRunner,
    timeout: int,
) -> tuple[list[str], list[dict[str, object]], dict[str, dict[str, str]]]:
    """Execute validated specs and collect transcript-bound gate evidence."""

    assertions: list[str] = []
    commands: list[dict[str, object]] = []
    artifacts: dict[str, dict[str, str]] = {}
    for index, spec in enumerate(specs, start=1):
        _validate_command(spec)
        result = _execute_command(spec, root=root, runner=runner, timeout=timeout)
        stdout_path = transcript_directory / f"{gate}-{index:02d}-{spec.name}.out"
        stderr_path = transcript_directory / f"{gate}-{index:02d}-{spec.name}.err"
        _atomic_write_bytes(stdout_path, result.stdout)
        _atomic_write_bytes(stderr_path, result.stderr)
        commands.append(
            {
                "name": spec.name,
                "argv": list(spec.argv),
                "exit_code": result.returncode,
                "stdout_path": stdout_path.relative_to(root).as_posix(),
                "stdout_sha256": _sha256_bytes(result.stdout),
                "stderr_path": stderr_path.relative_to(root).as_posix(),
                "stderr_sha256": _sha256_bytes(result.stderr),
            }
        )
        assertions.append(f"command:{spec.name}:exit_zero:{_pass(result.returncode == 0)}")
        for selector in spec.artifacts:
            artifact_path = _contained(root, root / selector.path)
            present = artifact_path.is_file() and not artifact_path.is_symlink()
            assertions.append(f"artifact:{selector.path}:present:{_pass(present)}")
            if not present:
                continue
            passes = not selector.require_pass or _artifact_passes(
                artifact_path,
                expected_feature=selector.expected_feature,
            )
            assertions.append(f"artifact:{selector.path}:contract:{_pass(passes)}")
            artifacts[selector.path.as_posix()] = {
                "path": selector.path.as_posix(),
                "sha256": _sha256_file(artifact_path),
            }
    return assertions, commands, artifacts


def _execute_command(
    spec: CommandSpec,
    *,
    root: Path,
    runner: CommandRunner,
    timeout: int,
) -> CommandResult:
    """Run one bounded argv-only command and normalize infrastructure failures."""

    try:
        return runner(spec.argv, root, timeout)
    except subprocess.TimeoutExpired as error:
        return CommandResult(124, _timeout_bytes(error.stdout), _timeout_bytes(error.stderr))
    except OSError as error:
        return CommandResult(127, b"", f"{type(error).__name__}: {error}\n".encode())


def validate_receipt(receipt_path: Path, project: Path) -> None:
    """Rehash every transcript and artifact bound by a Feature 075 receipt."""

    root = project.resolve()
    path = receipt_path if receipt_path.is_absolute() else root / receipt_path
    try:
        payload = json.loads(_contained(root, path).read_text(encoding="utf-8"))
        stable = payload["stable_result"]
        if stable["feature"] != FEATURE_ID or stable["status"] != "PASS":
            raise ReceiptValidationError("receipt feature/status contract is invalid")
        for command in stable["commands"]:
            for channel in ("stdout", "stderr"):
                evidence = _contained(root, root / command[f"{channel}_path"])
                if _sha256_file(evidence) != command[f"{channel}_sha256"]:
                    raise ReceiptValidationError(f"transcript hash mismatch: {evidence}")
        for artifact in stable["artifacts"]:
            evidence = _contained(root, root / artifact["path"])
            if _sha256_file(evidence) != artifact["sha256"]:
                raise ReceiptValidationError(f"artifact hash mismatch: {evidence}")
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as error:
        raise ReceiptValidationError("receipt is unreadable or malformed") from error


def main(argv: Sequence[str] | None = None) -> int:
    """Parse the closed runner CLI and return zero only for a validated PASS."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--feature", required=True)
    parser.add_argument("--gate", required=True)
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        receipt = run_gate(
            feature=args.feature,
            gate=args.gate,
            project=args.project,
            output=args.out,
        )
        validate_receipt(args.out, args.project)
    except (GateConfigurationError, ReceiptValidationError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    return 0 if receipt["stable_result"]["status"] == "PASS" else 1


def _validate_invocation(feature: str, gate: str, project: Path, output: Path) -> tuple[Path, Path]:
    if feature != FEATURE_ID:
        raise GateConfigurationError(f"unknown feature: {feature}")
    _require_gate(gate)
    root = project.expanduser().resolve()
    if not root.is_dir():
        raise GateConfigurationError(f"project is not a directory: {project}")
    expected = (root / FEATURE_075_GATE_RECEIPTS[gate]).resolve()
    candidate = (output if output.is_absolute() else root / output).resolve(strict=False)
    if candidate != expected:
        raise GateConfigurationError(
            f"--out must equal {FEATURE_075_GATE_RECEIPTS[gate].as_posix()}"
        )
    return root, candidate


def _require_gate(gate: str) -> None:
    if gate not in FEATURE_075_GATE_RECEIPTS:
        raise GateConfigurationError(f"unknown gate: {gate}")


def _validate_command(spec: CommandSpec) -> None:
    if not spec.name or not spec.argv or any("\0" in argument for argument in spec.argv):
        raise GateConfigurationError(f"invalid command spec: {spec.name!r}")


def _artifact_passes(path: Path, *, expected_feature: str | None) -> bool:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(payload, dict):
        return False
    stable = payload.get("stable_result")
    status = stable.get("status") if isinstance(stable, dict) else payload.get("status")
    feature = stable.get("feature") if isinstance(stable, dict) else payload.get("feature")
    return status == "PASS" and (expected_feature is None or feature == expected_feature)


def _run_command(argv: tuple[str, ...], cwd: Path, timeout: int) -> CommandResult:
    completed = subprocess.run(
        list(argv),
        cwd=cwd,
        check=False,
        capture_output=True,
        timeout=timeout,
        env={**os.environ, "LC_ALL": "C", "GIT_TERMINAL_PROMPT": "0"},
    )
    return CommandResult(completed.returncode, completed.stdout, completed.stderr)


def _contained(root: Path, path: Path) -> Path:
    resolved = path.resolve(strict=False)
    if resolved != root and not resolved.is_relative_to(root):
        raise GateConfigurationError(f"evidence path escapes project: {path}")
    return resolved


def _atomic_write_json(path: Path, payload: Mapping[str, object]) -> None:
    encoded = (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()
    _atomic_write_bytes(path, encoded)


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _timeout_bytes(value: bytes | str | None) -> bytes:
    if value is None:
        return b""
    return value if isinstance(value, bytes) else value.encode()


def _pass(condition: bool) -> str:
    return "PASS" if condition else "FAIL"


if __name__ == "__main__":
    raise SystemExit(main())
