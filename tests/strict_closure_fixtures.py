# @spec(FR-001)
# @spec(FR-002)
# @spec(FR-003)
# @spec(FR-004)
# @spec(FR-005)
"""C47 strict-closure positive, adversarial, and compatibility coverage."""

from __future__ import annotations

import hashlib
import json
import struct
import zlib
from pathlib import Path
from typing import Any


from penflow.actual_provenance import actual_provenance_path
from penflow.evidence import VISION_CATEGORIES
from penflow.pencil_persistence import verify_pencil_persistence
from penflow.reference_fidelity import REFERENCE_CATEGORIES

RUN_ID = "run-c6-strict-closure"


def _json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _crop(width: int = 8, height: int = 8) -> dict[str, int]:
    return {
        "x": 0,
        "y": 0,
        "width": width,
        "height": height,
        "source_width": width,
        "source_height": height,
    }


def _png(path: Path, color: tuple[int, int, int]) -> None:
    raw = bytearray()
    for _ in range(8):
        raw.append(0)
        for _ in range(8):
            raw.extend(color)
    chunks = [
        _png_chunk(b"IHDR", struct.pack(">IIBBBBB", 8, 8, 8, 2, 0, 0, 0)),
        _png_chunk(b"IDAT", zlib.compress(bytes(raw))),
        _png_chunk(b"IEND", b""),
    ]
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"".join(chunks))


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    checksum = zlib.crc32(kind + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", checksum)


def _proof(
    category: str,
    *,
    role: str,
    file: str,
    digest: str,
) -> dict[str, Any]:
    return {
        "category": category,
        "result": "pass",
        "evidence": f"Bound C6 evidence for {category} using {file}.",
        "blocking": True,
        "proof": {
            "run_id": RUN_ID,
            "surface": "web",
            "screen_id": "checkout",
            "region_id": "checkout.main",
            "state": "default",
            "assertion": category,
            "measurement": {"expected": "pass", "actual": "pass", "unit": "result"},
            "artifacts": [
                {
                    "role": role,
                    "file": file,
                    "sha256": digest,
                    "crop": _crop(),
                }
            ],
        },
    }


def _trees(root: Path) -> None:
    """Write the expected tree and independently bound actual provenance."""
    expected_root = {
        "id": "checkout",
        "role": "screen",
        "bbox": {"x": 0, "y": 0, "width": 390, "height": 844},
        "children": [],
    }
    actual_root = {
        "id": "checkout",
        "role": "screen",
        "bbox": {"x": 1, "y": 1, "width": 388, "height": 842},
        "children": [],
    }
    _json(
        root / "expected-ui-tree.json",
        {
            "issues": [],
            "screens": [{"name": "checkout", "pencil_id": "checkoutScreen", "root": expected_root}],
        },
    )
    actual = root / "actual-ui-tree.json"
    _json(
        actual,
        {
            "version": 1,
            "screen_id": "checkout",
            "viewport": {"width": 390, "height": 844},
            "root": actual_root,
        },
    )
    _json(
        actual_provenance_path(actual),
        {
            "kind": "penflow-actual-provenance",
            "version": 1,
            "sourceKind": "runtime-capture",
            "producer": {"name": "test-runtime-adapter", "version": "1"},
            "capturedAt": "2026-07-24T11:59:00Z",
            "target": {"surface": "web", "screen_id": "checkout"},
            "content": {"path": actual.name, "sha256": _sha(actual)},
            "sessionId": RUN_ID,
        },
    )


def _persistence(root: Path, run_dir: Path) -> None:
    """Create distinct fixture snapshots and verify their persistence receipt."""
    pre = root / "pre.snapshot.json"
    post = root / "post.snapshot.json"
    document = root / "ui.pen"
    pre.write_bytes(b'{"version":1,"children":[]}')
    post.write_bytes(b'{"version":1,"children":[{"id":"checkout","type":"frame"}]}')
    document.write_bytes(post.read_bytes())
    observation = root / "pencil-observation.json"
    _json(
        observation,
        {
            "kind": "penflow-pencil-persistence-observation",
            "version": 1,
            "run_id": RUN_ID,
            "document": {
                "path": document.name,
                "pre": {"path": pre.name, "sha256": _sha(pre)},
                "post": {"path": post.name, "sha256": _sha(post)},
            },
            "operation": "save-current-pencil-document",
            "trigger": {"provider": "pencil-operator", "status": "triggered"},
        },
    )
    verify_pencil_persistence(
        observation,
        document=document,
        run_id=RUN_ID,
        operation="save-current-pencil-document",
        out=run_dir / "pencil-persistence-receipt.json",
    )


def _reference_images(evidence: Path, references: Path) -> tuple[Path, Path, Path]:
    """Create the three deterministic images and their reference manifest."""
    export = evidence / "checkoutScreen.png"
    reference = references / "checkout-ref.png"
    contact = evidence / "checkout-reference-contact-sheet.png"
    _png(export, (202, 22, 22))
    _png(reference, (200, 20, 20))
    _png(contact, (201, 21, 21))
    reference_entry = {
        "screen_id": "checkout",
        "file": reference.name,
        "sha256": _sha(reference),
        "source": "unit-test",
        "mapping": {
            "surface": "web",
            "screen_id": "checkout",
            "region_id": "checkout.main",
            "state": "default",
            "crop": _crop(),
        },
    }
    _json(references / "references-manifest.json", [reference_entry])
    return export, reference, contact


def _visual_manifest(evidence: Path, export: Path) -> None:
    """Bind the fixture export and reference-manifest location."""
    declared = "../../references/references-manifest.json"
    _json(
        evidence / "manifest.json",
        {
            "renderer": "pencil-mcp",
            "sourceFile": "ui.pen",
            "status": "PASS",
            "validatedAt": "2026-07-24",
            "runId": RUN_ID,
            "references_manifest": declared,
            "screens": [
                {
                    "screen_id": "checkout",
                    "semantic_id": "checkout",
                    "pencil_node_id": "checkoutScreen",
                    "surface": "web",
                    "state": "default",
                    "regions": [{"region_id": "checkout.main", "crop": _crop()}],
                    "png": export.name,
                    "sha256": _sha(export),
                    "layout_checked": True,
                    "screenshot_checked": True,
                }
            ],
        },
    )


def _reference_criteria(export: Path, reference: Path, contact: Path) -> list[dict[str, Any]]:
    """Bind each required reference criterion to its three fixture artifacts."""
    reference_criteria = []
    for category in REFERENCE_CATEGORIES:
        criterion = _proof(
            category,
            role="reference",
            file=reference.name,
            digest=_sha(reference),
        )
        criterion["evidence"] = (
            f"Compared {reference.name} with {export.name} in {contact.name} for {category}."
        )
        criterion["proof"]["artifacts"].extend(
            [
                {
                    "role": "actual",
                    "file": export.name,
                    "sha256": _sha(export),
                    "crop": _crop(),
                },
                {
                    "role": "contact_sheet",
                    "file": contact.name,
                    "sha256": _sha(contact),
                    "crop": _crop(),
                },
            ]
        )
        reference_criteria.append(criterion)
    return reference_criteria


def _vision_report(evidence: Path, export: Path, reference: Path, contact: Path) -> None:
    """Write vision criteria with their corresponding image references."""
    reference_criteria = _reference_criteria(export, reference, contact)
    _json(
        evidence / "vision-report.json",
        {
            "version": 1,
            "kind": "penflow-vision-report",
            "status": "PASS",
            "runId": RUN_ID,
            "renderer": "pencil-mcp",
            "sourceFile": "ui.pen",
            "model": "test-vision-model",
            "generated_by": "pytest-strict-closure",
            "inputs": [
                {"file": export.name, "sha256": _sha(export)},
                {"file": contact.name, "sha256": _sha(contact)},
            ],
            "screens": [
                {
                    "screen_id": "checkout",
                    "semantic_id": "checkout",
                    "pencil_node_id": "checkoutScreen",
                    "surface": "web",
                    "region_id": "checkout.main",
                    "state": "default",
                    "png": export.name,
                    "criteria": [
                        _proof(category, role="actual", file=export.name, digest=_sha(export))
                        for category in VISION_CATEGORIES
                    ],
                }
            ],
            "reference_fidelity": [
                {
                    "screen_id": "checkout",
                    "reference": reference.name,
                    "export": export.name,
                    "contact_sheet": contact.name,
                    "mapping": {
                        "surface": "web",
                        "screen_id": "checkout",
                        "region_id": "checkout.main",
                        "state": "default",
                        "reference_crop": _crop(),
                        "actual_crop": _crop(),
                    },
                    "criteria": reference_criteria,
                }
            ],
        },
    )


def _layout(evidence: Path) -> None:
    """Write the deterministic fixture screen geometry."""
    _json(
        evidence / "layout-snapshot.json",
        {
            "screens": [
                {
                    "screen_id": "checkout",
                    "pencil_node_id": "checkoutScreen",
                    "width": 390,
                    "height": 844,
                }
            ]
        },
    )


def _workspace(root: Path) -> tuple[Path, Path]:
    """Compose the complete strict-closure workspace from distinct artifact builders."""
    root.mkdir(parents=True)
    evidence = root / ".mockup-validation" / "visual-evidence"
    references = root / "references"
    run_dir = root / ".penflow-run"
    evidence.mkdir(parents=True)
    references.mkdir()
    run_dir.mkdir()

    _trees(root)
    _persistence(root, run_dir)
    export, reference, contact = _reference_images(evidence, references)
    _visual_manifest(evidence, export)
    _vision_report(evidence, export, reference, contact)
    _layout(evidence)
    return root, references
