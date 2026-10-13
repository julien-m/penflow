"""Resolve external runtime tools before the immutable pilot changes directories."""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

PILOT = Path(__file__).parent / "runtime_pilot"


@pytest.fixture
def runner(monkeypatch):
    monkeypatch.syspath_prepend(str(PILOT))
    for name in ("PENFLOW_PILOT_NODE", "PENFLOW_PILOT_PLAYWRIGHT", "PENFLOW_PILOT_BROWSER"):
        monkeypatch.delenv(name, raising=False)
    spec = importlib.util.spec_from_file_location("pilot_paths_test", PILOT / "run_pilot.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def tools(tmp_path):
    node = shutil.which("node")
    if node is None:
        pytest.skip("external Node.js required for module-resolution regression")
    browser = tmp_path / "browser"
    browser.symlink_to(node)
    package = tmp_path / "node_modules" / "playwright"
    package.mkdir(parents=True)
    (package / "package.json").write_text(json.dumps({"name": "playwright", "version": "1.0.0"}))
    (package / "index.js").write_text(
        "exports.chromium = {executablePath: () => " + json.dumps(str(browser)) + "};\n"
    )
    return node, package / "index.js", browser


def bootstrap(runner, monkeypatch, tmp_path, arguments):
    """Run genuine module discovery and intercept only the retained Python execution."""
    original = subprocess.run
    commands = []

    def run(command, **kwargs):
        if command[0] == sys.executable:
            commands.append(command)
            return subprocess.CompletedProcess(command, 0, stdout="{}\n", stderr="")
        return original(command, **kwargs)

    monkeypatch.setattr(runner.subprocess, "run", run)
    monkeypatch.setattr(sys, "argv", ["run_pilot.py", "--project", str(tmp_path), *arguments])
    with pytest.raises(SystemExit) as stopped:
        runner.main()
    assert stopped.value.code == 0
    return commands[0]


def test_defaults_resolve_installed_module_and_managed_browser_before_snapshot(
    runner, monkeypatch, tmp_path, tools
):
    node, playwright, browser = tools
    monkeypatch.chdir(tmp_path)
    command = bootstrap(runner, monkeypatch, tmp_path, ["--node", node])
    assert command[command.index("--playwright") + 1] == str(playwright)
    assert command[command.index("--browser") + 1] == str(browser)


def test_relative_overrides_are_resolved_in_callers_directory(runner, monkeypatch, tmp_path, tools):
    node, playwright, browser = tools
    monkeypatch.chdir(tmp_path)
    command = bootstrap(
        runner,
        monkeypatch,
        tmp_path,
        [
            "--node",
            node,
            "--playwright",
            "./node_modules/playwright/index.js",
            "--browser",
            "./browser",
        ],
    )
    assert command[command.index("--playwright") + 1] == str(playwright)
    assert command[command.index("--browser") + 1] == str(browser)


def test_missing_playwright_is_actionable_before_snapshot(runner, monkeypatch, tmp_path, capsys):
    node = shutil.which("node")
    if node is None:
        pytest.skip("external Node.js required")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_pilot.py",
            "--project",
            str(tmp_path),
            "--node",
            node,
            "--playwright",
            str(tmp_path / "missing.js"),
        ],
    )
    with pytest.raises(SystemExit) as stopped:
        runner.main()
    assert stopped.value.code == 2
    assert "--playwright" in capsys.readouterr().err
    assert not (tmp_path / ".specs").exists()


def test_selected_node_discovers_adjacent_modules(runner, monkeypatch, tmp_path, tools):
    node, playwright, browser = tools
    runtime = tmp_path / "runtime"
    (runtime / "bin").mkdir(parents=True)
    selected = runtime / "bin" / "node"
    selected.symlink_to(node)
    shutil.move(tmp_path / "node_modules", runtime / "node_modules")
    monkeypatch.chdir(tmp_path)
    command = bootstrap(runner, monkeypatch, tmp_path, ["--node", str(selected)])
    assert command[command.index("--playwright") + 1] == str(
        runtime / "node_modules" / "playwright" / "index.js"
    )
    assert command[command.index("--browser") + 1] == str(browser)


def test_environment_overrides_expand_home_and_cli_takes_precedence(
    runner, monkeypatch, tmp_path, tools
):
    node, playwright, browser = tools
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("PENFLOW_PILOT_NODE", node)
    monkeypatch.setenv("PENFLOW_PILOT_PLAYWRIGHT", "~/node_modules/playwright/index.js")
    monkeypatch.setenv("PENFLOW_PILOT_BROWSER", "~/browser")
    # Reload the runner's environment defaults without executing its main entrypoint.
    spec = importlib.util.spec_from_file_location(runner.__name__, PILOT / "run_pilot.py")
    spec.loader.exec_module(runner)
    command = bootstrap(runner, monkeypatch, tmp_path, [])
    assert command[command.index("--playwright") + 1] == str(playwright)
    assert command[command.index("--browser") + 1] == str(browser)
    replacement = tmp_path / "explicit-browser"
    replacement.symlink_to(node)
    command = bootstrap(runner, monkeypatch, tmp_path, ["--browser", str(replacement)])
    assert command[command.index("--browser") + 1] == str(replacement)


def test_browser_command_is_resolved_on_path(runner, monkeypatch, tmp_path, tools):
    node, playwright, browser = tools
    monkeypatch.setenv("PATH", str(tmp_path))
    command = bootstrap(
        runner,
        monkeypatch,
        tmp_path,
        ["--node", node, "--playwright", str(playwright), "--browser", "browser"],
    )
    assert command[command.index("--browser") + 1] == str(browser)


def test_missing_managed_browser_is_actionable(runner, monkeypatch, tmp_path, tools, capsys):
    node, playwright, browser = tools
    browser.unlink()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["run_pilot.py", "--project", str(tmp_path), "--node", node])
    with pytest.raises(SystemExit) as stopped:
        runner.main()
    assert stopped.value.code == 2
    assert "playwright install chromium" in capsys.readouterr().err
    assert not (tmp_path / ".specs").exists()


def test_missing_node_is_actionable(runner, monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(
        sys,
        "argv",
        ["run_pilot.py", "--project", str(tmp_path), "--node", str(tmp_path / "missing-node")],
    )
    with pytest.raises(SystemExit) as stopped:
        runner.main()
    assert stopped.value.code == 2
    assert "--node" in capsys.readouterr().err
    assert not (tmp_path / ".specs").exists()
