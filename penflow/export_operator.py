"""Durable export operator receipt (C48).

Bind native Pencil ``export_nodes`` design proof to one versioned request/receipt
contract. Pencil and MCP stay outside this module: an operator produces one request
plus the exported PNGs and reference PNGs; Penflow re-reads every byte, recomputes
every digest and PNG dimension itself, revalidates the C46 persistence receipt, and
emits a content-addressed receipt. PASS alone closes export coverage.

The verifier imports only the standard library plus the existing C46 validator
``validate_pencil_persistence_receipt`` — no Pencil MCP, renderer, browser, simulator,
Playwright, Xcode, cc-hub, or UI-runtime dependency.

@spec FR-001: request/receipt binding — .specs/features/073-durable-export-operator-receipt/spec.md#fr-001
@spec FR-002: coverage over native export_nodes PNGs — .specs/features/073-durable-export-operator-receipt/spec.md#fr-002
@spec FR-003: two homologous references — .specs/features/073-durable-export-operator-receipt/spec.md#fr-003
@spec FR-004: content-addressed revalidation — .specs/features/073-durable-export-operator-receipt/spec.md#fr-004
@spec FR-005: local-bytes only, no runtime dependency — .specs/features/073-durable-export-operator-receipt/spec.md#fr-005
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from .pencil_persistence import validate_pencil_persistence_receipt
from .schema_cache import validator_for

REQUEST_KIND = "penflow-export-operator-request"
RECEIPT_KIND = "penflow-export-operator-receipt"
EXPORT_OPERATOR_VERSION = 1
NATIVE_OPERATION = "export_nodes"
_REQUEST_SCHEMA = "export-operator-request.schema.json"

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_CROP_RATIO_TOLERANCE = 0.02


def verify_export_operation(
    request: str | Path,
    *,
    source_pen: str | Path,
    run_id: str,
    out: str | Path | None = None,
) -> dict[str, Any]:
    """Verify one operator export request against independently read bytes.

    Args:
        request: Operator JSON declaring the run, source, document, C46 receipt,
            frozen product contract, and per surface/screen/state export + references.
        source_pen: Current ``.pen`` document whose bytes bind the run.
        run_id: Exact run expected by the caller; other-run requests are rejected.
        out: Optional path for the structured export receipt.

    Returns:
        A deterministic PASS/FAIL receipt. PASS alone closes export coverage.
    """
    request_path = Path(request).resolve()
    source_path = Path(source_pen).resolve()
    issues: list[dict[str, str]] = []
    parsed, request_sha256 = _load_json(request_path, issues, label="request")
    checks = _empty_checks()

    source_current = _digest_file(source_path)
    checks["source_present"] = source_current is not None
    if source_current is None:
        issues.append(
            _issue(
                "export.source.missing",
                "$.source.path",
                f"source .pen does not exist: {source_path}",
            )
        )

    source_declared: str | None = None
    document_identity: dict[str, str | None] = {"id": None, "name": None}
    persistence: dict[str, Any] = {
        "path": None,
        "sha256": None,
        "status": None,
        "revalidated": False,
    }
    contract_block: dict[str, str | None] = {
        "path": None,
        "declared_sha256": None,
        "current_sha256": None,
    }
    coverage: list[dict[str, Any]] = []

    if isinstance(parsed, dict):
        issues.extend(_schema_issues(parsed))
        checks["operation_native"] = parsed.get("operation") == NATIVE_OPERATION
        checks["run_matches"] = parsed.get("run_id") == run_id
        if not checks["operation_native"]:
            issues.append(
                _issue(
                    "export.operation.not_native",
                    "$.operation",
                    f"operation must be the native {NATIVE_OPERATION!r} export",
                )
            )
        if not checks["run_matches"]:
            issues.append(
                _issue(
                    "export.run.replayed",
                    "$.run_id",
                    f"request run does not match expected run {run_id!r}",
                )
            )

        source_declared = _str_or_none(_dig(parsed, "source", "sha256"))
        checks["source_digest_matches"] = bool(
            source_declared and source_current and source_declared == source_current
        )
        if not checks["source_digest_matches"]:
            issues.append(
                _issue(
                    "export.source.digest_mismatch",
                    "$.source.sha256",
                    "declared source .pen digest does not match recomputed bytes",
                )
            )
        declared_source_path = _resolve(request_path, _dig(parsed, "source", "path"))
        checks["source_path_matches"] = declared_source_path == source_path
        if not checks["source_path_matches"]:
            issues.append(
                _issue(
                    "export.source.path_mismatch",
                    "$.source.path",
                    "declared source path does not match the supplied .pen document",
                )
            )

        document_identity = _document_identity(parsed, checks, issues)
        persistence = _persistence_result(
            parsed, request_path, run_id, source_current, checks, issues
        )
        contract_block, universe = _contract_result(parsed, request_path, checks, issues)
        coverage = _coverage_results(parsed, request_path, universe, checks, issues)
    else:
        _mark_absent(checks)

    issues.sort(key=lambda issue: (issue["path"], issue["code"], issue["message"]))
    status = "PASS" if not issues and all(checks.values()) else "FAIL"
    receipt: dict[str, Any] = {
        "kind": RECEIPT_KIND,
        "version": EXPORT_OPERATOR_VERSION,
        "status": status,
        "closes_export": status == "PASS",
        "run_id": run_id,
        "operation": parsed.get("operation") if isinstance(parsed, dict) else None,
        "request": {"path": str(request_path), "sha256": request_sha256},
        "source": {
            "path": str(source_path),
            "declared_sha256": source_declared,
            "current_sha256": source_current,
        },
        "document": document_identity,
        "persistence": persistence,
        "contract": contract_block,
        "coverage": coverage,
        "checks": checks,
        "verifier": {
            "name": "penflow",
            "method": "independent-byte-digest",
            "result": "pass" if status == "PASS" else "fail",
        },
        "issues": issues,
    }
    receipt["integrity"] = {"algorithm": "sha256", "sha256": _receipt_digest(receipt)}
    if out is not None:
        output_path = Path(out)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    return receipt


def validate_export_operation_receipt(receipt: dict[str, Any]) -> list[dict[str, str]]:
    """Re-read a receipt's evidence and reject stale, replayed, or tampered contents.

    Returns report-schema issues. Empty means the stored receipt exactly matches a
    fresh independent verification.
    """
    issues: list[dict[str, str]] = []
    integrity = receipt.get("integrity")
    declared_integrity = integrity.get("sha256") if isinstance(integrity, dict) else None
    if declared_integrity != _receipt_digest(receipt):
        issues.append(
            _report_issue(
                "$.integrity.sha256", "export receipt integrity digest does not match its contents"
            )
        )
        return issues

    request = receipt.get("request")
    source = receipt.get("source")
    run_id = receipt.get("run_id")
    if not isinstance(request, dict) or not isinstance(source, dict) or not isinstance(run_id, str):
        return issues
    request_path = request.get("path")
    source_path = source.get("path")
    if not (
        isinstance(request_path, str)
        and request_path
        and isinstance(source_path, str)
        and source_path
    ):
        return issues

    fresh = verify_export_operation(request_path, source_pen=source_path, run_id=run_id)
    if _without_integrity(fresh) != _without_integrity(receipt):
        issues.append(
            _report_issue(
                "$",
                "export receipt is stale, replayed, or tampered relative to independently read bytes",
            )
        )
    return issues


# --- binding helpers -------------------------------------------------------


def _document_identity(
    parsed: dict[str, Any], checks: dict[str, bool], issues: list[dict[str, str]]
) -> dict[str, str | None]:
    document = parsed.get("document")
    document = document if isinstance(document, dict) else {}
    doc_id = _str_or_none(document.get("id"))
    doc_name = _str_or_none(document.get("name"))
    checks["document_identity"] = bool(doc_id and doc_name)
    if not checks["document_identity"]:
        issues.append(
            _issue(
                "export.document.identity_missing",
                "$.document",
                "request must declare a non-empty Pencil document id and name",
            )
        )
    return {"id": doc_id, "name": doc_name}


def _persistence_result(
    parsed: dict[str, Any],
    request_path: Path,
    run_id: str,
    source_current: str | None,
    checks: dict[str, bool],
    issues: list[dict[str, str]],
) -> dict[str, Any]:
    block = parsed.get("persistence_receipt")
    declared_path = block.get("path") if isinstance(block, dict) else None
    receipt_path = _resolve(request_path, declared_path)
    result: dict[str, Any] = {"path": None, "sha256": None, "status": None, "revalidated": False}
    if receipt_path is None or not receipt_path.is_file():
        issues.append(
            _issue(
                "export.persistence.missing",
                "$.persistence_receipt.path",
                "C46 persistence receipt file does not exist",
            )
        )
        return result
    result["path"] = str(receipt_path)
    raw = receipt_path.read_bytes()
    result["sha256"] = hashlib.sha256(raw).hexdigest()
    try:
        c46 = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        issues.append(
            _issue(
                "export.persistence.invalid_json",
                "$.persistence_receipt.path",
                "C46 persistence receipt is not valid JSON",
            )
        )
        return result
    if not isinstance(c46, dict) or c46.get("kind") != "penflow-pencil-persistence-receipt":
        issues.append(
            _issue(
                "export.persistence.kind",
                "$.persistence_receipt.path",
                "referenced receipt is not a penflow-pencil-persistence-receipt",
            )
        )
        return result
    result["status"] = c46.get("status")
    # Reuse the C46 validator unchanged (no refactor): revalidate stored bytes.
    revalidation = validate_pencil_persistence_receipt(c46)
    checks["persistence_revalidates"] = not revalidation
    result["revalidated"] = not revalidation
    if revalidation:
        issues.append(
            _issue(
                "export.persistence.stale",
                "$.persistence_receipt",
                "C46 persistence receipt is stale or tampered on revalidation",
            )
        )
    checks["persistence_pass"] = (
        c46.get("status") == "PASS" and c46.get("closes_persistence") is True
    )
    if not checks["persistence_pass"]:
        issues.append(
            _issue(
                "export.persistence.not_closed",
                "$.persistence_receipt",
                "C46 persistence receipt does not close persistence with PASS",
            )
        )
    checks["persistence_run_matches"] = c46.get("run_id") == run_id
    if not checks["persistence_run_matches"]:
        issues.append(
            _issue(
                "export.persistence.run_mismatch",
                "$.persistence_receipt",
                "C46 persistence receipt run does not match this run",
            )
        )
    c46_document = c46.get("document")
    document = c46_document if isinstance(c46_document, dict) else {}
    checks["persistence_document_matches"] = bool(
        source_current and document.get("current_sha256") == source_current
    )
    if not checks["persistence_document_matches"]:
        issues.append(
            _issue(
                "export.persistence.document_mismatch",
                "$.persistence_receipt",
                "C46 receipt document bytes do not match the current .pen",
            )
        )
    return result


def _contract_result(
    parsed: dict[str, Any],
    request_path: Path,
    checks: dict[str, bool],
    issues: list[dict[str, str]],
) -> tuple[dict[str, str | None], set[tuple[str, str, str]]]:
    block = parsed.get("contract")
    declared_path = block.get("path") if isinstance(block, dict) else None
    declared_sha = _str_or_none(block.get("sha256")) if isinstance(block, dict) else None
    contract_path = _resolve(request_path, declared_path)
    result: dict[str, str | None] = {
        "path": str(contract_path) if contract_path else None,
        "declared_sha256": declared_sha,
        "current_sha256": None,
    }
    universe: set[tuple[str, str, str]] = set()
    if contract_path is None or not contract_path.is_file():
        issues.append(
            _issue(
                "export.contract.missing",
                "$.contract.path",
                "frozen product contract file does not exist",
            )
        )
        return result, universe
    raw = contract_path.read_bytes()
    current = hashlib.sha256(raw).hexdigest()
    result["current_sha256"] = current
    checks["contract_digest_matches"] = bool(declared_sha and declared_sha == current)
    if not checks["contract_digest_matches"]:
        issues.append(
            _issue(
                "export.contract.digest_mismatch",
                "$.contract.sha256",
                "declared contract digest does not match recomputed bytes",
            )
        )
    try:
        contract_obj = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        issues.append(
            _issue(
                "export.contract.unreadable",
                "$.contract.path",
                "frozen product contract is not valid JSON",
            )
        )
        return result, universe
    universe = _declared_universe(contract_obj)
    if not universe:
        issues.append(
            _issue(
                "export.contract.empty",
                "$.contract",
                "frozen product contract declares no product surface/screen/state",
            )
        )
    return result, universe


def _declared_universe(contract_obj: Any) -> set[tuple[str, str, str]]:
    universe: set[tuple[str, str, str]] = set()
    surfaces = contract_obj.get("surfaces") if isinstance(contract_obj, dict) else None
    if not isinstance(surfaces, list):
        return universe
    for surface in surfaces:
        if not isinstance(surface, dict):
            continue
        kind = surface.get("kind")
        is_screen = kind == "screen" or (kind == "technical" and surface.get("user_facing") is True)
        if not is_screen:
            continue
        surface_name = _str_or_none(surface.get("surface"))
        screen_id = _str_or_none(surface.get("id"))
        states = surface.get("states")
        if not (surface_name and screen_id and isinstance(states, list)):
            continue
        for state in states:
            state_id = _str_or_none(state.get("id")) if isinstance(state, dict) else None
            if state_id:
                universe.add((surface_name, screen_id, state_id))
    return universe


def _coverage_results(
    parsed: dict[str, Any],
    request_path: Path,
    universe: set[tuple[str, str, str]],
    checks: dict[str, bool],
    issues: list[dict[str, str]],
) -> list[dict[str, Any]]:
    raw_coverage = parsed.get("coverage")
    coverage_items = raw_coverage if isinstance(raw_coverage, list) else []
    results: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str, str]] = set()
    export_paths: set[str] = set()
    export_sha_by_key: dict[str, tuple[str, str, str]] = {}
    reference_sha_by_mapping: dict[str, tuple[str, str, str, str, str]] = {}
    covered: set[tuple[str, str, str]] = set()

    checks["coverage_present"] = bool(coverage_items)
    if not coverage_items:
        issues.append(
            _issue(
                "export.coverage.empty",
                "$.coverage",
                "request declares no covered surface/screen/state",
            )
        )

    for index, item in enumerate(coverage_items):
        prefix = f"$.coverage[{index}]"
        if not isinstance(item, dict):
            issues.append(
                _issue("export.coverage.invalid", prefix, "coverage item must be an object")
            )
            continue
        surface = _str_or_none(item.get("surface")) or ""
        screen = _str_or_none(item.get("screen")) or ""
        state = _str_or_none(item.get("state")) or ""
        key = (surface, screen, state)
        if key in seen_keys:
            checks["coverage_no_duplicate"] = False
            issues.append(
                _issue("export.coverage.duplicate", prefix, f"duplicate coverage of {key}")
            )
        seen_keys.add(key)
        if universe and key not in universe:
            checks["coverage_declared"] = False
            issues.append(
                _issue(
                    "export.coverage.undeclared",
                    prefix,
                    f"covered {key} is not declared in the frozen product contract",
                )
            )
        else:
            covered.add(key)

        node_id = _str_or_none(item.get("node_id"))
        if not node_id:
            checks["coverage_nodes"] = False
            issues.append(
                _issue(
                    "export.node.missing",
                    f"{prefix}.node_id",
                    "covered item must bind an exact Pencil node id",
                )
            )

        export = _export_result(
            item, request_path, prefix, export_paths, export_sha_by_key, key, checks, issues
        )
        references = _reference_results(
            item, request_path, prefix, key, export, reference_sha_by_mapping, checks, issues
        )
        results.append(
            {
                "surface": surface,
                "screen": screen,
                "state": state,
                "node_id": node_id,
                "export": export,
                "references": references,
            }
        )

    missing = sorted(universe - covered)
    if missing:
        checks["coverage_exhaustive"] = False
        for entry in missing:
            issues.append(
                _issue(
                    "export.coverage.missing",
                    "$.coverage",
                    f"declared {entry} has no covering export",
                )
            )
    return results


def _export_result(
    item: dict[str, Any],
    request_path: Path,
    prefix: str,
    export_paths: set[str],
    export_sha_by_key: dict[str, tuple[str, str, str]],
    key: tuple[str, str, str],
    checks: dict[str, bool],
    issues: list[dict[str, str]],
) -> dict[str, Any]:
    raw_export = item.get("export")
    export = raw_export if isinstance(raw_export, dict) else {}
    declared_sha = _str_or_none(export.get("sha256"))
    declared_w = export.get("width")
    declared_h = export.get("height")
    scale = export.get("scale")
    fmt = export.get("format")
    path = _resolve(request_path, export.get("path"))
    result: dict[str, Any] = {
        "path": str(path) if path else None,
        "declared_sha256": declared_sha,
        "actual_sha256": None,
        "width": declared_w if isinstance(declared_w, int) else None,
        "height": declared_h if isinstance(declared_h, int) else None,
        "scale": scale if isinstance(scale, (int, float)) and not isinstance(scale, bool) else None,
        "format": fmt if isinstance(fmt, str) else None,
    }
    epref = f"{prefix}.export"
    if path is None or not path.is_file():
        checks["exports_present"] = False
        issues.append(
            _issue("export.artifact.missing", f"{epref}.path", "export PNG does not exist")
        )
        return result
    if str(path) in export_paths:
        checks["exports_distinct"] = False
        issues.append(
            _issue(
                "export.artifact.duplicate",
                f"{epref}.path",
                "export PNG path is reused across covered items",
            )
        )
    export_paths.add(str(path))
    data = path.read_bytes()
    if not data:
        checks["exports_nonempty"] = False
        issues.append(_issue("export.artifact.empty", f"{epref}.path", "export PNG is empty"))
        return result
    actual_sha = hashlib.sha256(data).hexdigest()
    result["actual_sha256"] = actual_sha
    if declared_sha != actual_sha:
        checks["exports_digest"] = False
        issues.append(
            _issue(
                "export.artifact.digest_mismatch",
                f"{epref}.sha256",
                "declared export digest does not match recomputed bytes",
            )
        )
    if actual_sha in export_sha_by_key and export_sha_by_key[actual_sha] != key:
        checks["exports_distinct"] = False
        issues.append(
            _issue(
                "export.artifact.reused",
                f"{epref}.sha256",
                "identical export bytes reused for a different surface/screen/state",
            )
        )
    export_sha_by_key.setdefault(actual_sha, key)

    dimensions = _png_dimensions(data)
    if dimensions is None:
        checks["exports_png"] = False
        issues.append(
            _issue(
                "export.artifact.not_png",
                f"{epref}.path",
                "export is not a valid PNG (missing signature/IHDR); synthetic or renamed",
            )
        )
        return result
    width, height = dimensions
    if fmt != "png":
        checks["exports_format"] = False
        issues.append(
            _issue("export.artifact.format", f"{epref}.format", "export format must be 'png'")
        )
    if not (isinstance(result["scale"], (int, float)) and result["scale"] and result["scale"] > 0):
        checks["exports_scale"] = False
        issues.append(
            _issue(
                "export.artifact.scale", f"{epref}.scale", "export scale must be a positive number"
            )
        )
    if declared_w != width or declared_h != height:
        checks["exports_dimensions"] = False
        issues.append(
            _issue(
                "export.artifact.dimensions_mismatch",
                f"{epref}",
                f"declared dimensions {declared_w}x{declared_h} != PNG {width}x{height}",
            )
        )
    result["width"] = width
    result["height"] = height
    return result


def _reference_results(
    item: dict[str, Any],
    request_path: Path,
    prefix: str,
    key: tuple[str, str, str],
    export: dict[str, Any],
    reference_sha_by_mapping: dict[str, tuple[str, str, str, str, str]],
    checks: dict[str, bool],
    issues: list[dict[str, str]],
) -> list[dict[str, Any]]:
    raw_refs = item.get("references")
    refs = raw_refs if isinstance(raw_refs, list) else []
    rpref = f"{prefix}.references"
    if len(refs) != 2:
        checks["reference_pair"] = False
        issues.append(
            _issue(
                "export.reference.pair_required",
                rpref,
                "each covered item requires exactly two homologous references",
            )
        )
    surface, state = key[0], key[2]
    export_sha = export.get("actual_sha256")
    export_w = export.get("width")
    export_h = export.get("height")
    seen_sha: set[str] = set()
    results: list[dict[str, Any]] = []
    roles: set[str] = set()
    regions: set[str] = set()
    intents: set[str] = set()

    for index, ref in enumerate(refs):
        ipref = f"{rpref}[{index}]"
        if not isinstance(ref, dict):
            checks["reference_valid"] = False
            issues.append(_issue("export.reference.invalid", ipref, "reference must be an object"))
            continue
        declared_sha = _str_or_none(ref.get("sha256"))
        path = _resolve(request_path, ref.get("path"))
        r_surface = _str_or_none(ref.get("surface"))
        r_role = _str_or_none(ref.get("role"))
        r_state = _str_or_none(ref.get("state"))
        r_region = _str_or_none(ref.get("region"))
        r_intent = _str_or_none(ref.get("design_intent"))
        entry: dict[str, Any] = {
            "path": str(path) if path else None,
            "declared_sha256": declared_sha,
            "actual_sha256": None,
            "surface": r_surface,
            "role": r_role,
            "state": r_state,
            "region": r_region,
            "design_intent": r_intent,
        }
        results.append(entry)
        if r_role:
            roles.add(r_role)
        if r_region:
            regions.add(r_region)
        if r_intent:
            intents.add(r_intent)

        if path is None or not path.is_file():
            checks["reference_present"] = False
            issues.append(
                _issue("export.reference.missing", f"{ipref}.path", "reference PNG does not exist")
            )
            continue
        data = path.read_bytes()
        if not data:
            checks["reference_present"] = False
            issues.append(
                _issue("export.reference.empty", f"{ipref}.path", "reference PNG is empty")
            )
            continue
        actual_sha = hashlib.sha256(data).hexdigest()
        entry["actual_sha256"] = actual_sha
        if declared_sha != actual_sha:
            checks["reference_digest"] = False
            issues.append(
                _issue(
                    "export.reference.digest_mismatch",
                    f"{ipref}.sha256",
                    "declared reference digest does not match recomputed bytes",
                )
            )
        if _png_dimensions(data) is None:
            checks["reference_png"] = False
            issues.append(
                _issue("export.reference.not_png", f"{ipref}.path", "reference is not a valid PNG")
            )
        if export_sha and actual_sha == export_sha:
            checks["reference_independent"] = False
            issues.append(
                _issue("export.reference.copy", ipref, "reference is a byte copy of the export")
            )
        if actual_sha in seen_sha:
            checks["reference_independent"] = False
            issues.append(
                _issue(
                    "export.reference.not_independent",
                    ipref,
                    "the two references must be independent (distinct bytes)",
                )
            )
        seen_sha.add(actual_sha)
        # homology to the covered item
        if r_surface != surface or r_state != state:
            checks["reference_homologous"] = False
            issues.append(
                _issue(
                    "export.reference.non_homologous",
                    ipref,
                    "reference surface/state does not match the covered item",
                )
            )
        # a reference reused across a different homology mapping
        mapping = (r_surface or "", r_role or "", r_state or "", r_region or "", r_intent or "")
        prior = reference_sha_by_mapping.get(actual_sha)
        if prior is not None and prior != mapping:
            checks["reference_homologous"] = False
            issues.append(
                _issue(
                    "export.reference.non_homologous_reuse",
                    ipref,
                    "reference bytes reused across a non-homologous mapping",
                )
            )
        reference_sha_by_mapping.setdefault(actual_sha, mapping)
        # stretched crop
        crop = ref.get("crop")
        if (
            isinstance(crop, dict)
            and isinstance(export_w, int)
            and isinstance(export_h, int)
            and export_h
        ):
            cw = crop.get("width")
            ch = crop.get("height")
            if (
                isinstance(cw, (int, float))
                and isinstance(ch, (int, float))
                and ch
                and not isinstance(cw, bool)
                and not isinstance(ch, bool)
            ):
                if abs((cw / ch) - (export_w / export_h)) > _CROP_RATIO_TOLERANCE:
                    checks["reference_not_stretched"] = False
                    issues.append(
                        _issue(
                            "export.reference.stretched",
                            f"{ipref}.crop",
                            "reference crop aspect ratio would require stretching the export",
                        )
                    )

    if refs and (len(roles) > 1 or len(regions) > 1 or len(intents) > 1):
        checks["reference_homologous"] = False
        issues.append(
            _issue(
                "export.reference.non_homologous",
                rpref,
                "the reference pair must share one role, region, and design intent",
            )
        )
    return results


# --- primitive helpers -----------------------------------------------------


def _png_dimensions(data: bytes) -> tuple[int, int] | None:
    if len(data) < 24 or data[:8] != _PNG_SIGNATURE or data[12:16] != b"IHDR":
        return None
    width = int.from_bytes(data[16:20], "big")
    height = int.from_bytes(data[20:24], "big")
    if width <= 0 or height <= 0:
        return None
    return width, height


def _load_json(
    path: Path, issues: list[dict[str, str]], *, label: str
) -> tuple[dict[str, Any] | None, str | None]:
    if not path.is_file():
        issues.append(
            _issue(f"export.{label}.missing", "$", f"{label} file does not exist: {path}")
        )
        return None, None
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    try:
        parsed = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        issues.append(
            _issue(f"export.{label}.invalid_json", "$", f"{label} is not valid JSON: {error}")
        )
        return None, digest
    if not isinstance(parsed, dict):
        issues.append(
            _issue(f"export.{label}.invalid_root", "$", f"{label} root must be an object")
        )
        return None, digest
    return parsed, digest


def _schema_issues(request: dict[str, Any]) -> list[dict[str, str]]:
    return [
        _issue("export.request.schema", _json_path(error.absolute_path), error.message)
        for error in validator_for(_REQUEST_SCHEMA).iter_errors(request)
    ]


def _digest_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _resolve(base: Path, value: Any) -> Path | None:
    if not isinstance(value, str) or not value:
        return None
    candidate = Path(value)
    return (candidate if candidate.is_absolute() else base.parent / candidate).resolve()


def _dig(obj: Any, *keys: str) -> Any:
    current = obj
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _str_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _empty_checks() -> dict[str, bool]:
    return {
        "operation_native": False,
        "run_matches": False,
        "source_present": False,
        "source_digest_matches": False,
        "source_path_matches": False,
        "document_identity": False,
        "persistence_revalidates": False,
        "persistence_pass": False,
        "persistence_run_matches": False,
        "persistence_document_matches": False,
        "contract_digest_matches": False,
        "coverage_present": True,
        "coverage_no_duplicate": True,
        "coverage_declared": True,
        "coverage_exhaustive": True,
        "coverage_nodes": True,
        "exports_present": True,
        "exports_nonempty": True,
        "exports_digest": True,
        "exports_png": True,
        "exports_format": True,
        "exports_scale": True,
        "exports_dimensions": True,
        "exports_distinct": True,
        "reference_pair": True,
        "reference_valid": True,
        "reference_present": True,
        "reference_digest": True,
        "reference_png": True,
        "reference_independent": True,
        "reference_homologous": True,
        "reference_not_stretched": True,
    }


def _mark_absent(checks: dict[str, bool]) -> None:
    for key in list(checks):
        checks[key] = False


def _receipt_digest(receipt: dict[str, Any]) -> str:
    canonical = _without_integrity(receipt)
    payload = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _without_integrity(receipt: dict[str, Any]) -> dict[str, Any]:
    canonical = copy.deepcopy(receipt)
    canonical.pop("integrity", None)
    return canonical


def _json_path(parts: Any) -> str:
    return "$" + "".join(f".{part}" if isinstance(part, str) else f"[{part}]" for part in parts)


def _issue(code: str, path: str, message: str) -> dict[str, str]:
    return {"severity": "error", "code": code, "path": path, "message": message}


def _report_issue(path: str, message: str) -> dict[str, str]:
    return {"severity": "error", "path": path, "message": message}
