# @spec(FR-001)
# @spec(FR-002)
# @spec(FR-003)
# @spec(FR-004)
# @spec(FR-005)
# @spec(FR-006)
"""C48 durable export operator receipt — coverage over independently read bytes.

Source flow (direct call), installed flow (`python -m penflow` subprocess), and a
bounded adversarial matrix. Reuses the C46 persistence receipt validator unchanged.
"""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from penflow.cli import main
from penflow.export_operator import (
    validate_export_operation_receipt,
    verify_export_operation,
)
from penflow.pencil_persistence import verify_pencil_persistence

RUN_ID = "run-export-operator-001"
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _png(width: int, height: int, salt: bytes = b"") -> bytes:
    return (
        _PNG_SIGNATURE
        + b"\x00\x00\x00\x0dIHDR"
        + width.to_bytes(4, "big")
        + height.to_bytes(4, "big")
        + b"\x08\x06\x00\x00\x00"
        + salt
        + b"IEND"
    )


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write(path: Path, data: bytes) -> str:
    path.write_bytes(data)
    return _sha(data)


def _codes(receipt: dict[str, Any]) -> set[str]:
    return {issue["code"] for issue in receipt["issues"]}


def _c46_receipt(tmp_path: Path) -> Path:
    """Build a valid C46 PASS persistence receipt bound to ui.pen."""
    pre = tmp_path / "pre.snapshot.json"
    pre.write_bytes(b'{"version":"0.9","children":[]}')
    post = tmp_path / "post.snapshot.json"
    post.write_bytes(b'{"version":"1.0","children":[]}')
    document = tmp_path / "ui.pen"
    document.write_bytes(post.read_bytes())
    observation = {
        "kind": "penflow-pencil-persistence-observation",
        "version": 1,
        "run_id": RUN_ID,
        "document": {
            "path": document.name,
            "pre": {"path": pre.name, "sha256": _sha(pre.read_bytes())},
            "post": {"path": post.name, "sha256": _sha(post.read_bytes())},
        },
        "operation": "save",
        "trigger": {"provider": "operator", "status": "triggered"},
    }
    (tmp_path / "observation.json").write_text(json.dumps(observation), encoding="utf-8")
    receipt = verify_pencil_persistence(
        tmp_path / "observation.json",
        document=document,
        run_id=RUN_ID,
        operation="save",
        out=tmp_path / "c46.json",
    )
    assert receipt["status"] == "PASS", receipt["issues"]
    return tmp_path / "c46.json"


def _packet(tmp_path: Path) -> tuple[Path, Path]:
    """Write a complete valid request; return (request_path, source_pen_path)."""
    _c46_receipt(tmp_path)
    document = tmp_path / "ui.pen"

    contract = {
        "kind": "product-contract",
        "version": 1,
        "product": "demo",
        "surfaces": [
            {
                "id": "welcome",
                "surface": "web-desktop",
                "role": "landing",
                "kind": "screen",
                "user_facing": True,
                "states": [{"id": "default"}, {"id": "error"}],
            }
        ],
    }
    contract_bytes = json.dumps(contract).encode("utf-8")
    (tmp_path / "contract.json").write_bytes(contract_bytes)

    exports_dir = tmp_path / "exports"
    exports_dir.mkdir()
    coverage = []
    for state, salt in (("default", b"D"), ("error", b"E")):
        exp = _png(1440, 1024, salt)
        exp_sha = _write(exports_dir / f"welcome-{state}.png", exp)
        ref_a = _png(1440, 1024, salt + b"A")
        ref_b = _png(1440, 1024, salt + b"B")
        ra_sha = _write(exports_dir / f"welcome-{state}-a.png", ref_a)
        rb_sha = _write(exports_dir / f"welcome-{state}-b.png", ref_b)
        coverage.append(
            {
                "surface": "web-desktop",
                "screen": "welcome",
                "state": state,
                "node_id": f"n-{state}",
                "export": {
                    "path": f"exports/welcome-{state}.png",
                    "sha256": exp_sha,
                    "width": 1440,
                    "height": 1024,
                    "scale": 2,
                    "format": "png",
                },
                "references": [
                    {
                        "path": f"exports/welcome-{state}-a.png",
                        "sha256": ra_sha,
                        "surface": "web-desktop",
                        "role": "landing",
                        "state": state,
                        "region": "full",
                        "design_intent": "calm minimal",
                    },
                    {
                        "path": f"exports/welcome-{state}-b.png",
                        "sha256": rb_sha,
                        "surface": "web-desktop",
                        "role": "landing",
                        "state": state,
                        "region": "full",
                        "design_intent": "calm minimal",
                    },
                ],
            }
        )

    request = {
        "kind": "penflow-export-operator-request",
        "version": 1,
        "run_id": RUN_ID,
        "operation": "export_nodes",
        "source": {"path": document.name, "sha256": _sha(document.read_bytes())},
        "document": {"id": "doc-welcome", "name": "Demo.pen"},
        "persistence_receipt": {"path": "c46.json"},
        "contract": {"path": "contract.json", "sha256": _sha(contract_bytes)},
        "coverage": coverage,
    }
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(request), encoding="utf-8")
    return request_path, document


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _mutate(request_path: Path, fn: Any) -> None:
    data = _load(request_path)
    fn(data)
    request_path.write_text(json.dumps(data), encoding="utf-8")


def _verify(request_path: Path, document: Path, run_id: str = RUN_ID) -> dict[str, Any]:
    return verify_export_operation(request_path, source_pen=document, run_id=run_id)


# --- D1: positive source + installed flow ----------------------------------


def test_source_flow_passes_and_revalidates(tmp_path: Path) -> None:
    request_path, document = _packet(tmp_path)
    receipt = verify_export_operation(
        request_path, source_pen=document, run_id=RUN_ID, out=tmp_path / "receipt.json"
    )
    assert receipt["status"] == "PASS", receipt["issues"]
    assert receipt["closes_export"] is True
    assert validate_export_operation_receipt(_load(tmp_path / "receipt.json")) == []


def test_installed_cli_flow_passes(tmp_path: Path) -> None:
    request_path, document = _packet(tmp_path)
    out = tmp_path / "receipt.json"
    # Installed-flow process boundaries are hard-bounded to prevent CI hangs.
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True, timeout=10)
    assert main(["doctor", "--project", str(tmp_path), "--fix", "--json"]) == 0
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "penflow",
            "verify-export-operation",
            "--project",
            str(tmp_path),
            str(request_path),
            "--source-pen",
            str(document),
            "--run-id",
            RUN_ID,
            "--out",
            str(out),
            "--json",
        ],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).resolve().parents[1]),
        check=False,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert _load(out)["status"] == "PASS"
    # validate-report re-reads and revalidates the receipt kind.
    revalidate = subprocess.run(
        [
            sys.executable,
            "-m",
            "penflow",
            "validate-report",
            str(out),
            "--schema",
            "--project",
            str(tmp_path),
            "--json",
        ],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).resolve().parents[1]),
        check=False,
        timeout=10,
    )
    assert revalidate.returncode == 0, revalidate.stdout + revalidate.stderr


def test_non_native_operation_fails_closed(tmp_path: Path) -> None:
    request_path, document = _packet(tmp_path)
    _mutate(request_path, lambda d: d.__setitem__("operation", "get_screenshot"))
    receipt = _verify(request_path, document)
    assert receipt["status"] == "FAIL"
    assert "export.operation.not_native" in _codes(receipt)


def test_replayed_run_fails_closed(tmp_path: Path) -> None:
    request_path, document = _packet(tmp_path)
    receipt = _verify(request_path, document, run_id="other-run")
    assert receipt["status"] == "FAIL"
    assert "export.run.replayed" in _codes(receipt)


def test_source_digest_mismatch_fails_closed(tmp_path: Path) -> None:
    request_path, document = _packet(tmp_path)
    document.write_bytes(document.read_bytes() + b"mutated")
    receipt = _verify(request_path, document)
    assert receipt["status"] == "FAIL"
    assert "export.source.digest_mismatch" in _codes(receipt)


def test_missing_document_identity_fails_closed(tmp_path: Path) -> None:
    request_path, document = _packet(tmp_path)
    _mutate(request_path, lambda d: d.__setitem__("document", {"id": "", "name": ""}))
    receipt = _verify(request_path, document)
    assert receipt["status"] == "FAIL"
    # schema (minLength) and the identity check both fire; identity is the stable code.
    assert "export.document.identity_missing" in _codes(
        receipt
    ) or "export.request.schema" in _codes(receipt)


def test_failed_persistence_receipt_fails_closed(tmp_path: Path) -> None:
    request_path, document = _packet(tmp_path)
    # Tamper the C46 receipt so revalidation and PASS both fail.
    c46 = _load(tmp_path / "c46.json")
    c46["status"] = "FAIL"
    (tmp_path / "c46.json").write_text(json.dumps(c46), encoding="utf-8")
    receipt = _verify(request_path, document)
    assert receipt["status"] == "FAIL"
    assert {"export.persistence.stale", "export.persistence.not_closed"} & _codes(receipt)


# --- D2: coverage ----------------------------------------------------------


def test_missing_coverage_item_fails_closed(tmp_path: Path) -> None:
    request_path, document = _packet(tmp_path)
    _mutate(request_path, lambda d: d["coverage"].pop())  # drop the "error" state
    receipt = _verify(request_path, document)
    assert receipt["status"] == "FAIL"
    assert "export.coverage.missing" in _codes(receipt)


def test_undeclared_coverage_item_fails_closed(tmp_path: Path) -> None:
    request_path, document = _packet(tmp_path)
    _mutate(request_path, lambda d: d["coverage"][0].__setitem__("state", "ghost"))
    receipt = _verify(request_path, document)
    assert receipt["status"] == "FAIL"
    assert "export.coverage.undeclared" in _codes(receipt)


def test_duplicate_coverage_item_fails_closed(tmp_path: Path) -> None:
    request_path, document = _packet(tmp_path)
    _mutate(request_path, lambda d: d["coverage"].__setitem__(1, copy.deepcopy(d["coverage"][0])))
    receipt = _verify(request_path, document)
    assert receipt["status"] == "FAIL"
    assert "export.coverage.duplicate" in _codes(receipt)


def test_empty_export_fails_closed(tmp_path: Path) -> None:
    request_path, document = _packet(tmp_path)
    (tmp_path / "exports" / "welcome-default.png").write_bytes(b"")
    receipt = _verify(request_path, document)
    assert receipt["status"] == "FAIL"
    assert "export.artifact.empty" in _codes(receipt)


def test_non_png_export_fails_closed(tmp_path: Path) -> None:
    request_path, document = _packet(tmp_path)
    fake = b"not a png but named .png"
    _mutate(request_path, lambda d: d["coverage"][0]["export"].__setitem__("sha256", _sha(fake)))
    (tmp_path / "exports" / "welcome-default.png").write_bytes(fake)
    receipt = _verify(request_path, document)
    assert receipt["status"] == "FAIL"
    assert "export.artifact.not_png" in _codes(receipt)


def test_export_digest_mismatch_fails_closed(tmp_path: Path) -> None:
    request_path, document = _packet(tmp_path)
    (tmp_path / "exports" / "welcome-default.png").write_bytes(_png(1440, 1024, b"TAMPER"))
    receipt = _verify(request_path, document)
    assert receipt["status"] == "FAIL"
    assert "export.artifact.digest_mismatch" in _codes(receipt)


def test_export_dimensions_mismatch_fails_closed(tmp_path: Path) -> None:
    request_path, document = _packet(tmp_path)
    _mutate(request_path, lambda d: d["coverage"][0]["export"].__setitem__("width", 999))
    receipt = _verify(request_path, document)
    assert receipt["status"] == "FAIL"
    assert "export.artifact.dimensions_mismatch" in _codes(receipt)


def test_reused_export_bytes_fails_closed(tmp_path: Path) -> None:
    request_path, document = _packet(tmp_path)
    # Point the "error" export at the "default" export bytes.
    shared = (tmp_path / "exports" / "welcome-default.png").read_bytes()
    (tmp_path / "exports" / "welcome-error.png").write_bytes(shared)
    _mutate(request_path, lambda d: d["coverage"][1]["export"].__setitem__("sha256", _sha(shared)))
    receipt = _verify(request_path, document)
    assert receipt["status"] == "FAIL"
    assert "export.artifact.reused" in _codes(receipt)


# --- D3: homologous references ---------------------------------------------


def test_single_reference_fails_closed(tmp_path: Path) -> None:
    request_path, document = _packet(tmp_path)
    _mutate(request_path, lambda d: d["coverage"][0]["references"].pop())
    receipt = _verify(request_path, document)
    assert receipt["status"] == "FAIL"
    assert "export.reference.pair_required" in _codes(receipt)


def test_reference_is_copy_of_export_fails_closed(tmp_path: Path) -> None:
    request_path, document = _packet(tmp_path)
    exp = (tmp_path / "exports" / "welcome-default.png").read_bytes()

    def mut(d: dict[str, Any]) -> None:
        d["coverage"][0]["references"][0].update(
            {"path": "exports/welcome-default.png", "sha256": _sha(exp)}
        )

    _mutate(request_path, mut)
    receipt = _verify(request_path, document)
    assert receipt["status"] == "FAIL"
    assert "export.reference.copy" in _codes(receipt)


def test_non_homologous_reference_fails_closed(tmp_path: Path) -> None:
    request_path, document = _packet(tmp_path)
    _mutate(request_path, lambda d: d["coverage"][0]["references"][0].__setitem__("state", "other"))
    receipt = _verify(request_path, document)
    assert receipt["status"] == "FAIL"
    assert "export.reference.non_homologous" in _codes(receipt)


def test_non_independent_reference_pair_fails_closed(tmp_path: Path) -> None:
    request_path, document = _packet(tmp_path)
    shared = (tmp_path / "exports" / "welcome-default-a.png").read_bytes()
    (tmp_path / "exports" / "welcome-default-b.png").write_bytes(shared)
    _mutate(
        request_path,
        lambda d: d["coverage"][0]["references"][1].__setitem__("sha256", _sha(shared)),
    )
    receipt = _verify(request_path, document)
    assert receipt["status"] == "FAIL"
    assert "export.reference.not_independent" in _codes(receipt)


def test_non_homologous_reference_reuse_fails_closed(tmp_path: Path) -> None:
    request_path, document = _packet(tmp_path)
    # Reuse the "default" reference-a bytes for the "error" item's reference-a.
    shared = (tmp_path / "exports" / "welcome-default-a.png").read_bytes()
    (tmp_path / "exports" / "welcome-error-a.png").write_bytes(shared)
    _mutate(
        request_path,
        lambda d: d["coverage"][1]["references"][0].__setitem__("sha256", _sha(shared)),
    )
    receipt = _verify(request_path, document)
    assert receipt["status"] == "FAIL"
    assert "export.reference.non_homologous_reuse" in _codes(receipt)


def test_stretched_reference_crop_fails_closed(tmp_path: Path) -> None:
    request_path, document = _packet(tmp_path)
    _mutate(
        request_path,
        lambda d: d["coverage"][0]["references"][0].__setitem__(
            "crop", {"width": 100, "height": 900}
        ),
    )
    receipt = _verify(request_path, document)
    assert receipt["status"] == "FAIL"
    assert "export.reference.stretched" in _codes(receipt)


# --- D4: content-addressed freshness ---------------------------------------


def test_contract_mutation_invalidates_pass(tmp_path: Path) -> None:
    request_path, document = _packet(tmp_path)
    (tmp_path / "contract.json").write_bytes((tmp_path / "contract.json").read_bytes() + b" ")
    receipt = _verify(request_path, document)
    assert receipt["status"] == "FAIL"
    assert "export.contract.digest_mismatch" in _codes(receipt)


def test_tampered_receipt_fails_validate_report(tmp_path: Path) -> None:
    request_path, document = _packet(tmp_path)
    verify_export_operation(
        request_path, source_pen=document, run_id=RUN_ID, out=tmp_path / "receipt.json"
    )
    receipt = _load(tmp_path / "receipt.json")
    receipt["run_id"] = "tampered"
    issues = validate_export_operation_receipt(receipt)
    assert issues and "integrity" in issues[0]["message"]


def test_stale_receipt_after_export_mutation_fails_validate_report(tmp_path: Path) -> None:
    request_path, document = _packet(tmp_path)
    verify_export_operation(
        request_path, source_pen=document, run_id=RUN_ID, out=tmp_path / "receipt.json"
    )
    # Mutate an export PNG after the receipt was written: stored receipt is now stale.
    (tmp_path / "exports" / "welcome-default.png").write_bytes(_png(1440, 1024, b"LATER"))
    issues = validate_export_operation_receipt(_load(tmp_path / "receipt.json"))
    assert issues, "stale receipt must fail revalidation"


def test_validate_report_rejects_tampered_receipt_via_cli(tmp_path: Path) -> None:
    request_path, document = _packet(tmp_path)
    verify_export_operation(
        request_path, source_pen=document, run_id=RUN_ID, out=tmp_path / "receipt.json"
    )
    receipt = _load(tmp_path / "receipt.json")
    receipt["operation"] = "screenshot"
    (tmp_path / "receipt.json").write_text(json.dumps(receipt), encoding="utf-8")
    rc = main(["validate-report", str(tmp_path / "receipt.json"), "--schema", "--json"])
    assert rc != 0


# --- D5: no forbidden runtime dependency -----------------------------------


def test_export_operator_has_no_forbidden_runtime_import() -> None:
    """Guard D5: the verifier imports only stdlib + the C46 validator — no runtime deps.

    Scans import statements only (not prose): the module docstring legitimately names
    forbidden runtimes when stating the boundary.
    """
    source = (Path(__file__).resolve().parents[1] / "penflow" / "export_operator.py").read_text()
    import_lines = [
        line.strip() for line in source.splitlines() if line.startswith(("import ", "from "))
    ]
    forbidden = (
        "mcp",
        "pencil_mcp",
        "playwright",
        "selenium",
        "webdriver",
        "cc_hub",
        "subprocess",
        "requests",
        "xcodebuild",
        "simulator",
        "browser",
        "visual_preview",
        "PIL",
        "cairosvg",
    )
    for line in import_lines:
        for token in forbidden:
            assert token not in line, f"forbidden import {token!r} in: {line}"
    # Only the C46 validator and stdlib/schema_cache are imported from penflow.
    assert any("pencil_persistence" in line for line in import_lines)
