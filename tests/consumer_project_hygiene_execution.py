# @spec AC-014 AC-015 FR-012: Feature 074 real-consumer proof.
"""Real-consumer hygiene proof responsibility module."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path

from penflow.artifact_policy import MANAGED_IGNORE_BLOCK_LINES
from tests.consumer_project_hygiene_discovery import (
    DISCOVERY_PRUNE_NAMES,
    _git_bytes,
    _is_single_link_regular,
    _sha256_bytes,
    capture_layout_snapshot,
    capture_project_snapshot,
)
from tests.consumer_project_hygiene_types import (
    CommandResult,
    CommandRunner,
    ConsumerMarker,
    CopyExerciser,
    JsonReceipt,
    ProjectSnapshot,
)

COMMAND_TIMEOUT_SECONDS = 30
FEATURE_ID = "074-penflow-doctor-consumer-project-hygiene"


def _reject_live_mutation_paths(
    consumers: Sequence[ConsumerMarker],
    output: Path,
    temporary_parent: Path | None,
) -> None:
    candidate_paths = [output.resolve(strict=False)]
    if temporary_parent is not None:
        candidate_paths.append(temporary_parent.resolve(strict=False))
    for consumer in consumers:
        live_root = (
            consumer.project_root.resolve()
            if consumer.project_root is not None
            else consumer.ui_pen.parent.resolve()
        )
        for candidate in candidate_paths:
            if candidate == live_root or live_root in candidate.parents:
                raise ValueError(f"probe mutation path is inside live consumer: {candidate}")


def _inventory_receipt_row(consumer: ConsumerMarker) -> dict[str, object]:
    return {
        "label": consumer.label,
        "marker": consumer.marker_relative,
        "marker_sha256": consumer.marker_sha256,
        "companion": consumer.companion_relative,
        "companion_sha256": consumer.companion_sha256,
        "git_available": consumer.project_root is not None,
    }


def _check_live_consumer(consumer: ConsumerMarker, command_runner: CommandRunner) -> JsonReceipt:
    if consumer.project_root is None:
        is_git_consumer = False
        live_root = consumer.ui_pen.parent
        before = capture_layout_snapshot(live_root)
    else:
        is_git_consumer = True
        live_root = consumer.project_root
        before = capture_project_snapshot(live_root)
    argv = (
        sys.executable,
        "-m",
        "penflow",
        "doctor",
        "--project",
        str(live_root),
        "--check",
        "--json",
    )
    try:
        command_result = command_runner(argv, live_root, COMMAND_TIMEOUT_SECONDS)
        doctor_status, finding_codes, is_truthful = _parse_doctor_result(command_result)
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
        command_result = CommandResult(3, b"", str(error).encode())
        doctor_status, finding_codes, is_truthful = "ERROR", ["doctor_unavailable"], False
    after = (
        capture_project_snapshot(live_root)
        if is_git_consumer
        else capture_layout_snapshot(live_root)
    )
    zero_diff = before == after
    return {
        "status": "PASS" if is_truthful and zero_diff else "FAIL",
        "doctor_status": doctor_status,
        "doctor_exit": command_result.returncode,
        "finding_codes": finding_codes,
        "stdout_sha256": _sha256_bytes(command_result.stdout),
        "stderr_sha256": _sha256_bytes(command_result.stderr),
        "zero_diff": zero_diff,
        "before": _snapshot_receipt(before, git_available=is_git_consumer),
        "after": _snapshot_receipt(after, git_available=is_git_consumer),
    }


def _parse_doctor_result(result: CommandResult) -> tuple[str, list[str], bool]:
    try:
        payload = json.loads(result.stdout)
        stable = payload["stable_result"]
        status = stable["status"]
        findings = stable.get("findings", [])
        finding_codes = sorted(
            str(finding["code"])
            for finding in findings
            if isinstance(finding, dict) and "code" in finding
        )
    except (json.JSONDecodeError, KeyError, TypeError):
        return "ERROR", ["doctor_json_invalid"], False
    if result.returncode == 0:
        return str(status), finding_codes, status == "PASS"
    if result.returncode == 1:
        is_blocked = status in {"BLOCKED", "FAIL"} and bool(finding_codes)
        return str(status), finding_codes, is_blocked
    return str(status), finding_codes, False


def _snapshot_receipt(
    snapshot: ProjectSnapshot, *, git_available: bool = True
) -> dict[str, object]:
    return {
        "git_available": git_available,
        "index_sha256": snapshot.index_sha256,
        "porcelain_sha256": snapshot.porcelain_sha256,
        "tree_sha256": snapshot.tree_sha256,
        "entry_count": len(snapshot.files),
    }


def _check_consumer_copy(
    consumer: ConsumerMarker,
    exerciser: CopyExerciser,
    *,
    temporary_parent: Path | None,
) -> tuple[JsonReceipt, Path]:
    parent = temporary_parent
    if parent is not None:
        parent.mkdir(parents=True, exist_ok=True)
    copy_root = (
        Path(tempfile.mkdtemp(prefix=f"{consumer.label}-", dir=parent)) / "project"
    ).resolve()
    try:
        # A discovered handoff is the representative consumer layout. Copying its
        # entire host monorepo would import unrelated fixtures/archives and create
        # artificial multi-ui.pen ambiguity that is absent from the handoff itself.
        copied_marker = copy_root / "penflow" / "ui.pen"
        copied_marker.parent.mkdir(parents=True)
        shutil.copy2(consumer.ui_pen, copied_marker, follow_symlinks=False)
        companion = consumer.search_root / consumer.companion_relative
        copied_companion = copied_marker.parent / companion.relative_to(consumer.ui_pen.parent)
        copied_companion.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(companion, copied_companion, follow_symlinks=False)
        _initialize_copy_git(copy_root)
        evidence = dict(exerciser(copy_root, copied_marker))
        assertions = evidence.get("assertions")
        has_passing_assertions = (
            isinstance(assertions, list)
            and bool(assertions)
            and all(isinstance(row, str) and row.endswith(":PASS") for row in assertions)
        )
        contract_complete = (
            evidence.get("status") == "PASS"
            and evidence.get("doctor_fix_runs") == 2
            and evidence.get("producer_runs") == 2
            and has_passing_assertions
        )
        evidence["contract_complete"] = contract_complete
        evidence["status"] = "PASS" if contract_complete else "FAIL"
        return evidence, copy_root
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        return {
            "status": "FAIL",
            "finding": "copy_unavailable",
            "error_class": type(error).__name__,
        }, copy_root


def _copy_ignore(_directory: str, names: list[str]) -> set[str]:
    return {name for name in names if name in DISCOVERY_PRUNE_NAMES}


def _initialize_copy_git(copy_root: Path) -> None:
    _git_bytes(copy_root, "init", "-q")
    _git_bytes(copy_root, "config", "user.email", "penflow-probe@example.invalid")
    _git_bytes(copy_root, "config", "user.name", "Penflow Consumer Probe")
    _git_bytes(copy_root, "add", "--all")
    _git_bytes(copy_root, "commit", "-qm", "isolated consumer layout")


def _exercise_consumer_copy(
    copy_root: Path,
    copied_marker: Path,
    command_runner: CommandRunner,
) -> JsonReceipt:
    command_rows = _run_copy_commands(copy_root, copied_marker, command_runner)
    pen_paths = _copy_pen_paths(copy_root)
    ignore_count, tracked_temp, completed_payloads = _copy_hygiene_state(copy_root)
    assertions = {
        "commands_zero": all(row["exit_code"] == 0 for row in command_rows),
        "one_ui_pen": len(pen_paths) == 1 and Path(pen_paths[0]).name == "ui.pen",
        "one_ignore_block": ignore_count == 1,
        "no_tracked_temp": not tracked_temp,
        "no_completed_payload": not completed_payloads,
    }
    return {
        "status": "PASS" if all(assertions.values()) else "FAIL",
        "doctor_fix_runs": 2,
        "producer_runs": 2,
        "commands": command_rows,
        "pen_paths": pen_paths,
        "ignore_block_count": ignore_count,
        "tracked_temp_paths": sorted(tracked_temp),
        "completed_payloads": completed_payloads,
        "assertions": [
            f"{name}:{'PASS' if passed else 'FAIL'}" for name, passed in sorted(assertions.items())
        ],
    }


def _run_copy_commands(
    copy_root: Path, copied_marker: Path, command_runner: CommandRunner
) -> list[dict[str, object]]:
    commands = (
        ("doctor-fix-1", "doctor", "--project", str(copy_root), "--fix", "--json"),
        ("doctor-fix-2", "doctor", "--project", str(copy_root), "--fix", "--json"),
        (
            "producer-1",
            "export-expected",
            "--project",
            str(copy_root),
            str(copied_marker),
            "--out",
            str(copy_root / "expected-ui-tree.json"),
            "--json",
        ),
        (
            "producer-2",
            "export-expected",
            "--project",
            str(copy_root),
            str(copied_marker),
            "--out",
            str(copy_root / "expected-ui-tree.json"),
            "--json",
        ),
    )
    rows: list[dict[str, object]] = []
    for name, *command in commands:
        argv = (sys.executable, "-m", "penflow", *command)
        result = command_runner(argv, copy_root, COMMAND_TIMEOUT_SECONDS)
        rows.append(
            {
                "name": name,
                "exit_code": result.returncode,
                "stdout_sha256": _sha256_bytes(result.stdout),
                "stderr_sha256": _sha256_bytes(result.stderr),
            }
        )
    return rows


def _copy_pen_paths(copy_root: Path) -> list[str]:
    return sorted(
        path.relative_to(copy_root).as_posix()
        for path in copy_root.rglob("*.pen")
        if ".git" not in path.parts
        and ".penflow-tmp" not in path.parts
        and _is_single_link_regular(path)
    )


def _copy_hygiene_state(copy_root: Path) -> tuple[int, list[str], list[str]]:
    gitignore = copy_root / ".gitignore"
    begin_marker = MANAGED_IGNORE_BLOCK_LINES[0]
    ignore_count = (
        gitignore.read_text(encoding="utf-8").count(begin_marker) if gitignore.is_file() else 0
    )
    tracked_temp = _git_bytes(copy_root, "ls-files", "--", ".penflow-tmp").decode().splitlines()
    completed_payloads = (
        sorted(
            path.relative_to(copy_root).as_posix()
            for path in (copy_root / ".penflow-tmp" / "runs").glob("*")
        )
        if (copy_root / ".penflow-tmp" / "runs").is_dir()
        else []
    )
    return ignore_count, tracked_temp, completed_payloads


def _run_command(argv: tuple[str, ...], cwd: Path, timeout: int) -> CommandResult:
    # Penflow execution is argv-only with a hard timeout; no live command contains --fix.
    completed = subprocess.run(
        list(argv),
        cwd=cwd,
        check=False,
        capture_output=True,
        timeout=timeout,
    )
    return CommandResult(completed.returncode, completed.stdout, completed.stderr)


def _probe_receipt(
    *,
    status: str,
    assertions: Sequence[str],
    inventory_rows: Sequence[Mapping[str, object]],
    consumer_results: Sequence[Mapping[str, object]],
    diagnostics: Mapping[str, object],
) -> JsonReceipt:
    return {
        "schema_version": 1,
        "stable_result": {
            "feature": FEATURE_ID,
            "status": status,
            "inventory_count": len(inventory_rows),
            "inventory": list(inventory_rows),
            "consumers": list(consumer_results),
            "assertions": list(assertions),
        },
        "diagnostics": dict(diagnostics),
    }


def _atomic_write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()
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
