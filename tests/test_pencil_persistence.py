# @spec(FR-001)
# @spec(FR-002)
# @spec(FR-003)
# @spec(FR-004)
# @spec(FR-005)
"""C46 persistence receipt coverage over independently read document bytes."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from penflow.cli import main
from penflow.pencil_persistence import verify_pencil_persistence

RUN_ID = "run-pencil-persistence-001"
OPERATION = "save-current-pencil-document"


def _write(path: Path, content: bytes) -> Path:
    path.write_bytes(content)
    return path


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bundle(tmp_path: Path) -> tuple[Path, Path]:
    pre = _write(tmp_path / "pre.snapshot.json", b'{"version":1,"children":[]}')
    post = _write(
        tmp_path / "post.snapshot.json",
        b'{"version":1,"children":[{"id":"checkout","type":"frame"}]}',
    )
    document = _write(tmp_path / "ui.pen", post.read_bytes())
    observation = {
        "kind": "penflow-pencil-persistence-observation",
        "version": 1,
        "run_id": RUN_ID,
        "document": {
            "path": document.name,
            "pre": {"path": pre.name, "sha256": _digest(pre)},
            "post": {"path": post.name, "sha256": _digest(post)},
        },
        "operation": OPERATION,
        "trigger": {"provider": "pencil-operator", "status": "triggered"},
    }
    observation_path = tmp_path / "observation.json"
    observation_path.write_text(json.dumps(observation), encoding="utf-8")
    return observation_path, document


def _codes(receipt: dict[str, Any]) -> set[str]:
    return {issue["code"] for issue in receipt["issues"]}


def _cli(
    observation: Path,
    document: Path,
    out: Path,
    *,
    run_id: str = RUN_ID,
    operation: str = OPERATION,
) -> int:
    return main(
        [
            "verify-pencil-persistence",
            str(observation),
            "--document",
            str(document),
            "--run-id",
            run_id,
            "--operation",
            operation,
            "--out",
            str(out),
            "--json",
        ]
    )


def test_source_verifier_writes_revalidatable_pass_receipt(tmp_path: Path) -> None:
    observation, document = _bundle(tmp_path)
    receipt_path = tmp_path / "receipt.json"

    receipt = verify_pencil_persistence(
        observation,
        document=document,
        run_id=RUN_ID,
        operation=OPERATION,
        out=receipt_path,
    )

    assert receipt["status"] == "PASS"
    assert receipt["verifier"]["result"] == "pass"
    assert receipt["checks"]["content_changed"] is True
    assert receipt["checks"]["current_matches_post"] is True
    assert receipt["closes_persistence"] is True
    assert main(["validate-report", str(receipt_path), "--schema", "--json"]) == 0
    assert _cli(observation, document, tmp_path / "cli-receipt.json") == 0


def test_noop_same_digest_fails_closed(tmp_path: Path) -> None:
    observation, document = _bundle(tmp_path)
    data = json.loads(observation.read_text(encoding="utf-8"))
    pre = tmp_path / data["document"]["pre"]["path"]
    post = tmp_path / data["document"]["post"]["path"]
    pre.write_bytes(post.read_bytes())
    data["document"]["pre"]["sha256"] = _digest(pre)
    observation.write_text(json.dumps(data), encoding="utf-8")

    receipt = verify_pencil_persistence(
        observation,
        document=document,
        run_id=RUN_ID,
        operation=OPERATION,
    )

    assert receipt["status"] == "FAIL"
    assert "persistence.digest.same" in _codes(receipt)
    assert _cli(observation, document, tmp_path / "noop-receipt.json") == 1


def test_trigger_only_claim_fails_closed(tmp_path: Path) -> None:
    observation, document = _bundle(tmp_path)
    observation.write_text(
        json.dumps(
            {
                "kind": "penflow-pencil-sync",
                "status": "PASS",
                "closes_persistence": False,
            }
        ),
        encoding="utf-8",
    )

    receipt = verify_pencil_persistence(
        observation,
        document=document,
        run_id=RUN_ID,
        operation=OPERATION,
    )

    assert receipt["status"] == "FAIL"
    assert "persistence.trigger_only" in _codes(receipt)
    assert _cli(observation, document, tmp_path / "trigger-receipt.json") == 1


def test_missing_observation_fails_closed_with_receipt(tmp_path: Path) -> None:
    _, document = _bundle(tmp_path)
    missing = tmp_path / "missing-observation.json"
    receipt_path = tmp_path / "missing-receipt.json"

    receipt = verify_pencil_persistence(
        missing,
        document=document,
        run_id=RUN_ID,
        operation=OPERATION,
        out=receipt_path,
    )

    assert receipt["status"] == "FAIL"
    assert "persistence.observation.missing" in _codes(receipt)
    assert receipt_path.is_file()
    assert _cli(missing, document, tmp_path / "missing-cli-receipt.json") == 1


def test_stale_document_fails_closed(tmp_path: Path) -> None:
    observation, document = _bundle(tmp_path)
    document.write_bytes(b'{"version":1,"children":[{"id":"newer"}]}')

    receipt = verify_pencil_persistence(
        observation,
        document=document,
        run_id=RUN_ID,
        operation=OPERATION,
    )

    assert receipt["status"] == "FAIL"
    assert "persistence.document.stale" in _codes(receipt)
    assert _cli(observation, document, tmp_path / "stale-receipt.json") == 1


def test_replayed_run_fails_closed(tmp_path: Path) -> None:
    observation, document = _bundle(tmp_path)

    receipt = verify_pencil_persistence(
        observation,
        document=document,
        run_id="run-pencil-persistence-002",
        operation=OPERATION,
    )

    assert receipt["status"] == "FAIL"
    assert "persistence.run.replayed" in _codes(receipt)
    assert (
        _cli(
            observation,
            document,
            tmp_path / "replayed-receipt.json",
            run_id="run-pencil-persistence-002",
        )
        == 1
    )


def test_tampered_snapshot_fails_closed(tmp_path: Path) -> None:
    observation, document = _bundle(tmp_path)
    data = json.loads(observation.read_text(encoding="utf-8"))
    post = tmp_path / data["document"]["post"]["path"]
    post.write_bytes(post.read_bytes() + b"\ntampered")

    receipt = verify_pencil_persistence(
        observation,
        document=document,
        run_id=RUN_ID,
        operation=OPERATION,
    )

    assert receipt["status"] == "FAIL"
    assert "persistence.digest.post_mismatch" in _codes(receipt)
    assert _cli(observation, document, tmp_path / "tampered-receipt.json") == 1


def test_mismatched_operation_and_document_fail_closed(tmp_path: Path) -> None:
    observation, document = _bundle(tmp_path)
    other_document = _write(tmp_path / "other.pen", document.read_bytes())

    receipt = verify_pencil_persistence(
        observation,
        document=other_document,
        run_id=RUN_ID,
        operation="export-current-pencil-document",
    )

    assert receipt["status"] == "FAIL"
    assert _codes(receipt) >= {
        "persistence.operation.mismatch",
        "persistence.document.mismatch",
    }
    assert (
        _cli(
            observation,
            other_document,
            tmp_path / "mismatch-receipt.json",
            operation="export-current-pencil-document",
        )
        == 1
    )


def test_tampered_final_receipt_fails_validate_report(tmp_path: Path) -> None:
    observation, document = _bundle(tmp_path)
    receipt_path = tmp_path / "receipt.json"
    verify_pencil_persistence(
        observation,
        document=document,
        run_id=RUN_ID,
        operation=OPERATION,
        out=receipt_path,
    )
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["document"]["post"]["actual_sha256"] = "0" * 64
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    assert main(["validate-report", str(receipt_path), "--schema", "--json"]) == 1
