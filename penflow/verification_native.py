"""Revalidate native design evidence; never launch a renderer from certification."""

from functools import partial
from pathlib import Path
from typing import Any

from .evidence import validate_visual_evidence
from .export_operator import validate_export_operation_receipt
from .pencil_persistence import validate_pencil_persistence_receipt
from .reference_fidelity import validate_reference_fidelity
from .schema_cache import validator_for
from .theme import theme_fingerprint
from .verification_files import VerificationInputError
from .verification_json import decode_json
from .verification_policy import GateBook
from .verification_schema import issue
from .verification_snapshot import VerificationSnapshot


def evaluate_native(snapshot: VerificationSnapshot, gates: GateBook) -> None:
    """Require real persistence/vision evidence and source-derived native handoff duties."""
    gates.evaluate(
        "verify-pencil-persistence", lambda: _persistence(snapshot), dependencies=("validate-pen",)
    )
    gates.evaluate(
        "validate-visual-evidence",
        lambda: _visual(snapshot),
        dependencies=("export-expected", "verify-pencil-persistence"),
    )
    for gate_id, decision, action, dependencies in (
        (
            "validate-reference-fidelity",
            "homologous_references",
            _references,
            ("validate-visual-evidence",),
        ),
        ("verify-export-operation", "native_export", _export, ("verify-pencil-persistence",)),
    ):
        value = snapshot.policy.get(decision) if snapshot.policy is not None else None
        if value is None:
            gates.fail(
                gate_id,
                "verification.policy.missing",
                "applicability requires reviewed workflow provenance",
            )
        elif value == "not_applicable":
            gates.not_applicable(
                gate_id,
                f"/verification_policy/{decision}",
                "reviewed workflow explicitly excludes this procedure and no inherited duty requires it",
            )
        else:
            gates.evaluate(gate_id, partial(action, snapshot), dependencies=dependencies)


def bind_evidence_directory(snapshot: VerificationSnapshot, path: Path) -> None:
    """Snapshot each input in a bounded evidence directory before legacy validators read it."""
    if not path.is_dir():
        raise VerificationInputError(f"verification.evidence.directory_missing: {path}")
    for item in snapshot.reader.files(path):
        raw = snapshot.reader.read(item)
        if item.suffix == ".json":
            decode_json(raw)


def _receipt(snapshot: VerificationSnapshot, name: str, schema: str) -> dict[str, Any]:
    value = snapshot.object(name)
    if list(validator_for(schema).iter_errors(value)):
        raise VerificationInputError("verification.evidence.receipt_schema")
    if value.get("status") != "PASS" or value.get("issues"):
        raise VerificationInputError("verification.evidence.receipt_not_pass")
    _bind_references(snapshot, value, (snapshot.workspace / name).parent)
    return value


def _bind_references(snapshot: VerificationSnapshot, value: Any, base: Path) -> None:
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, list):
            pending.extend(item)
        elif isinstance(item, dict):
            path, sha = item.get("path"), item.get("sha256")
            if isinstance(path, str) and isinstance(sha, str):
                candidate = Path(path)
                snapshot.reader.reference(
                    {
                        "path": str(candidate if candidate.is_absolute() else base / candidate),
                        "sha256": sha,
                    }
                )
            pending.extend(item.values())


def _persistence(snapshot: VerificationSnapshot) -> list[dict[str, Any]]:
    receipt = _receipt(
        snapshot,
        ".penflow-run/pencil-persistence-receipt.json",
        "pencil-persistence-receipt.schema.json",
    )
    if (
        not receipt["closes_persistence"]
        or snapshot.reader.path(receipt["document"]["path"]) != snapshot.workspace / "ui.pen"
    ):
        return [
            issue(
                "verification.evidence.persistence_subject",
                "/document",
                "native persistence must certify this current Pencil document",
            )
        ]
    return list(validate_pencil_persistence_receipt(receipt))


def _visual(snapshot: VerificationSnapshot) -> list[dict[str, Any]]:
    directory = snapshot.workspace / ".mockup-validation/visual-evidence"
    bind_evidence_directory(snapshot, directory)
    theme = snapshot.workspace / "theme.css"
    fingerprint = theme_fingerprint(theme) if snapshot.reader.exists(theme) else None
    return validate_visual_evidence(
        directory,
        expected_tree_path=snapshot.workspace / "expected-ui-tree.json",
        theme_fingerprint=fingerprint,
    )


def _references(snapshot: VerificationSnapshot) -> list[dict[str, Any]]:
    directory = snapshot.workspace / "references"
    bind_evidence_directory(snapshot, directory)
    return validate_reference_fidelity(
        snapshot.workspace / ".mockup-validation/visual-evidence", directory
    )["issues"]


def _export(snapshot: VerificationSnapshot) -> list[dict[str, Any]]:
    receipt = _receipt(
        snapshot,
        ".mockup-validation/export-operation-receipt.json",
        "export-operator-receipt.schema.json",
    )
    if snapshot.reader.path(receipt["source"]["path"]) != snapshot.workspace / "ui.pen":
        return [
            issue(
                "verification.evidence.export_subject",
                "/source",
                "native export must certify this Pencil document",
            )
        ]
    return list(validate_export_operation_receipt(receipt))
