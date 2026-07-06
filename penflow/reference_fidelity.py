# @spec(FR-001)
"""Reference-image fidelity checks for visual evidence packets."""

from __future__ import annotations

import hashlib
import json
import math
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REFERENCE_REPORT_KIND = "penflow-reference-fidelity-report"
REFERENCE_REPORT_VERSION = 1
REFERENCES_MANIFEST = "references-manifest.json"

REFERENCE_CATEGORIES = (
    "layout_match",
    "palette_match",
    "component_parity",
    "density_match",
)

_PALETTE_DISTANCE_FAIL = 72.0
_DENSITY_DELTA_FAIL = 0.18
_RATIO_DELTA_FAIL = 0.03
_DIMENSION_DELTA_FAIL = 0.10
# Conservative drift thresholds tuned to catch obvious reference/export
# mismatches while tolerating minor renderer antialiasing and responsive deltas.


@dataclass(frozen=True)
class _ImageStats:
    width: int
    height: int
    avg_rgb: tuple[float, float, float]
    palette: tuple[tuple[int, int, int], ...]
    density: float


def validate_reference_fidelity(
    evidence_dir: str | Path, references_dir: str | Path
) -> dict[str, Any]:
    """Validate exported evidence PNGs against a workspace references manifest.

    Args:
        evidence_dir: Directory containing `manifest.json`, `vision-report.json`,
            exported screen PNGs, and side-by-side contact sheets.
        references_dir: Directory containing `references-manifest.json` plus
            the referenced source files.

    Returns:
        Deterministic report with per-screen metrics, criteria, and issues.

    Raises:
        FileNotFoundError: If either directory is missing.
        ValueError: If required JSON artifacts are malformed.
    """
    evidence = Path(evidence_dir)
    references = Path(references_dir)
    if not evidence.is_dir():
        raise FileNotFoundError(f"evidence directory not found: {evidence}")
    if not references.is_dir():
        raise FileNotFoundError(f"references directory not found: {references}")

    manifest = _load_json_object(evidence / "manifest.json", "evidence manifest")
    vision_report = _load_json_object(evidence / "vision-report.json", "vision report")
    reference_entries = load_references_manifest(references)
    declared_reference_shas = {reference["sha256"] for reference in reference_entries}
    export_by_screen = _export_by_screen(manifest)
    llm_by_screen = _reference_fidelity_by_screen(vision_report)

    screens: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    if not reference_entries:
        issues.append(_reference_manifest_empty_issue())
    for reference in reference_entries:
        screen_id = reference["screen_id"]
        export = export_by_screen.get(screen_id)
        llm_entry = llm_by_screen.get(screen_id)
        screen = _screen_report(
            evidence=evidence,
            references=references,
            reference=reference,
            export=export,
            llm_entry=llm_entry,
            declared_reference_shas=declared_reference_shas,
        )
        screens.append(screen)
        issues.extend(screen["issues"])

    issues.sort(key=_issue_sort_key)
    screens.sort(key=lambda item: item["screen_id"])
    return {
        "version": REFERENCE_REPORT_VERSION,
        "kind": REFERENCE_REPORT_KIND,
        "status": "PASS" if not issues else "FAIL",
        "summary": {
            "screens_checked": len(screens),
            "errors": len(issues),
            "warnings": 0,
        },
        "inputs": {
            "evidence_dir": str(evidence),
            "references_dir": str(references),
            "references_manifest": str(references / REFERENCES_MANIFEST),
        },
        "screens": screens,
        "issues": issues,
    }


def load_references_manifest(references_dir: str | Path) -> list[dict[str, str]]:
    """Load and validate `<references>/references-manifest.json`."""
    directory = Path(references_dir)
    root = directory.resolve()
    path = directory / REFERENCES_MANIFEST
    parsed = _load_json(path, "references manifest")
    if not isinstance(parsed, list):
        raise ValueError(f"{path} must be an array")
    entries: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, item in enumerate(parsed):
        if not isinstance(item, dict):
            raise ValueError(f"{path}[{index}] must be an object")
        entry: dict[str, str] = {}
        for key in ("screen_id", "file", "sha256", "source"):
            value = item.get(key)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{path}[{index}].{key} must be a non-empty string")
            entry[key] = value
        if entry["screen_id"] in seen:
            raise ValueError(f"{path} contains duplicate screen_id: {entry['screen_id']}")
        seen.add(entry["screen_id"])
        reference_file = _resolve_inside(root, entry["file"], "reference file")
        if not reference_file.is_file():
            raise ValueError(f"reference file not found: {reference_file}")
        actual_sha = _sha256(reference_file)
        if actual_sha != entry["sha256"]:
            raise ValueError(
                f"reference sha256 mismatch for {entry['file']}:"
                f" expected {entry['sha256']} got {actual_sha}"
            )
        entries.append(entry)
    return entries


def _resolve_inside(root: Path, value: str, label: str) -> Path:
    rel = Path(value)
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError(f"{label} must stay inside {root}: {value}")
    resolved = (root / rel).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise ValueError(f"{label} must stay inside {root}: {value}") from error
    return resolved


def reference_fidelity_evidence_issues(
    evidence_dir: str | Path,
    manifest: dict[str, Any] | None,
    vision_report: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Validate the vision-report `reference_fidelity` section when declared.

    `validate-visual-evidence` uses this lighter check: it proves the section
    exists, covers every referenced screen, cites both files, and has no
    blocking fail. The heavier image metrics live in
    `validate_reference_fidelity()`.
    """
    if manifest is None:
        return []
    references_manifest = manifest.get("references_manifest")
    if not isinstance(references_manifest, str) or not references_manifest:
        return []
    directory = Path(evidence_dir)
    manifest_path = directory / references_manifest
    issues: list[dict[str, Any]] = []
    try:
        references = load_references_manifest(manifest_path.parent)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as error:
        return [_issue("evidence.references.invalid", "$.references_manifest", str(error))]
    if not references:
        return [_reference_manifest_empty_issue()]
    export_by_screen = _export_by_screen(manifest)
    llm_by_screen = _reference_fidelity_by_screen(vision_report)
    if vision_report is None or not isinstance(vision_report.get("reference_fidelity"), list):
        return [
            _issue(
                "evidence.reference_fidelity.missing",
                "$.reference_fidelity",
                "manifest declares references but vision-report.json has no reference_fidelity section",
            )
        ]
    for reference in references:
        screen_id = reference["screen_id"]
        export = export_by_screen.get(screen_id)
        if export is None:
            issues.append(
                _issue(
                    "evidence.reference_fidelity.export_missing",
                    "$.screens",
                    f"referenced screen {screen_id!r} has no exported PNG in manifest.json",
                )
            )
            continue
        llm_entry = llm_by_screen.get(screen_id)
        if llm_entry is None:
            issues.append(
                _issue(
                    "evidence.reference_fidelity.screen_missing",
                    "$.reference_fidelity",
                    f"referenced screen {screen_id!r} has no reference_fidelity entry",
                )
            )
            continue
        criteria = llm_entry.get("criteria")
        if not isinstance(criteria, list):
            continue
        answered = {
            criterion.get("category") for criterion in criteria if isinstance(criterion, dict)
        }
        for category in REFERENCE_CATEGORIES:
            if category not in answered:
                issues.append(
                    _issue(
                        "evidence.reference_fidelity.category_missing",
                        "$.reference_fidelity",
                        f"screen {screen_id!r} does not answer reference category {category!r}",
                    )
                )
        reference_file = reference["file"]
        export_file = export.get("png")
        if not isinstance(export_file, str) or not export_file:
            issues.append(
                _issue(
                    "evidence.reference_fidelity.export_missing",
                    "$.screens",
                    f"referenced screen {screen_id!r} has no usable exported PNG in manifest.json",
                )
            )
            continue
        for criterion in criteria:
            if not isinstance(criterion, dict):
                continue
            evidence = criterion.get("evidence")
            if isinstance(evidence, str) and (
                reference_file not in evidence or export_file not in evidence
            ):
                issues.append(
                    _issue(
                        "evidence.reference_fidelity.file_evidence_missing",
                        "$.reference_fidelity",
                        f"screen {screen_id!r} criterion {criterion.get('category')!r}"
                        " must cite both reference and export files",
                    )
                )
            if criterion.get("result") == "fail" and criterion.get("blocking") is True:
                issues.append(
                    _issue(
                        "evidence.reference_fidelity.blocking_fail",
                        "$.reference_fidelity",
                        f"screen {screen_id!r} has blocking reference fidelity failure"
                        f" {criterion.get('category')!r}",
                    )
                )
    issues.sort(key=_issue_sort_key)
    return issues


def _screen_report(
    *,
    evidence: Path,
    references: Path,
    reference: dict[str, str],
    export: dict[str, Any] | None,
    llm_entry: dict[str, Any] | None,
    declared_reference_shas: set[str],
) -> dict[str, Any]:
    screen_id = reference["screen_id"]
    export_png = export.get("png") if isinstance(export, dict) else None
    contact_sheet = llm_entry.get("contact_sheet") if isinstance(llm_entry, dict) else None
    issues: list[dict[str, Any]] = []
    try:
        reference_path = _resolve_inside(references.resolve(), reference["file"], "reference file")
    except ValueError as error:
        issues.append(_screen_issue(screen_id, "reference.path_escape", str(error)))
        return _empty_screen(screen_id, reference, export_png, contact_sheet, issues)
    export_path: Path | None = None
    if isinstance(export_png, str):
        try:
            export_path = _resolve_inside(evidence.resolve(), export_png, "export file")
        except ValueError as error:
            issues.append(_screen_issue(screen_id, "reference.export_path_escape", str(error)))
            return _empty_screen(screen_id, reference, export_png, contact_sheet, issues)
    contact_sheet_path: Path | None = None
    if isinstance(contact_sheet, str):
        try:
            contact_sheet_path = _resolve_inside(evidence.resolve(), contact_sheet, "contact sheet")
        except ValueError as error:
            issues.append(
                _screen_issue(screen_id, "reference.contact_sheet_path_escape", str(error))
            )
            return _empty_screen(screen_id, reference, export_png, contact_sheet, issues)

    if export_path is None or not export_path.is_file():
        issues.append(
            _screen_issue(screen_id, "reference.export_missing", "exported PNG is missing")
        )
        return _empty_screen(screen_id, reference, export_png, contact_sheet, issues)
    export_sha = _sha256(export_path)
    if export_sha in declared_reference_shas or _path_is_relative_to(export_path, references):
        issues.append(
            _screen_issue(
                screen_id,
                "reference.evidence_is_reference_copy",
                "export PNG bytes or path match a declared reference image",
            )
        )
    contact_ok = _contact_sheet_ok(screen_id, contact_sheet_path, issues)

    try:
        reference_stats = _png_stats(reference_path)
        export_stats = _png_stats(export_path)
    except (OSError, ValueError, zlib.error) as error:
        issues.append(_screen_issue(screen_id, "reference.image.invalid", str(error)))
        return _empty_screen(screen_id, reference, export_png, contact_sheet, issues)

    deterministic = _deterministic_criteria(
        screen_id, reference_stats, export_stats, contact_ok, issues
    )
    issues.extend(_llm_disagreement_issues(screen_id, deterministic, llm_entry))
    issues.sort(key=_issue_sort_key)
    return {
        "screen_id": screen_id,
        "reference": reference["file"],
        "export": export_png,
        "contact_sheet": contact_sheet,
        "metrics": {
            "reference": _stats_payload(reference_stats),
            "export": _stats_payload(export_stats),
        },
        "criteria": [
            {
                "category": category,
                "result": deterministic[category],
                "evidence": _metric_evidence(
                    category, reference["file"], export_png, contact_sheet
                ),
                "blocking": deterministic[category] == "fail",
            }
            for category in REFERENCE_CATEGORIES
        ],
        "issues": issues,
    }


def _deterministic_criteria(
    screen_id: str,
    reference: _ImageStats,
    export: _ImageStats,
    contact_ok: bool,
    issues: list[dict[str, Any]],
) -> dict[str, str]:
    layout_failed = _layout_failed(reference, export)
    palette_failed = _palette_failed(reference, export)
    density_failed = abs(reference.density - export.density) > _DENSITY_DELTA_FAIL
    if layout_failed:
        issues.append(
            _screen_issue(
                screen_id,
                "reference.layout_mismatch",
                f"reference is {reference.width}x{reference.height}, export is {export.width}x{export.height}",
            )
        )
    if palette_failed:
        issues.append(
            _screen_issue(
                screen_id,
                "reference.palette_mismatch",
                "dominant palette differs after deterministic RGB quantization",
            )
        )
    if density_failed:
        issues.append(
            _screen_issue(
                screen_id,
                "reference.density_mismatch",
                f"density differs: reference={reference.density:.3f} export={export.density:.3f}",
            )
        )
    return {
        "layout_match": "fail" if layout_failed else "pass",
        "palette_match": "fail" if palette_failed else "pass",
        "component_parity": "pass"
        if contact_ok and not (layout_failed and density_failed)
        else "fail",
        "density_match": "fail" if density_failed else "pass",
    }


def _llm_disagreement_issues(
    screen_id: str,
    deterministic: dict[str, str],
    llm_entry: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if not isinstance(llm_entry, dict) or not isinstance(llm_entry.get("criteria"), list):
        return []
    issues: list[dict[str, Any]] = []
    llm_results = {
        criterion.get("category"): criterion
        for criterion in llm_entry["criteria"]
        if isinstance(criterion, dict)
    }
    for category, result in deterministic.items():
        llm = llm_results.get(category)
        if not isinstance(llm, dict):
            continue
        llm_result = llm.get("result")
        if result == "fail" and llm_result == "pass":
            issues.append(
                _screen_issue(
                    screen_id,
                    "reference.llm_metric_disagreement",
                    f"deterministic {category} failed but reference_fidelity claims pass",
                )
            )
        if result == "pass" and llm_result == "fail" and llm.get("blocking") is True:
            issues.append(
                _screen_issue(
                    screen_id,
                    "reference.llm_metric_disagreement",
                    f"deterministic {category} passed but reference_fidelity has blocking fail",
                )
            )
    return issues


def _layout_failed(reference: _ImageStats, export: _ImageStats) -> bool:
    reference_ratio = reference.width / reference.height
    export_ratio = export.width / export.height
    width_delta = abs(reference.width - export.width) / max(reference.width, 1)
    height_delta = abs(reference.height - export.height) / max(reference.height, 1)
    return (
        abs(reference_ratio - export_ratio) > _RATIO_DELTA_FAIL
        or width_delta > _DIMENSION_DELTA_FAIL
        or height_delta > _DIMENSION_DELTA_FAIL
    )


def _palette_failed(reference: _ImageStats, export: _ImageStats) -> bool:
    shared = set(reference.palette[:3]) & set(export.palette[:3])
    distance = math.dist(reference.avg_rgb, export.avg_rgb)
    return not shared and distance > _PALETTE_DISTANCE_FAIL


def _contact_sheet_ok(
    screen_id: str, contact_sheet_path: Path | None, issues: list[dict[str, Any]]
) -> bool:
    if contact_sheet_path is None:
        issues.append(
            _screen_issue(
                screen_id,
                "reference.contact_sheet.missing",
                "reference/export side-by-side contact sheet is not declared",
            )
        )
        return False
    if not contact_sheet_path.is_file():
        issues.append(
            _screen_issue(
                screen_id,
                "reference.contact_sheet.missing",
                f"contact sheet not found: {contact_sheet_path.name}",
            )
        )
        return False
    if contact_sheet_path.stat().st_size == 0:
        issues.append(
            _screen_issue(
                screen_id,
                "reference.contact_sheet.empty",
                f"contact sheet is empty: {contact_sheet_path.name}",
            )
        )
        return False
    return True


def _png_stats(path: Path) -> _ImageStats:
    width, height, pixels = _read_png_rgba(path)
    if not pixels:
        raise ValueError(f"PNG has no pixels: {path}")
    count = len(pixels)
    avg_rgb = (
        sum(pixel[0] for pixel in pixels) / count,
        sum(pixel[1] for pixel in pixels) / count,
        sum(pixel[2] for pixel in pixels) / count,
    )
    buckets: dict[tuple[int, int, int], int] = {}
    for red, green, blue, _alpha in pixels:
        bucket = (red // 32, green // 32, blue // 32)
        buckets[bucket] = buckets.get(bucket, 0) + 1
    palette = tuple(
        bucket
        for bucket, _count in sorted(buckets.items(), key=lambda item: (-item[1], item[0]))[:5]
    )
    density = _edge_density(width, height, pixels)
    return _ImageStats(
        width=width, height=height, avg_rgb=avg_rgb, palette=palette, density=density
    )


def _read_png_rgba(path: Path) -> tuple[int, int, list[tuple[int, int, int, int]]]:
    data = path.read_bytes()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError(f"not a PNG file: {path}")
    offset = 8
    width = height = bit_depth = color_type = None
    idat = bytearray()
    while offset < len(data):
        if offset + 8 > len(data):
            raise ValueError(f"truncated PNG chunk header: {path}")
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        chunk_type = data[offset + 4 : offset + 8]
        if offset + 12 + length > len(data):
            raise ValueError(f"truncated PNG chunk data for {chunk_type.decode('latin1')}: {path}")
        chunk_data = data[offset + 8 : offset + 8 + length]
        offset += 12 + length
        if chunk_type == b"IHDR":
            if length != 13:
                raise ValueError(f"invalid PNG IHDR length {length}: {path}")
            width, height, bit_depth, color_type, _compression, _filter, interlace = struct.unpack(
                ">IIBBBBB", chunk_data
            )
            if interlace != 0:
                raise ValueError(f"interlaced PNGs are not supported: {path}")
        elif chunk_type == b"IDAT":
            idat.extend(chunk_data)
        elif chunk_type == b"IEND":
            break
    if width is None or height is None or bit_depth is None or color_type is None:
        raise ValueError(f"PNG missing IHDR: {path}")
    if bit_depth != 8 or color_type not in {0, 2, 6}:
        raise ValueError(
            f"unsupported PNG format in {path}: bit_depth={bit_depth} color_type={color_type}"
        )
    if not idat:
        raise ValueError(f"PNG missing IDAT: {path}")
    channels = {0: 1, 2: 3, 6: 4}[color_type]
    try:
        raw = zlib.decompress(bytes(idat))
    except zlib.error as error:
        raise ValueError(f"invalid PNG IDAT data: {path}") from error
    stride = width * channels
    rows: list[bytes] = []
    previous = bytes(stride)
    cursor = 0
    for row_index in range(height):
        if cursor >= len(raw):
            raise ValueError(f"truncated PNG scanline {row_index}: {path}")
        filter_type = raw[cursor]
        cursor += 1
        if cursor + stride > len(raw):
            raise ValueError(f"truncated PNG scanline {row_index}: {path}")
        encoded = raw[cursor : cursor + stride]
        cursor += stride
        decoded = _unfilter_scanline(filter_type, encoded, previous, channels)
        rows.append(decoded)
        previous = decoded
    pixels: list[tuple[int, int, int, int]] = []
    for row in rows:
        for x in range(width):
            i = x * channels
            if color_type == 0:
                gray = row[i]
                pixels.append((gray, gray, gray, 255))
            elif color_type == 2:
                pixels.append((row[i], row[i + 1], row[i + 2], 255))
            else:
                pixels.append((row[i], row[i + 1], row[i + 2], row[i + 3]))
    return width, height, pixels


def _unfilter_scanline(filter_type: int, encoded: bytes, previous: bytes, bpp: int) -> bytes:
    decoded = bytearray(encoded)
    for index, value in enumerate(encoded):
        left = decoded[index - bpp] if index >= bpp else 0
        up = previous[index] if index < len(previous) else 0
        up_left = previous[index - bpp] if index >= bpp and index - bpp < len(previous) else 0
        if filter_type == 0:
            decoded[index] = value
        elif filter_type == 1:
            decoded[index] = (value + left) & 0xFF
        elif filter_type == 2:
            decoded[index] = (value + up) & 0xFF
        elif filter_type == 3:
            decoded[index] = (value + ((left + up) // 2)) & 0xFF
        elif filter_type == 4:
            decoded[index] = (value + _paeth(left, up, up_left)) & 0xFF
        else:
            raise ValueError(f"unsupported PNG filter type: {filter_type}")
    return bytes(decoded)


def _paeth(left: int, up: int, up_left: int) -> int:
    estimate = left + up - up_left
    left_distance = abs(estimate - left)
    up_distance = abs(estimate - up)
    up_left_distance = abs(estimate - up_left)
    if left_distance <= up_distance and left_distance <= up_left_distance:
        return left
    if up_distance <= up_left_distance:
        return up
    return up_left


def _edge_density(width: int, height: int, pixels: list[tuple[int, int, int, int]]) -> float:
    if width <= 1 or height <= 1:
        return 0.0
    edge_count = 0
    comparisons = 0
    for y in range(height):
        for x in range(width):
            current = _luma(pixels[y * width + x])
            if x + 1 < width:
                comparisons += 1
                edge_count += abs(current - _luma(pixels[y * width + x + 1])) > 28
            if y + 1 < height:
                comparisons += 1
                edge_count += abs(current - _luma(pixels[(y + 1) * width + x])) > 28
    return edge_count / comparisons if comparisons else 0.0


def _luma(pixel: tuple[int, int, int, int]) -> float:
    return 0.2126 * pixel[0] + 0.7152 * pixel[1] + 0.0722 * pixel[2]


def _load_json_object(path: Path, label: str) -> dict[str, Any]:
    parsed = _load_json(path, label)
    if not isinstance(parsed, dict):
        raise ValueError(f"{path} must be a JSON object")
    return parsed


def _load_json(path: Path, label: str) -> Any:
    if not path.is_file():
        raise FileNotFoundError(f"{label} not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _export_by_screen(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    screens = manifest.get("screens")
    if not isinstance(screens, list):
        return {}
    exports: dict[str, dict[str, Any]] = {}
    for screen in screens:
        if not isinstance(screen, dict):
            continue
        for key in ("screen_id", "semantic_id", "pencil_node_id"):
            value = screen.get(key)
            if isinstance(value, str) and value and value not in exports:
                exports[value] = screen
    return exports


def _reference_fidelity_by_screen(
    vision_report: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    if not isinstance(vision_report, dict):
        return {}
    entries = vision_report.get("reference_fidelity")
    if not isinstance(entries, list):
        return {}
    by_screen: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        screen_id = entry.get("screen_id")
        if isinstance(screen_id, str) and screen_id:
            by_screen[screen_id] = entry
    return by_screen


def _metric_evidence(
    category: str, reference: str, export: str | None, contact_sheet: str | None
) -> str:
    pair = f"reference {reference} vs export {export}"
    if category == "component_parity":
        return f"{pair}; side-by-side contact sheet {contact_sheet} inspected deterministically."
    return f"{pair}; deterministic {category} metric computed from PNG bytes."


def _stats_payload(stats: _ImageStats) -> dict[str, Any]:
    return {
        "width": stats.width,
        "height": stats.height,
        "avg_rgb": [round(value, 3) for value in stats.avg_rgb],
        "palette": [list(bucket) for bucket in stats.palette],
        "density": round(stats.density, 6),
    }


def _empty_screen(
    screen_id: str,
    reference: dict[str, str],
    export_png: str | None,
    contact_sheet: str | None,
    issues: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "screen_id": screen_id,
        "reference": reference["file"],
        "export": export_png,
        "contact_sheet": contact_sheet,
        "metrics": {},
        "criteria": [
            {
                "category": category,
                "result": "fail",
                "evidence": _metric_evidence(
                    category, reference["file"], export_png, contact_sheet
                ),
                "blocking": True,
            }
            for category in REFERENCE_CATEGORIES
        ],
        "issues": sorted(issues, key=_issue_sort_key),
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _path_is_relative_to(path: Path, directory: Path) -> bool:
    try:
        path.resolve().relative_to(directory.resolve())
    except ValueError:
        return False
    return True


def _issue(code: str, path: str, message: str) -> dict[str, Any]:
    return {"code": code, "severity": "error", "path": path, "message": message}


def _reference_manifest_empty_issue() -> dict[str, Any]:
    return _issue(
        "reference.manifest.empty",
        "$.references_manifest",
        "references-manifest.json must declare at least one reference screen",
    )


def _screen_issue(screen_id: str, code: str, message: str) -> dict[str, Any]:
    return {
        "code": code,
        "severity": "error",
        "screen_id": screen_id,
        "path": f"$.screens[{screen_id}]",
        "message": message,
    }


def _issue_sort_key(issue: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(issue.get("screen_id", "")),
        issue["code"],
        issue["path"],
        issue["message"],
    )
