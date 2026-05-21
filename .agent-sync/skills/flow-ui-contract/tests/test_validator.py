# @spec FR-022: pytest suite covering all BLOCKING check categories
#   — .specs/features/027-define-flow-screen-spec-grammar/spec.md#fr-005
"""Tests for flow-ui-contract validator.py.

Each test class covers one category of BLOCKING checks.
At least one pass + one fail case per category.

Run: python3 -m pytest .agent-sync/skills/flow-ui-contract/tests/ -v
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# Resolve paths
VALIDATOR = Path(__file__).parent.parent / "validator.py"
FIXTURES = Path(__file__).parent / "fixtures"

VALID_FLOW = FIXTURES / "valid_flow.md"
VALID_SCREEN = FIXTURES / "valid_screen.md"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def run_validator(*args: str) -> tuple[int, str]:
    """Run validator.py with given args, return (exit_code, stdout)."""
    result = subprocess.run(
        [sys.executable, str(VALIDATOR), *args],
        capture_output=True,
        text=True,
    )
    return result.returncode, result.stdout


def assert_pass(path: Path) -> str:
    code, output = run_validator(str(path))
    assert code == 0, f"Expected PASS (exit 0) but got exit {code}.\nOutput:\n{output}"
    assert "VALIDATION_RESULT: PASS" in output
    return output


def assert_fail(path: Path, expected_fragment: str = "") -> str:
    code, output = run_validator(str(path))
    assert code == 1, f"Expected FAIL (exit 1) but got exit {code}.\nOutput:\n{output}"
    assert "VALIDATION_RESULT: FAIL" in output
    if expected_fragment:
        assert expected_fragment in output, (
            f"Expected fragment '{expected_fragment}' not found in output:\n{output}"
        )
    return output


# ---------------------------------------------------------------------------
# Category: Frontmatter parsing
# ---------------------------------------------------------------------------


class TestFrontmatterParsing:
    def test_valid_flow_passes(self):
        assert_pass(VALID_FLOW)

    def test_invalid_yaml_fails(self):
        assert_fail(FIXTURES / "invalid_bad_frontmatter.md", "YAML parse error")

    def test_valid_screen_passes(self):
        assert_pass(VALID_SCREEN)


# ---------------------------------------------------------------------------
# Category: Required fields
# ---------------------------------------------------------------------------


class TestRequiredFields:
    def test_valid_flow_has_all_fields(self):
        output = assert_pass(VALID_FLOW)
        assert "Missing required frontmatter field" not in output

    def test_missing_field_fails(self, tmp_path):
        # Create a flow without the 'title' field
        content = VALID_FLOW.read_text().replace('title: "Reserve a session"\n', "")
        f = tmp_path / "no_title.md"
        f.write_text(content)
        assert_fail(f, "title")


# ---------------------------------------------------------------------------
# Category: Required sections
# ---------------------------------------------------------------------------


class TestRequiredSections:
    def test_valid_flow_has_all_sections(self):
        assert_pass(VALID_FLOW)

    def test_missing_success_criteria_fails(self):
        assert_fail(FIXTURES / "invalid_missing_section.md", "## Success Criteria")

    def test_valid_screen_has_all_sections(self):
        assert_pass(VALID_SCREEN)

    def test_missing_screen_section_fails(self, tmp_path):
        content = VALID_SCREEN.read_text().replace("## Erreurs\n", "")
        f = tmp_path / "no_errors_section.md"
        f.write_text(content)
        assert_fail(f, "## Erreurs")


# ---------------------------------------------------------------------------
# Category: ID sequentiality
# ---------------------------------------------------------------------------


class TestIDSequentiality:
    def test_valid_flow_ids_pass(self):
        assert_pass(VALID_FLOW)

    def test_id_gap_fails(self):
        assert_fail(FIXTURES / "invalid_id_gap.md", "gap")

    def test_flow_id_format(self, tmp_path):
        content = VALID_FLOW.read_text().replace("FLOW-BOOKING", "flow-booking")
        f = tmp_path / "bad_flow_id.md"
        f.write_text(content)
        assert_fail(f)


# ---------------------------------------------------------------------------
# Category: AC↔FR mapping
# ---------------------------------------------------------------------------


class TestACFRMapping:
    def test_valid_mapping_passes(self):
        assert_pass(VALID_FLOW)

    def test_fr_cites_missing_ac_fails(self):
        assert_fail(FIXTURES / "invalid_fr_cites_missing_ac.md", "AC-099")

    def test_uncited_ac_fails(self, tmp_path):
        # Add AC-004 which is not cited by any FR (FRs only cite AC-001, AC-002, AC-003)
        content = VALID_FLOW.read_text().replace(
            "- **AC-003** — A confirmation screen is shown after successful booking.",
            "- **AC-003** — A confirmation screen is shown after successful booking.\n- **AC-004** — Extra AC not cited by any FR.",
        )
        f = tmp_path / "uncited_ac.md"
        f.write_text(content)
        assert_fail(f, "AC-004")


# ---------------------------------------------------------------------------
# Category: Stories — P1 required
# ---------------------------------------------------------------------------


class TestStories:
    def test_valid_flow_stories_pass(self):
        assert_pass(VALID_FLOW)

    def test_no_p1_story_fails(self, tmp_path):
        content = VALID_FLOW.read_text().replace(
            "### P1 — Client books a session successfully",
            "### P2 — Client books a session successfully",
        )
        f = tmp_path / "no_p1.md"
        f.write_text(content)
        assert_fail(f, "P1")

    def test_missing_narrative_fails(self, tmp_path):
        content = VALID_FLOW.read_text().replace(
            "- **As a** registered client\n- **I want** to select a time slot and confirm a booking\n- **So that** I can reserve time with a practitioner",
            "Narrative intentionally removed.",
        )
        f = tmp_path / "no_narrative.md"
        f.write_text(content)
        assert_fail(f, "As a")

    def test_missing_priority_reason_fails(self, tmp_path):
        content = VALID_FLOW.read_text().replace(
            "**Priority reason:** Core revenue flow — without it the product has no value.", ""
        )
        f = tmp_path / "no_priority_reason.md"
        f.write_text(content)
        assert_fail(f, "Priority reason")


# ---------------------------------------------------------------------------
# Category: Gherkin blocks
# ---------------------------------------------------------------------------


class TestGherkinBlocks:
    def test_valid_gherkin_passes(self):
        assert_pass(VALID_FLOW)

    def test_pseudo_gherkin_fails(self):
        assert_fail(FIXTURES / "invalid_no_gherkin.md")

    def test_missing_feature_keyword_fails(self, tmp_path):
        content = VALID_FLOW.read_text().replace("Feature: Session booking", "")
        f = tmp_path / "no_feature_kw.md"
        f.write_text(content)
        assert_fail(f, "Feature:")

    def test_missing_scenario_keyword_fails(self, tmp_path):
        content = (
            VALID_FLOW.read_text()
            .replace(
                "  Scenario: Client books an available slot",
                "  Case: Client books an available slot",
            )
            .replace("  Scenario: No slots available", "  Case: No slots available")
        )
        f = tmp_path / "no_scenario_kw.md"
        f.write_text(content)
        assert_fail(f, "Scenario:")


# ---------------------------------------------------------------------------
# Category: Mermaid blocks
# ---------------------------------------------------------------------------


class TestMermaidBlocks:
    def test_valid_mermaid_passes(self):
        assert_pass(VALID_FLOW)

    def test_missing_mermaid_fails(self):
        assert_fail(FIXTURES / "invalid_no_mermaid.md", "No fenced ```mermaid block")

    def test_mermaid_without_flowchart_fails(self, tmp_path):
        content = VALID_FLOW.read_text().replace(
            "flowchart TD\n    A[Client opens booking form]", "sequenceDiagram\n    participant A"
        )
        f = tmp_path / "mermaid_no_flowchart.md"
        f.write_text(content)
        assert_fail(f, "flowchart TD")


# ---------------------------------------------------------------------------
# Category: NEEDS CLARIFICATION count
# ---------------------------------------------------------------------------


class TestNeedsClarification:
    def test_no_clarifications_passes(self):
        output = assert_pass(VALID_FLOW)
        assert "NEEDS CLARIFICATION" not in output or "WARNING" not in output

    def test_too_many_clarifications_warns(self):
        code, output = run_validator(str(FIXTURES / "invalid_too_many_clarifications.md"))
        # Too many clarifications = WARNING only (not BLOCKING for draft status)
        # Exit code should be 0 (PASS) since it's only a warning
        assert code == 0, (
            f"Expected exit 0 (warnings don't block) but got {code}.\nOutput:\n{output}"
        )
        assert "WARNING" in output
        assert "NEEDS CLARIFICATION" in output

    def test_too_many_clarifications_blocks_reviewed_status(self, tmp_path):
        content = (
            (FIXTURES / "invalid_too_many_clarifications.md")
            .read_text()
            .replace("status: draft", "status: reviewed")
        )
        f = tmp_path / "reviewed_with_open_questions.md"
        f.write_text(content)
        assert_fail(f, "blocks reviewed/promoted")


# ---------------------------------------------------------------------------
# Category: Batch --dir mode
# ---------------------------------------------------------------------------


class TestBatchDir:
    def test_dir_with_valid_only(self, tmp_path):
        import shutil

        shutil.copy(VALID_FLOW, tmp_path / "flow1.md")
        shutil.copy(VALID_SCREEN, tmp_path / "screen1.md")
        code, output = run_validator("--dir", str(tmp_path))
        assert code == 0, f"Expected exit 0 for all-valid dir.\nOutput:\n{output}"
        assert output.count("VALIDATION_RESULT: PASS") == 2

    def test_dir_with_mix_fails(self, tmp_path):
        import shutil

        shutil.copy(VALID_FLOW, tmp_path / "valid.md")
        shutil.copy(FIXTURES / "invalid_missing_section.md", tmp_path / "invalid.md")
        code, output = run_validator("--dir", str(tmp_path))
        assert code == 1, f"Expected exit 1 for mixed dir.\nOutput:\n{output}"
        assert "VALIDATION_RESULT: FAIL" in output
        assert "VALIDATION_RESULT: PASS" in output

    def test_dir_all_invalid_fails(self, tmp_path):
        import shutil

        shutil.copy(FIXTURES / "invalid_missing_section.md", tmp_path / "a.md")
        shutil.copy(FIXTURES / "invalid_id_gap.md", tmp_path / "b.md")
        code, output = run_validator("--dir", str(tmp_path))
        assert code == 1
        assert output.count("VALIDATION_RESULT: FAIL") == 2

    def test_dir_recurses_into_nested_specs_tree(self, tmp_path):
        import shutil

        flows_dir = tmp_path / "flows"
        screens_dir = tmp_path / "screens"
        flows_dir.mkdir()
        screens_dir.mkdir()
        shutil.copy(VALID_FLOW, flows_dir / "booking.md")
        shutil.copy(VALID_SCREEN, screens_dir / "web_payment.md")
        code, output = run_validator("--dir", str(tmp_path))
        assert code == 0, f"Expected recursive dir validation to pass.\nOutput:\n{output}"
        assert output.count("VALIDATION_RESULT: PASS") == 2


# ---------------------------------------------------------------------------
# Category: Status / surface / priority validation
# ---------------------------------------------------------------------------


class TestEnumValidation:
    def test_invalid_status_fails(self, tmp_path):
        content = VALID_FLOW.read_text().replace("status: draft", "status: wip")
        f = tmp_path / "bad_status.md"
        f.write_text(content)
        assert_fail(f, "status")

    def test_invalid_priority_fails(self, tmp_path):
        content = VALID_FLOW.read_text().replace("priority: P1", "priority: P4")
        f = tmp_path / "bad_priority.md"
        f.write_text(content)
        assert_fail(f, "priority")

    def test_invalid_surface_fails(self, tmp_path):
        content = VALID_FLOW.read_text().replace("  - mobile\n", "  - tablet\n")
        f = tmp_path / "bad_surface.md"
        f.write_text(content)
        assert_fail(f, "tablet")


# ---------------------------------------------------------------------------
# Category: Manifest status mode
# ---------------------------------------------------------------------------


class TestStatusMode:
    def test_status_reports_fresh_stale_and_unspecified(self, tmp_path):
        manifest = tmp_path / "mockups" / "manifest.json"
        manifest.parent.mkdir()
        manifest.write_text((FIXTURES / "status_manifest.json").read_text())

        code, output = run_validator("--status", "--target", str(tmp_path))

        assert code == 0, output
        assert "STATUS_RESULT: PASS" in output
        assert "fresh_screen | fresh" in output
        assert "stale_screen | stale" in output
        assert "missing_spec | unspecified" in output
        assert "fresh: 1" in output
        assert "stale: 1" in output
        assert "unspecified: 1" in output

    def test_status_missing_manifest_fails(self, tmp_path):
        code, output = run_validator("--status", "--target", str(tmp_path))

        assert code == 1
        assert "STATUS_RESULT: FAIL" in output
        assert "manifest.json not found" in output
