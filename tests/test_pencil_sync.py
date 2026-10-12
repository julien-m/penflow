# @spec AC-009: trigger contract keeps UNVERIFIED and digest comparison — .specs/features/078-pen-dev-operator-compatibility/spec.md#ac-009
# @spec AC-003: pencil-sync --app CLI wiring — .specs/features/078-pen-dev-operator-compatibility/spec.md#ac-003
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from penflow import cli
from penflow.artifact_policy import MANAGED_IGNORE_BLOCK
from penflow.pencil_sync import SaveOutcome, sync_pencil_to_disk


def write_json(path: Path, data: dict[str, Any]) -> Path:
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def screen(name: str) -> dict[str, Any]:
    return {
        "id": name,
        "type": "frame",
        "name": name,
        "context": {"semantic_id": name, "role": "screen"},
        "children": [
            {
                "id": f"{name}.title",
                "type": "text",
                "content": name,
                "context": {"semantic_id": f"{name}.title", "role": "text"},
            }
        ],
    }


def pen_with_screens(count: int) -> dict[str, Any]:
    return {"version": 1, "children": [screen(f"screen-{index}") for index in range(count)]}


def advance_mtime(path: Path) -> None:
    next_mtime = path.stat().st_mtime_ns + 1_000_000_000
    os.utime(path, ns=(next_mtime, next_mtime))


def test_pencil_sync_passes_after_save_persists_expected_screens(tmp_path: Path) -> None:
    pen_path = write_json(tmp_path / "ui.pen", pen_with_screens(1))

    def save(path: Path) -> SaveOutcome:
        write_json(path, pen_with_screens(8))
        advance_mtime(path)
        return SaveOutcome(ok=True, method="fake", message="saved")

    result = sync_pencil_to_disk(
        pen_path,
        expect_min_nodes=16,
        expect_screens=8,
        save_runner=save,
    )

    assert result["status"] == "PASS"
    assert result["before"]["screen_count"] == 1
    assert result["after"]["screen_count"] == 8
    assert result["after"]["node_count"] == 16
    assert result["checks"]["mtime_advanced"] is True
    assert result["checks"]["content_changed"] is True
    assert result["persistence_status"] == "UNVERIFIED"
    assert result["closes_persistence"] is False


def test_pencil_sync_fails_when_save_is_same_digest_noop(tmp_path: Path) -> None:
    pen_path = write_json(tmp_path / "ui.pen", pen_with_screens(8))

    result = sync_pencil_to_disk(
        pen_path,
        expect_screens=8,
        save_runner=lambda path: SaveOutcome(ok=True, method="fake", message="no-op"),
        save_timeout=0,
    )

    assert result["status"] == "FAIL"
    assert result["checks"]["content_changed"] is False
    assert "did not persist" in result["message"]


def test_pencil_sync_does_not_use_mtime_as_persistence_proof(tmp_path: Path) -> None:
    pen_path = write_json(tmp_path / "ui.pen", pen_with_screens(1))
    original_mtime = pen_path.stat().st_mtime_ns

    def save(path: Path) -> SaveOutcome:
        write_json(path, pen_with_screens(2))
        os.utime(path, ns=(original_mtime, original_mtime))
        return SaveOutcome(ok=True, method="fake", message="saved")

    result = sync_pencil_to_disk(pen_path, expect_screens=2, save_runner=save)

    assert result["status"] == "PASS"
    assert result["checks"]["mtime_advanced"] is False
    assert result["checks"]["content_changed"] is True
    assert result["closes_persistence"] is False


def test_pencil_sync_fails_when_disk_inspection_is_below_expectation(tmp_path: Path) -> None:
    pen_path = write_json(tmp_path / "ui.pen", pen_with_screens(1))

    def save(path: Path) -> SaveOutcome:
        write_json(path, pen_with_screens(2))
        advance_mtime(path)
        return SaveOutcome(ok=True, method="fake", message="saved")

    result = sync_pencil_to_disk(pen_path, expect_screens=8, save_runner=save)

    assert result["status"] == "FAIL"
    assert result["checks"]["screens"] == {"actual": 2, "expected": 8, "passed": False}
    assert "disk inspection did not meet expectations" in result["message"]


def test_pencil_sync_cli_returns_exit_code_from_status(tmp_path: Path, monkeypatch) -> None:
    pen_path = write_json(tmp_path / "ui.pen", pen_with_screens(1))
    # Git is a real system boundary; setup must succeed within the test budget.
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True, timeout=10)
    (tmp_path / ".gitignore").write_text(MANAGED_IGNORE_BLOCK, encoding="utf-8")
    observed: dict[str, Any] = {}

    def fake_sync(
        path: str,
        *,
        expect_min_nodes: int | None,
        expect_screens: int | None,
        app: str | None,
        save_timeout: float,
    ):
        observed.update(
            {
                "path": path,
                "expect_min_nodes": expect_min_nodes,
                "expect_screens": expect_screens,
                "app": app,
                "save_timeout": save_timeout,
            }
        )
        return {
            "kind": "penflow-pencil-sync",
            "status": "PASS",
            "pen": path,
            "message": "ok",
            "save": {},
            "before": {},
            "after": {},
            "checks": {},
        }

    monkeypatch.setattr(cli, "sync_pencil_to_disk", fake_sync)
    flags = "--expect-min-nodes 3 --expect-screens 1 --app /Applications/Pen.app --save-timeout 2.5"
    argv = ["pencil-sync", str(pen_path), *flags.split(), "--json", "--project", str(tmp_path)]

    assert cli.main(argv) == 0
    assert observed == {
        "path": str(pen_path),
        "expect_min_nodes": 3,
        "expect_screens": 1,
        "app": "/Applications/Pen.app",
        "save_timeout": 2.5,
    }
