# @spec(AC-011)
# @spec(AC-012)
# @spec(FR-001)
# @spec(FR-007)
# @spec(FR-008)
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
THEME_CONTRACT = ROOT / "docs" / "theme-contract.md"
PENCIL_EXPORT_BATCH_ISSUE = ROOT / "docs" / "pencil-export-nodes-batch-issue.md"


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


def test_pencil_sync_gate_is_documented_for_stale_editor_state() -> None:
    penflow_skill = PENFLOW_SKILL.read_text(encoding="utf-8")
    mockup_skill = MOCKUP_SKILL.read_text(encoding="utf-8")
    readme = README.read_text(encoding="utf-8")
    combined = "\n".join([penflow_skill, mockup_skill, readme])

    for phrase in (
        "penflow pencil-sync",
        "After every Pencil",
        "batch_design",
        "before any Penflow CLI command that reads",
        "BLOCKED",
        "fewer screens",
    ):
        assert phrase in combined


def test_draft_pen_from_tree_is_documented_as_wireframe_not_final_mockup() -> None:
    penflow_skill = PENFLOW_SKILL.read_text(encoding="utf-8")
    flow_skill = FLOW_SKILL.read_text(encoding="utf-8")
    mockup_skill = MOCKUP_SKILL.read_text(encoding="utf-8")
    readme = README.read_text(encoding="utf-8")
    combined = "\n".join([penflow_skill, flow_skill, mockup_skill, readme])

    for phrase in (
        'fidelity: "wireframe"',
        "draft = structure / wireframe",
        "PAS un mockup final",
        "hi-fi passe par mockup-factory",
    ):
        assert phrase in combined


def test_penflow_run_apex_no_goal_and_export_nodes_fallback_are_documented() -> None:
    penflow_skill = PENFLOW_SKILL.read_text(encoding="utf-8")
    issue = PENCIL_EXPORT_BATCH_ISSUE.read_text(encoding="utf-8")

    for phrase in (
        "penflow run --target",
        "unite naturelle",
        "Penflow ne cree jamais de goal runtime propre",
        "-G/--no-goal",
        "export_nodes",
        "exports unitaires",
        "wrong .pen file",
        "PF-PENCIL-EXPORT-NODES-BATCH-20260701",
    ):
        assert phrase in penflow_skill

    for phrase in (
        "PF-PENCIL-EXPORT-NODES-BATCH-20260701",
        "wrong .pen file",
        "get_editor_state",
        "unit export",
        "three-node batch succeeds",
        "four-node batch fails",
        "Pencil MCP/app batch-export state issue",
        "exports unitaires",
    ):
        assert phrase in issue


def test_theme_contract_documents_extended_token_lint_surface() -> None:
    contract = THEME_CONTRACT.read_text(encoding="utf-8")
    penflow_skill = PENFLOW_SKILL.read_text(encoding="utf-8")
    readme = README.read_text(encoding="utf-8")
    combined = "\n".join([contract, penflow_skill, readme])

    for phrase in (
        "docs/theme-contract.md",
        "font-mono",
        "font-size-xs",
        "font-size-xl",
        "success",
        "warning",
        "info",
        "panel-2",
        "palette-*",
        "radius-*",
        "spacing_scale",
        "radius_scale",
        "fontsize_scale",
        "random families still fail",
    ):
        assert phrase in combined


def test_context_grammar_and_strict_anchor_mapping_are_documented() -> None:
    penflow_skill = PENFLOW_SKILL.read_text(encoding="utf-8")
    flow_skill = FLOW_SKILL.read_text(encoding="utf-8")
    mockup_skill = MOCKUP_SKILL.read_text(encoding="utf-8")
    readme = README.read_text(encoding="utf-8")
    combined = "\n".join([penflow_skill, flow_skill, mockup_skill, readme])

    for phrase in (
        "Pencil Context Grammar",
        "key=value",
        "semantic_id=cockpit-live.git; role=container",
        "batch_design",
        "--strict-anchors",
        "--create-placeholders",
        "PARTIAL",
        "ambiguous or unmapped anchors block",
    ):
        assert phrase in combined


def test_dense_consistency_grouping_is_documented() -> None:
    penflow_skill = PENFLOW_SKILL.read_text(encoding="utf-8")
    mockup_skill = MOCKUP_SKILL.read_text(encoding="utf-8")
    rubric = MOCKUP_RUBRIC.read_text(encoding="utf-8")
    readme = README.read_text(encoding="utf-8")
    combined = "\n".join([penflow_skill, mockup_skill, rubric, readme])

    for phrase in (
        "role+intent+variant+size-class",
        "anonymous containers",
        "56px headers",
        "820px panel",
        "aggregated",
        "`fill`/`fontFamily`",
    ):
        assert phrase in combined


def test_audit_visual_layout_snapshot_gate_is_documented() -> None:
    penflow_skill = PENFLOW_SKILL.read_text(encoding="utf-8")
    mockup_skill = MOCKUP_SKILL.read_text(encoding="utf-8")
    rubric = MOCKUP_RUBRIC.read_text(encoding="utf-8")
    workflow = MOCKUP_WORKFLOW.read_text(encoding="utf-8")
    readme = README.read_text(encoding="utf-8")
    combined = "\n".join([penflow_skill, mockup_skill, rubric, workflow, readme])

    for phrase in (
        "--layout-snapshot",
        "layout-snapshot.json",
        "when a renderer",
        "real Pencil bboxes",
        "flex-parent",
        "non-geometric checks",
    ):
        assert phrase in combined


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
        "Quality Gate",
        "gate table",
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


def test_visual_evidence_gate_is_the_exit_code_not_prose() -> None:
    visual = MOCKUP_VISUAL.read_text(encoding="utf-8")

    for phrase in (
        "export_nodes",
        "snapshot_layout",
        "layout-snapshot.json",
        "vision-report.json",
        "penflow validate-visual-evidence",
        "visual_balance",
        "rendering_artifacts",
        "readability",
        "perceived_hierarchy",
        "imagery_quality",
        "exit code, not prose",
        "BLOCKED_VISUAL_NOT_RUN",
        "penflow-vision-report",
        "evidence.screen.uncovered",
        "evidence.snapshot.bbox_mismatch",
        "Reference Fidelity",
        "references-manifest.json",
        "reference_fidelity",
        "layout_match",
        "palette_match",
        "component_parity",
        "density_match",
        "validate-reference-fidelity",
        "reference.evidence_is_reference_copy",
        "reference.llm_metric_disagreement",
    ):
        assert phrase in visual

    # Deterministic categories stay with audit-visual; vision must not absorb them.
    assert "audit-visual" in visual

    skill = MOCKUP_SKILL.read_text(encoding="utf-8")
    workflow = MOCKUP_WORKFLOW.read_text(encoding="utf-8")
    rubric = MOCKUP_RUBRIC.read_text(encoding="utf-8")
    penflow_skill = PENFLOW_SKILL.read_text(encoding="utf-8")
    root_readme = README.read_text(encoding="utf-8")
    project_guide = PROJECT_INTEGRATION.read_text(encoding="utf-8")
    for doc in (skill, workflow, rubric, penflow_skill, root_readme, project_guide):
        assert "validate-visual-evidence" in doc
    for doc in (skill, penflow_skill, root_readme):
        assert "validate-reference-fidelity" in doc


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


# @spec AC-001, AC-002: prescriptive gate table + single Critical definition — .specs/features/052-prescriptive-rubric-bounded-fix-loop/spec.md
def test_mockup_factory_rubric_maps_every_category_to_a_scripted_gate() -> None:
    rubric = MOCKUP_RUBRIC.read_text(encoding="utf-8")

    for phrase in (
        "penflow lint-tokens",
        "penflow check-consistency",
        "penflow audit-visual",
        "penflow detect-drift",
        "penflow compare-tree",
        "penflow validate-visual-evidence",
        "exit 0",
        "summary.blocking == 0",
        "0.98",
        "`blocking: true`",
        "error severity",
        "error-severity",
        "Critical — Single Definition",
        "Advisory UX Notes — Never Decide PASS/FAIL",
        "penflow-mockup-audit",
        "penflow validate-report",
        "no `--lenient` in the canonical chain",
        "BLOCKED_VISUAL_NOT_RUN",
    ):
        assert phrase in rubric

    for gate in (
        "`tokens`",
        "`consistency`",
        "`accessibility_alignment`",
        "`contract`",
        "`structural_fidelity`",
        "`balance_readability`",
    ):
        assert gate in rubric


# @spec AC-008: contact-sheet protocol documented — .specs/features/053-cross-mockup-coherence-contact-sheet/spec.md#ac-008
def test_mockup_factory_documents_cross_mockup_coherence_contact_sheet() -> None:
    visual = MOCKUP_VISUAL.read_text(encoding="utf-8")
    workflow = MOCKUP_WORKFLOW.read_text(encoding="utf-8")

    for phrase in (
        "Cross-Mockup Coherence (Contact Sheet)",
        "uniform scale",
        "contact sheet",
        "contact_sheet_png",
        "cross_screen_rhythm",
        "palette_coherence",
        "typography_coherence",
        "component_recognition",
        "evidence.coherence.missing",
        "evidence.contact_sheet.missing",
        "evidence.coherence.category_missing",
        "penflow check-consistency",
        "≥ 2 screens",
    ):
        assert phrase in visual

    # The numeric anchor stays deterministic; vision never restates it.
    assert "047" in visual

    for phrase in (
        "contact sheet",
        "coherence",
        "uniform scale",
        "check-consistency",
    ):
        assert phrase in workflow


# @spec AC-001: exported PNGs use terminal and browser preview channels — .specs/features/057-visual-preview-proof-channel/spec.md#ac-001
def test_mockup_factory_docs_expose_pngs_through_visual_preview_channel() -> None:
    visual = MOCKUP_VISUAL.read_text(encoding="utf-8")
    skill = MOCKUP_SKILL.read_text(encoding="utf-8")
    mockup_readme = MOCKUP_README.read_text(encoding="utf-8")
    root_readme = README.read_text(encoding="utf-8")
    combined = "\n".join([visual, skill, mockup_readme, root_readme])

    for phrase in (
        "visual-preview url",
        "Markdown image",
        "absolute path",
        "contact-sheet.png",
        "annotation and iteration only",
        "preview URLs",
        "not canonical proof",
        "penflow validate-visual-evidence",
        "exit 0",
        "visual-preview is unavailable",
        "browser preview unavailable",
        "Allowed from this skill",
        "Forbidden in Penflow Python core",
    ):
        assert phrase in combined


# @spec AC-003: bounded fix-re-audit loop — .specs/features/052-prescriptive-rubric-bounded-fix-loop/spec.md#ac-003
def test_mockup_factory_workflow_bounds_the_fix_loop() -> None:
    workflow = MOCKUP_WORKFLOW.read_text(encoding="utf-8")

    for phrase in (
        "iteration <= 3",
        "after iteration 3",
        "No PASS without a final clean run",
        "Rerun the full command chain",
        "ESCALATED",
        "residual_issues",
        "state.json",
        "penflow lint-tokens",
        "penflow check-consistency",
        "penflow audit-visual",
        "penflow validate-report",
        "penflow-mockup-audit",
        "penflow-mockup-checklist",
        "BLOCKED_VISUAL_NOT_RUN",
    ):
        assert phrase in workflow


# @spec AC-010: SKILL.md preconditions + quality gate — .specs/features/052-prescriptive-rubric-bounded-fix-loop/spec.md#ac-010
def test_mockup_factory_skill_preconditions_include_the_three_gate_commands() -> None:
    skill = MOCKUP_SKILL.read_text(encoding="utf-8")

    for phrase in (
        "penflow lint-tokens",
        "penflow check-consistency",
        "penflow audit-visual",
        "no `--lenient` in the canonical chain",
        "iteration <= 3",
        "no PASS without a final clean run",
        "penflow-mockup-audit",
        "penflow validate-report .mockup-validation/audit-report.json --schema",
        "single CI-able final check",
    ):
        assert phrase in skill


def test_mockup_factory_docs_require_receipts_before_visual_pass() -> None:
    skill = MOCKUP_SKILL.read_text(encoding="utf-8")
    visual = MOCKUP_VISUAL.read_text(encoding="utf-8")
    combined = "\n".join([skill, visual])

    for phrase in (
        "before writing `vision-report.json`",
        "do not write `vision-report.json` before displaying each image",
        "generated_by",
        "inputs[]",
        "sha256",
        "Every category evidence sentence must cite the evaluated file name",
        "every evaluated PNG/contact sheet must resolve inside",
        "symlinks into `references/`",
        "SHA mismatch",
        "Receipts are mandatory and prose cannot replace them",
        "every executed gate must cite an existing `report_path`",
        "`pass` => 0",
        "`fail` => non-zero",
        "`not_run` => null/null",
    ):
        assert phrase in combined


# @spec AC-011: docs seed checklist via penflow checklist-from-drift — .specs/features/055-checklist-from-drift-seeding/spec.md#ac-011
def test_mockup_factory_docs_seed_checklist_via_checklist_from_drift() -> None:
    skill = MOCKUP_SKILL.read_text(encoding="utf-8")
    workflow = MOCKUP_WORKFLOW.read_text(encoding="utf-8")

    for document in (skill, workflow):
        assert "penflow checklist-from-drift" in document
        # The contract gate is machine-seeded; other-gate items are appended
        # at the skill layer only after seeding.
        assert "after seeding" in document


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


# @spec AC-010: Skill docs pin runId, theme-fingerprint, and --theme-css — .specs/features/056-evidence-run-identity-theme-fingerprint/spec.md#ac-010
def test_mockup_factory_docs_bind_evidence_to_run_and_theme() -> None:
    visual = MOCKUP_VISUAL.read_text(encoding="utf-8")
    workflow = MOCKUP_WORKFLOW.read_text(encoding="utf-8")
    skill = MOCKUP_SKILL.read_text(encoding="utf-8")

    # Step 5 (evidence artifacts write) stamps the manifest with run identity
    # and the theme fingerprint obtained via the command.
    for phrase in ("runId", "penflow theme-fingerprint", "theme"):
        assert phrase in visual
    # The gate command is armed with the theme in all three documents.
    for document in (visual, workflow, skill):
        assert "--theme-css" in document
        assert "penflow theme-fingerprint" in document
        assert "runId" in document


def test_readme_documents_theme_fingerprint_and_armed_gate() -> None:
    readme = README.read_text(encoding="utf-8")

    assert "penflow theme-fingerprint theme.css --json" in readme
    assert "--theme-css" in readme
    assert "evidence.theme.stale" in readme
    assert "evidence.theme.missing" in readme
    assert "runId" in readme
