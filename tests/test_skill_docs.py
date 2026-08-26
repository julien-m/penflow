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
import re
from pathlib import Path

import pytest

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
MOCKUP_DESIGN_TASTE = (
    ROOT / ".agent-sync" / "skills" / "mockup-factory" / "references" / "design-taste-advisory.md"
)
FLOW_DESIGN_READ = (
    ROOT / ".agent-sync" / "skills" / "flow-ui-contract" / "references" / "design-read.md"
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

PENFLOW_DEMO_COMMANDS = (
    'demo --out "$fresh"',
    'run --target "$fresh" --json',
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
        "ui.pen",
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
        "enrich-pen penflow/ui.pen",
        "map-pencil-context penflow/ui.pen",
        "reverse-pen penflow/ui.pen --out penflow/reverse-output",
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


PRIMARY_GOVERNANCE_DOCS = (README, PROJECT_INTEGRATION, PENFLOW_SKILL, FLOW_SKILL, MOCKUP_SKILL)
GOVERNANCE_CONTRACTS = (
    pytest.param(
        ("penflow doctor --project", "--check --json", "start", "end"), (), id="doctor-receipts"
    ),
    pytest.param(
        ("ui.pen", "active", "draft", "archive"),
        ("exactly one", "one canonical", "sole regular"),
        id="single-canvas-lifecycle",
    ),
    pytest.param(
        (".penflow-tmp/", "managed", "ignored", "preflight", "postflight"),
        (),
        id="managed-temporaries",
    ),
    pytest.param(("multiple_pen_files", "staged"), (), id="manual-resolution"),
)


@pytest.mark.parametrize("path", PRIMARY_GOVERNANCE_DOCS, ids=lambda path: path.name)
@pytest.mark.parametrize(("required", "alternatives"), GOVERNANCE_CONTRACTS)
def test_governed_guidance_contract(
    path: Path, required: tuple[str, ...], alternatives: tuple[str, ...]
) -> None:
    document = path.read_text(encoding="utf-8").lower()
    assert all(phrase in document for phrase in required)
    assert not alternatives or any(phrase in document for phrase in alternatives)


def test_governed_guidance_never_teaches_peer_pen_documents() -> None:
    governed_paths = [README, PROJECT_INTEGRATION]
    for skill_root in (
        PENFLOW_SKILL.parent,
        FLOW_SKILL.parent,
        MOCKUP_SKILL.parent,
    ):
        governed_paths.extend(sorted(skill_root.rglob("*.md")))

    combined = "\n".join(path.read_text(encoding="utf-8") for path in governed_paths)
    for forbidden_name in ("draft.pen", "ui.enriched.pen", "ui.visual.pen"):
        assert forbidden_name not in combined
    assert re.search(r"(?:backup|recovery)[^`\n]*\.pen", combined, re.IGNORECASE) is None


def test_governed_guidance_uses_exact_consumer_project_boundary_language() -> None:
    governed_paths = (
        README,
        PROJECT_INTEGRATION,
        PENFLOW_SKILL,
        FLOW_SKILL,
        FLOW_README,
        MOCKUP_SKILL,
        MOCKUP_README,
    )

    for path in governed_paths:
        document = path.read_text(encoding="utf-8")
        assert "<consumer-project-root>" in document, path
        assert "<consumer-git-root>" not in document, path
        assert re.search(r"consumer git root|containing git root", document, re.IGNORECASE) is None

    combined = "\n".join(path.read_text(encoding="utf-8") for path in governed_paths)
    assert "never widened" in combined
    assert "collective Git worktree" in combined
    assert "git_root" in combined


def test_flow_contract_sequences_keep_every_handoff_under_target() -> None:
    documents = (FLOW_README, FLOW_SKILL)
    required_fragments = (
        "--out <target>/semantic-ui-tree.json",
        "<target>/semantic-ui-tree.json --project <consumer-project-root> --out <target>/ui.pen",
        "--out <target>/pencil-context-map.json",
        "--out <target>/expected-ui-tree.json",
        "--out <target>/code-ir.json",
    )

    for path in documents:
        document = path.read_text(encoding="utf-8")
        for fragment in required_fragments:
            assert fragment in document
        for unscoped_output in (
            "--out semantic-ui-tree.json",
            "--out pencil-context-map.json",
            "--out expected-ui-tree.json",
            "--out code-ir.json",
        ):
            assert unscoped_output not in document

        for heading in ("Forward", "Enrichment", "Reverse"):
            command_block = re.search(
                rf"## {heading}(?: Command Sequence)?\n.*?```bash\n(.*?)```",
                document,
                re.DOTALL,
            )
            assert command_block is not None, (path, heading)
            for line in command_block.group(1).splitlines():
                if line.startswith("penflow "):
                    assert "--project <consumer-project-root>" in line, (path, line)


def test_c16_guidance_cleans_its_temporary_consumer() -> None:
    cleanup_sequence = "consumer=$(mktemp -d)\ntrap 'rm -rf -- \"$consumer\"' EXIT"

    assert cleanup_sequence in README.read_text(encoding="utf-8")
    assert cleanup_sequence in PENFLOW_SKILL.read_text(encoding="utf-8")

    for path in (README, PENFLOW_SKILL):
        document = path.read_text(encoding="utf-8")
        command_block = re.search(
            r"(?:#### Regression|## Regression Mode).*?```bash\n(.*?)```",
            document,
            re.DOTALL,
        )
        assert command_block is not None, path
        for line in command_block.group(1).splitlines():
            if line.startswith("penflow "):
                assert '--project "$consumer"' in line, (path, line)


def test_feature_074_registry_ci_and_example_hygiene_are_static_contracts() -> None:
    registry = (ROOT / ".specs" / "README.md").read_text(encoding="utf-8")
    canonical_row = (
        "| [074-penflow-doctor-consumer-project-hygiene]"
        "(features/074-penflow-doctor-consumer-project-hygiene/) | Implemented | P1 |"
    )
    assert registry.count(canonical_row) == 1
    assert re.search(r"^\| 074 \|", registry, re.MULTILINE) is None
    assert (ROOT / ".specs" / "changelog.md").read_bytes().endswith(b"\n")

    workflow_lines = (
        (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8").splitlines()
    )
    retention_index = next(
        index for index, line in enumerate(workflow_lines) if "retention-days: 30" in line
    )
    assert "evidence" in workflow_lines[retention_index - 1].lower()

    for example in sorted((ROOT / "examples").iterdir()):
        if not example.is_dir():
            continue
        pen_files = sorted(example.rglob("*.pen"))
        assert len(pen_files) <= 1, example
        assert not pen_files or pen_files[0].name == "ui.pen"


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
