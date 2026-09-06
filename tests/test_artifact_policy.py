"""Behavioral tests for the closed Feature 074 artifact and command policy."""

from dataclasses import FrozenInstanceError

import pytest

from penflow.artifact_policy import (
    CANONICAL_PEN_NAME,
    COMMAND_POLICIES,
    LIFECYCLE_EXEMPT_COMMANDS,
    MANAGED_IGNORE_BLOCK,
    MANAGED_TEMP_ROOT,
    PRODUCER_COMMANDS,
    READ_ONLY_COMMANDS,
    RECOGNIZED_LEGACY_ROOTS,
    ArtifactClass,
    CommandClassification,
    UnknownArtifactPathError,
    UnknownCommandError,
    artifact_policy_for,
    command_policy_for,
)


# @spec FR-003: Managed ignore policy — .specs/features/074-penflow-doctor-consumer-project-hygiene/spec.md#fr-003
def test_managed_ignore_block_matches_the_normative_bytes() -> None:
    assert MANAGED_IGNORE_BLOCK == (
        "# >>> Penflow managed temporary artifacts v1 >>>\n"
        ".penflow-tmp/\n"
        ".penflow-run/\n"
        ".mockup-validation/\n"
        "# <<< Penflow managed temporary artifacts v1 <<<\n"
    )


# @spec FR-006: Closed artifact classes — .specs/features/074-penflow-doctor-consumer-project-hygiene/spec.md#fr-006
@pytest.mark.parametrize(
    ("relative_path", "expected_class"),
    [
        (CANONICAL_PEN_NAME, ArtifactClass.DURABLE),
        (f"penflow/{CANONICAL_PEN_NAME}", ArtifactClass.DURABLE),
        (MANAGED_TEMP_ROOT, ArtifactClass.MANAGED_TEMPORARY),
        (f"{MANAGED_TEMP_ROOT}/runs/run-1/output.json", ArtifactClass.MANAGED_TEMPORARY),
        (RECOGNIZED_LEGACY_ROOTS[0], ArtifactClass.RECOGNIZED_LEGACY),
        (
            f"{RECOGNIZED_LEGACY_ROOTS[1]}/visual-evidence/screen.png",
            ArtifactClass.RECOGNIZED_LEGACY,
        ),
    ],
)
def test_artifact_policy_classifies_only_governed_paths(
    relative_path: str, expected_class: ArtifactClass
) -> None:
    assert artifact_policy_for(relative_path).artifact_class is expected_class


# @spec FR-006: Unknown artifacts fail closed — .specs/features/074-penflow-doctor-consumer-project-hygiene/spec.md#fr-006
@pytest.mark.parametrize(
    "relative_path",
    [
        "",
        ".",
        "other.json",
        "draft.pen",
        "/tmp/ui.pen",
        "../ui.pen",
        ".penflow-tmp/../ui.pen",
        ".penflow-tmp\\runs\\run-1",
    ],
)
def test_artifact_policy_rejects_unknown_or_non_normalized_paths(relative_path: str) -> None:
    with pytest.raises(UnknownArtifactPathError):
        artifact_policy_for(relative_path)


# @spec FR-010: Exact command registry — .specs/features/074-penflow-doctor-consumer-project-hygiene/spec.md#fr-010
def test_command_registry_matches_the_normative_closed_sets() -> None:
    assert PRODUCER_COMMANDS == frozenset(
        {
            "run",
            "pencil-sync",
            "verify-pencil-persistence",
            "verify-export-operation",
            "export-expected",
            "export-semantic-tree",
            "export-flow-docs",
            "audit-context-coverage",
            "migrate-flow-contract",
            "draft-pen-from-tree",
            "enrich-pen",
            "map-pencil-context",
            "reverse-pen",
            "detect-drift",
            "checklist-from-drift",
            "compare-tree",
            "check-consistency",
            "audit-visual",
            "flow-to-screens",
            "draft-pen",
            "update-pen",
            "extract-tokens",
            "lint-tokens",
            "export-ir",
            "code-ir",
            "codegen",
            "ci",
            "review-report",
            "fix-report",
            "demo",
        }
    )
    assert READ_ONLY_COMMANDS == frozenset(
        {
            "inspect",
            "validate-pen",
            "validate-flow-specs",
            "validate-flow-contract",
            "validate-causal-evidence",
            "validate-semantic-tree",
            "validate-actual",
            "validate-actual-provenance",
            "validate-visual-evidence",
            "validate-reference-fidelity",
            "validate-flow",
            "validate-screen",
            "theme-fingerprint",
            "validate-code-ir",
            "validate-report",
            "authority",
        }
    )
    assert LIFECYCLE_EXEMPT_COMMANDS == frozenset({"doctor", "--help", "--version"})
    assert len(COMMAND_POLICIES) == (
        len(PRODUCER_COMMANDS) + len(READ_ONLY_COMMANDS) + len(LIFECYCLE_EXEMPT_COMMANDS)
    )


def test_command_policy_returns_typed_immutable_entries_and_rejects_unknown() -> None:
    producer = command_policy_for("run")
    assert producer.category is CommandClassification.PRODUCER
    with pytest.raises(FrozenInstanceError):
        # Dynamic assignment exercises the frozen dataclass runtime guard beyond static typing.
        setattr(producer, "command", "inspect")
    with pytest.raises(UnknownCommandError):
        command_policy_for("future-command")
