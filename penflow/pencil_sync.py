"""Operator-layer pen.dev save trigger and disk observation.

This module can trigger pen.dev on macOS, but its report never closes
persistence. The runtime-agnostic verifier lives in `pencil_persistence.py`.
"""

# @spec FR-001: resolve exactly one pen.dev bundle — .specs/features/078-pen-dev-operator-compatibility/spec.md#fr-001
# @spec FR-002: address the save to the exact process id — .specs/features/078-pen-dev-operator-compatibility/spec.md#fr-002
# @spec FR-003: C33 trigger contract keeps UNVERIFIED and records the target — .specs/features/078-pen-dev-operator-compatibility/spec.md#fr-003

from __future__ import annotations

import hashlib
import os
import platform
import plistlib
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .pen import inspect_pen

PEN_APP_ENV = "PENFLOW_PEN_APP"
PEN_APP_NAME = "Pen.app"
# pen.dev installs per machine or per user; both locations are searched, never the whole disk.
DEFAULT_PEN_APP_DIRS = (Path("/Applications"), Path.home() / "Applications")
# AppleScript round-trips stay short; a hung System Events call must not block the operator.
OSASCRIPT_TIMEOUT_SECONDS = 10
PS_TIMEOUT_SECONDS = 5


@dataclass(frozen=True)
class PenAppTarget:
    """The single pen.dev bundle and running process a save trigger may address."""

    app_path: str
    bundle_id: str | None
    executable: str
    pid: int


@dataclass(frozen=True)
class SaveOutcome:
    ok: bool
    method: str
    message: str
    returncode: int | None = None
    stdout: str = ""
    stderr: str = ""
    target: dict[str, Any] | None = None


class PencilSyncError(RuntimeError):
    """Raised when pencil-sync cannot inspect its target file."""


class PenTargetError(RuntimeError):
    """Raised when no single pen.dev application process can be addressed."""


SaveRunner = Callable[[Path], SaveOutcome]
ProcessLister = Callable[[], Sequence[tuple[int, str]]]
ScriptExecutor = Callable[[str], subprocess.CompletedProcess[str]]


def sync_pencil_to_disk(
    pen: str | Path,
    *,
    expect_min_nodes: int | None = None,
    expect_screens: int | None = None,
    app: str | Path | None = None,
    save_runner: SaveRunner | None = None,
) -> dict[str, Any]:
    """Trigger save and report disk changes without closing persistence.

    Args:
        pen: The `.pen` document expected to change on disk.
        expect_min_nodes: Optional minimum node count after the save.
        expect_screens: Optional minimum screen count after the save.
        app: Explicit pen.dev bundle for the default runner; ignored with ``save_runner``.
        save_runner: Injectable trigger; defaults to the pen.dev osascript runner.

    Returns:
        The ``penflow-pencil-sync`` report; persistence always remains ``UNVERIFIED``.

    Raises:
        PencilSyncError: If the document is missing or expectations are negative.
    """
    pen_path = _validated_request(Path(pen), expect_min_nodes, expect_screens)
    before_stat = pen_path.stat()
    before_sha256 = hashlib.sha256(pen_path.read_bytes()).hexdigest()
    before_inspect = inspect_pen(pen_path)
    runner = save_runner or (lambda path: run_pencil_save_via_osascript(path, app=app))
    save = runner(pen_path)
    after_stat = pen_path.stat()
    after_sha256 = hashlib.sha256(pen_path.read_bytes()).hexdigest()
    after_inspect = inspect_pen(pen_path)

    checks = {
        "mtime_advanced": after_stat.st_mtime_ns > before_stat.st_mtime_ns,
        "content_changed": after_sha256 != before_sha256,
        "min_nodes": _expectation(
            actual=int(after_inspect["node_count"]), expected=expect_min_nodes
        ),
        "screens": _expectation(actual=len(after_inspect["screens"]), expected=expect_screens),
    }
    status = (
        "PASS" if save.ok and checks["content_changed"] and _expectations_pass(checks) else "FAIL"
    )
    return {
        "kind": "penflow-pencil-sync",
        "status": status,
        "persistence_status": "UNVERIFIED",
        "closes_persistence": False,
        "pen": str(pen_path),
        "message": _message(status, save, checks),
        "save": asdict(save),
        "before": _inspection_summary(before_stat.st_mtime_ns, before_sha256, before_inspect),
        "after": _inspection_summary(after_stat.st_mtime_ns, after_sha256, after_inspect),
        "checks": checks,
    }


def _validated_request(
    pen_path: Path, expect_min_nodes: int | None, expect_screens: int | None
) -> Path:
    if not pen_path.exists():
        raise PencilSyncError(f".pen file not found: {pen_path}")
    if expect_min_nodes is not None and expect_min_nodes < 0:
        raise PencilSyncError("--expect-min-nodes must be >= 0")
    if expect_screens is not None and expect_screens < 0:
        raise PencilSyncError("--expect-screens must be >= 0")
    return pen_path


def resolve_pen_app(
    app: str | Path | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    search_dirs: Sequence[Path] = DEFAULT_PEN_APP_DIRS,
) -> Path:
    """Select exactly one pen.dev bundle: explicit ``app``, then ``PENFLOW_PEN_APP``, then defaults.

    Args:
        app: Explicit bundle path; when given, it is the only candidate.
        environ: Environment used for the ``PENFLOW_PEN_APP`` fallback.
        search_dirs: Directories searched for ``Pen.app`` when nothing explicit is given.

    Returns:
        The resolved bundle path.

    Raises:
        PenTargetError: If the explicit path is not a bundle or the default search finds
            zero or several bundles.
    """
    env = os.environ if environ is None else environ
    explicit = app if app is not None else env.get(PEN_APP_ENV) or None
    if explicit is not None:
        bundle = Path(explicit).expanduser()
        if bundle.suffix != ".app" or not (bundle / "Contents" / "Info.plist").is_file():
            raise PenTargetError(f"not a pen.dev application bundle: {bundle}")
        return bundle
    candidates = [
        directory / PEN_APP_NAME
        for directory in search_dirs
        if (directory / PEN_APP_NAME / "Contents" / "Info.plist").is_file()
    ]
    if len(candidates) != 1:
        found = ", ".join(str(path) for path in candidates) or "none"
        raise PenTargetError(
            f"expected exactly one {PEN_APP_NAME} in "
            f"{', '.join(str(d) for d in search_dirs)} (found: {found}); "
            f"pass --app or set {PEN_APP_ENV}"
        )
    return candidates[0]


def bundle_identity(bundle: Path) -> tuple[str | None, str]:
    """Read the bundle id and absolute executable path from a bundle's ``Info.plist``.

    Raises:
        PenTargetError: If the plist is unreadable or declares no executable.
    """
    try:
        with (bundle / "Contents" / "Info.plist").open("rb") as stream:
            info = plistlib.load(stream)
    except (OSError, plistlib.InvalidFileException) as error:
        raise PenTargetError(f"unreadable Info.plist in {bundle}: {error}") from error
    executable = info.get("CFBundleExecutable")
    if not isinstance(executable, str) or not executable:
        raise PenTargetError(f"no CFBundleExecutable in {bundle}")
    bundle_id = info.get("CFBundleIdentifier")
    return (
        bundle_id if isinstance(bundle_id, str) else None,
        str(bundle / "Contents" / "MacOS" / executable),
    )


def list_processes() -> list[tuple[int, str]]:
    """List ``(pid, executable path)`` pairs via ``ps``.

    `ps -axww -o pid=,comm=` prints one process per line with the full executable path on
    macOS (no truncation with ``ww``); unparseable lines are skipped because they cannot match
    an absolute bundle executable anyway.
    """
    completed = subprocess.run(
        ["ps", "-axww", "-o", "pid=,comm="],
        capture_output=True,
        check=True,
        text=True,
        timeout=PS_TIMEOUT_SECONDS,
    )
    processes = []
    for line in completed.stdout.splitlines():
        pid, _, command = line.strip().partition(" ")
        if pid.isdigit() and command:
            processes.append((int(pid), command.strip()))
    return processes


def find_pen_process(
    bundle: Path, *, process_lister: ProcessLister = list_processes
) -> PenAppTarget:
    """Match the single running process whose executable is exactly the bundle's executable.

    Raises:
        PenTargetError: If zero or several processes run that executable.
    """
    bundle_id, executable = bundle_identity(bundle)
    wanted = os.path.realpath(executable)
    pids = [pid for pid, command in process_lister() if os.path.realpath(command) == wanted]
    if len(pids) != 1:
        state = "is not running" if not pids else f"runs {len(pids)} times (pids {pids})"
        raise PenTargetError(
            f"{executable} {state}; open ui.pen in pen.dev and keep one instance running"
        )
    return PenAppTarget(str(bundle), bundle_id, executable, pids[0])


def build_save_script(pid: int) -> str:
    """Build the AppleScript that saves the frontmost document of one exact process.

    Flow: bring the process with this unix id to the front, click File > Save, and fall back
    to Cmd+S on the same process when the menu label is missing (localized menus). The script
    prints ``menu`` or ``shortcut`` so the caller records which path ran.
    """
    return f"""
tell application "System Events"
    set penProcess to first application process whose unix id is {pid}
    set frontmost of penProcess to true
    delay 0.3
    tell penProcess
        try
            click menu item "Save" of menu "File" of menu bar 1
            return "menu"
        on error
            keystroke "s" using command down
            return "shortcut"
        end try
    end tell
end tell
"""


def run_osascript(script: str) -> subprocess.CompletedProcess[str]:
    """Run one AppleScript; exit 0 means System Events accepted the save request."""
    return subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        check=False,
        text=True,
        timeout=OSASCRIPT_TIMEOUT_SECONDS,
    )


def run_pencil_save_via_osascript(
    pen_path: Path,
    *,
    app: str | Path | None = None,
    environ: Mapping[str, str] | None = None,
    search_dirs: Sequence[Path] = DEFAULT_PEN_APP_DIRS,
    process_lister: ProcessLister = list_processes,
    executor: ScriptExecutor = run_osascript,
    system: str | None = None,
) -> SaveOutcome:
    """Trigger File > Save in the single resolved pen.dev process.

    ``pen_path`` is not used by AppleScript: pen.dev saves its frontmost document, and the
    caller proves the effect by comparing the document digest before and after.
    """
    if (system or platform.system()) != "Darwin":
        return SaveOutcome(
            ok=False,
            method="osascript",
            message="pencil-sync requires macOS osascript to trigger pen.dev File > Save",
        )
    try:
        target = find_pen_process(
            resolve_pen_app(app, environ=environ, search_dirs=search_dirs),
            process_lister=process_lister,
        )
    except (PenTargetError, OSError, subprocess.SubprocessError) as error:
        return SaveOutcome(ok=False, method="osascript", message=f"pen.dev target: {error}")
    try:
        completed = executor(build_save_script(target.pid))
    except subprocess.TimeoutExpired as error:
        return SaveOutcome(
            ok=False,
            method="osascript",
            message="pen.dev File > Save timed out",
            stdout=error.stdout.strip() if isinstance(error.stdout, str) else "",
            stderr=error.stderr.strip() if isinstance(error.stderr, str) else "",
            target=asdict(target),
        )
    ok = completed.returncode == 0
    path_taken = completed.stdout.strip()
    return SaveOutcome(
        ok=ok,
        method=f"osascript:{path_taken}" if ok and path_taken else "osascript",
        message="pen.dev File > Save triggered" if ok else "pen.dev File > Save failed",
        returncode=completed.returncode,
        stdout=path_taken,
        stderr=completed.stderr.strip(),
        target=asdict(target),
    )


def _inspection_summary(
    mtime_ns: int,
    sha256: str,
    inspected: dict[str, Any],
) -> dict[str, Any]:
    return {
        "mtime_ns": mtime_ns,
        "sha256": sha256,
        "node_count": inspected["node_count"],
        "screen_count": len(inspected["screens"]),
        "screens": inspected["screens"],
    }


def _expectation(*, actual: int, expected: int | None) -> dict[str, Any]:
    return {
        "actual": actual,
        "expected": expected,
        "passed": True if expected is None else actual >= expected,
    }


def _expectations_pass(checks: dict[str, Any]) -> bool:
    return bool(checks["min_nodes"]["passed"] and checks["screens"]["passed"])


def _message(status: str, save: SaveOutcome, checks: dict[str, Any]) -> str:
    if status == "PASS":
        return (
            "pen.dev save trigger changed disk bytes and inspection met expectations; "
            "persistence remains UNVERIFIED until a persistence receipt passes."
        )
    if not save.ok:
        return _not_persisted_message(f"save failed: {save.message}")
    if not checks["content_changed"]:
        return _not_persisted_message("document digest did not change after File > Save")
    failed = [
        name
        for name in ("min_nodes", "screens")
        if isinstance(checks.get(name), dict) and not checks[name]["passed"]
    ]
    return "pen.dev saved, but disk inspection did not meet expectations: " + ", ".join(failed)


def _not_persisted_message(reason: str) -> str:
    return (
        "pen.dev editor did not persist the file - "
        "is ui.pen open in pen.dev, is the app running, and is Accessibility permission "
        f"granted? ({reason})"
    )
