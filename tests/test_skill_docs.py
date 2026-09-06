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

import json


from skill_doc_paths import (
    ROOT,
    PENFLOW_SKILL,
    FLOW_SKILL,
    FLOW_README,
    MOCKUP_SKILL,
    MOCKUP_WORKFLOW,
    MOCKUP_RUBRIC,
    MOCKUP_DESIGN_TASTE,
    FLOW_DESIGN_READ,
    SEMANTIC_TREE_REFERENCE,
    README,
    THEME_CONTRACT,
    PENCIL_EXPORT_BATCH_ISSUE,
    REQUIRED_COMMANDS,
    PENFLOW_DEMO_COMMANDS,
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

    for command in (*REQUIRED_COMMANDS[:-1], *PENFLOW_DEMO_COMMANDS):
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
    combined = f"{penflow_skill}\n{mockup_skill}\n{readme}"

    for phrase in (
        "penflow pencil-sync",
        "After every Pencil",
        "batch_design",
        "before any Penflow CLI command that reads",
        "BLOCKED",
        "fewer screens",
    ):
        assert phrase in combined


def test_pencil_persistence_receipt_is_documented_as_the_only_closing_gate() -> None:
    penflow_skill = PENFLOW_SKILL.read_text(encoding="utf-8")
    readme = README.read_text(encoding="utf-8")
    combined = f"{penflow_skill}\n{readme}"

    for phrase in (
        "verify-pencil-persistence",
        "persistence_status: UNVERIFIED",
        "closes_persistence: false",
        "distinct pre/post",
        "validate-report",
        "Only",
        "PASS",
        "stale",
        "replayed",
        "tampered",
    ):
        assert phrase in combined


def test_strict_closure_is_explicit_read_only_and_fail_closed() -> None:
    combined = "\n".join(
        [
            PENFLOW_SKILL.read_text(encoding="utf-8"),
            README.read_text(encoding="utf-8"),
        ]
    )

    for phrase in (
        "--strict-closure",
        ".penflow-run/strict-closure.json",
        "fresh independent `runtime-capture`",
        "homologous",
        "structured blocking",
        "one identical run id",
        "read-only",
        "Omitting `--strict-closure`",
    ):
        assert phrase in combined


def test_draft_pen_from_tree_is_documented_as_wireframe_not_final_mockup() -> None:
    penflow_skill = PENFLOW_SKILL.read_text(encoding="utf-8")
    flow_skill = FLOW_SKILL.read_text(encoding="utf-8")
    mockup_skill = MOCKUP_SKILL.read_text(encoding="utf-8")
    readme = README.read_text(encoding="utf-8")
    combined = f"{penflow_skill}\n{flow_skill}\n{mockup_skill}\n{readme}"

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
    combined = f"{contract}\n{penflow_skill}\n{readme}"

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


def test_context_grammar_and_exhaustive_mapping_are_documented() -> None:
    penflow_skill = PENFLOW_SKILL.read_text(encoding="utf-8")
    flow_skill = FLOW_SKILL.read_text(encoding="utf-8")
    mockup_skill = MOCKUP_SKILL.read_text(encoding="utf-8")
    readme = README.read_text(encoding="utf-8")
    combined = f"{penflow_skill}\n{flow_skill}\n{mockup_skill}\n{readme}"

    for phrase in (
        "Pencil Context Grammar",
        "key=value",
        "classification=semantic",
        "classification=inherited",
        "classification=decorative",
        "batch_design",
        "--strict-coverage",
        "--coverage-out",
        "audit-context-coverage",
        "--strict-anchors",
        "forward-only diagnostic evidence",
    ):
        assert phrase in combined


def test_dense_consistency_grouping_is_documented() -> None:
    penflow_skill = PENFLOW_SKILL.read_text(encoding="utf-8")
    mockup_skill = MOCKUP_SKILL.read_text(encoding="utf-8")
    rubric = MOCKUP_RUBRIC.read_text(encoding="utf-8")
    readme = README.read_text(encoding="utf-8")
    combined = f"{penflow_skill}\n{mockup_skill}\n{rubric}\n{readme}"

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
    combined = f"{penflow_skill}\n{mockup_skill}\n{rubric}\n{workflow}\n{readme}"

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


def test_design_read_capture_is_documented() -> None:
    skill = FLOW_SKILL.read_text(encoding="utf-8")
    reference = FLOW_DESIGN_READ.read_text(encoding="utf-8")
    combined = skill + "\n" + reference

    for phrase in (
        "Design Read Capture",
        "design-read.json",
        "design-read-protocol.md",
        "Reading this as:",
        "landing",
        "showcase",
        "variance",
        "motion",
        "density",
    ):
        assert phrase in combined


def test_design_taste_advisory_pass_is_documented() -> None:
    skill = MOCKUP_SKILL.read_text(encoding="utf-8")
    rubric = MOCKUP_RUBRIC.read_text(encoding="utf-8")
    reference = MOCKUP_DESIGN_TASTE.read_text(encoding="utf-8")

    for phrase in (
        "design-taste-advisory",
        "design-taste.md",
        "never decides PASS/FAIL",
        "never adds checklist items",
        "never changes gate status",
    ):
        assert phrase in skill + "\n" + reference

    assert "Design taste" in rubric
    assert "Advisory only" in reference


def test_vision_report_schema_categories_unchanged() -> None:
    schema = json.loads((ROOT / "penflow" / "schemas" / "vision-report.schema.json").read_text())

    screen_categories = schema["properties"]["screens"]["items"]["properties"]["criteria"]["items"][
        "properties"
    ]["category"]["enum"]
    coherence_categories = schema["properties"]["coherence"]["properties"]["criteria"]["items"][
        "properties"
    ]["category"]["enum"]
    reference_categories = schema["properties"]["reference_fidelity"]["items"]["properties"][
        "criteria"
    ]["items"]["properties"]["category"]["enum"]

    assert screen_categories == [
        "visual_balance",
        "rendering_artifacts",
        "readability",
        "perceived_hierarchy",
        "imagery_quality",
    ]
    assert coherence_categories == [
        "cross_screen_rhythm",
        "palette_coherence",
        "typography_coherence",
        "component_recognition",
    ]
    assert reference_categories == [
        "layout_match",
        "palette_match",
        "component_parity",
        "density_match",
    ]

    rubric = MOCKUP_RUBRIC.read_text(encoding="utf-8")
    gate_table = rubric.split("## Gate Table", maxsplit=1)[1].split(
        "## Advisory UX Notes", maxsplit=1
    )[0]
    advisory_notes = rubric.split("## Advisory UX Notes", maxsplit=1)[1]
    gate_rows = [
        line
        for line in gate_table.splitlines()
        if line.startswith("| `") and not line.startswith("| `Gate")
    ]
    assert gate_rows == [
        "| `tokens` | Design tokens (palette, spacing, radius, typography) | `penflow lint-tokens <target>/ui.pen --theme-css <target>/theme.css -o <target>/token-lint-report.json --json` | exit 0 | `token-lint-report.json` |",
        "| `consistency` | Cross-screen component consistency | `penflow check-consistency <target>/expected-ui-tree.json --group-by role+intent+variant+size-class -o <target>/consistency-report.json --json` | exit 0 | `consistency-report.json` |",
        "| `accessibility_alignment` | Accessibility + Visual alignment (contrast, touch targets, overlap/overflow, text fit) | `penflow audit-visual <target>/expected-ui-tree.json --theme-css <target>/theme.css --layout-snapshot <target>/.mockup-validation/visual-evidence/layout-snapshot.json -o <target>/visual-metrics-report.json --json` when a renderer produced `layout-snapshot.json`; otherwise omit `--layout-snapshot` | zero error-severity issues — exit 0 under the strict default (`info` never blocks) | `visual-metrics-report.json` |",
        "| `contract` | Semantic contract drift | `penflow detect-drift <target>/flow-ui-contract/contract.json <target>/semantic-ui-tree.json <target>/ui.pen --out <target>/drift-report.json --json` | `summary.blocking == 0` and exit 0 | `drift-report.json` |",
        "| `structural_fidelity` | Structural fidelity vs runtime | `penflow compare-tree <target>/expected-ui-tree.json <target>/actual-ui-tree.json --out <target>/compare-report.json --json` | score ≥ 0.98 (strict default threshold) — exit 0 | `compare-report.json` |",
        "| `balance_readability` | Balance / readability (vision-only) | `penflow validate-visual-evidence <target>/.mockup-validation/visual-evidence --expected <target>/expected-ui-tree.json --json`; when references exist, also `penflow validate-reference-fidelity <target>/.mockup-validation/visual-evidence --references <target>/references --json` | both exits 0, zero `blocking: true` criteria with result `fail` in `vision-report.json`, and reference-fidelity status PASS when references exist | `.mockup-validation/visual-evidence/vision-report.json`, optional reference-fidelity report |",
    ]
    assert "Design taste" not in gate_table
    assert "Design taste" in advisory_notes


def test_c45_structured_blocking_visual_proof_is_documented() -> None:
    schema = json.loads((ROOT / "penflow" / "schemas" / "vision-report.schema.json").read_text())
    criterion = schema["properties"]["screens"]["items"]["properties"]["criteria"]["items"]
    docs = PENFLOW_SKILL.read_text(encoding="utf-8") + "\n" + README.read_text(encoding="utf-8")

    assert "runId" in schema["required"]
    assert "proof" in criterion["required"]
    for phrase in (
        "blocking: true",
        "hierarchical region",
        "in-bounds crops",
        "non-homologous mappings",
    ):
        assert phrase in docs


def test_semantic_tree_reference_documents_formation_contract() -> None:
    reference = SEMANTIC_TREE_REFERENCE.read_text(encoding="utf-8")

    for phrase in (
        "Do not hand-write production semantic trees or generated Markdown",
        "Canonical source: `<target>/flow-ui-contract/contract.json`",
        "Generated projections",
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
