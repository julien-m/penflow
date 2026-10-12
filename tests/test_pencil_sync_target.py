# @spec AC-001: save addressed to the single pen.dev process — .specs/features/078-pen-dev-operator-compatibility/spec.md#ac-001
# @spec AC-002: ambiguous or missing targets never run a script — .specs/features/078-pen-dev-operator-compatibility/spec.md#ac-002
# @spec AC-003: explicit app precedence — .specs/features/078-pen-dev-operator-compatibility/spec.md#ac-003
# @spec AC-009: trigger contract stays UNVERIFIED — .specs/features/078-pen-dev-operator-compatibility/spec.md#ac-009
"""pen.dev save target resolution never reaches a legacy Pencil copy."""

from __future__ import annotations

import json
import plistlib
import subprocess
from pathlib import Path

import pytest

from penflow import save_helper
from penflow.pencil_sync import (
    PenTargetError,
    SaveOutcome,
    build_save_script,
    find_pen_process,
    resolve_pen_app,
    run_pencil_save_via_osascript,
    sync_pencil_to_disk,
)

BUNDLE_ID = "dev.pencil.desktop"


@pytest.fixture(autouse=True)
def isolate_real_save_helper(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Never pick up a Penflow Save.app installed on the machine running the tests."""
    monkeypatch.delenv("PENFLOW_SAVE_HELPER", raising=False)
    monkeypatch.setattr(save_helper, "DEFAULT_HELPER_DIR", tmp_path / "no-helper")


def make_bundle(root: Path, name: str = "Pen.app", executable: str = "Pen") -> Path:
    bundle = root / name
    (bundle / "Contents" / "MacOS").mkdir(parents=True)
    with (bundle / "Contents" / "Info.plist").open("wb") as stream:
        plistlib.dump({"CFBundleIdentifier": BUNDLE_ID, "CFBundleExecutable": executable}, stream)
    return bundle


def executable_of(bundle: Path, name: str = "Pen") -> str:
    return str(bundle / "Contents" / "MacOS" / name)


class RecordingExecutor:
    def __init__(self, stdout: str = "menu\n", returncode: int = 0) -> None:
        self.scripts: list[str] = []
        self.stdout = stdout
        self.returncode = returncode

    def __call__(self, script: str) -> subprocess.CompletedProcess[str]:
        self.scripts.append(script)
        return subprocess.CompletedProcess(["osascript"], self.returncode, self.stdout, "")


def test_single_pen_process_is_addressed_by_unix_id_beside_a_legacy_pencil(
    tmp_path: Path,
) -> None:
    pen = make_bundle(tmp_path / "user")
    legacy = make_bundle(tmp_path / "backups", "Pencil.app", "Pencil")
    executor = RecordingExecutor()

    outcome = run_pencil_save_via_osascript(
        tmp_path / "ui.pen",
        environ={},
        search_dirs=(tmp_path / "system", tmp_path / "user"),
        process_lister=lambda: [
            (42615, executable_of(legacy, "Pencil")),
            (17575, executable_of(pen)),
        ],
        executor=executor,
        system="Darwin",
    )

    assert outcome.ok is True
    assert outcome.method == "osascript:menu"
    assert outcome.target == {
        "app_path": str(pen),
        "bundle_id": BUNDLE_ID,
        "executable": executable_of(pen),
        "pid": 17575,
    }
    (script,) = executor.scripts
    assert "whose unix id is 17575" in script
    assert "42615" not in script
    assert 'application "Pencil"' not in script and 'process "Pencil"' not in script


def test_generated_script_saves_by_menu_then_shortcut_on_the_same_process() -> None:
    script = build_save_script(17575)
    assert "first application process whose unix id is 17575" in script
    assert script.index("set frontmost of penProcess to true") < script.index("tell penProcess")
    assert 'click menu item "Save" of menu "File" of menu bar 1' in script
    assert 'keystroke "s" using command down' in script


@pytest.mark.parametrize("installs", [0, 2])
def test_zero_or_several_bundles_fail_without_running_a_script(
    tmp_path: Path, installs: int
) -> None:
    dirs = (tmp_path / "system", tmp_path / "user")
    for directory in dirs[:installs]:
        make_bundle(directory)
    executor = RecordingExecutor()

    outcome = run_pencil_save_via_osascript(
        tmp_path / "ui.pen",
        environ={},
        search_dirs=dirs,
        process_lister=lambda: [],
        executor=executor,
        system="Darwin",
    )

    assert outcome.ok is False
    assert executor.scripts == []
    assert "expected exactly one Pen.app" in outcome.message
    assert "--app" in outcome.message
    assert str(dirs[0]) in outcome.message and str(dirs[1]) in outcome.message
    if installs == 2:
        assert str(dirs[0] / "Pen.app") in outcome.message
        assert str(dirs[1] / "Pen.app") in outcome.message


@pytest.mark.parametrize(("pids", "fragment"), [([], "is not running"), ([1, 2], "runs 2 times")])
def test_missing_or_duplicate_process_fails_without_running_a_script(
    tmp_path: Path, pids: list[int], fragment: str
) -> None:
    pen = make_bundle(tmp_path / "user")
    executor = RecordingExecutor()

    outcome = run_pencil_save_via_osascript(
        tmp_path / "ui.pen",
        app=pen,
        process_lister=lambda: [(pid, executable_of(pen)) for pid in pids],
        executor=executor,
        system="Darwin",
    )

    assert outcome.ok is False
    assert executor.scripts == []
    assert fragment in outcome.message
    assert "open ui.pen in pen.dev" in outcome.message


def test_explicit_app_wins_over_environment_and_defaults(tmp_path: Path) -> None:
    explicit = make_bundle(tmp_path / "explicit")
    env_bundle = make_bundle(tmp_path / "env")
    make_bundle(tmp_path / "user")
    defaults = (tmp_path / "user",)

    assert (
        resolve_pen_app(
            explicit, environ={"PENFLOW_PEN_APP": str(env_bundle)}, search_dirs=defaults
        )
        == explicit
    )
    assert resolve_pen_app(None, environ={}, search_dirs=defaults) == tmp_path / "user" / "Pen.app"
    assert (
        resolve_pen_app(None, environ={"PENFLOW_PEN_APP": str(env_bundle)}, search_dirs=defaults)
        == env_bundle
    )
    assert (
        resolve_pen_app(None, environ={"PENFLOW_PEN_APP": str(env_bundle)}, search_dirs=())
        == env_bundle
    )


@pytest.mark.parametrize("kind", ["file", "missing-plist", "wrong-suffix"])
def test_explicit_path_that_is_not_a_bundle_fails(tmp_path: Path, kind: str) -> None:
    if kind == "file":
        target = tmp_path / "Pen.app"
        target.write_text("not a bundle")
    elif kind == "missing-plist":
        target = tmp_path / "Pen.app"
        target.mkdir()
    else:
        target = make_bundle(tmp_path).rename(tmp_path / "Pen.bundle")
    with pytest.raises(PenTargetError) as raised:
        resolve_pen_app(target, environ={})
    assert str(raised.value) == f"not a pen.dev application bundle: {target}"


def test_bundle_without_executable_is_rejected(tmp_path: Path) -> None:
    bundle = tmp_path / "Pen.app"
    (bundle / "Contents").mkdir(parents=True)
    with (bundle / "Contents" / "Info.plist").open("wb") as stream:
        plistlib.dump({"CFBundleIdentifier": BUNDLE_ID}, stream)
    with pytest.raises(PenTargetError) as raised:
        find_pen_process(bundle, process_lister=lambda: [])
    assert "CFBundleExecutable" in str(raised.value)


def test_non_macos_never_resolves_or_runs(tmp_path: Path) -> None:
    executor = RecordingExecutor()
    outcome = run_pencil_save_via_osascript(
        tmp_path / "ui.pen", executor=executor, system="Linux", process_lister=lambda: []
    )
    assert outcome.ok is False
    assert executor.scripts == []


def test_failed_target_resolution_keeps_trigger_contract_and_never_passes(tmp_path: Path) -> None:
    pen_path = tmp_path / "ui.pen"
    pen_path.write_text(json.dumps({"version": "2.11", "children": []}), encoding="utf-8")
    executor = RecordingExecutor()

    result = sync_pencil_to_disk(
        pen_path,
        save_runner=lambda path: run_pencil_save_via_osascript(
            path,
            environ={},
            search_dirs=(tmp_path / "none",),
            process_lister=lambda: [],
            executor=executor,
            system="Darwin",
        ),
    )

    assert result["status"] == "FAIL"
    assert result["persistence_status"] == "UNVERIFIED"
    assert result["closes_persistence"] is False
    assert result["checks"]["content_changed"] is False
    assert result["save"]["target"] is None
    assert "pen.dev target" in result["message"]
    assert executor.scripts == []


def test_shortcut_fallback_is_recorded_as_the_save_method(tmp_path: Path) -> None:
    pen = make_bundle(tmp_path / "user")
    outcome = run_pencil_save_via_osascript(
        tmp_path / "ui.pen",
        app=pen,
        process_lister=lambda: [(17575, executable_of(pen))],
        executor=RecordingExecutor(stdout="shortcut\n"),
        system="Darwin",
    )
    assert (outcome.ok, outcome.method) == (True, "osascript:shortcut")


def test_successful_save_through_the_resolved_process_records_its_target(tmp_path: Path) -> None:
    pen = make_bundle(tmp_path / "user")
    pen_path = tmp_path / "ui.pen"
    pen_path.write_text(json.dumps({"version": "2.11", "children": []}), encoding="utf-8")

    def saving_executor(script: str) -> subprocess.CompletedProcess[str]:
        pen_path.write_text(json.dumps({"version": "2.17", "children": []}), encoding="utf-8")
        return subprocess.CompletedProcess(["osascript"], 0, "menu\n", "")

    result = sync_pencil_to_disk(
        pen_path,
        save_runner=lambda path: run_pencil_save_via_osascript(
            path,
            app=pen,
            process_lister=lambda: [(17575, executable_of(pen))],
            executor=saving_executor,
            system="Darwin",
        ),
    )
    assert (result["status"], result["save"]["target"]["pid"]) == ("PASS", 17575)


def test_failed_save_never_passes_even_when_the_document_changed(tmp_path: Path) -> None:
    pen_path = tmp_path / "ui.pen"
    pen_path.write_text(json.dumps({"version": "2.11", "children": []}), encoding="utf-8")

    def changed_but_failed(path: Path) -> SaveOutcome:
        path.write_text(json.dumps({"version": "2.17", "children": []}), encoding="utf-8")
        return SaveOutcome(ok=False, method="osascript", message="pen.dev target: ambiguous")

    result = sync_pencil_to_disk(pen_path, save_runner=changed_but_failed)
    assert (result["checks"]["content_changed"], result["status"]) == (True, "FAIL")


def make_helper(directory: Path) -> Path:
    helper = directory / save_helper.HELPER_NAME
    (helper / "Contents").mkdir(parents=True)
    with (helper / "Contents" / "Info.plist").open("wb") as stream:
        plistlib.dump({"CFBundleIdentifier": save_helper.HELPER_BUNDLE_ID}, stream)
    return helper


class HelperOpen:
    def __init__(self, result: str) -> None:
        self.result = result
        self.commands: list[list[str]] = []

    def __call__(self, command: list[str]) -> subprocess.CompletedProcess[str]:
        self.commands.append(command)
        Path(command[-1]).write_text(self.result, encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "")


def test_installed_helper_saves_instead_of_direct_osascript(tmp_path: Path) -> None:
    pen = make_bundle(tmp_path / "user")
    helper = make_helper(tmp_path / "apps")
    opener, executor = HelperOpen("OK menu"), RecordingExecutor()
    outcome = run_pencil_save_via_osascript(
        tmp_path / "ui.pen",
        app=pen,
        environ={},
        process_lister=lambda: [(17575, executable_of(pen))],
        executor=executor,
        system="Darwin",
        helper_dir=tmp_path / "apps",
        helper_runner=opener,
    )
    assert (outcome.ok, outcome.method, outcome.helper) == (True, "helper:menu", str(helper))
    assert opener.commands[0][6:8] == ["17575", str(tmp_path / "ui.pen")]
    assert executor.scripts == []


@pytest.mark.parametrize(
    ("result", "remedy"),
    [
        ("DENIED not allowed assistive access", "Privacy & Security > Accessibility"),
        ("NOT_FOUND pid 17575", "open ui.pen in pen.dev"),
    ],
    ids=["denied", "not-found"],
)
def test_helper_refusals_fail_with_their_remedy(tmp_path: Path, result: str, remedy: str) -> None:
    pen = make_bundle(tmp_path / "user")
    make_helper(tmp_path / "apps")
    outcome = run_pencil_save_via_osascript(
        tmp_path / "ui.pen",
        app=pen,
        environ={},
        process_lister=lambda: [(17575, executable_of(pen))],
        executor=RecordingExecutor(),
        system="Darwin",
        helper_dir=tmp_path / "apps",
        helper_runner=HelperOpen(result),
    )
    assert outcome.ok is False
    assert remedy in outcome.message


def test_explicit_helper_that_is_not_a_bundle_fails_without_fallback(tmp_path: Path) -> None:
    pen = make_bundle(tmp_path / "user")
    executor = RecordingExecutor()
    outcome = run_pencil_save_via_osascript(
        tmp_path / "ui.pen",
        app=pen,
        environ={"PENFLOW_SAVE_HELPER": str(tmp_path / "Missing.app")},
        process_lister=lambda: [(17575, executable_of(pen))],
        executor=executor,
        system="Darwin",
        helper_runner=HelperOpen("OK menu"),
    )
    assert (outcome.ok, executor.scripts) == (False, [])
    assert "save helper not found" in outcome.message


def test_symlinked_install_matches_the_running_executable(tmp_path: Path) -> None:
    real = make_bundle(tmp_path / "real")
    (tmp_path / "linked").mkdir()
    linked = tmp_path / "linked" / "Pen.app"
    linked.symlink_to(real, target_is_directory=True)
    target = find_pen_process(linked, process_lister=lambda: [(17575, executable_of(real))])
    assert target.pid == 17575


def test_shortcut_fallback_rechecks_that_pen_dev_is_frontmost() -> None:
    script = build_save_script(17575)
    check = "if unix id of (first application process whose frontmost is true) is not 17575"
    assert script.index(check) < script.index('keystroke "s" using command down')


@pytest.mark.parametrize(
    ("result", "ok", "method"),
    [("OK shortcut", True, "helper:shortcut"), ("ERROR -1708 boom", False, "helper")],
    ids=["shortcut", "error"],
)
def test_helper_shortcut_and_error_results_reach_the_save_outcome(
    tmp_path: Path, result: str, ok: bool, method: str
) -> None:
    pen = make_bundle(tmp_path / "user")
    make_helper(tmp_path / "apps")
    outcome = run_pencil_save_via_osascript(
        tmp_path / "ui.pen",
        app=pen,
        environ={},
        process_lister=lambda: [(17575, executable_of(pen))],
        executor=RecordingExecutor(),
        system="Darwin",
        helper_dir=tmp_path / "apps",
        helper_runner=HelperOpen(result),
    )
    assert (outcome.ok, outcome.method) == (ok, method)
