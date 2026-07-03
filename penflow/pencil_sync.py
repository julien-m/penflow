"""Pencil editor-to-disk sync verification."""

from __future__ import annotations

import platform
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

from .pen import inspect_pen


@dataclass(frozen=True)
class SaveOutcome:
    ok: bool
    method: str
    message: str
    returncode: int | None = None
    stdout: str = ""
    stderr: str = ""


class PencilSyncError(RuntimeError):
    """Raised when pencil-sync cannot inspect its target file."""


SaveRunner = Callable[[Path], SaveOutcome]


def sync_pencil_to_disk(
    pen: str | Path,
    *,
    expect_min_nodes: int | None = None,
    expect_screens: int | None = None,
    save_runner: SaveRunner | None = None,
) -> dict[str, Any]:
    """Save the open Pencil document, then verify the `.pen` persisted to disk."""
    pen_path = Path(pen)
    if not pen_path.exists():
        raise PencilSyncError(f".pen file not found: {pen_path}")
    if expect_min_nodes is not None and expect_min_nodes < 0:
        raise PencilSyncError("--expect-min-nodes must be >= 0")
    if expect_screens is not None and expect_screens < 0:
        raise PencilSyncError("--expect-screens must be >= 0")

    before_stat = pen_path.stat()
    before_inspect = inspect_pen(pen_path)
    runner = save_runner or run_pencil_save_via_osascript
    save = runner(pen_path)
    after_stat = pen_path.stat()
    after_inspect = inspect_pen(pen_path)

    checks = {
        "mtime_advanced": after_stat.st_mtime_ns > before_stat.st_mtime_ns,
        "min_nodes": _expectation(
            actual=int(after_inspect["node_count"]),
            expected=expect_min_nodes,
        ),
        "screens": _expectation(
            actual=len(after_inspect["screens"]),
            expected=expect_screens,
        ),
    }
    status = (
        "PASS" if save.ok and checks["mtime_advanced"] and _expectations_pass(checks) else "FAIL"
    )
    return {
        "kind": "penflow-pencil-sync",
        "status": status,
        "pen": str(pen_path),
        "message": _message(status, save, checks),
        "save": asdict(save),
        "before": _inspection_summary(before_stat.st_mtime_ns, before_inspect),
        "after": _inspection_summary(after_stat.st_mtime_ns, after_inspect),
        "checks": checks,
    }


def run_pencil_save_via_osascript(pen_path: Path) -> SaveOutcome:
    """Trigger Pencil's File > Save menu with AppleScript."""
    if platform.system() != "Darwin":
        return SaveOutcome(
            ok=False,
            method="osascript",
            message="pencil-sync requires macOS osascript to trigger Pencil File > Save",
        )

    script = f"""
tell application "Pencil"
    activate
end tell
delay 0.5
tell application "System Events"
    tell process "Pencil"
        set frontmost to true
        delay 0.3
        click menu item "Save" of menu "File" of menu bar 1
    end tell
end tell
-- target: {pen_path}
"""
    try:
        completed = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            check=False,
            text=True,
            timeout=10,
        )
    except subprocess.TimeoutExpired as error:
        return SaveOutcome(
            ok=False,
            method="osascript",
            message="Pencil File > Save timed out",
            stdout=(error.stdout or "").strip() if isinstance(error.stdout, str) else "",
            stderr=(error.stderr or "").strip() if isinstance(error.stderr, str) else "",
        )
    ok = completed.returncode == 0
    return SaveOutcome(
        ok=ok,
        method="osascript",
        message="Pencil File > Save triggered" if ok else "Pencil File > Save failed",
        returncode=completed.returncode,
        stdout=completed.stdout.strip(),
        stderr=completed.stderr.strip(),
    )


def _inspection_summary(mtime_ns: int, inspected: dict[str, Any]) -> dict[str, Any]:
    return {
        "mtime_ns": mtime_ns,
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
        return "Pencil editor state persisted and disk inspection met expectations."
    if not save.ok:
        return _not_persisted_message(f"save failed: {save.message}")
    if not checks["mtime_advanced"]:
        return _not_persisted_message("mtime did not advance after File > Save")
    failed = [
        name
        for name in ("min_nodes", "screens")
        if isinstance(checks.get(name), dict) and not checks[name]["passed"]
    ]
    return "Pencil saved, but disk inspection did not meet expectations: " + ", ".join(failed)


def _not_persisted_message(reason: str) -> str:
    return (
        "Pencil editor did not persist the file - "
        f"is the file open, is the app running, and is Accessibility permission granted? ({reason})"
    )
