# @spec AC-012: versioned helper installed idempotently by Doctor — .specs/features/078-pen-dev-operator-compatibility/spec.md#ac-012
# @spec AC-013: helper invocation and result mapping — .specs/features/078-pen-dev-operator-compatibility/spec.md#ac-013
"""`Penflow Save.app` is installed only where asked and speaks a closed result protocol."""

from __future__ import annotations

import json
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from penflow import cli, save_helper
from penflow.save_helper import (
    HELPER_BUNDLE_ID,
    HELPER_NAME,
    HELPER_VERSION,
    SaveHelperError,
    install_save_helper,
    parse_helper_result,
    resolve_save_helper,
    run_helper_save,
)


class FakeTools:
    """Stands in for osacompile/codesign: builds a minimal bundle and records commands."""

    def __init__(self, fail: str | None = None) -> None:
        self.commands: list[list[str]] = []
        self.fail = fail

    def __call__(self, command: list[str]) -> subprocess.CompletedProcess[str]:
        self.commands.append(command)
        if command[0] == self.fail:
            return subprocess.CompletedProcess(command, 1, "", f"{command[0]} refused")
        if command[0] == "osacompile":
            bundle = Path(command[2])
            (bundle / "Contents" / "MacOS").mkdir(parents=True)
            with (bundle / "Contents" / "Info.plist").open("wb") as stream:
                plistlib.dump({"CFBundleExecutable": "applet", "CFBundleName": "x"}, stream)
        return subprocess.CompletedProcess(command, 0, "", "")


def info(bundle: Path) -> dict:
    with (bundle / "Contents" / "Info.plist").open("rb") as stream:
        return plistlib.load(stream)


def test_install_builds_a_background_versioned_signed_bundle(tmp_path: Path) -> None:
    tools = FakeTools()
    report = install_save_helper(tmp_path, runner=tools)
    bundle = tmp_path / HELPER_NAME
    plist = info(bundle)
    assert (report["status"], report["path"]) == ("installed", str(bundle))
    assert (plist["CFBundleIdentifier"], plist["CFBundleShortVersionString"]) == (
        HELPER_BUNDLE_ID,
        HELPER_VERSION,
    )
    assert plist["LSUIElement"] is True
    assert plist[save_helper.SOURCE_KEY] == report["source_sha256"]
    assert [command[0] for command in tools.commands] == ["osacompile", "codesign"]
    assert tools.commands[1][:4] == ["codesign", "--force", "--sign", "-"]
    assert sorted(path.name for path in tmp_path.iterdir()) == [HELPER_NAME]


def test_second_install_of_the_same_version_is_unchanged(tmp_path: Path) -> None:
    install_save_helper(tmp_path, runner=FakeTools())
    tools = FakeTools()
    report = install_save_helper(tmp_path, runner=tools)
    assert (report["status"], tools.commands) == ("unchanged", [])


def test_new_version_replaces_the_bundle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    install_save_helper(tmp_path, runner=FakeTools())
    monkeypatch.setattr(save_helper, "HELPER_VERSION", "2")
    report = install_save_helper(tmp_path, runner=FakeTools())
    assert (report["status"], info(tmp_path / HELPER_NAME)["CFBundleShortVersionString"]) == (
        "replaced",
        "2",
    )
    assert sorted(path.name for path in tmp_path.iterdir()) == [HELPER_NAME]


@pytest.mark.parametrize("tool", ["osacompile", "codesign"])
def test_failed_build_keeps_the_installed_helper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tool: str
) -> None:
    install_save_helper(tmp_path, runner=FakeTools())
    before = (tmp_path / HELPER_NAME / "Contents" / "Info.plist").read_bytes()
    monkeypatch.setattr(save_helper, "HELPER_VERSION", "2")
    with pytest.raises(SaveHelperError) as raised:
        install_save_helper(tmp_path, runner=FakeTools(fail=tool))
    assert tool in str(raised.value)
    assert (tmp_path / HELPER_NAME / "Contents" / "Info.plist").read_bytes() == before
    assert sorted(path.name for path in tmp_path.iterdir()) == [HELPER_NAME]


@pytest.mark.parametrize(
    ("text", "status", "detail"),
    [
        ("OK menu", "OK", "menu"),
        ("OK shortcut\n", "OK", "shortcut"),
        ("DENIED not allowed assistive access", "DENIED", "not allowed assistive access"),
        ("NOT_FOUND pid 42", "NOT_FOUND", "pid 42"),
        ("ERROR -1708 oops", "ERROR", "-1708 oops"),
        ("YES", "ERROR", "unknown save helper result: 'YES'"),
        ("", "ERROR", "unknown save helper result: ''"),
    ],
    ids=["ok-menu", "ok-shortcut", "denied", "not-found", "error", "unknown", "empty"],
)
def test_helper_results_use_a_closed_status_set(text: str, status: str, detail: str) -> None:
    assert parse_helper_result(text) == save_helper.HelperResult(status, detail)


def make_fake_helper(directory: Path) -> Path:
    helper = directory / HELPER_NAME
    (helper / "Contents").mkdir(parents=True)
    with (helper / "Contents" / "Info.plist").open("wb") as stream:
        plistlib.dump({"CFBundleIdentifier": HELPER_BUNDLE_ID}, stream)
    return helper


class FakeOpen:
    """Records `open` calls and writes a helper result into the requested result file."""

    def __init__(self, result: str | None, returncode: int = 0) -> None:
        self.result = result
        self.returncode = returncode
        self.commands: list[list[str]] = []

    def __call__(self, command: list[str]) -> subprocess.CompletedProcess[str]:
        self.commands.append(command)
        if self.result is not None:
            Path(command[-1]).write_text(self.result, encoding="utf-8")
        return subprocess.CompletedProcess(command, self.returncode, "", "no app")


def test_helper_is_opened_with_wait_new_instance_and_a_fresh_result_file(tmp_path: Path) -> None:
    helper = make_fake_helper(tmp_path)
    opener = FakeOpen("OK menu")
    result = run_helper_save(helper, 17575, tmp_path / "ui.pen", runner=opener)
    (command,) = opener.commands
    assert result == save_helper.HelperResult("OK", "menu")
    assert command[:6] == ["open", "-W", "-n", "-a", str(helper), "--args"]
    assert command[6:8] == ["17575", str(tmp_path / "ui.pen")]
    assert not Path(command[8]).exists()


@pytest.mark.parametrize(
    ("opener", "fragment"),
    [
        (FakeOpen(None), "exited without writing a result"),
        (FakeOpen("OK menu", returncode=1), "open failed"),
    ],
    ids=["missing-result", "open-failed"],
)
def test_missing_result_or_failed_open_is_an_error(
    tmp_path: Path, opener: FakeOpen, fragment: str
) -> None:
    result = run_helper_save(make_fake_helper(tmp_path), 1, tmp_path / "ui.pen", runner=opener)
    assert result.status == "ERROR" and fragment in result.detail


def test_helper_timeout_is_an_error(tmp_path: Path) -> None:
    def stuck(command: list[str]) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(command, save_helper.HELPER_TIMEOUT_SECONDS)

    result = run_helper_save(make_fake_helper(tmp_path), 1, tmp_path / "ui.pen", runner=stuck)
    assert result.status == "ERROR" and "timed out" in result.detail


def test_missing_helper_bundle_is_an_error(tmp_path: Path) -> None:
    result = run_helper_save(tmp_path / HELPER_NAME, 1, tmp_path / "ui.pen", runner=FakeOpen("OK"))
    assert result.status == "ERROR" and "save helper not found" in result.detail


def test_helper_resolution_prefers_the_environment_then_the_install_path(tmp_path: Path) -> None:
    installed = make_fake_helper(tmp_path / "apps")
    assert resolve_save_helper({}, tmp_path / "apps") == installed
    assert resolve_save_helper({}, tmp_path / "empty") is None
    assert resolve_save_helper({"PENFLOW_SAVE_HELPER": "/x/Other.app"}, tmp_path / "apps") == Path(
        "/x/Other.app"
    )


def test_doctor_installs_the_helper_only_into_the_requested_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(save_helper, "run_command", FakeTools())
    target = tmp_path / "apps"
    exit_code = cli.main(
        ["doctor", "--install-save-helper", "--save-helper-dir", str(target), "--json"]
    )
    report = json.loads(capsys.readouterr().out)
    assert (exit_code, report["status"], report["path"]) == (
        0,
        "installed",
        str(target / HELPER_NAME),
    )


def test_doctor_reports_a_failed_install(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(save_helper, "run_command", FakeTools(fail="osacompile"))
    exit_code = cli.main(
        ["doctor", "--install-save-helper", "--save-helper-dir", str(tmp_path), "--json"]
    )
    report = json.loads(capsys.readouterr().out)
    assert (exit_code, report["status"]) == (1, "failed")


@pytest.mark.skipif(
    sys.platform != "darwin" or shutil.which("osacompile") is None,
    reason="real AppleScript compilation needs macOS osacompile",
)
def test_real_osacompile_install_into_a_temporary_directory(tmp_path: Path) -> None:
    report = install_save_helper(tmp_path)
    bundle = tmp_path / HELPER_NAME
    assert report["status"] == "installed"
    assert info(bundle)["CFBundleIdentifier"] == HELPER_BUNDLE_ID
    assert (bundle / "Contents" / "MacOS" / "applet").is_file()
    assert install_save_helper(tmp_path)["status"] == "unchanged"


def test_default_install_directory_is_used_without_an_explicit_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(save_helper, "DEFAULT_HELPER_DIR", tmp_path / "Applications")
    report = install_save_helper(runner=FakeTools())
    assert report["path"] == str(tmp_path / "Applications" / HELPER_NAME)


def test_default_helper_location_is_the_user_applications_folder() -> None:
    assert save_helper.DEFAULT_HELPER_DIR == Path.home() / "Applications"
    assert HELPER_NAME == "Penflow Save.app"


def test_default_helper_is_found_without_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(save_helper, "DEFAULT_HELPER_DIR", tmp_path / "Applications")
    installed = make_fake_helper(tmp_path / "Applications")
    assert resolve_save_helper({}) == installed


def test_changed_source_with_the_same_version_replaces_the_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_save_helper(tmp_path, runner=FakeTools())
    monkeypatch.setattr(save_helper, "HELPER_SOURCE", save_helper.HELPER_SOURCE + "-- changed\n")
    report = install_save_helper(tmp_path, runner=FakeTools())
    assert (report["status"], info(tmp_path / HELPER_NAME)["CFBundleShortVersionString"]) == (
        "replaced",
        HELPER_VERSION,
    )


def test_default_command_runner_bounds_the_helper_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        seen.update(kwargs)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(save_helper.subprocess, "run", fake_run)
    save_helper.run_command(["open", "-W"])
    assert seen["timeout"] == save_helper.HELPER_TIMEOUT_SECONDS
