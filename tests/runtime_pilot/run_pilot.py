"""Execute a snapshotted external test app/browser runner and retain authentic facts."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import selectors
import shutil
import signal
import subprocess
import sys
import tempfile
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from publish_capture import publish, source_references

NODE = os.environ.get("PENFLOW_PILOT_NODE") or shutil.which("node") or "node"
PLAYWRIGHT = os.environ.get("PENFLOW_PILOT_PLAYWRIGHT") or "playwright"
BROWSER = os.environ.get("PENFLOW_PILOT_BROWSER")
SCENARIOS = (
    "edit",
    "invalid",
    "save",
    "idempotent",
    "denied",
    "error",
    "storage_error",
    "back",
    "close",
)
SOURCES = (
    "run_pilot.py",
    "app.py",
    "index.html",
    "capture.mjs",
    "read_storage.py",
    "dom_capture.mjs",
    "observation_facts.py",
    "convert_observations.py",
    "convert_tree.py",
    "convert_causal.py",
    "publish_capture.py",
    "font_capture.mjs",
    "inter-regular.woff2",
    "inter-semibold.woff2",
    "inter-license.txt",
    "font-sources.json",
)
BUILD_ASSETS = {"app.py", "index.html", "inter-regular.woff2", "inter-semibold.woff2"}


def resolve_tools(settings: argparse.Namespace) -> None:
    """Resolve external tools in the caller's environment before snapshot execution."""
    node = shutil.which(os.path.expanduser(settings.node))
    if node is None:
        raise RuntimeError("Node.js unavailable; install Node.js or supply --node /path/to/node")
    settings.node = str(Path(node).absolute())
    requested = os.path.expanduser(settings.playwright)
    if requested.startswith(".") or Path(requested).is_absolute() or Path(requested).exists():
        requested = str(Path(requested).resolve())
    # Normal Node resolution (including NODE_PATH), plus modules beside the selected
    # Node installation. Resolve in the caller's cwd, never the retained snapshot.
    script = """
const path = require('node:path');
const [requested, node] = process.argv.slice(1);
const root = path.dirname(path.dirname(node));
const entry = require.resolve(requested, {paths: [process.cwd(), root, path.join(root, 'lib')]});
const {chromium} = require(entry);
console.log(JSON.stringify({entry, browser: chromium.executablePath()}));
"""
    try:
        result = subprocess.run(
            [settings.node, "-e", script, requested, settings.node],
            capture_output=True,
            text=True,
            timeout=15,
            check=True,
        )
        tools = json.loads(result.stdout)
        package = Path(tools["entry"]).with_name("package.json")
        json.loads(package.read_text())["version"]
    except (OSError, subprocess.SubprocessError, ValueError, KeyError) as exc:
        raise RuntimeError(
            "Playwright unavailable; install the external playwright package in the caller's "
            "Node environment or supply --playwright /path/to/playwright/index.js"
        ) from exc
    settings.playwright = str(Path(tools["entry"]).resolve())
    browser = os.path.expanduser(settings.browser) if settings.browser else tools["browser"]
    executable = shutil.which(browser)
    if executable is None:
        raise RuntimeError(
            "Chromium unavailable; install this Playwright version's browser with "
            "playwright install chromium or supply --browser /path/to/browser"
        )
    # Do not dereference executable symlinks: launchers can depend on their own path.
    settings.browser = str(Path(executable).absolute())


def write_json(path: Path, value: Any) -> None:
    """Persist inspectable strict JSON evidence."""
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def reference(path: Path, project: Path) -> dict[str, str]:
    """Bind exact retained bytes to a path within the caller project."""
    resolved = path.resolve(strict=True)
    return {
        "path": str(resolved.relative_to(project)),
        "sha256": hashlib.sha256(resolved.read_bytes()).hexdigest(),
    }


def storage(database: Path) -> dict[str, Any]:
    """Read SQLite directly, independently of app responses and browser assertions."""
    command = [sys.executable, str(Path(__file__).with_name("read_storage.py")), str(database)]
    return json.loads(subprocess.check_output(command, text=True, timeout=10))


def server_storage(ready: dict[str, Any]) -> dict[str, Any]:
    """Observe a real SELECT executed by the current identified server process."""
    with urllib.request.urlopen(f"http://127.0.0.1:{ready['port']}/storage", timeout=5) as response:
        return json.load(response)


def stop(process: subprocess.Popen[str]) -> None:
    """Terminate only a child process owned by this runner, including timeout recovery."""
    if process.poll() is None:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)


def start_app(database: Path, log: Any) -> tuple[subprocess.Popen[str], dict[str, Any]]:
    """Start the actual snapshot and require readiness from its HTTP endpoint."""
    process = subprocess.Popen(
        [sys.executable, str(Path(__file__).with_name("app.py")), "--database", str(database)],
        stdout=subprocess.PIPE,
        stderr=log,
        text=True,
        start_new_session=True,
    )
    try:
        if process.stdout is None:
            raise RuntimeError("application readiness pipe absent")
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            if not selector.select(timeout=10):
                raise RuntimeError("application readiness timed out")
        ready = json.loads(process.stdout.readline())
        with urllib.request.urlopen(
            f"http://127.0.0.1:{ready['port']}/health", timeout=5
        ) as response:
            health = json.load(response)
        if health["process_instance"] != ready["process_instance"]:
            raise RuntimeError("application process readiness identity mismatch")
        return process, ready
    except BaseException:
        stop(process)
        raise


def capture(
    base_url: str, scenario: str, output: Path, settings: argparse.Namespace, log: Any
) -> None:
    """Run the snapshotted adapter against the real ephemeral browser."""
    command = [
        settings.node,
        str(Path(__file__).with_name("capture.mjs")),
        base_url,
        scenario,
        str(output),
        settings.playwright,
        settings.browser,
    ]
    process = subprocess.Popen(command, stdout=log, stderr=log, text=True, start_new_session=True)
    try:
        if process.wait(timeout=60):
            raise RuntimeError(f"browser scenario {scenario} failed; inspect browser.log")
    finally:
        stop(process)


def run_scenarios(settings: argparse.Namespace, evidence: Path) -> dict[str, Any]:
    """Observe scenario effects and persistence through distinct app processes."""
    database = evidence / "payments.sqlite3"
    observations = []
    process = None
    with (
        (evidence / "application.log").open("w") as app_log,
        (evidence / "browser.log").open("w") as browser_log,
    ):
        try:
            process, ready = start_app(database, app_log)
            for scenario in SCENARIOS:
                before = server_storage(ready)
                independent_before = storage(database)
                raw_path = evidence / f"{scenario}.browser.json"
                capture(
                    f"http://127.0.0.1:{ready['port']}/", scenario, raw_path, settings, browser_log
                )
                raw = json.loads(raw_path.read_text())
                after = server_storage(ready)
                record = {
                    "scenario_id": scenario,
                    "session_id": raw["session_id"],
                    "before": before,
                    "after": after,
                    "independent_before": independent_before,
                    "independent_after": storage(database),
                }
                if scenario in {"save", "idempotent"}:
                    old_process = ready["process_instance"]
                    stop(process)
                    process, ready = start_app(database, app_log)
                    record["readback"] = server_storage(ready)
                    record["independent_readback"] = storage(database)
                    record["restart"] = {
                        "before_process": old_process,
                        "after_process": ready["process_instance"],
                    }
                validate_scenario(scenario, raw, record)
                write_json(evidence / f"{scenario}.storage.json", record)
                observations.append(record)
        finally:
            if process is not None:
                stop(process)
    return {"scenarios": observations, "database": str(database)}


def validate_scenario(scenario: str, raw: dict[str, Any], record: dict[str, Any]) -> None:
    """Reject incorrect measured results; these assertions are not C51 certification."""
    before, after = record["before"], record["after"]
    for key in ("before", "after", "readback"):
        if key in record:
            assert (
                record[key]["process_instance"] != record[f"independent_{key}"]["process_instance"]
            )
            assert all(
                record[key][field] == record[f"independent_{key}"][field]
                for field in ("value", "exists", "row_count")
            )
    if scenario == "save":
        assert not before["exists"] and after["value"] == {"amount": 10, "status": "paid"}
        assert record["restart"]["before_process"] != record["restart"]["after_process"]
        assert record["readback"]["value"] == after["value"] and after["row_count"] == 1
    else:
        assert all(before[key] == after[key] for key in ("value", "exists", "row_count"))
    if scenario == "edit":
        assert (
            next(
                node for node in raw["before"]["nodes"] if node["semantic_id"] == "checkout.amount"
            )["value"]
            == 5
        )
        assert (
            next(
                node for node in raw["after"]["nodes"] if node["semantic_id"] == "checkout.amount"
            )["value"]
            == 10
        )
        assert not any(request["method"] == "POST" for request in raw["requests"])
    elif scenario == "back":
        assert raw["after"]["url"] == raw["navigation"]["previous_url"]
        assert raw["before"]["url"] != raw["after"]["url"]
    elif scenario == "close":
        assert raw["after"] == {"visible": False, "surface_present": False, "url": None}
        assert raw["navigation"]["parent_open"]
    elif scenario in {"invalid", "denied"}:
        assert raw["network"] is None and not any(
            request["method"] == "POST" for request in raw["requests"]
        )
        result = next(
            node for node in raw["after"]["nodes"] if node["semantic_id"] == "checkout.result"
        )
        assert result["text"] == scenario and result["visible"]
    else:
        status, outcome = {
            "save": (201, "success"),
            "invalid": (422, "invalid"),
            "idempotent": (200, "idempotent"),
            "denied": (403, "denied"),
            "error": (503, "error"),
            "storage_error": (500, "error"),
        }[scenario]
        assert raw["network"]["response"]["status"] == status
        assert raw["network"]["response"]["body"]["outcome"] == outcome
        result = next(
            node for node in raw["after"]["nodes"] if node["semantic_id"] == "checkout.result"
        )
        assert result["text"] == outcome and result["visible"]


def execute(settings: argparse.Namespace) -> Path:
    """Serialize external capture publication with an automatically released process lock."""
    lock_path = Path(__file__).parent.parent.parent / ".capture.lock"
    with lock_path.open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError(
                "another runtime pilot owns this project's capture publication"
            ) from exc
        return execute_locked(settings)


def execute_locked(settings: argparse.Namespace) -> Path:
    """Publish a build manifest only after the real runner completes its measurements."""
    project = settings.project.resolve()
    retained = Path(__file__).parent.parent
    evidence = retained / "evidence"
    evidence.mkdir()
    snapshot_refs = [reference(Path(__file__).with_name(name), project) for name in SOURCES]
    source_refs = (
        source_references(project, settings.contract.resolve()) if settings.contract else []
    )
    result = run_scenarios(settings, evidence)
    source_after = (
        source_references(project, settings.contract.resolve()) if settings.contract else []
    )
    if source_after != source_refs:
        raise RuntimeError("contract changed during runtime capture")
    if snapshot_refs != [reference(Path(__file__).with_name(name), project) for name in SOURCES]:
        raise RuntimeError("executed producer/build changed during runtime capture")
    artifacts = [
        ref for name, ref in zip(SOURCES, snapshot_refs, strict=True) if name in BUILD_ASSETS
    ]
    build_id = hashlib.sha256(json.dumps(artifacts, sort_keys=True).encode()).hexdigest()
    outputs = (
        publish(settings.contract.resolve(), evidence, project, build_id, settings.invocation)
        if settings.contract
        else []
    )
    summary = {
        "kind": "penflow-runtime-pilot-result",
        "version": 1,
        "status": "PASS",
        "certification": "not-run",
        "scope": "bounded test application only",
        "build_id": build_id,
        "producer_invocation_id": settings.invocation,
        "contract_bound": bool(settings.contract),
        "tools": {
            "python": sys.version,
            "node": {
                "path": settings.node,
                "version": subprocess.check_output([settings.node, "--version"], text=True).strip(),
            },
            "playwright": {
                "path": settings.playwright,
                "version": json.loads(
                    Path(settings.playwright).with_name("package.json").read_text()
                )["version"],
            },
            "browser": {
                "path": settings.browser,
                "version": json.loads((evidence / "save.browser.json").read_text())[
                    "browser_version"
                ],
            },
        },
        **result,
    }
    write_json(evidence / "runtime-result.json", summary)
    manifest = {
        "kind": "penflow-build-manifest",
        "version": 1,
        "scope": {"project_root": str(project)},
        "build": {"id": build_id, "artifacts": artifacts},
        "producer": {
            "id": "penflow-test-payment-browser",
            "entrypoint": snapshot_refs[0],
            "invocation_id": settings.invocation,
        },
        "capture": {
            "session_ids": [row["session_id"] for row in result["scenarios"]],
            "scenario_ids": list(SCENARIOS),
        },
        "sources": source_refs
        + [
            ref
            for name, ref in zip(SOURCES, snapshot_refs, strict=True)
            if name not in BUILD_ASSETS and name != "run_pilot.py"
        ],
        "evidence": [
            reference(path, project) for path in sorted(evidence.iterdir()) if path.is_file()
        ]
        + [reference(path, project) for path in outputs],
        "issued_at": datetime.now(timezone.utc).isoformat(),
    }
    manifest_path = retained / "build-manifest.json"
    if snapshot_refs != [reference(Path(__file__).with_name(name), project) for name in SOURCES]:
        raise RuntimeError("executed producer/build changed before manifest publication")
    if settings.contract and source_refs != source_references(project, settings.contract.resolve()):
        raise RuntimeError("contract changed before manifest publication")
    write_json(manifest_path, manifest)
    return manifest_path


def main() -> None:
    """Bootstrap an immutable runner snapshot, then execute precisely those bytes."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path)
    parser.add_argument("--contract", type=Path)
    parser.add_argument("--node", default=NODE)
    parser.add_argument("--playwright", default=PLAYWRIGHT)
    parser.add_argument("--browser", default=BROWSER)
    parser.add_argument("--execute", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--invocation", default=str(uuid.uuid4()), help=argparse.SUPPRESS)
    settings = parser.parse_args()
    try:
        resolve_tools(settings)
    except RuntimeError as exc:
        parser.error(str(exc))
    if settings.execute:
        print(json.dumps({"build_manifest": str(execute(settings))}))
        return
    project = (settings.project or Path(tempfile.mkdtemp(prefix="penflow-real-pilot-"))).resolve()
    if settings.contract:
        settings.contract = settings.contract.resolve()
        settings.contract.relative_to(project)
    retained = project / ".specs" / "testing" / "runtime-evidence" / settings.invocation
    snapshot = retained / "producer"
    snapshot.mkdir(parents=True, exist_ok=False)
    for name in SOURCES:
        shutil.copyfile(Path(__file__).with_name(name), snapshot / name)
    command = [
        sys.executable,
        str(snapshot / "run_pilot.py"),
        "--execute",
        "--project",
        str(project),
        "--invocation",
        settings.invocation,
        "--node",
        settings.node,
        "--playwright",
        settings.playwright,
        "--browser",
        settings.browser,
    ]
    if settings.contract:
        command.extend(("--contract", str(settings.contract)))
    completed = subprocess.run(command, capture_output=True, text=True, timeout=600, check=False)
    (retained / "runner.stdout.log").write_text(completed.stdout)
    (retained / "runner.stderr.log").write_text(completed.stderr)
    write_json(
        retained / "invocation.json",
        {
            "command": command,
            "exit_code": completed.returncode,
            "entrypoint": reference(snapshot / "run_pilot.py", project),
        },
    )
    print(completed.stdout, end="")
    if completed.returncode:
        print(completed.stderr, file=sys.stderr)
        print(f"Retained failed run: {retained}", file=sys.stderr)
    raise SystemExit(completed.returncode)


if __name__ == "__main__":
    main()
