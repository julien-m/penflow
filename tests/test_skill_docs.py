from __future__ import annotations

import ast
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PENFLOW_SKILL = ROOT / ".agent-sync" / "skills" / "penflow" / "SKILL.md"
FLOW_SKILL = ROOT / ".agent-sync" / "skills" / "flow-ui-contract" / "SKILL.md"
FLOW_README = ROOT / ".agent-sync" / "skills" / "flow-ui-contract" / "README.md"
MOCKUP_SKILL = ROOT / ".agent-sync" / "skills" / "mockup-factory" / "SKILL.md"
MOCKUP_README = ROOT / ".agent-sync" / "skills" / "mockup-factory" / "README.md"
MOCKUP_WORKFLOW = ROOT / ".agent-sync" / "skills" / "mockup-factory" / "references" / "workflow.md"
MOCKUP_RUBRIC = (
    ROOT / ".agent-sync" / "skills" / "mockup-factory" / "references" / "audit-rubric.md"
)
MOCKUP_VISUAL = (
    ROOT / ".agent-sync" / "skills" / "mockup-factory" / "references" / "visual-validation.md"
)
EXAMPLE_VISUAL_DIR = ROOT / "examples" / "full" / ".mockup-validation" / "visual-evidence"
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
        "review-report.json",
        "fix-report.json",
        "validate-flow-contract penflow/flow-ui-contract/contract.json",
        "export-semantic-tree penflow/flow-ui-contract/contract.json",
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


def test_mockup_factory_skill_is_penflow_local_and_tree_aware() -> None:
    skill = MOCKUP_SKILL.read_text(encoding="utf-8")
    readme = MOCKUP_README.read_text(encoding="utf-8")
    penflow_skill = PENFLOW_SKILL.read_text(encoding="utf-8")
    root_readme = README.read_text(encoding="utf-8")
    combined = "\n".join([skill, readme, penflow_skill, root_readme])

    for phrase in (
        "name: mockup-factory",
        "Penflow-local guided UX/UI optimizer",
        "flow-ui-contract/contract.json",
        "semantic-ui-tree.json",
        "ui.pen",
        "pencil-context-map.json",
        "expected-ui-tree.json",
        "drift-report.json",
        "penflow detect-drift",
        "screen_id",
        "semantic_id",
        "pencil_node_id",
        "Contract gate",
        "UX/UI gate",
    ):
        assert phrase in combined

    assert "Forbidden in Penflow Python core" in skill
    assert "../mockup-factory/SKILL.md" in penflow_skill
    assert ".agent-sync/skills/mockup-factory/SKILL.md" in root_readme
    assert "ai-ressources remains a conventions/reference source" in readme


def test_mockup_factory_visual_evidence_gate_is_documented() -> None:
    skill = MOCKUP_SKILL.read_text(encoding="utf-8")
    readme = MOCKUP_README.read_text(encoding="utf-8")
    workflow = MOCKUP_WORKFLOW.read_text(encoding="utf-8")
    rubric = MOCKUP_RUBRIC.read_text(encoding="utf-8")
    visual = MOCKUP_VISUAL.read_text(encoding="utf-8")
    penflow_skill = PENFLOW_SKILL.read_text(encoding="utf-8")
    root_readme = README.read_text(encoding="utf-8")
    project_guide = PROJECT_INTEGRATION.read_text(encoding="utf-8")
    combined = "\n".join(
        [skill, readme, workflow, rubric, visual, penflow_skill, root_readme, project_guide]
    )

    for phrase in (
        "Visual Evidence Gate",
        "snapshot_layout",
        "get_screenshot",
        "export PNG",
        ".mockup-validation/visual-evidence/manifest.json",
        "visual-report.json",
        "BLOCKED_VISUAL_NOT_RUN",
        "PASSED_WITH_WARNINGS",
        "ESCALATED",
        "layout snapshot",
        "screenshot inspection",
        "Pencil renderer",
        "screen_id",
        "semantic_id",
        "pencil_node_id",
    ):
        assert phrase in combined


def test_examples_full_visual_evidence_packet_is_real_and_anchored() -> None:
    manifest_path = EXAMPLE_VISUAL_DIR / "manifest.json"
    report_path = EXAMPLE_VISUAL_DIR / "visual-report.json"
    png_path = EXAMPLE_VISUAL_DIR / "checkoutScreen.png"

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert manifest["renderer"] == "pencil-mcp"
    assert manifest["sourceFile"] == "examples/full/ui.pen"
    assert manifest["status"] == "PASSED_WITH_WARNINGS"
    screen = manifest["screens"][0]
    assert screen["screen_id"] == "checkout"
    assert screen["semantic_id"] == "checkout"
    assert screen["pencil_node_id"] == "checkoutScreen"
    assert screen["png"] == "checkoutScreen.png"
    assert screen["layout_checked"] is True
    assert screen["screenshot_checked"] is True

    assert png_path.exists()
    assert png_path.stat().st_size > 0
    assert report["status"] == "PASSED_WITH_WARNINGS"
    assert report["renderer"] == "pencil-mcp"
    screen_report = report["screens"][0]
    assert screen_report["pencil_node_id"] == "checkoutScreen"
    assert any("snapshot_layout" in item for item in screen_report["evidence"])
    assert any("get_screenshot" in item for item in screen_report["evidence"])
    assert any("export_nodes" in item for item in screen_report["evidence"])
    categories = {item["category"] for item in screen_report["audit"]}
    assert "Density" in categories
    assert "Responsive behavior" in categories


def test_mockup_factory_rubric_covers_guided_optimizer_gate() -> None:
    workflow = MOCKUP_WORKFLOW.read_text(encoding="utf-8")
    rubric = MOCKUP_RUBRIC.read_text(encoding="utf-8")
    project_guide = PROJECT_INTEGRATION.read_text(encoding="utf-8")
    combined = workflow + "\n" + rubric + "\n" + project_guide

    for phrase in (
        "Freeze a checklist",
        "Fix only checklist items",
        "PASS",
        "PASSED_WITH_WARNINGS",
        "ESCALATED",
        "Semantic contract",
        "Visual alignment",
        "Hierarchy",
        "CTA placement",
        "Density",
        "Accessibility",
        "Responsive behavior",
        "Modernity",
        "Polish",
        "critical UX/UI issues",
    ):
        assert phrase in combined


def test_penflow_python_core_has_no_mockup_factory_runtime_dependencies() -> None:
    forbidden_imports = (
        "appium",
        "browser_use",
        "cc_hub",
        "mcp__pencil",
        "playwright",
        "selenium",
    )

    for path in (ROOT / "penflow").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module)

        for token in forbidden_imports:
            assert all(not module.startswith(token) for module in imports), (
                f"{path} must not import {token}"
            )

    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8").lower()
    for token in (
        "appium",
        "browser-use",
        "cc-hub",
        "mcp-pencil",
        "playwright",
        "react-native",
        "selenium",
        "xcode",
    ):
        assert token not in pyproject
