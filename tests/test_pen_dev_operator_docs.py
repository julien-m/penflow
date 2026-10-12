# @spec AC-006: guidance names the pen.dev 1.2 MCP surface — .specs/features/078-pen-dev-operator-compatibility/spec.md#ac-006
# @spec AC-007: ordered C46 file-copy protocol, no filesystem prohibition — .specs/features/078-pen-dev-operator-compatibility/spec.md#ac-007
# @spec AC-008: C46 at design closure, preparation noncertifying — .specs/features/078-pen-dev-operator-compatibility/spec.md#ac-008
# @spec AC-014: save helper Accessibility grant and MCP save limitation — .specs/features/078-pen-dev-operator-compatibility/spec.md#ac-014
"""Operator guidance matches the pen.dev 1.2 MCP surface and the C46 verifier."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PENFLOW_SKILL = ROOT / ".agent-sync/skills/penflow/SKILL.md"
MOCKUP_SKILL = ROOT / ".agent-sync/skills/mockup-factory/SKILL.md"
GUIDES = (
    PENFLOW_SKILL,
    MOCKUP_SKILL,
    *sorted((ROOT / ".agent-sync/skills/mockup-factory/references").glob("*.md")),
    ROOT / "docs/verification-workflow.md",
    ROOT / "README.md",
)
OPERATOR_GUIDES = (
    PENFLOW_SKILL,
    MOCKUP_SKILL,
    ROOT / ".agent-sync/skills/mockup-factory/references/visual-validation.md",
    ROOT / "docs/verification-workflow.md",
    ROOT / "README.md",
)
OPERATOR_PHRASES = ("get_app_state", "`execute`", "ui.pen", "pen.dev")
OPEN_DOCUMENT = re.compile(r"open `[^`]*ui\.pen` in pen\.dev", re.IGNORECASE)
# A reworded prohibition still pairs a negation with reading/opening .pen bytes in one clause.
READ_PROHIBITION = re.compile(
    r"\b(never|do not|don't|must not|cannot)\b[^.\n]{0,40}\b(read|grep|access)\w*\b[^.\n]{0,40}\.pen\b",
    re.IGNORECASE,
)
REMOVED_TOOLS = re.compile(
    r"\b(batch_design|batch_get|snapshot_layout|get_screenshot|get_editor_state|export_nodes)\b"
)
LABELS = ("legacy", "historical", "receipt operation")
FILESYSTEM_PROHIBITIONS = (
    "MCP-only",
    "never use Read or Grep on .pen",
    "no .pen FS access",
    "must not read ui.pen",
)


@pytest.mark.parametrize("guide", GUIDES, ids=lambda path: path.relative_to(ROOT).as_posix())
def test_removed_mcp_tools_appear_only_in_labeled_lines(guide: Path) -> None:
    unlabeled = [
        line
        for line in guide.read_text(encoding="utf-8").splitlines()
        if REMOVED_TOOLS.search(line) and not any(label in line for label in LABELS)
    ]
    assert unlabeled == []


@pytest.mark.parametrize("guide", GUIDES, ids=lambda path: path.relative_to(ROOT).as_posix())
def test_no_guide_forbids_penflow_reading_the_pen_file(guide: Path) -> None:
    text = guide.read_text(encoding="utf-8")
    assert not [phrase for phrase in FILESYSTEM_PROHIBITIONS if phrase in text]
    assert READ_PROHIBITION.findall(text) == []


def test_current_mcp_surface_and_open_document_precondition_are_documented() -> None:
    combined = "\n".join(path.read_text(encoding="utf-8") for path in GUIDES)
    for phrase in ("get_app_state", "`execute`", "read_skill", "Open `ui.pen` in pen.dev"):
        assert phrase in combined
    for guide in OPERATOR_GUIDES:
        text = guide.read_text(encoding="utf-8")
        assert [phrase for phrase in OPERATOR_PHRASES if phrase not in text] == []
        assert OPEN_DOCUMENT.search(text) is not None


def test_c46_file_copy_protocol_steps_are_ordered() -> None:
    text = PENFLOW_SKILL.read_text(encoding="utf-8")
    section = text[text.index("## pen.dev 1.2 operator protocol") : text.index("## C51 workflow")]
    steps = (
        "pre.pen",
        "through `execute`",
        "penflow pencil-sync",
        "post.pen",
        "penflow-pencil-persistence-observation",
        "penflow verify-pencil-persistence",
        "penflow validate-report",
    )
    positions = [section.index(step) for step in steps]
    assert positions == sorted(positions)


def test_mockup_factory_requires_c46_at_design_closure_not_before_first_read() -> None:
    text = MOCKUP_SKILL.read_text(encoding="utf-8")
    assert "C46 is required at design closure, before any PASS" in text
    assert "preparation reads after a PASS trigger are noncertifying" in text
    assert "close actual C46 persistence before reading" not in text


@pytest.mark.parametrize(
    ("guide", "anchor", "steps"),
    [
        (
            ".agent-sync/skills/mockup-factory/SKILL.md",
            "Before any pen.dev MCP call",
            (
                "copy `ui.pen` to a pre snapshot",
                "mutate through `execute`",
                "penflow pencil-sync",
                "copy `ui.pen` to a post snapshot",
                "penflow-pencil-persistence-observation",
                "penflow verify-pencil-persistence",
                "penflow validate-report",
            ),
        ),
        (
            "docs/verification-workflow.md",
            "Open `ui.pen` in pen.dev and confirm it with `get_app_state`",
            (
                "copy `ui.pen` before the final mutation batch",
                "mutate through `execute`",
                "`pencil-sync` save trigger",
                "copy `ui.pen` again",
                "penflow-pencil-persistence-observation",
                "verify-pencil-persistence",
                "validate-report",
            ),
        ),
    ],
    ids=["mockup-factory", "verification-workflow"],
)
def test_c46_protocol_order_holds_in_each_operator_guide(
    guide: str, anchor: str, steps: tuple[str, ...]
) -> None:
    full = (ROOT / guide).read_text(encoding="utf-8")
    text = full[full.index(anchor) :]
    positions = [text.index(step) for step in steps]
    assert positions == sorted(positions)


HELPER_PHRASES = (
    "penflow doctor --install-save-helper",
    "Penflow Save.app",
    "Privacy & Security > Accessibility",
    "Automation prompt",
    "--save-timeout",
)
MCP_SAVE_PHRASES = (
    "MCP cannot save",
    "`execute` with `filePath` requires",
    "no mutation reaches disk without a save",
)


@pytest.mark.parametrize("guide", [PENFLOW_SKILL, ROOT / "README.md"], ids=["skill", "readme"])
def test_save_helper_grant_and_mcp_save_limit_are_documented(guide: Path) -> None:
    text = guide.read_text(encoding="utf-8")
    assert [phrase for phrase in HELPER_PHRASES if phrase not in text] == []
    assert [phrase for phrase in MCP_SAVE_PHRASES if phrase.lower() not in text.lower()] == []
