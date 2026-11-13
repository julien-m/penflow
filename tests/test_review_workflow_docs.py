"""Current skill entry points select review, not archived certification gates."""

from pathlib import Path
import re

import pytest

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / ".agent-sync/skills"


@pytest.mark.parametrize("name", ["penflow", "flow-ui-contract", "mockup-factory"])
def test_current_entry_is_short_and_keeps_diagnostics_explicit(name: str) -> None:
    path = SKILLS / name / "SKILL.md"
    text = path.read_text()
    assert "review-led-workflow.md" in text
    assert "penflow check --target" in text
    assert "certification.md" in text
    assert "C51 alone decides" not in text
    assert "require exact-profile PASS" not in text.lower()
    assert len(text.splitlines()) < 100
    archive = (path.parent / "certification.md").read_text()
    assert "## C51 workflow authority" in archive
    assert "C51 alone decides cumulative closure" in archive
    for target in re.findall(r"\]\(([^)]+\.md)\)", text):
        assert (path.parent / target).resolve().is_file(), target


def test_normal_policy_preserves_missing_observations_and_one_native_review() -> None:
    text = (ROOT / "docs/review-led-workflow.md").read_text()
    for phrase in (
        "one fresh generic native reviewer",
        "without implementer conversation history",
        "NOT_RUN",
        "certified: false",
        "Essential missing observations remain explicitly unverified",
        "Do not fabricate PASS",
        "historical FAIL/BLOCKED remains FAIL/BLOCKED",
        "ambiguous-write/deletion protections",
    ):
        assert phrase in text
