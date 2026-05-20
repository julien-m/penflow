from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PENFLOW_SKILL = ROOT / ".agent-sync" / "skills" / "penflow" / "SKILL.md"
FLOW_SKILL = ROOT / ".agent-sync" / "skills" / "flow-ui-contract" / "SKILL.md"
FLOW_README = ROOT / ".agent-sync" / "skills" / "flow-ui-contract" / "README.md"
SEMANTIC_TREE_REFERENCE = (
    ROOT / ".agent-sync" / "skills" / "flow-ui-contract" / "references" / "semantic-ui-tree.md"
)
README = ROOT / "README.md"
PROJECT_INTEGRATION = ROOT / "docs" / "project-integration.md"


REQUIRED_COMMANDS = (
    "export-semantic-tree",
    "validate-semantic-tree",
    "draft-pen-from-tree",
    "enrich-pen",
    "map-pencil-context",
    "validate-pen",
    "export-expected",
    "code-ir --from-context",
    "reverse-pen",
    "validate-actual actual-ui-tree.json --schema",
    "compare-tree expected-ui-tree.json actual-ui-tree.json",
    "review-report compare-report.json",
    "fix-report compare-report.json",
    "demo --out examples/full",
)


def test_penflow_skill_documents_llm_workflow_modes() -> None:
    skill = PENFLOW_SKILL.read_text(encoding="utf-8")

    for heading in (
        "## Purpose",
        "## Tree Contracts",
        "## Forward Mode",
        "## Pencil Enrichment Mode",
        "## Reverse Mode",
        "## Post-Implementation Compare Mode",
        "## Full Demo Mode",
        "## Review Mode",
        "## Fix Mode",
    ):
        assert heading in skill

    for command in REQUIRED_COMMANDS:
        assert command in skill

    assert "semantic-ui-tree.json" in skill
    assert "expected-ui-tree.json" in skill
    assert "actual-ui-tree.json" in skill
    assert "../flow-ui-contract/references/semantic-ui-tree.md" in skill
    assert "External adapters produce `actual-ui-tree.json`" in skill
    assert "does **not** run browsers, Xcode, simulators, Playwright, React Native" in skill


def test_flow_ui_contract_skill_and_readme_document_modes() -> None:
    skill = FLOW_SKILL.read_text(encoding="utf-8")
    readme = FLOW_README.read_text(encoding="utf-8")
    combined = skill + "\n" + readme

    for phrase in (
        "Forward Command Sequence",
        "Enrichment Command Sequence",
        "Reverse Command Sequence",
        "Post-Implementation Compare Sequence",
        "Full Demo Sequence",
        "Tree Formation Contract",
        "Semantic Tree Formation",
        "Expected `semantic-ui-tree.json` excerpt",
        "NEEDS CLARIFICATION",
        "never write into LiveSpec `.specs/`",
        "external adapters emit `actual-ui-tree.json`",
        "writes a directory containing `semantic-ui-tree.json` and `flow-ui-contract/`",
    ):
        assert phrase in combined

    for command in REQUIRED_COMMANDS:
        assert command in combined

    assert "flow-ui-contract` skill" in skill
    assert "no separate `specify-flows` slash command" in combined
    assert "flow-ui-contract/flows" in skill
    assert "flow-ui-contract/screens" in skill
    assert "transition: checkout-form --submit_payment--> confirmation" in skill
    assert '"trigger": "submit_payment"' in skill
    assert "references/semantic-ui-tree.md" in combined
    assert "does **not** run browser, Xcode, simulator, Playwright, React Native" in skill


def test_semantic_tree_reference_documents_formation_contract() -> None:
    reference = SEMANTIC_TREE_REFERENCE.read_text(encoding="utf-8")

    for phrase in (
        "Do not hand-write `semantic-ui-tree.json`",
        "flows/*.md` becomes `flows[]`",
        "screens/*.md` becomes `screens[]`",
        "root` plus recursive `children`",
        "data dependencies become `binding` and `entity`",
        "`states[]`, `validations[]`, and `side_effects[]`",
        "Pencil `context`",
        "`expected-ui-tree.json`",
        "`actual-ui-tree.json`",
    ):
        assert phrase in reference


def test_root_readme_syncs_c15_command_sequences() -> None:
    readme = README.read_text(encoding="utf-8")

    for heading in (
        "### LLM Workflow Sequences",
        "### Semantic Tree Formation",
        "#### Forward",
        "#### Enrichment",
        "#### Reverse",
        "#### Post-Implementation Compare",
        "#### Full Demo",
    ):
        assert heading in readme

    for command in REQUIRED_COMMANDS:
        assert command in readme

    assert (
        "Penflow validates and compares that file; it does not launch or inspect the running app"
        in readme
    )
    assert "writes a directory containing `semantic-ui-tree.json` and `flow-ui-contract/`" in readme
    assert ".agent-sync/skills/flow-ui-contract/references/semantic-ui-tree.md" in readme


def test_project_integration_guide_documents_existing_project_adoption() -> None:
    guide = PROJECT_INTEGRATION.read_text(encoding="utf-8")

    for heading in (
        "# Integrating Penflow Into an Existing Project",
        "## Recommended Layout",
        "## Path A: New Project or New Feature Area",
        "## Path B: Existing Pencil Mockups",
        "## Path C: Legacy Project With Mockups but No Flows",
        "## Implementation Handoff",
        "## Runtime Verification",
        "## CI Gate",
        "## Migration Checklist",
    ):
        assert heading in guide

    for phrase in (
        "my-app/",
        "penflow/flow-ui-contract",
        "semantic-ui-tree.json",
        "ui.enriched.pen",
        "pencil-context-map.json",
        "expected-ui-tree.json",
        "code-ir.json",
        "actual-ui-tree.json",
        "compare-report.json",
        "review.md",
        "fix.md",
        "validate-flow-specs penflow/flow-ui-contract",
        "export-semantic-tree penflow/flow-ui-contract",
        "draft-pen-from-tree penflow/semantic-ui-tree.json",
        "enrich-pen design/ui.pen",
        "map-pencil-context penflow/ui.enriched.pen",
        "reverse-pen design/ui.pen --out penflow/reverse-output",
        "penflow/reverse-output/semantic-ui-tree.json",
        "[NEEDS CLARIFICATION]",
        "validate-actual penflow/actual-ui-tree.json --schema",
        "compare-tree penflow/expected-ui-tree.json penflow/actual-ui-tree.json",
        "review-report penflow/compare-report.json",
        "fix-report penflow/compare-report.json",
        "semantic_id",
        "binding",
        "entity",
        "test_id",
        "Penflow validates and compares that file; it does not launch the app",
    ):
        assert phrase in guide


def test_project_integration_guide_is_discoverable() -> None:
    readme = README.read_text(encoding="utf-8")
    skill = PENFLOW_SKILL.read_text(encoding="utf-8")

    assert "docs/project-integration.md" in readme
    assert "Existing Project Integration" in readme
    assert "Project Integration Mode" in skill
    assert "../../../docs/project-integration.md" in skill
