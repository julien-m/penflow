"""Closed artifact and command policy for consumer-project lifecycle operations.

This module is deliberately pure: it classifies normalized project-relative paths and
command identifiers but performs no filesystem, Git, or CLI side effects.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import PurePosixPath
from types import MappingProxyType
from typing import Final, Mapping


class ArtifactClass(str, Enum):
    """Describe the lifecycle class of a governed artifact path."""

    DURABLE = "durable"
    MANAGED_TEMPORARY = "managed_temporary"
    RECOGNIZED_LEGACY = "recognized_legacy"


class Retention(str, Enum):
    """Describe whether a manifest entry is working data or a durable output."""

    WORKING = "working"
    DURABLE = "durable"


class CleanupRule(str, Enum):
    """Describe the only cleanup authorization granted by an artifact policy."""

    NEVER = "never"
    CATALOGUED_ONLY = "catalogued_only"


class GitRule(str, Enum):
    """Describe whether a governed artifact may appear in the Git index."""

    ALLOW_TRACKED = "allow_tracked"
    BLOCK_IF_TRACKED_OR_STAGED = "block_if_tracked_or_staged"


class CommandClassification(str, Enum):
    """Describe how one CLI command participates in the shared lifecycle."""

    PRODUCER = "producer"
    READ_ONLY = "read_only"
    LIFECYCLE_EXEMPT = "lifecycle_exempt"


# Backward-compatible public spelling for early Feature 074 consumers.
CommandCategory = CommandClassification


@dataclass(frozen=True, slots=True)
class ArtifactPolicy:
    """Define immutable cleanup and Git rules for one closed path pattern."""

    pattern: str
    artifact_class: ArtifactClass
    cleanup_rule: CleanupRule
    git_rule: GitRule


@dataclass(frozen=True, slots=True)
class CommandPolicy:
    """Define immutable lifecycle classification for one exact command identifier."""

    command: str
    category: CommandClassification
    rationale: str


class UnknownArtifactPathError(ValueError):
    """Raised when a path is not normalized or absent from the closed artifact policy."""

    def __init__(self, relative_path: str) -> None:
        super().__init__(f"artifact path is not governed by the closed policy: {relative_path!r}")
        self.relative_path = relative_path


class UnknownCommandError(ValueError):
    """Raised when a command is absent from the authoritative command registry."""

    def __init__(self, command: str) -> None:
        super().__init__(f"command is not classified by the lifecycle policy: {command!r}")
        self.command = command


CANONICAL_PEN_NAME: Final = "ui.pen"
MANAGED_TEMP_ROOT: Final = ".penflow-tmp"
MANAGED_ROOTS: Final = (MANAGED_TEMP_ROOT,)
RECOGNIZED_LEGACY_ROOTS: Final = (".penflow-run", ".mockup-validation")


# @spec FR-003: Exact managed ignore block — .specs/features/074-penflow-doctor-consumer-project-hygiene/spec.md#fr-003
MANAGED_IGNORE_BLOCK_LINES: Final = (
    "# >>> Penflow managed temporary artifacts v1 >>>",
    ".penflow-tmp/",
    ".penflow-run/",
    ".mockup-validation/",
    "# <<< Penflow managed temporary artifacts v1 <<<",
)
MANAGED_IGNORE_BLOCK: Final = "\n".join(MANAGED_IGNORE_BLOCK_LINES) + "\n"


# @spec FR-002: Canonical candidate policy, FR-006: Managed artifact classes — .specs/features/074-penflow-doctor-consumer-project-hygiene/spec.md#fr-002
CANONICAL_PEN_POLICY: Final = ArtifactPolicy(
    pattern="**/ui.pen",
    artifact_class=ArtifactClass.DURABLE,
    cleanup_rule=CleanupRule.NEVER,
    git_rule=GitRule.ALLOW_TRACKED,
)
MANAGED_ROOT_POLICY: Final = ArtifactPolicy(
    pattern=f"{MANAGED_TEMP_ROOT}/**",
    artifact_class=ArtifactClass.MANAGED_TEMPORARY,
    cleanup_rule=CleanupRule.CATALOGUED_ONLY,
    git_rule=GitRule.BLOCK_IF_TRACKED_OR_STAGED,
)
LEGACY_ROOT_POLICIES: Final = tuple(
    ArtifactPolicy(
        pattern=f"{root}/**",
        artifact_class=ArtifactClass.RECOGNIZED_LEGACY,
        cleanup_rule=CleanupRule.CATALOGUED_ONLY,
        git_rule=GitRule.BLOCK_IF_TRACKED_OR_STAGED,
    )
    for root in RECOGNIZED_LEGACY_ROOTS
)
ARTIFACT_POLICIES: Final = (
    CANONICAL_PEN_POLICY,
    MANAGED_ROOT_POLICY,
    *LEGACY_ROOT_POLICIES,
)


# @spec FR-010: Exact command lifecycle registry — .specs/features/074-penflow-doctor-consumer-project-hygiene/spec.md#fr-010
PRODUCER_COMMANDS: Final = frozenset(
    {
        "run",
        "pencil-sync",
        "verify-pencil-persistence",
        "verify-export-operation",
        "export-expected",
        "export-semantic-tree",
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
READ_ONLY_COMMANDS: Final = frozenset(
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
    }
)
LIFECYCLE_EXEMPT_COMMANDS: Final = frozenset({"doctor", "--help", "--version"})

_COMMAND_RATIONALES: Final[Mapping[CommandClassification, str]] = MappingProxyType(
    {
        CommandClassification.PRODUCER: "successful execution can mutate consumer-project bytes",
        CommandClassification.READ_ONLY: "validation or inspection produces no project artifact",
        CommandClassification.LIFECYCLE_EXEMPT: "lifecycle boundary command must not recurse",
    }
)


def _command_policies(
    commands: frozenset[str], category: CommandClassification
) -> tuple[CommandPolicy, ...]:
    return tuple(
        CommandPolicy(
            command=command,
            category=category,
            rationale=_COMMAND_RATIONALES[category],
        )
        for command in sorted(commands)
    )


COMMAND_POLICIES: Final = (
    *_command_policies(PRODUCER_COMMANDS, CommandClassification.PRODUCER),
    *_command_policies(READ_ONLY_COMMANDS, CommandClassification.READ_ONLY),
    *_command_policies(LIFECYCLE_EXEMPT_COMMANDS, CommandClassification.LIFECYCLE_EXEMPT),
)
COMMAND_POLICY_BY_ID: Final[Mapping[str, CommandPolicy]] = MappingProxyType(
    {policy.command: policy for policy in COMMAND_POLICIES}
)


def _normalized_relative_path(relative_path: str | PurePosixPath) -> PurePosixPath:
    raw_path = (
        relative_path.as_posix() if isinstance(relative_path, PurePosixPath) else relative_path
    )
    raw_parts = raw_path.split("/")
    if (
        not raw_path
        or raw_path.startswith("/")
        or "\\" in raw_path
        or "" in raw_parts
        or "." in raw_parts
        or ".." in raw_parts
    ):
        raise UnknownArtifactPathError(raw_path)
    normalized = PurePosixPath(raw_path)
    if normalized.is_absolute() or normalized.as_posix() != raw_path:
        raise UnknownArtifactPathError(raw_path)
    return normalized


# @spec FR-006: Unknown artifact paths block — .specs/features/074-penflow-doctor-consumer-project-hygiene/spec.md#fr-006
def artifact_policy_for(relative_path: str | PurePosixPath) -> ArtifactPolicy:
    """Return the closed policy for one normalized project-relative path.

    Args:
        relative_path: POSIX project-relative path to classify without filesystem access.

    Returns:
        The immutable matching artifact policy.

    Raises:
        UnknownArtifactPathError: If the path is unsafe, non-normalized, or unclassified.
    """
    normalized = _normalized_relative_path(relative_path)
    if normalized.parts[0] == ".git":
        raise UnknownArtifactPathError(normalized.as_posix())
    if normalized.name == CANONICAL_PEN_NAME:
        return CANONICAL_PEN_POLICY
    if normalized.parts[0] == MANAGED_TEMP_ROOT:
        return MANAGED_ROOT_POLICY
    for root, policy in zip(RECOGNIZED_LEGACY_ROOTS, LEGACY_ROOT_POLICIES, strict=True):
        if normalized.parts[0] == root:
            return policy
    raise UnknownArtifactPathError(normalized.as_posix())


# @spec FR-010: Unknown commands block — .specs/features/074-penflow-doctor-consumer-project-hygiene/spec.md#fr-010
def command_policy_for(command: str) -> CommandPolicy:
    """Return the authoritative lifecycle policy for an exact command ID.

    Args:
        command: Exact argparse command identifier or exempt top-level flag.

    Returns:
        The immutable command policy.

    Raises:
        UnknownCommandError: If the command is absent from the closed registry.
    """
    try:
        return COMMAND_POLICY_BY_ID[command]
    except KeyError as error:
        raise UnknownCommandError(command) from error
