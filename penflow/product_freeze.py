"""Authenticate Brainstorm's existing accepted product freeze without consumer imports."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .verification_files import InputReader, VerificationInputError
from .verification_json import canonical_bytes, digest


def load_frozen_product(
    reader: InputReader, workspace: Path
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    """Verify current product/view bytes and the entire immutable accepted-freeze chain."""
    read_start = len(reader.read_log)
    root = reader.path(workspace / "product-contract")
    if reader.exists(root / "product-contract.pending.json"):
        raise VerificationInputError("product.freeze.pending")
    contract = reader.object(reader.read(root / "product-contract.json"))
    view = reader.read(root / "product-contract.md")
    freeze_raw = reader.read(root / "product-contract.freeze.json")
    freeze = reader.object(freeze_raw)
    if (
        freeze.get("kind") != "product-contract-freeze"
        or type(freeze.get("version")) is not int
        or freeze["version"] != 1
    ):
        raise VerificationInputError("product.freeze.invalid")
    if freeze.get("hash") != digest(canonical_bytes(contract)) or freeze.get(
        "view_sha256"
    ) != digest(view):
        raise VerificationInputError("product.freeze.stale")
    reference = reader.object(reader.read(root / "product-contract.accepted.json"))
    _history(reader, root, reference, freeze_raw)
    change_path = root / "product-contract.change-request.json"
    if reader.exists(change_path):
        change = reader.object(reader.read(change_path))
        if change.get("status") != "applied" or change.get("new_hash") != freeze["hash"]:
            raise VerificationInputError("product.change_request.pending_or_stale")
    sources = [
        {"path": str(path), "sha256": reader.observed[path]}
        for path in sorted(set(reader.read_log[read_start:]))
        if path.is_relative_to(root)
    ]
    return contract, sources


def _snapshot(
    reader: InputReader, root: Path, reference: dict[str, Any]
) -> tuple[dict[str, Any], bytes]:
    if (
        not isinstance(reference, dict)
        or set(reference) != {"path", "sha256"}
        or reference["path"] != f".freeze-history/{reference['sha256']}.json"
    ):
        raise VerificationInputError("product.history.reference")
    raw = reader.reference({"path": str(root / reference["path"]), "sha256": reference["sha256"]})
    return reader.object(raw), raw


def _history(
    reader: InputReader, root: Path, reference: dict[str, Any], current_freeze: bytes
) -> None:
    seen: set[str] = set()
    current = True
    while reference is not None:
        node, _ = _snapshot(reader, root, reference)
        if reference["sha256"] in seen:
            raise VerificationInputError("product.history.cycle")
        seen.add(reference["sha256"])
        _validate_acceptance(node)
        freeze, raw = _snapshot(reader, root, node["freeze"])
        _validate_freeze(freeze)
        if current and raw != current_freeze:
            raise VerificationInputError("product.history.current_mismatch")
        previous = node["previous"]
        if previous is not None:
            prior, _ = _snapshot(reader, root, previous)
            _validate_acceptance(prior)
            old_freeze, _ = _snapshot(reader, root, prior["freeze"])
            _validate_freeze(old_freeze)
            if old_freeze["hash"] != freeze["hash"]:
                change, _ = _snapshot(reader, root, node["change_request"])
                _validate_change(change, old_freeze["hash"], freeze["hash"])
            elif node["change_request"] is not None:
                raise VerificationInputError("product.history.unnecessary_change")
        elif node["change_request"] is not None:
            raise VerificationInputError("product.history.unbound_change")
        reference = previous
        current = False


def _validate_acceptance(node: dict[str, Any]) -> None:
    if (
        set(node) != {"kind", "version", "freeze", "previous", "change_request"}
        or node["kind"] != "product-contract-acceptance"
        or type(node["version"]) is not int
        or node["version"] != 1
    ):
        raise VerificationInputError("product.history.shape")


def _validate_freeze(freeze: dict[str, Any]) -> None:
    if (
        freeze.get("kind") != "product-contract-freeze"
        or type(freeze.get("version")) is not int
        or freeze["version"] != 1
    ):
        raise VerificationInputError("product.freeze.invalid")
    for key in ("hash", "view_sha256"):
        value = freeze.get(key)
        if (
            not isinstance(value, str)
            or len(value) != 64
            or any(char not in "0123456789abcdef" for char in value)
        ):
            raise VerificationInputError("product.freeze.digest")


def _validate_change(change: dict[str, Any], old_hash: str, new_hash: str) -> None:
    if (
        change.get("kind") != "product-contract-change-request"
        or change.get("status") != "applied"
        or change.get("old_hash") != old_hash
        or change.get("new_hash") != new_hash
        or not isinstance(change.get("reason"), str)
        or not change["reason"].strip()
    ):
        raise VerificationInputError("product.history.change_not_approved")
