# @spec(AC-001)
# @spec(AC-002)
# @spec(FR-006)
# @spec(FR-007)
# @spec(FR-008)
from __future__ import annotations

import json
from pathlib import Path

import pytest

from penflow.cli import main
from penflow.evidence import (
    COHERENCE_CATEGORIES,
    VISION_CATEGORIES,
    validate_visual_evidence,
)

EXAMPLES_EVIDENCE = Path("examples/full/.mockup-validation/visual-evidence")
EXAMPLES_EXPECTED = Path("examples/full/expected-ui-tree.json")


def _expected_tree(path: Path, screen_ids: tuple[str, ...] = ("checkout",)) -> Path:
    screens = [
        {
            "name": screen_id,
            "pencil_id": f"{screen_id}Screen",
            "root": {
                "id": screen_id,
                "role": "container",
                "bbox": {"x": 0.0, "y": 0.0, "width": 390.0, "height": 844.0},
                "children": [],
            },
        }
        for screen_id in screen_ids
    ]
    path.write_text(json.dumps({"issues": [], "screens": screens}), encoding="utf-8")
    return path


def _criteria() -> list[dict[str, object]]:
    return [
        {
            "category": category,
            "result": "pass",
            "evidence": f"Vision evidence sentence for {category} on the checkout screen.",
            "blocking": False,
        }
        for category in VISION_CATEGORIES
    ]


def _coherence_criteria() -> list[dict[str, object]]:
    return [
        {
            "category": category,
            "result": "pass",
            "evidence": f"Coherence evidence sentence for {category} across the contact sheet.",
            "blocking": False,
        }
        for category in COHERENCE_CATEGORIES
    ]


def _add_coherence(evidence: Path, png: str = "contact-sheet.png") -> None:
    """Inject a valid coherence section and a non-empty contact-sheet PNG."""
    (evidence / png).write_bytes(b"\x89PNG\r\n\x1a\nfake-but-non-empty-sheet")
    _mutate_vision_report(
        evidence,
        lambda report: report.update(
            {"coherence": {"contact_sheet_png": png, "criteria": _coherence_criteria()}}
        ),
    )


def _packet(tmp_path: Path, screen_ids: tuple[str, ...] = ("checkout",)) -> tuple[Path, Path]:
    """Write a complete, valid evidence packet and matching expected tree."""
    evidence = tmp_path / "visual-evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    manifest_screens = []
    report_screens = []
    snapshot_screens = []
    for screen_id in screen_ids:
        png = f"{screen_id}Screen.png"
        (evidence / png).write_bytes(b"\x89PNG\r\n\x1a\nfake-but-non-empty")
        manifest_screens.append(
            {
                "screen_id": screen_id,
                "semantic_id": screen_id,
                "pencil_node_id": f"{screen_id}Screen",
                "png": png,
                "layout_checked": True,
                "screenshot_checked": True,
            }
        )
        report_screens.append(
            {
                "screen_id": screen_id,
                "semantic_id": screen_id,
                "pencil_node_id": f"{screen_id}Screen",
                "png": png,
                "criteria": _criteria(),
            }
        )
        snapshot_screens.append(
            {
                "screen_id": screen_id,
                "pencil_node_id": f"{screen_id}Screen",
                "width": 390,
                "height": 844,
            }
        )
    (evidence / "manifest.json").write_text(
        json.dumps(
            {
                "renderer": "pencil-mcp",
                "sourceFile": "ui.pen",
                "status": "PASS",
                "validatedAt": "2026-06-10",
                "screens": manifest_screens,
            }
        ),
        encoding="utf-8",
    )
    (evidence / "vision-report.json").write_text(
        json.dumps(
            {
                "version": 1,
                "kind": "penflow-vision-report",
                "status": "PASS",
                "renderer": "pencil-mcp",
                "sourceFile": "ui.pen",
                "model": "test-vision-model",
                "screens": report_screens,
            }
        ),
        encoding="utf-8",
    )
    (evidence / "layout-snapshot.json").write_text(
        json.dumps({"screens": snapshot_screens}), encoding="utf-8"
    )
    expected = _expected_tree(tmp_path / "expected-ui-tree.json", screen_ids)
    return evidence, expected


def _codes(evidence: Path, expected: Path | None) -> list[str]:
    issues = validate_visual_evidence(
        evidence, expected_tree_path=expected if expected is not None else None
    )
    return [issue["code"] for issue in issues]


def _mutate_vision_report(evidence: Path, mutate) -> None:
    path = evidence / "vision-report.json"
    report = json.loads(path.read_text(encoding="utf-8"))
    mutate(report)
    path.write_text(json.dumps(report), encoding="utf-8")


def test_complete_packet_passes(tmp_path: Path) -> None:
    evidence, expected = _packet(tmp_path)

    assert validate_visual_evidence(evidence, expected_tree_path=expected) == []
    assert (
        main(["validate-visual-evidence", str(evidence), "--expected", str(expected), "--json"])
        == 0
    )


def test_validator_output_is_byte_identical_on_reruns(tmp_path: Path) -> None:
    evidence, expected = _packet(tmp_path)
    (evidence / "checkoutScreen.png").unlink()
    _mutate_vision_report(evidence, lambda report: report["screens"][0]["criteria"].pop())

    first = json.dumps(validate_visual_evidence(evidence, expected_tree_path=expected))
    second = json.dumps(validate_visual_evidence(evidence, expected_tree_path=expected))

    assert first == second
    assert first != "[]"


def test_missing_png_fails(tmp_path: Path) -> None:
    evidence, expected = _packet(tmp_path)
    (evidence / "checkoutScreen.png").unlink()

    assert "evidence.png.missing" in _codes(evidence, expected)
    assert (
        main(["validate-visual-evidence", str(evidence), "--expected", str(expected), "--json"])
        == 1
    )


def test_empty_png_fails(tmp_path: Path) -> None:
    evidence, expected = _packet(tmp_path)
    (evidence / "checkoutScreen.png").write_bytes(b"")

    assert "evidence.png.empty" in _codes(evidence, expected)


def test_lenient_does_not_forgive_evidence_errors(tmp_path: Path) -> None:
    evidence, expected = _packet(tmp_path)
    (evidence / "checkoutScreen.png").unlink()

    assert (
        main(
            [
                "validate-visual-evidence",
                str(evidence),
                "--expected",
                str(expected),
                "--lenient",
                "--json",
            ]
        )
        == 1
    )


def test_uncovered_expected_screen_fails(tmp_path: Path) -> None:
    evidence, _ = _packet(tmp_path)
    expected = _expected_tree(tmp_path / "expected-two.json", ("checkout", "settings"))

    issues = validate_visual_evidence(evidence, expected_tree_path=expected)
    uncovered = [issue for issue in issues if issue["code"] == "evidence.screen.uncovered"]

    # The settings screen is missing from both the manifest and the vision report.
    assert len(uncovered) == 2
    assert {"manifest.json", "vision-report.json"} == {
        issue["message"].rsplit(" ", 1)[-1] for issue in uncovered
    }
    assert all("settings" in issue["message"] for issue in uncovered)


def test_no_expected_skips_coverage_and_bbox_checks(tmp_path: Path) -> None:
    evidence, _ = _packet(tmp_path)
    snapshot = json.loads((evidence / "layout-snapshot.json").read_text(encoding="utf-8"))
    snapshot["screens"][0]["height"] = 900  # would mismatch if expected were provided

    (evidence / "layout-snapshot.json").write_text(json.dumps(snapshot), encoding="utf-8")

    assert validate_visual_evidence(evidence) == []
    assert main(["validate-visual-evidence", str(evidence), "--json"]) == 0


def test_smuggled_deterministic_category_is_rejected_by_schema(tmp_path: Path) -> None:
    evidence, expected = _packet(tmp_path)
    _mutate_vision_report(
        evidence,
        lambda report: report["screens"][0]["criteria"][0].update({"category": "contrast"}),
    )

    codes = _codes(evidence, expected)

    assert "evidence.vision_report.invalid" in codes
    # The replaced criterion no longer answers its locked category either.
    assert "evidence.vision.category_missing" in codes
    assert (
        main(["validate-visual-evidence", str(evidence), "--expected", str(expected), "--json"])
        == 1
    )
    # The same lock holds through validate-report --schema (kind routing).
    assert (
        main(["validate-report", str(evidence / "vision-report.json"), "--schema", "--json"]) == 1
    )


@pytest.mark.parametrize("category", ["contrast", "touch_targets", "overflow", "alignment"])
def test_every_deterministic_category_fails_validate_report(tmp_path: Path, category: str) -> None:
    evidence, _ = _packet(tmp_path)
    _mutate_vision_report(
        evidence,
        lambda report: report["screens"][0]["criteria"][0].update({"category": category}),
    )

    assert (
        main(["validate-report", str(evidence / "vision-report.json"), "--schema", "--json"]) == 1
    )


def test_short_evidence_sentence_is_rejected(tmp_path: Path) -> None:
    evidence, expected = _packet(tmp_path)
    _mutate_vision_report(
        evidence,
        lambda report: report["screens"][0]["criteria"][0].update({"evidence": "ok"}),
    )

    assert "evidence.vision_report.invalid" in _codes(evidence, expected)
    assert (
        main(["validate-report", str(evidence / "vision-report.json"), "--schema", "--json"]) == 1
    )


def test_lowercase_result_enum_is_locked(tmp_path: Path) -> None:
    evidence, expected = _packet(tmp_path)
    _mutate_vision_report(
        evidence,
        lambda report: report["screens"][0]["criteria"][0].update({"result": "PASS"}),
    )

    assert "evidence.vision_report.invalid" in _codes(evidence, expected)


def test_additional_criterion_property_fails_closed(tmp_path: Path) -> None:
    evidence, expected = _packet(tmp_path)
    _mutate_vision_report(
        evidence,
        lambda report: report["screens"][0]["criteria"][0].update({"vibe": "good"}),
    )

    assert "evidence.vision_report.invalid" in _codes(evidence, expected)
    assert (
        main(["validate-report", str(evidence / "vision-report.json"), "--schema", "--json"]) == 1
    )


def test_missing_vision_category_fails(tmp_path: Path) -> None:
    evidence, expected = _packet(tmp_path)
    _mutate_vision_report(
        evidence,
        lambda report: report["screens"][0].update({"criteria": _criteria()[:4]}),
    )

    issues = validate_visual_evidence(evidence, expected_tree_path=expected)
    missing = [issue for issue in issues if issue["code"] == "evidence.vision.category_missing"]

    assert len(missing) == 1
    assert "imagery_quality" in missing[0]["message"]


def test_snapshot_within_tolerance_passes(tmp_path: Path) -> None:
    evidence, expected = _packet(tmp_path)
    snapshot = {"screens": [{"screen_id": "checkout", "width": 390, "height": 847}]}
    (evidence / "layout-snapshot.json").write_text(json.dumps(snapshot), encoding="utf-8")

    assert "evidence.snapshot.bbox_mismatch" not in _codes(evidence, expected)


def test_snapshot_beyond_tolerance_fails(tmp_path: Path) -> None:
    evidence, expected = _packet(tmp_path)
    snapshot = {"screens": [{"screen_id": "checkout", "width": 390, "height": 850}]}
    (evidence / "layout-snapshot.json").write_text(json.dumps(snapshot), encoding="utf-8")

    issues = validate_visual_evidence(evidence, expected_tree_path=expected)
    mismatches = [issue for issue in issues if issue["code"] == "evidence.snapshot.bbox_mismatch"]

    assert len(mismatches) == 1
    assert "390x850" in mismatches[0]["message"]
    assert "390x844" in mismatches[0]["message"]


def test_snapshot_is_optional(tmp_path: Path) -> None:
    evidence, expected = _packet(tmp_path)
    (evidence / "layout-snapshot.json").unlink()

    assert validate_visual_evidence(evidence, expected_tree_path=expected) == []


def test_malformed_snapshot_fails_closed(tmp_path: Path) -> None:
    evidence, expected = _packet(tmp_path)
    (evidence / "layout-snapshot.json").write_text("not json", encoding="utf-8")
    assert "evidence.snapshot.invalid" in _codes(evidence, expected)

    (evidence / "layout-snapshot.json").write_text(json.dumps({"frames": []}), encoding="utf-8")
    assert "evidence.snapshot.invalid" in _codes(evidence, expected)

    (evidence / "layout-snapshot.json").write_text(
        json.dumps({"screens": [{"screen_id": "checkout", "width": "390", "height": 844}]}),
        encoding="utf-8",
    )
    assert "evidence.snapshot.invalid" in _codes(evidence, expected)


def test_unmatched_snapshot_screen_is_ignored(tmp_path: Path) -> None:
    evidence, expected = _packet(tmp_path)
    snapshot = {"screens": [{"screen_id": "unknown-screen", "width": 9999, "height": 9999}]}
    (evidence / "layout-snapshot.json").write_text(json.dumps(snapshot), encoding="utf-8")

    assert validate_visual_evidence(evidence, expected_tree_path=expected) == []


def test_empty_evidence_dir_reports_missing_artifacts(tmp_path: Path) -> None:
    evidence = tmp_path / "empty-evidence"
    evidence.mkdir()
    expected = _expected_tree(tmp_path / "expected-ui-tree.json")

    codes = _codes(evidence, expected)

    assert "evidence.manifest.missing" in codes
    assert "evidence.vision_report.missing" in codes
    assert (
        main(["validate-visual-evidence", str(evidence), "--expected", str(expected), "--json"])
        == 1
    )


def test_unparseable_manifest_is_invalid_but_other_checks_run(tmp_path: Path) -> None:
    evidence, expected = _packet(tmp_path)
    (evidence / "manifest.json").write_text("{broken", encoding="utf-8")

    codes = _codes(evidence, expected)

    assert "evidence.manifest.invalid" in codes
    # Vision-report coverage still runs and is satisfied.
    assert "evidence.screen.uncovered" not in codes


def test_schema_invalid_manifest_still_checks_pngs(tmp_path: Path) -> None:
    evidence, expected = _packet(tmp_path)
    manifest = json.loads((evidence / "manifest.json").read_text(encoding="utf-8"))
    del manifest["renderer"]
    manifest["screens"][0]["png"] = "missing.png"
    (evidence / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    codes = _codes(evidence, expected)

    assert "evidence.manifest.invalid" in codes
    assert "evidence.png.missing" in codes


def test_missing_directory_exits_2(tmp_path: Path) -> None:
    assert main(["validate-visual-evidence", str(tmp_path / "nope"), "--json"]) == 2


def test_missing_expected_tree_exits_2(tmp_path: Path) -> None:
    evidence, _ = _packet(tmp_path)

    assert (
        main(
            [
                "validate-visual-evidence",
                str(evidence),
                "--expected",
                str(tmp_path / "missing.json"),
                "--json",
            ]
        )
        == 2
    )


def test_malformed_expected_tree_exits_2(tmp_path: Path) -> None:
    evidence, _ = _packet(tmp_path)
    malformed = tmp_path / "malformed.json"
    malformed.write_text(json.dumps({"screens": "nope"}), encoding="utf-8")

    assert (
        main(["validate-visual-evidence", str(evidence), "--expected", str(malformed), "--json"])
        == 2
    )


def test_validate_report_routes_by_kind_not_filename(tmp_path: Path) -> None:
    evidence, _ = _packet(tmp_path)
    renamed = tmp_path / "anything.json"
    renamed.write_text(
        (evidence / "vision-report.json").read_text(encoding="utf-8"), encoding="utf-8"
    )

    assert main(["validate-report", str(renamed), "--schema", "--json"]) == 0


def test_examples_full_packet_passes_end_to_end() -> None:
    assert (
        main(
            [
                "validate-visual-evidence",
                str(EXAMPLES_EVIDENCE),
                "--expected",
                str(EXAMPLES_EXPECTED),
                "--json",
            ]
        )
        == 0
    )
    assert (
        main(
            ["validate-report", str(EXAMPLES_EVIDENCE / "vision-report.json"), "--schema", "--json"]
        )
        == 0
    )


# @spec AC-003: multi-screen tree without coherence fails — .specs/features/053-cross-mockup-coherence-contact-sheet/spec.md#ac-003
def test_multi_screen_packet_without_coherence_fails(tmp_path: Path) -> None:
    evidence, expected = _packet(tmp_path, ("checkout", "settings"))

    codes = _codes(evidence, expected)

    assert "evidence.coherence.missing" in codes
    assert (
        main(["validate-visual-evidence", str(evidence), "--expected", str(expected), "--json"])
        == 1
    )


# @spec AC-001: valid coherence section passes both validators — .specs/features/053-cross-mockup-coherence-contact-sheet/spec.md#ac-001
def test_multi_screen_packet_with_coherence_passes(tmp_path: Path) -> None:
    evidence, expected = _packet(tmp_path, ("checkout", "settings"))
    _add_coherence(evidence)

    assert validate_visual_evidence(evidence, expected_tree_path=expected) == []
    assert (
        main(["validate-visual-evidence", str(evidence), "--expected", str(expected), "--json"])
        == 0
    )


# @spec AC-004: single-screen tree passes without coherence — .specs/features/053-cross-mockup-coherence-contact-sheet/spec.md#ac-004
def test_single_screen_packet_passes_without_coherence(tmp_path: Path) -> None:
    evidence, expected = _packet(tmp_path)

    assert "evidence.coherence.missing" not in _codes(evidence, expected)
    assert validate_visual_evidence(evidence, expected_tree_path=expected) == []


def test_no_expected_tree_does_not_require_coherence(tmp_path: Path) -> None:
    # Without --expected the screen count is unknowable, mirroring coverage checks.
    evidence, _ = _packet(tmp_path, ("checkout", "settings"))

    assert validate_visual_evidence(evidence) == []
    assert main(["validate-visual-evidence", str(evidence), "--json"]) == 0


# @spec AC-002: category smuggling fails in both directions — .specs/features/053-cross-mockup-coherence-contact-sheet/spec.md#ac-002
def test_per_screen_category_smuggled_into_coherence_fails_schema(tmp_path: Path) -> None:
    evidence, expected = _packet(tmp_path, ("checkout", "settings"))
    _add_coherence(evidence)
    _mutate_vision_report(
        evidence,
        lambda report: report["coherence"]["criteria"][0].update({"category": "readability"}),
    )

    codes = _codes(evidence, expected)

    assert "evidence.vision_report.invalid" in codes
    # The replaced criterion no longer answers its locked coherence category either.
    assert "evidence.coherence.category_missing" in codes
    assert (
        main(["validate-report", str(evidence / "vision-report.json"), "--schema", "--json"]) == 1
    )


def test_coherence_category_smuggled_into_screen_fails_schema(tmp_path: Path) -> None:
    evidence, expected = _packet(tmp_path)
    _mutate_vision_report(
        evidence,
        lambda report: report["screens"][0]["criteria"][0].update(
            {"category": "palette_coherence"}
        ),
    )

    assert "evidence.vision_report.invalid" in _codes(evidence, expected)
    assert (
        main(["validate-report", str(evidence / "vision-report.json"), "--schema", "--json"]) == 1
    )


@pytest.mark.parametrize("category", ["contrast", "consistency", "alignment"])
def test_deterministic_category_in_coherence_fails_validate_report(
    tmp_path: Path, category: str
) -> None:
    evidence, _ = _packet(tmp_path)
    _add_coherence(evidence)
    _mutate_vision_report(
        evidence,
        lambda report: report["coherence"]["criteria"][0].update({"category": category}),
    )

    assert (
        main(["validate-report", str(evidence / "vision-report.json"), "--schema", "--json"]) == 1
    )


# @spec AC-005: contact sheet PNG must exist non-empty — .specs/features/053-cross-mockup-coherence-contact-sheet/spec.md#ac-005
def test_missing_contact_sheet_png_fails(tmp_path: Path) -> None:
    evidence, expected = _packet(tmp_path, ("checkout", "settings"))
    _add_coherence(evidence)
    (evidence / "contact-sheet.png").unlink()

    assert "evidence.contact_sheet.missing" in _codes(evidence, expected)
    assert (
        main(["validate-visual-evidence", str(evidence), "--expected", str(expected), "--json"])
        == 1
    )


def test_empty_contact_sheet_png_fails(tmp_path: Path) -> None:
    evidence, expected = _packet(tmp_path, ("checkout", "settings"))
    _add_coherence(evidence)
    (evidence / "contact-sheet.png").write_bytes(b"")

    assert "evidence.contact_sheet.empty" in _codes(evidence, expected)


# @spec AC-006: incomplete coherence categories fail — .specs/features/053-cross-mockup-coherence-contact-sheet/spec.md#ac-006
def test_incomplete_coherence_categories_fail(tmp_path: Path) -> None:
    evidence, expected = _packet(tmp_path, ("checkout", "settings"))
    _add_coherence(evidence)
    _mutate_vision_report(
        evidence,
        lambda report: report["coherence"].update({"criteria": _coherence_criteria()[:3]}),
    )

    issues = validate_visual_evidence(evidence, expected_tree_path=expected)
    missing = [issue for issue in issues if issue["code"] == "evidence.coherence.category_missing"]

    assert len(missing) == 1
    assert "component_recognition" in missing[0]["message"]


def test_coherence_section_on_single_screen_is_still_validated(tmp_path: Path) -> None:
    # Optional section, but once present its contact sheet must be provable.
    evidence, expected = _packet(tmp_path)
    _add_coherence(evidence)
    (evidence / "contact-sheet.png").unlink()

    assert "evidence.contact_sheet.missing" in _codes(evidence, expected)


# @spec AC-007: byte-identical reruns on a failing coherence packet — .specs/features/053-cross-mockup-coherence-contact-sheet/spec.md#ac-007
def test_coherence_validator_output_is_byte_identical_on_reruns(tmp_path: Path) -> None:
    evidence, expected = _packet(tmp_path, ("checkout", "settings"))
    _add_coherence(evidence)
    (evidence / "contact-sheet.png").write_bytes(b"")
    _mutate_vision_report(
        evidence,
        lambda report: report["coherence"]["criteria"].pop(),
    )

    first = json.dumps(validate_visual_evidence(evidence, expected_tree_path=expected))
    second = json.dumps(validate_visual_evidence(evidence, expected_tree_path=expected))

    assert first == second
    assert first != "[]"


# @spec AC-009: examples/full packet carries a valid coherence section — .specs/features/053-cross-mockup-coherence-contact-sheet/spec.md#ac-009
def test_examples_full_coherence_section_is_valid() -> None:
    report = json.loads((EXAMPLES_EVIDENCE / "vision-report.json").read_text(encoding="utf-8"))

    assert report["coherence"]["contact_sheet_png"] == "contact-sheet.png"
    assert {item["category"] for item in report["coherence"]["criteria"]} == set(
        COHERENCE_CATEGORIES
    )
    sheet = EXAMPLES_EVIDENCE / "contact-sheet.png"
    assert sheet.exists()
    assert sheet.stat().st_size > 0


def test_legacy_visual_report_result_enum_is_tightened(tmp_path: Path) -> None:
    legacy = json.loads((EXAMPLES_EVIDENCE / "visual-report.json").read_text(encoding="utf-8"))
    legacy["screens"][0]["audit"][0]["result"] = "Looks fine to me"
    path = tmp_path / "visual-report.json"
    path.write_text(json.dumps(legacy), encoding="utf-8")

    assert main(["validate-report", str(path), "--schema", "--json"]) == 1
