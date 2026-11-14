"""Confined contract-only semantic publication, independent of canvas health."""

from __future__ import annotations

import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .doctor_context import ProjectContext
from .json_filesystem import write_json_atomically
from .semantic_contract import semantic_tree_from_contract
from .semantic_validation import validate_semantic_tree
from .verification_files import InputReader

# Match the bounded local-input policy used by normal review led checks.
MAX_EXPORT_INPUT_BYTES = 64 * 1024 * 1024


class SemanticExportError(ValueError):
    """A source/output boundary cannot safely publish the selected artifact."""


@dataclass(frozen=True)
class PreparedSemanticExport:
    """Validated projection and observed paths held under the existing writer lock."""

    context: ProjectContext
    reader: InputReader
    contract: Path
    output: Path
    tree: dict[str, Any]
    issues: list[dict[str, Any]]
    destination_identity: tuple[int, int] | None

    def publish(self, *, allow_warnings: bool = False) -> None:
        """Recheck source/destination and atomically publish only a valid projection."""
        if any(
            issue.get("severity") == "error"
            or (issue.get("severity") == "warning" and not allow_warnings)
            for issue in self.issues
        ):
            raise SemanticExportError("semantic.output.invalid: projection validation failed")
        try:
            self.context.resolve_path(self.contract, must_exist=True)
            self.context.resolve_path(self.output)
            self.context.resolve_path(self.output.parent, must_exist=True)
            identity = _destination(self.reader, self.output, self.contract)
            if identity != self.destination_identity:
                raise SemanticExportError("semantic.output.changed: destination identity changed")
            self.reader.recheck()
            write_json_atomically(self.output, self.tree)
        except (OSError, ValueError) as error:
            raise SemanticExportError(str(error)) from error


def prepare_semantic_export(
    context: ProjectContext, source: str | Path, output: str | Path
) -> PreparedSemanticExport:
    """Read a bounded strict contract and prepare one owned semantic artifact.

    Canvas, theme, hygiene and managed-run contents are not inputs. This factory
    reads source/output metadata only; publication is separate and atomic.
    """
    try:
        selected = context.resolve_path(source, must_exist=True)
        contract = selected if selected.name == "contract.json" else selected / "contract.json"
        contract = context.resolve_path(contract, must_exist=True)
        destination = context.resolve_path(output)
        context.resolve_path(destination.parent, must_exist=True)
        reader = InputReader(context.project_root, read_limit=MAX_EXPORT_INPUT_BYTES)
        data = reader.object(reader.read(contract))
        identity = _destination(reader, destination, contract)
    except (OSError, ValueError) as error:
        raise SemanticExportError(str(error)) from error
    # Reuse the canonical validator/projection, then validate before any write.
    tree = semantic_tree_from_contract(data, source_path=str(contract))
    issues = validate_semantic_tree(tree)
    return PreparedSemanticExport(context, reader, contract, destination, tree, issues, identity)


def _destination(reader: InputReader, output: Path, contract: Path) -> tuple[int, int] | None:
    """Accept new JSON or a valid semantic tree owned by this exact contract."""
    reader.path(output)
    if output == contract or output.suffix.lower() != ".json":
        raise SemanticExportError("semantic.output.unsafe: source alias or non-JSON destination")
    if not reader.lexists(output):
        return None
    metadata = output.lstat()
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
        raise SemanticExportError(
            "semantic.output.unsafe: destination must be an unaliased regular file"
        )
    existing = reader.object(reader.read(output))
    if existing.get("kind") != "semantic-ui-tree" or any(
        issue.get("severity") == "error" for issue in validate_semantic_tree(existing)
    ):
        raise SemanticExportError(
            "semantic.output.unowned: existing file is not a valid semantic tree"
        )
    source = existing.get("source")
    provenance = source.get("contract") if isinstance(source, dict) else None
    if not isinstance(provenance, str) or reader.path(provenance) != contract:
        raise SemanticExportError(
            "semantic.output.unowned: existing tree belongs to another source"
        )
    return metadata.st_dev, metadata.st_ino
