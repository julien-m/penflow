"""Exercise visual alignment through the public, read-only CLI."""

from __future__ import annotations

import json
import struct
import zlib
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest

from penflow import cli
from penflow.cli import main
from penflow.rendered_measurements import compare_rendered

# Manifest and comparison files are heterogeneous JSON boundary objects.
JsonObject = dict[str, Any]


def _write_json(path: Path, value: JsonObject) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def _write_png(path: Path, viewport: list[int], shade: int = 70, *, joined: bool = True) -> None:
    """Write valid grayscale evidence with either a runtime panel or a vis-à-vis."""
    width, height = viewport
    design = bytes([30]) * width if joined else b""
    pixels = design + bytes([shade]) * width
    scanline = b"\x00" + pixels
    header = struct.pack(">IIBBBBB", len(pixels), height, 8, 0, 0, 0, 0)
    chunks = ((b"IHDR", header), (b"IDAT", zlib.compress(scanline * height)), (b"IEND", b""))
    image = bytearray(b"\x89PNG\r\n\x1a\n")
    for kind, data in chunks:
        image.extend(struct.pack(">I", len(data)))
        image.extend(kind + data)
        image.extend(struct.pack(">I", zlib.crc32(kind + data)))
    path.write_bytes(image)


def _rendered_report(pair: JsonObject, evidence: Path, *, expanded: bool = True) -> JsonObject:
    """Drive the real comparator using fixed, independently offset controls."""
    design = pair["design"]
    screen_id, state = design["screen"], design["state"]
    viewport = dict(zip(("width", "height"), design["viewport"], strict=True))
    expected: JsonObject = {
        "version": 1,
        "screens": [
            {
                "screen_id": screen_id,
                "pencil_id": design["frame"],
                "states": [state],
                "viewport": viewport,
                "root": {
                    "id": screen_id,
                    "role": "screen",
                    "bbox": {"x": 0, "y": 0, **viewport},
                    "children": [
                        {
                            "id": f"settings.{label}",
                            "semantic_id": f"settings.{label}",
                            "role": "button",
                            "bbox": {"x": 5, "y": y, "width": 70, "height": 24},
                            "sizing": {"width": "fixed", "height": "fixed"},
                        }
                        for label, y in [("save", 5), ("dismiss", 50)]
                    ],
                },
            }
        ],
    }
    screens = deepcopy(expected["screens"])
    screens[0].pop("states")
    screens[0].update(state=state, scenario_id="settings-ready")
    if expanded:
        for control in screens[0]["root"]["children"]:
            control["bbox"]["height"] += 15
    capture = pair["images"].get("runtime") or pair["images"]["side_by_side"]
    actual = {
        "version": 1,
        "measurement": {
            "source": "runtime",
            "units": "css-px",
            "coordinate_space": "screen-relative",
            "zoom": 1,
            "device_pixel_ratio": 1,
            "method": "getBoundingClientRect+getComputedStyle",
        },
        "screens": screens,
        "observed_states": [
            {
                "screen_id": screen_id,
                "state": state,
                "scenario_id": "settings-ready",
                "session_id": "settings-observation",
                "evidence": {
                    "path": capture,
                    "sha256": sha256((evidence / capture).read_bytes()).hexdigest(),
                },
            }
        ],
    }
    return compare_rendered(expected, actual)


def _review_item(priority: int, *, action: str = "product_fix") -> JsonObject:
    return {
        "priority": priority,
        "title": f"Finding {priority:02d}",
        "action": action,
        "basis": "visual",
        "region": "Right image, settings footer, primary action",
        "expected": "Compact primary button",
        "observed": "Expanded primary button",
        "proposal": "Apply the compact control variant",
        "verify": "Capture ready settings and check the primary button height",
        "evidence": [{"path": "before.png", "note": "Compare the two primary actions"}],
    }


@pytest.fixture
def review(tmp_path: Path) -> tuple[Path, JsonObject]:
    """Build a self-contained review with no Git or consumer runtime."""
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    viewport = [128, 96]
    metadata = {"screen": "settings", "state": "ready", "variant": None, "viewport": viewport}
    pair = {
        "design": {**deepcopy(metadata), "frame": "settings-frame"},
        "runtime": metadata,
        "images": {"side_by_side": "before.png"},
        "report": "before-check.json",
    }
    _write_png(evidence / "before.png", viewport)
    _write_json(evidence / "before-check.json", _rendered_report(pair, evidence))
    manifest = {
        "version": 1,
        "cases": [{"title": "Settings review", "before": pair, "findings": [_review_item(1)]}],
    }
    return evidence, manifest


def _run(review: tuple[Path, JsonObject], output: pytest.CaptureFixture[str]) -> str:
    evidence, manifest = review
    manifest_path = evidence.parent / "review.json"
    _write_json(manifest_path, manifest)
    assert main(["visual-alignment", str(manifest_path), "--evidence-root", str(evidence)]) == 0
    captured = output.readouterr()
    assert not captured.err
    return captured.out


@pytest.mark.parametrize("wrapped", [False, True], ids=["rendered-report", "check-report"])
def test_report_prioritizes_three_and_preserves_grouped_machine_details(
    review: tuple[Path, JsonObject], capsys: pytest.CaptureFixture[str], wrapped: bool
) -> None:
    evidence, manifest = review
    case = manifest["cases"][0]
    case["findings"] = [_review_item(rank) for rank in [4, 2, 1, 3]]
    report_path = evidence / case["before"]["report"]
    report = json.loads(report_path.read_bytes())
    machine_issues = report["issues"]
    assert [issue["code"] for issue in machine_issues] == ["node.bbox.height"] * 2
    if wrapped:
        _write_json(
            report_path,
            {
                "kind": "penflow-check-report",
                "checks": [
                    {
                        "name": "compare-rendered",
                        "status": "FAIL",
                        "exit_code": 1,
                        "issues": machine_issues,
                        "details": {key: value for key, value in report.items() if key != "issues"},
                    }
                ],
            },
        )
    before = {path.name: path.read_bytes() for path in evidence.iterdir()}

    output = _run(review, capsys)

    assert output == _run(review, capsys)
    headings = [line for line in output.splitlines() if line.startswith("#### ")]
    assert len(headings) == 3
    assert [line.partition(". ")[2] for line in headings] == [
        f"Finding {rank:02d}" for rank in (1, 2, 3)
    ]
    assert "Finding 04" in output  # Keep lower-priority observations discoverable.
    assert "Apply the compact control variant" in output
    assert "Right image, settings footer, primary action" in output
    assert "MATERIAL_DRIFT" in output and "before-check.json" in output
    assert "before.png" in output
    visible = output.replace("\\.", ".")
    assert visible.count("node.bbox.height") == 1
    for issue in machine_issues:
        assert issue["semantic_id"] in visible
    assert {path.name: path.read_bytes() for path in evidence.iterdir()} == before


@pytest.mark.parametrize(
    ("side", "field", "value", "diagnostic"),
    [
        ("runtime", "screen", "another-screen", "screen"),
        ("runtime", "state", "after-submit", "state"),
        ("runtime", "variant", "compact", "variant"),
        ("runtime", "viewport", [120, 90], "viewport"),
        ("design", "composite", True, "composite"),
    ],
)
def test_incompatible_pair_keeps_recapture_action_without_recommending_product_fix(
    review: tuple[Path, JsonObject],
    capsys: pytest.CaptureFixture[str],
    side: str,
    field: str,
    value: object,
    diagnostic: str,
) -> None:
    _, manifest = review
    case = manifest["cases"][0]
    case["before"][side][field] = value
    recapture = _review_item(2, action="recapture")
    recapture.update(proposal="Recapture the selected state at the reference dimensions")
    case["findings"].append(recapture)

    output = _run(review, capsys)

    assert "incompatible" in output.lower()
    assert diagnostic in output.lower()
    assert recapture["proposal"] in output
    assert "Apply the compact control variant" not in output
    assert "MATERIAL_DRIFT" in output


@pytest.mark.parametrize(
    "missing", ["runtime", "state", "variant", "images", "report", "measurement"]
)
def test_missing_observations_do_not_turn_machine_evidence_into_visual_conformance(
    review: tuple[Path, JsonObject], capsys: pytest.CaptureFixture[str], missing: str
) -> None:
    evidence, manifest = review
    pair = manifest["cases"][0]["before"]
    if missing == "measurement":
        _write_json(evidence / pair["report"], compare_rendered({}, None))
    elif missing == "state":
        pair["runtime"]["state"] = None
    elif missing == "variant":
        pair["runtime"].pop("variant")
    else:
        pair.pop(missing)

    output = _run(review, capsys)

    assert any(word in output.lower() for word in ("missing", "unobserved", "insufficient"))
    assert "Apply the compact control variant" not in output
    if missing == "measurement":
        assert "NOT_OBSERVED" in output
        assert "rendered.measurement.missing" in output.replace("\\.", ".")


def test_approval_and_measurements_require_resolvable_evidence(
    review: tuple[Path, JsonObject], capsys: pytest.CaptureFixture[str]
) -> None:
    evidence, manifest = review
    case = manifest["cases"][0]
    approval = _review_item(1, action="approved_divergence")
    approval.update(
        basis="decision",
        proposal="Keep the new ordering",
        approval={"path": "decision.md", "note": "Decision DESIGN-17"},
    )
    measurement = _review_item(2)
    measurement.update(
        basis="measurement",
        evidence=[{"path": "bounds.json", "note": "Observed height", "pointer": "/button/height"}],
    )
    case["findings"] = [approval, measurement]
    _write_json(evidence / "bounds.json", {"button": {"width": 70}})

    output = _run(review, capsys)

    assert "decision.md" in output.replace("\\.", ".") and "/button/height" in output
    assert approval["proposal"] not in output and measurement["proposal"] not in output

    (evidence / "decision.md").write_text("# DESIGN-17\nKeep the reviewed ordering.\n", "utf-8")
    _write_json(evidence / "bounds.json", {"button": {"height": 39}})
    output = _run(review, capsys)

    assert "Decision DESIGN-17" in output
    assert approval["proposal"] in output and measurement["proposal"] in output
    assert "39" in output


@pytest.mark.parametrize(
    "after_pair", ["matched", "new-state", "reused-capture", "combined", "metadata-only"]
)
def test_follow_up_requires_a_comparable_new_capture(
    review: tuple[Path, JsonObject], capsys: pytest.CaptureFixture[str], after_pair: str
) -> None:
    evidence, manifest = review
    case = manifest["cases"][0]
    after_observed = "Verified the compact variant on the new capture"
    follow_up = {
        "observed": after_observed,
        "evidence": [{"path": "after.png", "note": "Footer after the correction"}],
    }
    case["findings"][0]["follow_up"] = follow_up
    before = case["before"]
    after = deepcopy(before)
    case["after"] = after
    viewport = before["design"]["viewport"]
    after["report"] = "after-check.json"
    if after_pair == "combined":
        after["images"] = {"side_by_side": "after.png"}
        _write_png(evidence / "after.png", viewport, shade=90)
    else:
        before["images"] = {"design": "design.png", "runtime": "runtime.png"}
        after["images"] = {"design": "design.png", "runtime": "after.png"}
        _write_png(evidence / "design.png", viewport, shade=30, joined=False)
        _write_png(evidence / "runtime.png", viewport, joined=False)
        _write_png(evidence / "after.png", viewport, shade=90, joined=False)
    _write_json(evidence / "after-check.json", _rendered_report(after, evidence, expanded=False))
    if after_pair in {"reused-capture", "metadata-only"}:
        data = (evidence / "runtime.png").read_bytes()
        if after_pair == "metadata-only":
            text = b"tEXtAuthor\x00Reviewer"
            chunk = struct.pack(">I", len(text) - 4) + text + struct.pack(">I", zlib.crc32(text))
            data = data[:-12] + chunk + data[-12:]
        (evidence / "after.png").write_bytes(data)
    elif after_pair == "new-state":
        after["design"]["state"] = after["runtime"]["state"] = "different-state"

    output = _run(review, capsys)

    assert "after-check.json" in output
    assert (after_observed in output) == (after_pair == "matched")
    if after_pair == "new-state":
        assert "differ in frame, screen, state" in output
    elif after_pair in {"reused-capture", "metadata-only"}:
        assert "reuse the same runtime image data" in output
    elif after_pair == "combined":
        assert "separate design and runtime PNGs" in output


def test_outside_root_symlink_cannot_supply_a_capture(
    review: tuple[Path, JsonObject], capsys: pytest.CaptureFixture[str]
) -> None:
    evidence, manifest = review
    pair = manifest["cases"][0]["before"]
    capture = evidence / pair["images"]["side_by_side"]
    foreign = evidence.parent / "outside.png"
    capture.rename(foreign)
    capture.symlink_to(foreign)

    output = _run(review, capsys)

    assert "outside" in output.lower()
    assert "Apply the compact control variant" not in output
    assert capture.is_symlink() and foreign.is_file()


def test_capture_dimensions_can_invalidate_matching_viewport_declarations(
    review: tuple[Path, JsonObject], capsys: pytest.CaptureFixture[str]
) -> None:
    evidence, manifest = review
    pair = manifest["cases"][0]["before"]
    capture = evidence / pair["images"]["side_by_side"]
    width, height = pair["runtime"]["viewport"]
    _write_png(capture, [width - 1, height])

    output = _run(review, capsys)

    assert "incompatible" in output.lower()
    assert str((width - 1) * 2) in output
    assert "Apply the compact control variant" not in output


@pytest.mark.parametrize("content", ['{"version":1,"version":1}', '{"version":2,"cases":[]}', "[]"])
def test_invalid_manifest_has_an_error_exit_without_a_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], content: str
) -> None:
    path = tmp_path / "invalid.json"
    path.write_text(content, encoding="utf-8")

    assert main(["visual-alignment", str(path)]) == 2

    captured = capsys.readouterr()
    assert not captured.out
    assert captured.err


def test_separate_images_can_use_distinct_raster_scales(
    review: tuple[Path, JsonObject], capsys: pytest.CaptureFixture[str]
) -> None:
    evidence, manifest = review
    case = manifest["cases"][0]
    before = case["before"]
    viewport = before["design"]["viewport"]
    _write_png(evidence / "design.png", [axis * 2 for axis in viewport], joined=False)
    _write_png(evidence / "runtime.png", viewport, joined=False)
    before["images"] = {"design": "design.png", "design_scale": 2, "runtime": "runtime.png"}

    output = _run(review, capsys)

    assert "**Comparable**" in output
    assert "Apply the compact control variant" in output
    assert "/design.png)" in output and "/runtime.png)" in output

    before["images"].pop("design_scale")
    assert "**Incompatible**" in _run(review, capsys)


@pytest.mark.parametrize("status, comparisons", [("CONFORMING", [None]), ("NOT_OBSERVED", None)])
def test_unqualified_comparison_does_not_support_product_correction(
    review: tuple[Path, JsonObject],
    capsys: pytest.CaptureFixture[str],
    status: str,
    comparisons: list[object] | None,
) -> None:
    evidence, manifest = review
    pair = manifest["cases"][0]["before"]
    report_path = evidence / pair["report"]
    report = json.loads(report_path.read_bytes())
    report["status"] = status
    if comparisons is not None:
        report["comparisons"] = comparisons
    _write_json(report_path, report)

    output = _run(review, capsys)

    assert "**Insufficient observation**" in output
    assert status in output
    assert "Apply the compact control variant" not in output


def test_png_header_without_image_data_is_incompatible(
    review: tuple[Path, JsonObject], capsys: pytest.CaptureFixture[str]
) -> None:
    evidence, manifest = review
    capture = evidence / manifest["cases"][0]["before"]["images"]["side_by_side"]
    capture.write_bytes(capture.read_bytes()[:24])

    output = _run(review, capsys)

    assert "**Incompatible**" in output
    assert "incomplete PNG" in output
    assert "Apply the compact control variant" not in output


@pytest.mark.parametrize("explicit_project", [False, True])
def test_cli_resolves_evidence_relative_to_manifest_or_explicit_project(
    review: tuple[Path, JsonObject],
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    explicit_project: bool,
) -> None:
    evidence, manifest = review
    monkeypatch.chdir(evidence.parent)
    manifest_path = (evidence.parent if explicit_project else evidence) / "review.json"
    _write_json(manifest_path, manifest)
    args = ["visual-alignment", str(manifest_path.relative_to(evidence.parent))]
    if explicit_project:
        args.extend(["--project", "evidence"])

    # Exercise the parser before the legacy test harness can supply a project.
    assert cli.main(args) == 0
    captured = capsys.readouterr()
    assert not captured.err
    assert "**Comparable**" in captured.out
    assert "Apply the compact control variant" in captured.out
