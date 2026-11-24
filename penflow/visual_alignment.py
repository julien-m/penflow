"""Qualify review pairs and source-linked observations for a visual alignment report."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from .png_header import inspect_png
from .schema_cache import validator_for
from .verification_files import InputReader
from .verification_json import decode_json

JsonObject = dict[str, Any]  # The versioned manifest and existing reports are JSON boundaries.
PairStatus = Literal["comparable", "incompatible", "not_observed"]
MAX_INPUT_BYTES = 64 * 1024 * 1024  # Same per-file bound as the read-only check command.
MAX_PRIORITIZED = 3
_INPUT_ERRORS = (OSError, ValueError, RuntimeError)
_RENDERED_STATUSES = {"CONFORMING", "MATERIAL_DRIFT", "MEASUREMENT_ERROR", "NOT_OBSERVED"}


@dataclass(frozen=True)
class Evidence:
    """One supplied reference with its observed availability and optional JSON value."""

    path: str
    note: str = ""
    pointer: str | None = None
    value: str | int | float | bool | None = None
    error: str | None = None
    error_detail: str = ""


@dataclass(frozen=True)
class Notice:
    """Stable report message key and contextual interpolation parameters."""

    key: str
    params: tuple[str, ...] = ()


@dataclass(frozen=True)
class MachineReport:
    """The existing machine verdict, its envelope status and complete scoped issue list."""

    source: Evidence
    status: str
    check_status: str | None
    issues: list[JsonObject]
    compared: bool


@dataclass(frozen=True)
class Pair:
    """Two purported homologous screen observations and the evidence for their comparison."""

    design: JsonObject
    runtime: JsonObject
    status: PairStatus
    notices: list[Notice]
    images: list[Evidence]
    image_hashes: dict[str, str]
    report: MachineReport | None


@dataclass(frozen=True)
class Observation:
    """A submitted observation and local evidence qualification of its recommendations."""

    finding: JsonObject
    evidence: list[Evidence]
    approval: Evidence | None
    notices: list[Notice]
    follow_up: list[Evidence] = field(default_factory=list)
    follow_up_notices: list[Notice] = field(default_factory=list)


@dataclass(frozen=True)
class Case:
    """One visual review case with baseline, optional repeat and prioritized observations."""

    title: str
    before: Pair
    after: Pair | None
    after_notices: list[Notice]
    observations: list[Observation]


def load_review(manifest: Path, evidence_root: Path | None = None) -> tuple[str, list[Case]]:
    """Load case inputs and qualify evidence within the caller-selected directory.

    Args:
        manifest: Path to the versioned review input.
        evidence_root: Optional trusted root for paths cited in the manifest.

    Returns:
        Report locale and evaluated cases in input order.

    Raises:
        ValueError: The manifest is invalid or an input changes while being read.
        OSError: The manifest or selected evidence root cannot be opened.
    """
    manifest_reader = InputReader(manifest.absolute().parent, read_limit=MAX_INPUT_BYTES)
    data = manifest_reader.object(manifest_reader.read(manifest.name))
    error = next(validator_for("visual-alignment.schema.json").iter_errors(data), None)
    if error:
        location = "/" + "/".join(map(str, error.absolute_path))
        raise ValueError(f"visual-alignment manifest {location}: invalid {error.validator}")
    reader = InputReader(evidence_root or manifest_reader.root, read_limit=MAX_INPUT_BYTES)
    if not reader.root.is_dir():
        raise ValueError("visual-alignment evidence root must be a directory")

    cases = [_evaluate_case(case, reader) for case in data["cases"]]
    reader.recheck()
    manifest_reader.recheck()
    return data.get("locale", "en"), cases


def _evaluate_case(case: JsonObject, reader: InputReader) -> Case:
    before = _evaluate_pair(case["before"], reader)
    after = _evaluate_pair(case["after"], reader) if "after" in case else None
    after_notices = _compare_rounds(before, after)
    findings = sorted(case.get("findings", []), key=lambda item: item["priority"])
    observations = [_qualify(finding, before, after_notices, reader) for finding in findings]
    return Case(case["title"], before, after, after_notices, observations)


def _evaluate_pair(pair: JsonObject, reader: InputReader) -> Pair:
    # A missing field withholds homologous comparison. Conflicting identities or
    # incompatible image/measurement inputs take precedence over absence.
    design, runtime = pair.get("design", {}), pair.get("runtime", {})
    missing: list[Notice] = []
    conflicts = []
    for key in ("screen", "state", "variant", "viewport"):
        absent = [
            side
            for side, meta in (("design", design), ("runtime", runtime))
            if key not in meta or (key != "variant" and meta[key] is None)
        ]
        missing.extend(Notice("field_missing", (side, key)) for side in absent)
        if not absent and design[key] != runtime[key]:
            conflicts.append(Notice("field_conflict", (key,)))
    if not design.get("frame"):
        missing.append(Notice("frame_missing"))
    if design.get("composite") or runtime.get("composite"):
        conflicts.append(Notice("composite"))

    images, image_hashes = _read_images(pair.get("images", {}), design, runtime, reader)
    for evidence in images:
        if evidence.error == "missing":
            if evidence.path:
                missing.append(Notice("image_file_missing", (evidence.note, evidence.path)))
            else:
                missing.append(Notice("image_missing", (evidence.note,)))
        elif evidence.error:
            conflicts.append(
                Notice(
                    "image_invalid",
                    (
                        evidence.note,
                        evidence.error,
                        evidence.path,
                        evidence.error_detail,
                    ),
                )
            )
    if "design" in image_hashes and "runtime" in image_hashes and images[0].path == images[1].path:
        conflicts.append(Notice("image_alias"))

    report, report_notice = _read_report(pair.get("report"), reader)
    if report_notice:
        missing.append(report_notice)
    if report and report.status == "MEASUREMENT_ERROR":
        conflicts.append(Notice("measurement_error"))
    elif report and not report.compared:
        missing.append(Notice("measurements_missing"))
    status: PairStatus = (
        "incompatible" if conflicts else "not_observed" if missing else "comparable"
    )
    return Pair(design, runtime, status, conflicts + missing, images, image_hashes, report)


def _read_images(
    images: JsonObject, design: JsonObject, runtime: JsonObject, reader: InputReader
) -> tuple[list[Evidence], dict[str, str]]:
    scale: float = images.get("scale", 1)
    design_size, runtime_size = design.get("viewport"), runtime.get("viewport")
    slots: tuple[tuple[str, list[int] | None], ...]
    if "side_by_side" in images:
        # Combined panels are declared design-left/runtime-right at one shared scale.
        combined = (
            [design_size[0] + runtime_size[0], design_size[1]]
            if design_size and runtime_size and design_size[1] == runtime_size[1]
            else None
        )
        slots = (("side_by_side", combined),)
    else:
        slots = (("design", design_size), ("runtime", runtime_size))
    results, hashes = [], {}
    for name, logical_size in slots:
        path = images.get(name, "")
        panel_scale = (images.get(f"{name}_scale") or scale) if name != "side_by_side" else scale
        evidence, image_hash = _read_image(path, name, logical_size, panel_scale, reader)
        results.append(evidence)
        if image_hash is not None:
            hashes[name] = image_hash
    return results, hashes


def _read_image(
    path: str, name: str, logical_size: list[int] | None, scale: float, reader: InputReader
) -> tuple[Evidence, str | None]:
    if not path:
        return Evidence(path, name, error="missing"), None
    try:
        raw = reader.read(path)
        resolved = reader.path(path)
    except FileNotFoundError:
        return Evidence(path, name, error="missing"), None
    except _INPUT_ERRORS:
        return Evidence(path, name, error="file_unreadable"), None
    inspected = inspect_png(raw)
    if inspected is None:
        return Evidence(str(resolved), name, error="invalid_png"), None
    size, raster_hash = inspected
    if logical_size and any(
        actual != math.floor(logical * scale + 0.5)
        for actual, logical in zip(size, logical_size, strict=True)
    ):
        mismatch = f"{size[0]} × {size[1]} px ≠ {logical_size[0]} × {logical_size[1]} × {scale:g}"
        return Evidence(str(resolved), name, error="image_dimensions", error_detail=mismatch), None
    image_hash = raster_hash if name == "runtime" else reader.observed[resolved]
    return Evidence(str(resolved), name), image_hash


def _read_report(
    path: str | None, reader: InputReader
) -> tuple[MachineReport | None, Notice | None]:
    if not path:
        return None, Notice("report_missing")
    try:
        data = reader.object(reader.read(path))
        report = _extract_report(data, Evidence(str(reader.path(path))))
    except _INPUT_ERRORS:
        return None, Notice("report_unavailable", (path,))
    return report, None


def _extract_report(data: JsonObject, source: Evidence) -> MachineReport:
    check_status = None
    if data.get("kind") == "penflow-check-report":
        checks = data.get("checks")
        if not isinstance(checks, list):
            raise ValueError("invalid check report checks")
        rendered = [
            entry
            for entry in checks
            if isinstance(entry, dict) and entry.get("name") == "compare-rendered"
        ]
        if len(rendered) != 1:
            raise ValueError("check report must contain one compare-rendered entry")
        entry = rendered[0]
        details = entry.get("details")
        check_status = entry.get("status")
        if check_status not in ("PASS", "FAIL", "ERROR", "NOT_RUN", "NOT_OBSERVED"):
            raise ValueError("invalid compare-rendered check status")
        if not isinstance(details, dict):
            raise ValueError("invalid compare-rendered details")
        issues = entry.get("issues")
        data = {**details, "issues": issues}
        if check_status in ("NOT_RUN", "ERROR") and "status" not in details:
            data["status"] = check_status
    issues, status, comparisons = data.get("issues"), data.get("status"), data.get("comparisons")
    if status not in (*_RENDERED_STATUSES, "NOT_RUN", "ERROR") or not isinstance(issues, list):
        raise ValueError("expected the full compare-rendered diagnostic with individual issues")
    if any(
        not isinstance(item, dict)
        or not isinstance(item.get("code"), str)
        or not isinstance(item.get("message"), str)
        or any(
            item.get(key) is not None and not isinstance(item[key], str)
            for key in ("outcome", "severity", "semantic_id")
        )
        for item in issues
    ):
        raise ValueError("invalid compare-rendered issue")
    compared = (
        status in ("CONFORMING", "MATERIAL_DRIFT")
        and _observed_comparison(comparisons)
        and check_status not in ("ERROR", "NOT_RUN", "NOT_OBSERVED")
    )
    return MachineReport(source, status, check_status, issues, compared)


def _observed_comparison(comparisons: object) -> bool:
    if not isinstance(comparisons, list) or len(comparisons) != 1:
        return False  # The manifest selects one design frame per case.
    comparison = comparisons[0]
    if not isinstance(comparison, dict) or comparison.get("status") not in ("PASS", "FAIL"):
        return False
    summary = comparison.get("summary")
    if not isinstance(summary, dict):
        return False
    checks = summary.get("checks")
    return type(checks) is int and checks > 0 and isinstance(comparison.get("issues"), list)


def _compare_rounds(before: Pair, after: Pair | None) -> list[Notice]:
    if after is None:
        return [Notice("after_missing")]
    if before.status != "comparable" or after.status != "comparable":
        return [Notice("after_unqualified")]
    if any(
        before.design.get(key) != after.design.get(key)
        for key in ("frame", "screen", "state", "variant", "viewport")
    ):
        return [Notice("after_scope_conflict")]
    # A combined panel cannot show which half has changed.
    if "runtime" not in before.image_hashes or "runtime" not in after.image_hashes:
        return [Notice("after_split_required")]
    if before.image_hashes.get("design") != after.image_hashes.get("design"):
        return [Notice("after_design_changed")]
    if before.image_hashes["runtime"] == after.image_hashes["runtime"]:
        return [Notice("after_image_reused")]
    return []


def _qualify(
    finding: JsonObject, before: Pair, after_notices: list[Notice], reader: InputReader
) -> Observation:
    evidence = [_read_citation(reference, reader) for reference in finding.get("evidence", [])]
    approval = _read_citation(finding["approval"], reader) if "approval" in finding else None
    basis, action = finding["basis"], finding["action"]
    notices = []
    if action == "product_fix" and before.status != "comparable":
        notices.append(Notice("product_pair_unqualified"))
    if action == "product_fix" and basis not in ("measurement", "visual"):
        notices.append(Notice("product_observation_missing"))
    if action == "approved_divergence" and (approval is None or approval.error):
        notices.append(Notice("approval_missing"))
    if basis != "missing_observation" and (not evidence or any(item.error for item in evidence)):
        notices.append(Notice("evidence_missing"))
    if basis == "measurement" and not any(type(item.value) in (int, float) for item in evidence):
        notices.append(Notice("measurement_citation_missing"))
    if basis == "visual" and (not before.image_hashes or any(item.error for item in before.images)):
        notices.append(Notice("visual_citation_missing"))
    follow_up, follow_up_notices = [], []
    if "follow_up" in finding:
        follow_up = [
            _read_citation(citation, reader) for citation in finding["follow_up"]["evidence"]
        ]
        follow_up_notices = list(after_notices)
        if any(item.error for item in follow_up):
            follow_up_notices.append(Notice("evidence_missing"))
    return Observation(finding, evidence, approval, notices, follow_up, follow_up_notices)


def _read_citation(citation: JsonObject, reader: InputReader) -> Evidence:
    path, note, pointer = citation["path"], citation["note"], citation.get("pointer")
    try:
        raw = reader.read(path)
        if not raw:
            raise ValueError("empty evidence file")
        value = _pointer_value(raw, pointer) if pointer is not None else None
        return Evidence(str(reader.path(path)), note, pointer, value)
    except (KeyError, IndexError, ValueError):
        error = "pointer_unavailable" if pointer is not None else "file_unreadable"
        return Evidence(path, note, pointer, error=error)
    except (OSError, RuntimeError):
        return Evidence(path, note, pointer, error="file_unreadable")


def _pointer_value(raw: bytes, pointer: str) -> str | int | float | bool | None:
    value = decode_json(raw)
    # Use exact RFC 6901 tokens. Array indexes cannot use negative or padded offsets.
    for token in pointer.split("/")[1:]:
        key = token.replace("~1", "/").replace("~0", "~")
        if isinstance(value, dict) and key in value:
            value = value[key]
        elif (
            isinstance(value, list)
            and key.isascii()
            and key.isdecimal()
            and (key == "0" or not key.startswith("0"))
            and len(key) <= len(str(len(value)))
        ):
            value = value[int(key)]
        else:
            raise ValueError(f"JSON pointer does not resolve: {pointer}")
    return value if isinstance(value, str | int | float | bool) else None
