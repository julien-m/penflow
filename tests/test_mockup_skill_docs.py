# @spec(AC-007)
# @spec(AC-011)
# @spec(AC-012)
# @spec(AC-013)
# @spec(FR-001)
# @spec(FR-007)
# @spec(FR-008)
# @spec(FR-013)
# @spec(FR-014)
# @spec FR-008 AC-004 AC-005 AC-006: Feature 075 public project-boundary guidance.
from __future__ import annotations

import ast
import json


from skill_doc_paths import (
    ROOT,
    PENFLOW_SKILL,
    MOCKUP_SKILL,
    MOCKUP_README,
    MOCKUP_WORKFLOW,
    MOCKUP_RUBRIC,
    MOCKUP_VISUAL,
    EXAMPLE_VISUAL_DIR,
    README,
    PROJECT_INTEGRATION,
)


def test_mockup_factory_skill_is_penflow_local_and_tree_aware() -> None:
    skill = MOCKUP_SKILL.read_text(encoding="utf-8")
    readme = MOCKUP_README.read_text(encoding="utf-8")
    penflow_skill = PENFLOW_SKILL.read_text(encoding="utf-8")
    root_readme = README.read_text(encoding="utf-8")
    combined = f"{skill}\n{readme}\n{penflow_skill}\n{root_readme}"

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
    combined = f"{skill}\n{readme}\n{workflow}\n{rubric}\n{visual}\n{penflow_skill}\n{root_readme}\n{project_guide}"

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
    assert manifest["status"] == "PASS"
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
    combined = f"{visual}\n{skill}\n{mockup_readme}\n{root_readme}"

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
    combined = f"{skill}\n{visual}"

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


# @spec AC-012: actual provenance receipt is documented — .specs/features/067-wp2-9-run-pipeline/spec.md#ac-012
def test_actual_provenance_receipt_is_documented() -> None:
    penflow_skill = PENFLOW_SKILL.read_text(encoding="utf-8")
    readme = README.read_text(encoding="utf-8")

    for document in (penflow_skill, readme):
        for phrase in (
            "validate-actual-provenance",
            "actual-ui-tree.provenance.json",
            "penflow-actual-provenance",
            "sourceKind",
            "runtime-capture",
            "static-demo-fixture",
            "provenance.digest.mismatch",
            "provenance.actual.derived_from_expected",
            "provenance.source_kind.inadmissible",
            "provenance.content.path_mismatch",
            "provenance.content.path_invalid",
            "--require-fresh",
            "--actual-max-age-seconds",
            "86400",
            "finite and strictly positive",
            "1e999",
            "allow_nan=False",
            "SHA-256 of the actual-tree bytes",
        ):
            assert phrase in document

    # The run gate list includes the provenance gate as the final step.
    assert "validate-actual-provenance" in penflow_skill


def test_readme_documents_theme_fingerprint_and_armed_gate() -> None:
    readme = README.read_text(encoding="utf-8")

    assert "penflow theme-fingerprint theme.css --json" in readme
    assert "--theme-css" in readme
    assert "evidence.theme.stale" in readme
    assert "evidence.theme.missing" in readme
    assert "runId" in readme
