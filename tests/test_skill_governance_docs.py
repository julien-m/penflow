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

import re
from pathlib import Path

import pytest

from skill_doc_paths import (
    ROOT,
    PENFLOW_SKILL,
    FLOW_SKILL,
    FLOW_README,
    MOCKUP_SKILL,
    MOCKUP_README,
    README,
    PROJECT_INTEGRATION,
)


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
    # The LiveSpec registry is a local maintainer workspace and is not published.
    registry_path = ROOT / ".specs" / "README.md"
    if registry_path.exists():
        registry = registry_path.read_text(encoding="utf-8")
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
