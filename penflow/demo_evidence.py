# @spec(FR-013)
"""Persist explicitly synthetic demo observations and bundled visual evidence."""

from __future__ import annotations

import hashlib
from importlib import resources
from pathlib import Path
from typing import Any

from .actual_provenance import (
    RECEIPT_KIND,
    RECEIPT_VERSION,
    STATIC_DEMO_FIXTURE,
    actual_provenance_path,
)
from .demo_visual_reports import visual_reports
from .json_filesystem import write_json_atomically as _write_json


def write_actual_provenance_fixture(actual_path: Path, expected: dict[str, Any]) -> None:
    """Write the content-bound provenance receipt for the demo actual tree.

    The demo actual tree is derived from the expected tree, so its receipt is an
    explicitly qualified ``static-demo-fixture``: it declares a frozen capture
    time and a fixture reason, binds to the written actual bytes by SHA-256, and
    can never masquerade as a fresh runtime capture. ``content.path`` stays
    relative so reruns into any directory are byte-identical.
    """
    screen = expected["screens"][0]
    digest = hashlib.sha256(actual_path.read_bytes()).hexdigest()
    _write_json(
        actual_provenance_path(actual_path),
        {
            "kind": RECEIPT_KIND,
            "version": RECEIPT_VERSION,
            "sourceKind": STATIC_DEMO_FIXTURE,
            "producer": {"name": "penflow.demo", "version": "static-demo-fixture"},
            "capturedAt": "2026-07-24T00:00:00Z",
            "target": {"surface": "web", "screen_id": screen["screen_id"]},
            "content": {"path": actual_path.name, "sha256": digest},
            "fixture": {
                "reason": (
                    "Synthetic example data packaged with Penflow as an immutable "
                    "static-demo-fixture; not fresh runtime evidence."
                )
            },
        },
    )


def write_visual_evidence_fixture(out: Path, expected: dict[str, Any]) -> None:
    """Copy package-owned synthetic PNG bytes and derive their fixture receipts.

    Args:
        out: Destination demo directory.
        expected: Expected tree generated in this demo invocation.

    The fixture is not a fresh renderer, runtime or model verdict. No external
    application or existing examples workspace is read.
    """
    evidence_dir = out / ".mockup-validation" / "visual-evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    image_bytes = (
        resources.files("penflow").joinpath("demo-assets", "checkout-screen.png").read_bytes()
    )
    image_path = evidence_dir / "checkoutScreen.png"
    image_path.write_bytes(image_bytes)
    image_digest = hashlib.sha256(image_bytes).hexdigest()
    for name, report in visual_reports(
        expected["screens"][0], image_path.name, image_digest
    ).items():
        _write_json(evidence_dir / name, report)
