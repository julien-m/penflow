"""Coordinate official source authority and publication outside the runtime-agnostic core."""

from __future__ import annotations

from pathlib import Path
import hashlib

from convert_observations import convert as convert_observations
from convert_tree import convert as convert_tree
from convert_causal import convert as convert_causal


def source_references(project: Path, contract: Path) -> list[dict[str, str]]:
    """Ask Penflow for its authenticated stable source inventory, without reimplementing policy."""
    from penflow.verification_snapshot import verification_source_references

    return verification_source_references(project_root=project, workspace=contract.parent.parent)


def publish(
    contract: Path, evidence: Path, project: Path, build_id: str, invocation: str
) -> list[Path]:
    """Publish measured C12/outcomes; these artifacts alone never imply C51 PASS."""
    workspace = contract.parent.parent
    observation_dir = workspace / "outcome-observations"
    staged = evidence.parent / "staged-observations"
    paths = convert_observations(contract, evidence, staged, project, build_id, invocation)
    if observation_dir.is_symlink():
        raise ValueError("outcome observation destination is a symlink")
    if observation_dir.exists():
        observation_dir.rename(evidence.parent / "previous-observations")
    staged.rename(observation_dir)
    paths = [observation_dir / path.name for path in paths]
    identity = {
        "contract_sha256": hashlib.sha256(contract.read_bytes()).hexdigest(),
        "build_id": build_id,
        "producer_invocation_id": invocation,
    }
    return (
        paths
        + convert_tree(evidence, workspace, project, identity)
        + convert_causal(contract, evidence, workspace, project)
    )
