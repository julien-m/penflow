# @spec AC-010: bounded wait for the saved bytes — .specs/features/078-pen-dev-operator-compatibility/spec.md#ac-010
# @spec AC-011: --save-timeout validation — .specs/features/078-pen-dev-operator-compatibility/spec.md#ac-011
"""pencil-sync waits for pen.dev to finish writing before judging the digest."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from penflow import cli
from penflow.pencil_sync import PencilSyncError, SaveOutcome, sync_pencil_to_disk

SAVED = SaveOutcome(ok=True, method="fake", message="saved")


class FakeTime:
    """Monotonic clock whose sleep advances time and fires scheduled writes."""

    def __init__(self, pen: Path, writes: list[tuple[float, str]]) -> None:
        self.now = 0.0
        self.sleeps = 0
        self.pen = pen
        self.writes = sorted(writes)

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps += 1
        self.now += seconds
        while self.writes and self.writes[0][0] <= self.now:
            self.pen.write_text(self.writes.pop(0)[1], encoding="utf-8")


def pen_text(screens: int) -> str:
    children = [
        {
            "id": f"s{i}",
            "type": "frame",
            "name": f"s{i}",
            "context": {"semantic_id": f"s{i}", "role": "screen"},
        }
        for i in range(screens)
    ]
    return json.dumps({"version": "2.11", "children": children})


def make_pen(tmp_path: Path) -> Path:
    pen = tmp_path / "ui.pen"
    pen.write_text(pen_text(1), encoding="utf-8")
    return pen


def run(pen: Path, fake: FakeTime, *, timeout: float = 5.0, save: SaveOutcome = SAVED) -> dict:
    return sync_pencil_to_disk(
        pen, save_runner=lambda path: save, save_timeout=timeout, clock=fake.clock, sleep=fake.sleep
    )


def test_write_landing_after_the_request_but_within_the_timeout_passes(tmp_path: Path) -> None:
    pen = make_pen(tmp_path)
    fake = FakeTime(pen, [(1.2, pen_text(2))])
    result = run(pen, fake)
    assert (result["status"], result["checks"]["content_changed"]) == ("PASS", True)
    assert result["after"]["screen_count"] == 2
    assert 1.2 <= fake.now < 1.4


def test_no_write_fails_only_after_the_timeout(tmp_path: Path) -> None:
    pen = make_pen(tmp_path)
    fake = FakeTime(pen, [])
    result = run(pen, fake)
    assert (result["status"], result["checks"]["content_changed"]) == ("FAIL", False)
    assert "document digest did not change" in result["message"]
    assert math.isclose(fake.now, 5.0)


def test_write_after_the_timeout_is_still_a_failure(tmp_path: Path) -> None:
    pen = make_pen(tmp_path)
    fake = FakeTime(pen, [(6.0, pen_text(2))])
    result = run(pen, fake)
    assert (result["status"], result["checks"]["content_changed"]) == ("FAIL", False)


def test_partial_write_keeps_polling_until_the_bytes_parse(tmp_path: Path) -> None:
    pen = make_pen(tmp_path)
    fake = FakeTime(pen, [(0.5, '{"version": "2.11", "child'), (1.0, pen_text(3))])
    result = run(pen, fake)
    assert (result["status"], result["after"]["screen_count"]) == ("PASS", 3)
    assert fake.now >= 1.0


def test_zero_timeout_checks_once_without_sleeping(tmp_path: Path) -> None:
    pen = make_pen(tmp_path)
    fake = FakeTime(pen, [(0.1, pen_text(2))])
    result = run(pen, fake, timeout=0)
    assert (result["status"], fake.sleeps) == ("FAIL", 0)


def test_failed_save_request_never_waits(tmp_path: Path) -> None:
    pen = make_pen(tmp_path)
    fake = FakeTime(pen, [(0.5, pen_text(2))])
    failed = SaveOutcome(ok=False, method="fake", message="denied")
    result = run(pen, fake, save=failed)
    assert (result["status"], fake.sleeps, fake.now) == ("FAIL", 0, 0.0)


@pytest.mark.parametrize("timeout", [-1.0, math.inf, math.nan])
def test_invalid_timeout_is_rejected_by_the_api(tmp_path: Path, timeout: float) -> None:
    with pytest.raises(PencilSyncError) as raised:
        run(make_pen(tmp_path), FakeTime(tmp_path / "ui.pen", []), timeout=timeout)
    assert "--save-timeout" in str(raised.value)


@pytest.mark.parametrize("value", ["-1", "inf", "nan", "soon"])
def test_invalid_timeout_is_a_cli_usage_error(tmp_path: Path, value: str) -> None:
    with pytest.raises(SystemExit) as raised:
        cli.main(["pencil-sync", str(make_pen(tmp_path)), "--save-timeout", value])
    assert raised.value.code == 2
