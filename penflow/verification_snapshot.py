"""One authenticated source snapshot shared by report production and revalidation."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .contract_preparation import contract_test_id_issues
from .verification_applicability import read_policy_source
from .product_sources import load_brainstorm_requirements
from .requirement_sources import load_livespec_requirements
from .verification_files import InputReader, VerificationInputError


@dataclass
class VerificationSnapshot:
    """Caller authority and immutable identities for one bounded verification run."""

    reader: InputReader
    workspace: Path
    contract: dict[str, Any]
    projection: dict[str, Any]
    upstream: dict[str, Any]
    lifecycle_paths: set[Path] = field(default_factory=set)
    authority_sources: list[dict[str, str]] = field(default_factory=list)
    policy: dict[str, Any] | None = None

    def sources(self, *, excluding: set[Path] | None = None) -> list[dict[str, str]]:
        """Return observed raw identities, retaining approved archives across lifecycle changes."""
        omitted = self.lifecycle_paths | (excluding or set())
        return [
            {"path": str(path), "sha256": sha}
            for path, sha in sorted(self.reader.observed.items())
            if path not in omitted
        ]

    def object(self, name: str, definition: str | None = None) -> dict[str, Any]:
        """Read one exact workspace artifact through the current byte snapshot."""
        return self.reader.object(self.reader.read(self.workspace / name), definition)


def load_source_snapshot(reader: InputReader, workspace: str | Path) -> VerificationSnapshot:
    """Select actual caller authority independently of any submitted report or C20 flag."""
    target = reader.path(workspace)
    if any(
        part in {".penflow-tmp", ".penflow-run", ".mockup-validation"}
        for part in target.relative_to(reader.root).parts
    ):
        raise VerificationInputError("verification.scope.temporary_workspace")
    if not target.is_dir():
        raise VerificationInputError("verification.scope.workspace_missing")
    livespec = reader.lexists(".specs/penflow-requirements.json")
    product = reader.exists(target / "product-contract/product-contract.accepted.json")
    if not livespec and not product:
        raise VerificationInputError("verification.source.ambiguous_or_missing_authority")
    source_read_start = len(reader.read_log)
    upstream = (
        load_livespec_requirements(reader)
        if livespec
        else load_brainstorm_requirements(reader, target)
    )
    snapshot = VerificationSnapshot(
        reader, target, upstream["contract"], upstream["projection"], upstream
    )
    if livespec:
        if upstream["baseline"]["scope"]["workspace"] != str(target):
            raise VerificationInputError("verification.scope.workspace_mismatch")
        for key in ("sources", "plans"):
            snapshot.lifecycle_paths.update(
                reader.path(record["path"]) for record in upstream["snapshot"]["inputs"][key]
            )
    policy_ref = upstream["snapshot"]["inputs"].get("verification_policy") if livespec else None
    if not livespec and reader.lexists(target / "verification-policy-source.json"):
        path = target / "verification-policy-source.json"
        reader.read(path)
        policy_ref = {"path": str(path), "sha256": reader.observed[reader.path(path)]}
    if policy_ref is not None:
        policy = read_policy_source(reader, policy_ref, brainstorm=not livespec, current=True)
        if policy["decisions"] != snapshot.contract.get("verification_policy"):
            raise VerificationInputError("verification.policy.contract_mismatch")
        if contract_test_id_issues(snapshot.contract):
            raise VerificationInputError("verification.source.test_ids_missing_before_review")
        snapshot.policy = policy["decisions"]
    authority_paths = set(reader.read_log[source_read_start:]) - snapshot.lifecycle_paths
    snapshot.authority_sources = [
        {"path": str(path), "sha256": reader.observed[path]} for path in sorted(authority_paths)
    ]
    return snapshot


def verification_source_references(
    *, project_root: str | Path, workspace: str | Path
) -> list[dict[str, str]]:
    """Supply authenticated upstream raw references to an external build runner.

    Lifecycle-sensitive current Markdown is checked semantically against its authentic
    immutable snapshot; only that snapshot enters the stable raw manifest identity.
    This function approves no renderer, process execution or runtime observation.
    """
    reader = InputReader(Path(project_root))
    snapshot = load_source_snapshot(reader, workspace)
    reader.recheck()
    return snapshot.authority_sources
