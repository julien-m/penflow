"""Fixed-path pen.dev save helper (`Penflow Save.app`): install and invoke.

The helper is a background-only AppleScript applet. macOS grants Accessibility per
application, so granting it once to this stable bundle keeps `pencil-sync` working when
the agent host (Claude, Codex, a terminal) changes or updates.
"""

# @spec FR-009: versioned helper installed by Doctor, used by pencil-sync when present — .specs/features/078-pen-dev-operator-compatibility/spec.md#fr-009

from __future__ import annotations

import hashlib
import os
import plistlib
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

HELPER_NAME = "Penflow Save.app"
HELPER_BUNDLE_ID = "dev.penflow.save-helper"
# Bump when the applet source or its result protocol changes; Doctor then replaces it.
HELPER_VERSION = "1"
HELPER_ENV = "PENFLOW_SAVE_HELPER"
DEFAULT_HELPER_DIR = Path.home() / "Applications"
SOURCE_KEY = "PenflowSaveHelperSourceSHA256"
# The applet waits 0.3 s for focus plus one menu click; 20 s bounds a stuck System Events.
HELPER_TIMEOUT_SECONDS = 20
RESULT_STATUSES = ("OK", "DENIED", "NOT_FOUND", "ERROR")

# Flow: read the trailing `open --args` values (pid, document path, result file), save the
# frontmost document of that exact process through System Events (File > Save, else Cmd+S),
# and write one line `<STATUS> <detail>` to the result file because `open -W` does not
# forward the applet's exit status. -1719/-25211 mean Accessibility is missing and -1743
# means Automation (Apple Events) was refused.
HELPER_SOURCE = """use AppleScript version "2.4"
use framework "Foundation"
use scripting additions

-- Penflow Save helper version __VERSION__ (no top-level properties: an applet rewrites its
-- own script to persist them, which would break the signature and the Accessibility grant).

on run
	set argv to (current application's NSProcessInfo's processInfo()'s arguments()) as list
	if (count of argv) < 4 then return
	set resultPath to item -1 of argv
	try
		set targetPid to (item -3 of argv) as integer
		set outcome to my saveProcess(targetPid)
	on error errorMessage number errorNumber
		set outcome to "ERROR " & errorNumber & " " & errorMessage
	end try
	do shell script "printf %s " & quoted form of outcome & " > " & quoted form of resultPath
end run

on saveProcess(targetPid)
	try
		tell application "System Events"
			set matches to (application processes whose unix id is targetPid)
			if (count of matches) is 0 then return "NOT_FOUND pid " & targetPid
			set penProcess to item 1 of matches
			set frontmost of penProcess to true
			delay 0.3
			tell penProcess
				try
					click menu item "Save" of menu "File" of menu bar 1
					return "OK menu"
				on error
					if unix id of (first application process whose frontmost is true) is not targetPid then return "ERROR pen.dev is not frontmost; Save shortcut not sent"
					keystroke "s" using command down
					return "OK shortcut"
				end try
			end tell
		end tell
	on error errorMessage number errorNumber
		if errorNumber is in {-1719, -25211, -1743} then return "DENIED " & errorMessage
		return "ERROR " & errorNumber & " " & errorMessage
	end try
end saveProcess
"""

CommandRunner = Callable[[list[str]], subprocess.CompletedProcess[str]]


class SaveHelperError(RuntimeError):
    """Raised when the helper cannot be installed."""


@dataclass(frozen=True)
class HelperResult:
    """Parsed helper result file."""

    status: str
    detail: str


def helper_source() -> str:
    """Return the exact applet source for the current helper version."""
    return HELPER_SOURCE.replace("__VERSION__", HELPER_VERSION)


def run_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    """Run one local tool (osacompile, codesign, open); callers check the exit status."""
    return subprocess.run(
        command, capture_output=True, check=False, text=True, timeout=HELPER_TIMEOUT_SECONDS
    )


def install_save_helper(
    target_dir: Path | None = None,
    *,
    runner: CommandRunner | None = None,
) -> dict[str, Any]:
    """Install or refresh `Penflow Save.app` in ``target_dir`` idempotently.

    Args:
        target_dir: Directory receiving the bundle (default ``~/Applications``).
        runner: Executes ``osacompile`` and ``codesign``; injected by tests.

    Returns:
        ``{kind, status: installed|unchanged|replaced, path, version, source_sha256}``.

    Raises:
        SaveHelperError: If compilation or signing fails; the existing helper is kept.
    """
    target_dir = DEFAULT_HELPER_DIR if target_dir is None else target_dir
    runner = run_command if runner is None else runner
    source = helper_source()
    source_sha = hashlib.sha256(source.encode()).hexdigest()
    target = target_dir / HELPER_NAME
    previous = _installed_identity(target)
    if previous == (HELPER_VERSION, source_sha):
        return _report("unchanged", target, source_sha)
    target_dir.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".penflow-save-helper-", dir=target_dir))
    try:
        built = _build(staging, source, source_sha, runner)
        _swap_into_place(built, target)
    finally:
        shutil.rmtree(staging, ignore_errors=True)  # Only the staging copy Penflow created.
    return _report("installed" if previous is None else "replaced", target, source_sha)


def install_save_helper_report(target_dir: str | None) -> tuple[dict[str, Any], int]:
    """Doctor entry point: install the helper and map failures to a report with exit 1."""
    directory = Path(target_dir).expanduser() if target_dir else None
    try:
        return install_save_helper(directory), 0
    except (SaveHelperError, OSError, subprocess.SubprocessError) as error:
        return {"kind": "penflow-save-helper", "status": "failed", "message": str(error)}, 1


def resolve_save_helper(
    environ: Mapping[str, str] | None = None, default_dir: Path | None = None
) -> Path | None:
    """Return the helper bundle to use, or ``None`` for the direct osascript fallback.

    ``PENFLOW_SAVE_HELPER`` names an explicit bundle; otherwise the default install path is
    used when it exists.
    """
    env = os.environ if environ is None else environ
    explicit = env.get(HELPER_ENV)
    if explicit:
        return Path(explicit).expanduser()
    candidate = (DEFAULT_HELPER_DIR if default_dir is None else default_dir) / HELPER_NAME
    return candidate if (candidate / "Contents" / "Info.plist").is_file() else None


def run_helper_save(
    helper: Path, pid: int, pen_path: Path, *, runner: CommandRunner | None = None
) -> HelperResult:
    """Ask the helper to save the frontmost document of ``pid`` and read its result file."""
    if not (helper / "Contents" / "Info.plist").is_file():
        return HelperResult("ERROR", f"save helper not found: {helper}")
    with tempfile.TemporaryDirectory(prefix="penflow-save-") as scratch:
        result_file = Path(scratch) / "result.txt"
        # -W waits for the applet to quit; -n forces a fresh instance so the wait is real.
        command = ["open", "-W", "-n", "-a", str(helper), "--args"]
        try:
            completed = (run_command if runner is None else runner)(
                [*command, str(pid), str(pen_path), str(result_file)]
            )
        except subprocess.TimeoutExpired:
            return HelperResult("ERROR", f"save helper timed out after {HELPER_TIMEOUT_SECONDS}s")
        if completed.returncode != 0:
            return HelperResult("ERROR", f"open failed: {completed.stderr.strip()}")
        if not result_file.is_file():
            return HelperResult("ERROR", "save helper exited without writing a result")
        return parse_helper_result(result_file.read_text(encoding="utf-8"))


def parse_helper_result(text: str) -> HelperResult:
    """Parse ``<STATUS> <detail>``; anything else is an ``ERROR``."""
    status, _, detail = text.strip().partition(" ")
    if status not in RESULT_STATUSES:
        return HelperResult("ERROR", f"unknown save helper result: {text.strip()!r}")
    return HelperResult(status, detail)


def _installed_identity(target: Path) -> tuple[str, str] | None:
    try:
        with (target / "Contents" / "Info.plist").open("rb") as stream:
            info = plistlib.load(stream)
    except (OSError, plistlib.InvalidFileException):
        return None
    return str(info.get("CFBundleShortVersionString")), str(info.get(SOURCE_KEY))


def _build(staging: Path, source: str, source_sha: str, runner: CommandRunner) -> Path:
    script = staging / "penflow-save.applescript"
    script.write_text(source, encoding="utf-8")
    bundle = staging / HELPER_NAME
    _require(runner(["osacompile", "-o", str(bundle), str(script)]), "osacompile")
    info_path = bundle / "Contents" / "Info.plist"
    with info_path.open("rb") as stream:
        info = plistlib.load(stream)
    info.update(
        {
            "CFBundleIdentifier": HELPER_BUNDLE_ID,
            "CFBundleName": "Penflow Save",
            "CFBundleShortVersionString": HELPER_VERSION,
            "CFBundleVersion": HELPER_VERSION,
            "LSUIElement": True,
            "NSAppleEventsUsageDescription": "Penflow Save asks pen.dev to save the open .pen file.",
            SOURCE_KEY: source_sha,
        }
    )
    with info_path.open("wb") as stream:
        plistlib.dump(info, stream)
    # Editing Info.plist invalidates the ad hoc signature osacompile produced; re-sign it.
    _require(runner(["codesign", "--force", "--sign", "-", str(bundle)]), "codesign")
    return bundle


def _swap_into_place(built: Path, target: Path) -> None:
    """Rename the new bundle over the old one; the old one is kept until the rename succeeds."""
    retired = target.with_name(f".{HELPER_NAME}.previous")
    if retired.exists():
        shutil.rmtree(retired)  # A stale backup from an earlier Penflow install only.
    if target.exists():
        os.replace(target, retired)
    try:
        os.replace(built, target)
    except OSError:
        if retired.exists():
            os.replace(retired, target)  # Keep the working helper when the swap fails.
        raise
    if retired.exists():
        shutil.rmtree(retired)


def _require(completed: subprocess.CompletedProcess[str], tool: str) -> None:
    if completed.returncode != 0:
        raise SaveHelperError(f"{tool} failed: {completed.stderr.strip() or completed.returncode}")


def _report(status: str, target: Path, source_sha: str) -> dict[str, Any]:
    return {
        "kind": "penflow-save-helper",
        "status": status,
        "path": str(target),
        "version": HELPER_VERSION,
        "source_sha256": source_sha,
    }
