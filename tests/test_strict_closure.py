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
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from penflow.actual_provenance import actual_provenance_path
from penflow.cli import main
from penflow.evidence import VISION_CATEGORIES
from penflow.pencil_persistence import verify_pencil_persistence
from penflow.reference_fidelity import REFERENCE_CATEGORIES
from penflow.strict_closure import validate_strict_closure

RUN_ID = "run-c6-strict-closure"
NOW = datetime(2026, 7, 24, 12, 0, tzinfo=UTC)


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


def _workspace(root: Path) -> tuple[Path, Path]:
    root.mkdir(parents=True)
    evidence = root / ".mockup-validation" / "visual-evidence"
    references = root / "references"
    run_dir = root / ".penflow-run"
    evidence.mkdir(parents=True)
    references.mkdir()
    run_dir.mkdir()

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

    pre = root / "pre.pen"
    post = root / "post.pen"
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
    return root, references


def _mutate_json(path: Path, mutate: Callable[[Any], None]) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    mutate(data)
    _json(path, data)


def _codes(report: dict[str, Any]) -> set[str]:
    return {issue["code"] for issue in report["issues"]}


def test_strict_closure_passes_and_writes_only_selected_run_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    workspace, references = _workspace(tmp_path / "workspace")
    before = {path: _sha(path) for path in workspace.rglob("*") if path.is_file()}

    report = validate_strict_closure(
        workspace,
        references=references,
        now=NOW,
        actual_max_age_seconds=3600,
    )

    assert report["status"] == "PASS"
    assert report["exit"] == 0
    assert report["run_id"] == RUN_ID
    assert all(gate["status"] == "PASS" for gate in report["gates"].values())
    assert report["filesystem"]["outside_run_dir_unchanged"] is True
    report_path = workspace / ".penflow-run" / "strict-closure.json"
    assert report_path.is_file()
    assert {
        path: _sha(path) for path in workspace.rglob("*") if path.is_file() and path != report_path
    } == before
    assert main(["validate-report", str(report_path), "--schema", "--json"]) == 0

    def validate_with_frozen_clock(*args: Any, **kwargs: Any) -> dict[str, Any]:
        """Keep the CLI assertion on the same deterministic capture boundary."""
        return validate_strict_closure(*args, now=NOW, **kwargs)

    monkeypatch.setattr("penflow.cli.validate_strict_closure", validate_with_frozen_clock)
    assert (
        main(
            [
                "run",
                "--target",
                str(workspace),
                "--references",
                str(references),
                "--strict-closure",
                "--actual-max-age-seconds",
                "86400",
                "--json",
            ]
        )
        == 0
    )


def test_run_without_strict_closure_preserves_pipeline_compatibility(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[dict[str, Any]] = []

    def fake_pipeline(target: str, **kwargs: Any) -> dict[str, Any]:
        calls.append({"target": target, **kwargs})
        return {"exit": 0, "status": "PASS"}

    monkeypatch.setattr("penflow.cli.run_pipeline", fake_pipeline)
    assert main(["run", "--target", str(tmp_path), "--json"]) == 0
    assert calls == [
        {
            "target": str(tmp_path),
            "theme_css": None,
            "references": None,
            "strict": False,
            "actual_max_age_seconds": None,
        }
    ]


@pytest.mark.parametrize(
    "name,mutate",
    [
        (
            "missing",
            lambda workspace: (
                workspace / ".penflow-run" / "pencil-persistence-receipt.json"
            ).unlink(),
        ),
        (
            "skip",
            lambda workspace: _mutate_json(
                workspace / ".mockup-validation/visual-evidence/vision-report.json",
                lambda report: report.update(status="BLOCKED_VISUAL_NOT_RUN"),
            ),
        ),
        (
            "warning-only",
            lambda workspace: _mutate_json(
                workspace / ".mockup-validation/visual-evidence/vision-report.json",
                lambda report: report.update(status="PASSED_WITH_WARNINGS"),
            ),
        ),
        (
            "stale",
            lambda workspace: _mutate_json(
                workspace / "actual-ui-tree.provenance.json",
                lambda receipt: receipt.update(capturedAt="2020-01-01T00:00:00Z"),
            ),
        ),
        (
            "replayed",
            lambda workspace: _mutate_json(
                workspace / "actual-ui-tree.provenance.json",
                lambda receipt: receipt.update(sessionId="another-run"),
            ),
        ),
        (
            "mismatched",
            lambda workspace: _mutate_json(
                workspace / ".mockup-validation/visual-evidence/manifest.json",
                lambda manifest: manifest.update(runId="another-run"),
            ),
        ),
        (
            "non-blocking",
            lambda workspace: _mutate_json(
                workspace / ".mockup-validation/visual-evidence/vision-report.json",
                lambda report: report["screens"][0]["criteria"][0].update(blocking=False),
            ),
        ),
        (
            "generic",
            lambda workspace: _mutate_json(
                workspace / ".mockup-validation/visual-evidence/vision-report.json",
                lambda report: report["screens"][0]["criteria"][0].pop("proof"),
            ),
        ),
        (
            "duplicated",
            lambda workspace: _mutate_json(
                workspace / "references/references-manifest.json",
                lambda manifest: manifest.append(dict(manifest[0])),
            ),
        ),
        (
            "tampered",
            lambda workspace: _mutate_json(
                workspace / ".penflow-run/pencil-persistence-receipt.json",
                lambda receipt: receipt.update(run_id="tampered-run"),
            ),
        ),
    ],
)
def test_named_bad_states_fail_structured(
    tmp_path: Path,
    name: str,
    mutate: Callable[[Path], None],
) -> None:
    workspace, references = _workspace(tmp_path / name)
    mutate(workspace)

    report = validate_strict_closure(
        workspace,
        references=references,
        now=NOW,
        actual_max_age_seconds=3600,
    )

    assert report["status"] == "FAIL", name
    assert report["exit"] == 1
    assert report["issues"]
    assert all(
        {"severity", "code", "path", "message"} <= issue.keys() for issue in report["issues"]
    )
    if name == "missing":
        assert report["gates"]["persistence"]["status"] == "FAIL"


def test_strict_report_rejects_changed_bound_input(tmp_path: Path) -> None:
    workspace, references = _workspace(tmp_path / "workspace")
    report = validate_strict_closure(workspace, references=references, now=NOW)
    report_path = workspace / ".penflow-run/strict-closure.json"
    assert report["status"] == "PASS"
    (workspace / "ui.pen").write_bytes(b"tampered after closure")

    assert main(["validate-report", str(report_path), "--schema", "--json"]) == 1
