"""Run real-browser negative probes without importing Penflow or test factories."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from run_pilot import BROWSER, NODE, PLAYWRIGHT, SOURCES, resolve_tools, stop


def browser_probe(root: Path, mode: str, settings: argparse.Namespace) -> dict:
    """Serve changed HTML and observe rejection or its actual DOM role."""
    project = root / mode
    project.mkdir()
    for name in SOURCES:
        shutil.copyfile(Path(__file__).with_name(name), project / name)
    html = (project / "index.html").read_text()
    if mode == "unmapped-control":
        html = html.replace("</main>", "<button>Unmapped extra control</button></main>")
    else:
        html = re.sub(
            r'<button data-semantic="checkout\.pay"[^>]*>Pay</button>',
            '<span data-semantic="checkout.pay" data-role="button">Pay</span>',
            html,
        )
    (project / "index.html").write_text(html)
    # Execute that project's actual app; start_app otherwise binds its own module directory.
    ready_runner = "import run_pilot, pathlib; p,r=run_pilot.start_app(pathlib.Path('payments.sqlite3'),open('application.log','w')); print(__import__('json').dumps(r),flush=True); p.wait()"
    owner = subprocess.Popen(
        [sys.executable, "-c", ready_runner],
        cwd=project,
        stdout=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    app_pid = None
    try:
        if owner.stdout is None:
            raise RuntimeError("probe readiness pipe absent")
        ready = json.loads(owner.stdout.readline())
        app_pid = int(ready["process_instance"].split(":")[0])
        output = project / "observed.json"
        command = [
            settings.node,
            str(project / "capture.mjs"),
            f"http://127.0.0.1:{ready['port']}/",
            "inspect",
            str(output),
            settings.playwright,
            settings.browser,
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=60, check=False)
        (project / "browser.stdout.log").write_text(result.stdout)
        (project / "browser.stderr.log").write_text(result.stderr)
        if mode == "unmapped-control":
            assert (
                result.returncode != 0 and "Unmapped rendered interactive controls" in result.stderr
            )
            assert not output.exists()
            observed = "capture-blocked"
        else:
            assert result.returncode == 0, result.stderr
            facts = json.loads(output.read_text())
            control = next(
                node for node in facts["after"]["nodes"] if node["semantic_id"] == "checkout.pay"
            )
            assert control["role"] == "text"
            observed = control["role"]
        return {
            "probe": mode,
            "observed": observed,
            "exit_code": result.returncode,
            "path": str(project),
        }
    finally:
        if app_pid is not None:
            import os
            import signal

            os.killpg(app_pid, signal.SIGTERM)
        stop(owner)


def mutation_probe(root: Path) -> dict:
    """Mutate the executing build and require refusal before manifest publication."""
    project = root / "build-mutation"
    project.mkdir()
    command = [
        sys.executable,
        str(Path(__file__).with_name("run_pilot.py")),
        "--project",
        str(project),
    ]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    deadline = time.monotonic() + 30
    while not list(project.glob(".specs/testing/runtime-evidence/*/evidence/invalid.browser.json")):
        if process.poll() is not None or time.monotonic() > deadline:
            process.kill()
            raise RuntimeError("mutation probe never reached observed runtime boundary")
        time.sleep(0.05)
    snapshot = next(project.glob(".specs/testing/runtime-evidence/*/producer/index.html"))
    snapshot.write_text(
        snapshot.read_text() + "\n<!-- Actual adversarial mutation after capture began -->\n"
    )
    stdout, stderr = process.communicate(timeout=120)
    (project / "probe.stdout.log").write_text(stdout)
    (project / "probe.stderr.log").write_text(stderr)
    assert process.returncode != 0 and "executed producer/build changed" in stderr
    assert not list(project.glob(".specs/testing/runtime-evidence/*/build-manifest.json"))
    return {
        "probe": "build-mutation",
        "observed": "manifest-publication-blocked",
        "exit_code": process.returncode,
        "path": str(project),
    }


def main() -> None:
    """Retain every negative probe and print its exact result path."""
    settings = argparse.Namespace(node=NODE, playwright=PLAYWRIGHT, browser=BROWSER)
    resolve_tools(settings)
    root = Path(tempfile.mkdtemp(prefix="penflow-real-boundaries-")).resolve()
    results = [
        browser_probe(root, "unmapped-control", settings),
        browser_probe(root, "false-role", settings),
        mutation_probe(root),
    ]
    output = root / "results.json"
    output.write_text(json.dumps(results, indent=2) + "\n")
    print(json.dumps({"results": str(output), "probes": results}))


if __name__ == "__main__":
    main()
