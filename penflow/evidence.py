# @spec(FR-002)
# @spec(FR-003)
"""Deterministic visual-evidence packet validator.

Penflow NEVER runs vision, Pencil, or any renderer. The vision pass lives at
the skill layer (mockup-factory); this module only proves — from local files —
that the pass happened in a structured, complete, non-overlapping way:
the manifest validates, every screen PNG exists non-empty, the vision report
validates against the locked vision-only category enum, every expected-tree
screen is covered, an optional layout snapshot matches the expected
root bboxes within tolerance, — for multi-screen expected trees — a
cross-mockup coherence pass over one contact sheet answered the four locked
coherence categories with a non-empty contact-sheet PNG on disk, and — when
the gate is armed with a current theme fingerprint — the manifest theme
stamp matches the theme.css bytes the mockups were rendered against.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, TypeGuard, cast

from .reference_fidelity import reference_fidelity_evidence_issues
from .schema_cache import validator_for
from .tree import load_tree

VISION_REPORT_KIND = "penflow-vision-report"
VISION_REPORT_VERSION = 1

# The locked vision-only categories (C26). Deterministic ground — contrast,
# touch targets, overlap/overflow, tokens, consistency — belongs to
# audit-visual / lint-tokens / check-consistency (features 046/047/050) and is
# rejected by the vision-report schema enum.
VISION_CATEGORIES = (
    "visual_balance",
    "rendering_artifacts",
    "readability",
    "perceived_hierarchy",
    "imagery_quality",
)

# The locked cross-mockup coherence categories (C28). Numeric cross-screen
# ground — signature property divergence — belongs to check-consistency
# (feature 047) and is rejected by the coherence schema enum.
COHERENCE_CATEGORIES = (
    "cross_screen_rhythm",
    "palette_coherence",
    "typography_coherence",
    "component_recognition",
)

# Rendering-evidence tolerance for the layout snapshot cross-check; looser
# than compare-tree runtime tolerances because Pencil export rounding is not
# runtime drift.
SNAPSHOT_TOLERANCE_PX = 4.0

MANIFEST_FILENAME = "manifest.json"
VISION_REPORT_FILENAME = "vision-report.json"
LAYOUT_SNAPSHOT_FILENAME = "layout-snapshot.json"

_MANIFEST_SCHEMA = "mockup-validation-manifest.schema.json"
_VISION_REPORT_SCHEMA = "vision-report.schema.json"

RUN_IDENTITY_VERSION = 1
LINEAGE_DIGEST_KEYS = (
    "ui.pen",
    "contract",
    "expected",
    "actual",
    "theme",
    "references",
    "renderer",
    "exportTimestamp",
)
OPTIONAL_LINEAGE_STATE = "not-provided"


# @spec(FR-009)
# @spec(FR-010)
# @spec(FR-013)
def build_run_identity(
    *,
    ui_pen: str | Path,
    contract: str | Path,
    expected: str | Path,
    actual: str | Path,
    theme: str | Path | None,
    references: str | Path | None,
    renderer: str | None,
    export_timestamp: str | None,
) -> dict[str, Any]:
    """Build one deterministic versioned identity for a Penflow run.

    Required file sources are hashed byte-for-byte. An absent required source
    receives a source-specific absence digest and is listed in
    ``lineage.missing``. Optional theme and reference inputs use a canonical
    ``not-provided`` receipt when the corresponding gate is not armed; an
    explicitly provided but unreadable path still fails closed. Renderer and
    export time are canonical UTF-8 value receipts rather than filesystem
    inputs.
    """
    required_file_sources: dict[str, str | Path] = {
        "ui.pen": ui_pen,
        "contract": contract,
        "expected": expected,
        "actual": actual,
    }
    missing: list[str] = []
    digests: dict[str, str] = {}
    for key, source in required_file_sources.items():
        digest, present = _lineage_file_digest(key, source)
        digests[key] = digest
        if not present:
            missing.append(key)
    for key, optional_source in (("theme", theme), ("references", references)):
        if optional_source is None:
            digests[key] = _lineage_value_digest(key, OPTIONAL_LINEAGE_STATE)
            continue
        digest, present = _lineage_file_digest(key, optional_source)
        digests[key] = digest
        if not present:
            missing.append(key)
    for key, value in (
        ("renderer", renderer),
        ("exportTimestamp", export_timestamp),
    ):
        digests[key] = _lineage_value_digest(key, value)
        if value is None:
            missing.append(key)
    lineage_payload = {
        "version": RUN_IDENTITY_VERSION,
        "digests": digests,
        "missing": missing,
    }
    lineage_sha = _canonical_sha256(lineage_payload)
    lineage = lineage_payload | {"sha256": lineage_sha}
    return {
        "runId": f"penflow-v{RUN_IDENTITY_VERSION}-{lineage_sha[:24]}",
        "version": RUN_IDENTITY_VERSION,
        "lineage": lineage,
        "provenance": {
            "renderer": renderer,
            "exportTimestamp": export_timestamp,
        },
    }


# @spec(FR-012)
def validate_run_identity(
    candidate: dict[str, Any] | None,
    expected: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return fail-closed issues when a run or gate identity diverges."""
    if not isinstance(candidate, dict):
        return [
            _issue(
                "evidence.lineage.missing",
                "$",
                "run identity must be an object",
            )
        ]

    issues: list[dict[str, Any]] = []
    for key in ("runId", "version"):
        if candidate.get(key) != expected.get(key):
            issues.append(
                _issue(
                    "evidence.lineage.identity_mismatch",
                    f"$.{key}",
                    f"{key} does not match the canonical run identity",
                )
            )

    if candidate.get("provenance") != expected.get("provenance"):
        issues.append(
            _issue(
                "evidence.lineage.provenance_mismatch",
                "$.provenance",
                "renderer or export timestamp does not match the current run provenance",
            )
        )

    candidate_lineage = candidate.get("lineage")
    expected_lineage = expected.get("lineage")
    if not isinstance(candidate_lineage, dict) or not isinstance(expected_lineage, dict):
        issues.append(
            _issue(
                "evidence.lineage.missing",
                "$.lineage",
                "lineage must be an object",
            )
        )
        issues.sort(key=_issue_sort_key)
        return issues

    if candidate_lineage.get("version") != RUN_IDENTITY_VERSION:
        issues.append(
            _issue(
                "evidence.lineage.version_mismatch",
                "$.lineage.version",
                f"lineage version must be {RUN_IDENTITY_VERSION}",
            )
        )

    candidate_digests = candidate_lineage.get("digests")
    expected_digests = expected_lineage.get("digests")
    if not isinstance(candidate_digests, dict) or not isinstance(expected_digests, dict):
        issues.append(
            _issue(
                "evidence.lineage.digests_missing",
                "$.lineage.digests",
                "lineage digests must be an object",
            )
        )
    else:
        for key in LINEAGE_DIGEST_KEYS:
            if candidate_digests.get(key) != expected_digests.get(key):
                issues.append(
                    _issue(
                        "evidence.lineage.digest_mismatch",
                        f"$.lineage.digests.{key}",
                        f"{key} digest does not match the canonical run lineage",
                    )
                )
        unexpected = sorted(set(candidate_digests) - set(LINEAGE_DIGEST_KEYS))
        for key in unexpected:
            issues.append(
                _issue(
                    "evidence.lineage.digest_unexpected",
                    f"$.lineage.digests.{key}",
                    f"unexpected lineage digest: {key}",
                )
            )
        candidate_payload = {
            "version": candidate_lineage.get("version"),
            "digests": candidate_digests,
            "missing": candidate_lineage.get("missing"),
        }
        if candidate_lineage.get("sha256") != _canonical_sha256(candidate_payload):
            issues.append(
                _issue(
                    "evidence.lineage.sha_mismatch",
                    "$.lineage.sha256",
                    "lineage sha256 does not match its canonical payload",
                )
            )
    candidate_missing = candidate_lineage.get("missing")
    expected_missing = expected_lineage.get("missing")
    if candidate_missing != expected_missing:
        issues.append(
            _issue(
                "evidence.lineage.missing_mismatch",
                "$.lineage.missing",
                "missing lineage sources do not match the canonical run lineage",
            )
        )
    if isinstance(candidate_missing, list):
        for key in candidate_missing:
            issues.append(
                _issue(
                    "evidence.lineage.source_missing",
                    f"$.lineage.digests.{key}",
                    f"lineage source is missing: {key}",
                )
            )
    else:
        issues.append(
            _issue(
                "evidence.lineage.missing_invalid",
                "$.lineage.missing",
                "lineage missing must be an array",
            )
        )
    if candidate_lineage.get("sha256") != expected_lineage.get("sha256"):
        issues.append(
            _issue(
                "evidence.lineage.sha_mismatch",
                "$.lineage.sha256",
                "lineage sha256 does not match the canonical run lineage",
            )
        )
    issues.sort(key=_issue_sort_key)
    return issues


def validate_visual_evidence(
    evidence_dir: str | Path,
    *,
    expected_tree_path: str | Path | None = None,
    theme_fingerprint: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    # @spec FR-002: Deterministic evidence packet validation — .specs/features/051-vision-report-contract-evidence-validator/spec.md#fr-002
    """Validate a `.mockup-validation/visual-evidence/` packet deterministically.

    Args:
        evidence_dir: Directory containing `manifest.json`, screen PNGs,
            `vision-report.json`, and optionally `layout-snapshot.json`.
        expected_tree_path: Optional `expected-ui-tree.json` (feature 006
            shape) enabling screen-coverage and snapshot bbox cross-checks.
        theme_fingerprint: Optional current `{path, sha256}` fingerprint of
            the project theme.css (`penflow.theme.theme_fingerprint`). When
            provided, the manifest must carry a matching `theme.sha256` stamp
            (`evidence.theme.missing` / `evidence.theme.stale` otherwise);
            when ``None`` the theme check never runs and output is identical
            to pre-056 behavior.

    Returns:
        A deterministically sorted list of issues, each
        ``{code, severity, path, message}``. All evidence issues are
        ``error`` severity: a packet is either provably complete or it fails.

    Raises:
        FileNotFoundError: If ``evidence_dir`` is not a directory.
        ValueError: If the expected tree is malformed (fail closed, exit 2 at
            the CLI layer).
    """
    directory = Path(evidence_dir)
    if not directory.is_dir():
        raise FileNotFoundError(f"evidence directory not found: {directory}")
    expected_screens: list[dict[str, Any]] = []
    if expected_tree_path is not None:
        expected_screens = _load_expected_screens(expected_tree_path)

    issues: list[dict[str, Any]] = []
    manifest = _load_artifact(
        directory / MANIFEST_FILENAME, "evidence.manifest", _MANIFEST_SCHEMA, issues
    )
    vision_report = _load_artifact(
        directory / VISION_REPORT_FILENAME, "evidence.vision_report", _VISION_REPORT_SCHEMA, issues
    )
    issues.extend(_png_issues(directory, manifest))
    issues.extend(_vision_receipt_issues(directory, vision_report))
    issues.extend(_vision_manifest_screen_issues(manifest, vision_report))
    issues.extend(_structured_criteria_issues(manifest, vision_report))
    issues.extend(_theme_issues(manifest, theme_fingerprint))
    issues.extend(_category_issues(vision_report))
    issues.extend(_coherence_issues(directory, vision_report, expected_screens))
    issues.extend(reference_fidelity_evidence_issues(directory, manifest, vision_report))
    if expected_tree_path is not None:
        issues.extend(_coverage_issues(expected_screens, manifest, MANIFEST_FILENAME))
        issues.extend(_coverage_issues(expected_screens, vision_report, VISION_REPORT_FILENAME))
    issues.extend(_snapshot_issues(directory, expected_screens))
    issues.sort(key=_issue_sort_key)
    return issues


def _load_expected_screens(expected_tree_path: str | Path) -> list[dict[str, Any]]:
    tree = load_tree(expected_tree_path)
    if not isinstance(tree, dict) or not isinstance(tree.get("screens"), list):
        raise TypeError(
            f"expected tree must be an object with a screens list: {expected_tree_path}"
        )
    screens: list[dict[str, Any]] = []
    for index, screen in enumerate(tree["screens"]):
        if not isinstance(screen, dict):
            raise TypeError(f"screens[{index}] must be an object: {expected_tree_path}")
        screens.append(screen)
    return screens


def _load_artifact(
    path: Path,
    code_prefix: str,
    schema_name: str,
    issues: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Load and schema-validate one JSON artifact, appending issues in place.

    Returns the parsed object when it is a JSON object (even if schema
    violations were recorded), so downstream structural checks can still run.
    """
    if not path.is_file():
        issues.append(
            _issue(f"{code_prefix}.missing", "$", f"{path.name} not found in evidence directory")
        )
        return None
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        issues.append(
            _issue(f"{code_prefix}.invalid", "$", f"{path.name} is not valid JSON: {error}")
        )
        return None
    if not isinstance(parsed, dict):
        issues.append(_issue(f"{code_prefix}.invalid", "$", f"{path.name} must be a JSON object"))
        return None
    issues.extend(_schema_issues(parsed, schema_name, f"{code_prefix}.invalid", path.name))
    return parsed


def _schema_issues(
    value: dict[str, Any], schema_name: str, code: str, artifact: str
) -> list[dict[str, Any]]:
    # @spec FR-001: Locked vision-report schema enforcement — .specs/features/051-vision-report-contract-evidence-validator/spec.md#fr-001
    validator = validator_for(schema_name)
    formatted = [
        _issue(code, _json_path(error.absolute_path), f"{artifact}: {error.message}")
        for error in validator.iter_errors(value)
    ]
    formatted.sort(key=lambda item: (item["path"], item["message"]))
    return formatted


def _json_path(absolute_path: Any) -> str:
    return "$" + "".join(
        f".{part}" if isinstance(part, str) else f"[{part}]" for part in absolute_path
    )


def _png_issues(directory: Path, manifest: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Every manifest screen PNG must be inside the evidence dir and match its receipt."""
    if manifest is None or not isinstance(manifest.get("screens"), list):
        return []
    issues: list[dict[str, Any]] = []
    for index, screen in enumerate(manifest["screens"]):
        if not isinstance(screen, dict):
            continue
        png = screen.get("png")
        if not isinstance(png, str) or not png:
            continue  # the manifest schema already flags the malformed entry
        json_path = f"$.screens[{index}].png"
        path = _evidence_file_path(directory, png)
        if path is None:
            issues.append(
                _issue(
                    "evidence.png.outside_evidence_dir",
                    json_path,
                    f"exported PNG must resolve inside evidence directory: {png}",
                )
            )
            continue
        if not path.is_file():
            issues.append(
                _issue("evidence.png.missing", json_path, f"exported PNG not found: {png}")
            )
        elif path.stat().st_size == 0:
            issues.append(_issue("evidence.png.empty", json_path, f"exported PNG is empty: {png}"))
        else:
            expected_sha = screen.get("sha256")
            if isinstance(expected_sha, str) and _sha256(path) != expected_sha:
                issues.append(
                    _issue(
                        "evidence.png.sha_mismatch",
                        f"$.screens[{index}].sha256",
                        f"exported PNG sha256 does not match manifest receipt: {png}",
                    )
                )
    return issues


def _vision_receipt_issues(
    directory: Path,
    vision_report: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Cross-check vision-report inputs against evaluated evidence files."""
    if vision_report is None:
        return []
    inputs = vision_report.get("inputs")
    if not isinstance(inputs, list):
        return []  # the vision-report schema already flags missing/malformed receipts
    issues: list[dict[str, Any]] = []
    input_by_file = {
        item.get("file"): item.get("sha256")
        for item in inputs
        if isinstance(item, dict)
        and isinstance(item.get("file"), str)
        and isinstance(item.get("sha256"), str)
    }
    for index, item in enumerate(inputs):
        if not isinstance(item, dict):
            continue
        file_value = item.get("file")
        sha_value = item.get("sha256")
        if not isinstance(file_value, str) or not isinstance(sha_value, str):
            continue
        path = _evidence_file_path(directory, file_value)
        json_path = f"$.inputs[{index}].file"
        if path is None:
            issues.append(
                _issue(
                    "evidence.vision_input.outside_evidence_dir",
                    json_path,
                    f"vision input must resolve inside evidence directory: {file_value}",
                )
            )
        elif not path.is_file():
            issues.append(
                _issue(
                    "evidence.vision_input.missing",
                    json_path,
                    f"vision input file not found: {file_value}",
                )
            )
        elif _sha256(path) != sha_value:
            issues.append(
                _issue(
                    "evidence.vision_input.sha_mismatch",
                    f"$.inputs[{index}].sha256",
                    f"vision input sha256 does not match file bytes: {file_value}",
                )
            )
    evaluated_files = _evaluated_vision_files(vision_report)
    for file_value, json_path in evaluated_files:
        if file_value not in input_by_file:
            issues.append(
                _issue(
                    "evidence.vision_input.missing",
                    json_path,
                    f"vision-report inputs must include evaluated file: {file_value}",
                )
            )
    issues.extend(_criterion_file_evidence_issues(vision_report))
    return issues


def _vision_manifest_screen_issues(
    manifest: dict[str, Any] | None,
    vision_report: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Ensure the vision pass judged the exact screen exports listed by the manifest."""
    if (
        manifest is None
        or vision_report is None
        or not isinstance(manifest.get("screens"), list)
        or not isinstance(vision_report.get("screens"), list)
    ):
        return []
    manifest_by_screen = {
        screen.get("screen_id"): screen.get("png")
        for screen in manifest["screens"]
        if isinstance(screen, dict)
        and isinstance(screen.get("screen_id"), str)
        and isinstance(screen.get("png"), str)
    }
    issues: list[dict[str, Any]] = []
    for index, screen in enumerate(vision_report["screens"]):
        if not isinstance(screen, dict):
            continue
        screen_id = screen.get("screen_id")
        png = screen.get("png")
        if not isinstance(screen_id, str) or not isinstance(png, str):
            continue
        manifest_png = manifest_by_screen.get(screen_id)
        if manifest_png != png:
            expected = manifest_png if manifest_png is not None else "<missing manifest screen>"
            issues.append(
                _issue(
                    "evidence.vision_manifest.png_mismatch",
                    f"$.screens[{index}].png",
                    (
                        f"vision screen {screen_id!r} evaluated {png!r}, "
                        f"but manifest records {expected!r}"
                    ),
                )
            )
    return issues


def _evaluated_vision_files(vision_report: dict[str, Any]) -> list[tuple[str, str]]:
    files: list[tuple[str, str]] = []
    screens = vision_report.get("screens")
    if isinstance(screens, list):
        for index, screen in enumerate(screens):
            if isinstance(screen, dict) and isinstance(screen.get("png"), str):
                files.append((screen["png"], f"$.screens[{index}].png"))
    coherence = vision_report.get("coherence")
    if isinstance(coherence, dict) and isinstance(coherence.get("contact_sheet_png"), str):
        files.append((coherence["contact_sheet_png"], "$.coherence.contact_sheet_png"))
    references = vision_report.get("reference_fidelity")
    if isinstance(references, list):
        for index, entry in enumerate(references):
            if not isinstance(entry, dict):
                continue
            for key in ("export", "contact_sheet"):
                value = entry.get(key)
                if isinstance(value, str):
                    files.append((value, f"$.reference_fidelity[{index}].{key}"))
    return files


def _criterion_file_evidence_issues(vision_report: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    screens = vision_report.get("screens")
    if not isinstance(screens, list):
        return issues
    for screen_index, screen in enumerate(screens):
        if not isinstance(screen, dict):
            continue
        png = screen.get("png")
        criteria = screen.get("criteria")
        if not isinstance(png, str) or not isinstance(criteria, list):
            continue
        for criterion_index, criterion in enumerate(criteria):
            evidence = criterion.get("evidence") if isinstance(criterion, dict) else None
            if isinstance(evidence, str) and png not in evidence:
                issues.append(
                    _issue(
                        "evidence.vision.file_evidence_missing",
                        f"$.screens[{screen_index}].criteria[{criterion_index}].evidence",
                        f"criterion evidence must cite evaluated file {png}",
                    )
                )
    coherence = vision_report.get("coherence")
    if isinstance(coherence, dict):
        contact_sheet = coherence.get("contact_sheet_png")
        criteria = coherence.get("criteria")
        if isinstance(contact_sheet, str) and isinstance(criteria, list):
            for criterion_index, criterion in enumerate(criteria):
                evidence = criterion.get("evidence") if isinstance(criterion, dict) else None
                if isinstance(evidence, str) and contact_sheet not in evidence:
                    issues.append(
                        _issue(
                            "evidence.coherence.file_evidence_missing",
                            f"$.coherence.criteria[{criterion_index}].evidence",
                            f"criterion evidence must cite contact sheet {contact_sheet}",
                        )
                    )
    references = vision_report.get("reference_fidelity")
    if isinstance(references, list):
        for ref_index, entry in enumerate(references):
            if not isinstance(entry, dict):
                continue
            required_files = [
                value
                for value in (
                    entry.get("reference"),
                    entry.get("export"),
                    entry.get("contact_sheet"),
                )
                if isinstance(value, str) and value
            ]
            criteria = entry.get("criteria")
            if not isinstance(criteria, list):
                continue
            for criterion_index, criterion in enumerate(criteria):
                evidence = criterion.get("evidence") if isinstance(criterion, dict) else None
                if isinstance(evidence, str) and any(
                    path not in evidence for path in required_files
                ):
                    issues.append(
                        _issue(
                            "evidence.reference_fidelity.file_evidence_missing",
                            f"$.reference_fidelity[{ref_index}].criteria[{criterion_index}].evidence",
                            "criterion evidence must cite reference, export, and contact-sheet files",
                        )
                    )
    return issues


def _structured_criteria_issues(
    manifest: dict[str, Any] | None,
    vision_report: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Require run-bound, blocking, homologous proof for every locked criterion."""
    if manifest is None or vision_report is None:
        return []
    issues: list[dict[str, Any]] = []
    manifest_run_id = manifest.get("runId")
    report_run_id = vision_report.get("runId")
    if manifest_run_id != report_run_id:
        issues.append(
            _issue(
                "evidence.run_id.mismatch",
                "$.runId",
                "manifest.json and vision-report.json must identify the same exact run",
            )
        )
    if manifest.get("status") != "PASS":
        issues.append(
            _issue(
                "evidence.manifest.status_not_pass",
                "$.status",
                "manifest status must be PASS; warning and SKIP do not close required evidence",
            )
        )
    if vision_report.get("status") != "PASS":
        issues.append(
            _issue(
                "evidence.vision.status_not_pass",
                "$.status",
                "vision status must be PASS; warning and SKIP do not close required evidence",
            )
        )

    inputs: dict[str, str] = {}
    for item in vision_report.get("inputs", []):
        if not isinstance(item, dict):
            continue
        file_value = item.get("file")
        digest = item.get("sha256")
        if isinstance(file_value, str) and isinstance(digest, str):
            inputs[file_value] = digest
    manifest_regions: dict[tuple[Any, Any, Any, Any], dict[str, Any]] = {}
    for screen in manifest.get("screens", []):
        if not isinstance(screen, dict):
            continue
        for region in screen.get("regions", []):
            if not isinstance(region, dict):
                continue
            mapping = (
                screen.get("surface"),
                screen.get("screen_id"),
                region.get("region_id"),
                screen.get("state"),
            )
            manifest_regions[mapping] = {
                "crop": region.get("crop"),
                "file": screen.get("png"),
                "sha256": screen.get("sha256"),
            }

    usages: dict[tuple[str, str], set[tuple[Any, Any, Any, Any]]] = {}
    for index, screen in enumerate(vision_report.get("screens", [])):
        if not isinstance(screen, dict):
            continue
        mapping = _proof_mapping(screen)
        manifest_region = manifest_regions.get(mapping)
        if manifest_region is None:
            issues.append(
                _issue(
                    "evidence.mapping.region_mismatch",
                    f"$.screens[{index}]",
                    "vision surface/screen/region/state has no homologous manifest region",
                )
            )
        _criterion_proof_issues(
            screen.get("criteria"),
            f"$.screens[{index}].criteria",
            mapping=mapping,
            run_id=report_run_id,
            expected_roles={"actual"},
            expected_files={"actual": screen.get("png")},
            expected_crops={
                "actual": manifest_region.get("crop") if isinstance(manifest_region, dict) else None
            },
            inputs=inputs,
            usages=usages,
            issues=issues,
        )

    coherence = vision_report.get("coherence")
    if isinstance(coherence, dict):
        _criterion_proof_issues(
            coherence.get("criteria"),
            "$.coherence.criteria",
            mapping=_proof_mapping(coherence),
            run_id=report_run_id,
            expected_roles={"contact_sheet"},
            expected_files={"contact_sheet": coherence.get("contact_sheet_png")},
            expected_crops={},
            inputs=inputs,
            usages=usages,
            issues=issues,
        )

    for index, entry in enumerate(vision_report.get("reference_fidelity", [])):
        if not isinstance(entry, dict):
            continue
        reference_mapping = entry.get("mapping")
        mapping_tuple = _proof_mapping(reference_mapping)
        _criterion_proof_issues(
            entry.get("criteria"),
            f"$.reference_fidelity[{index}].criteria",
            mapping=mapping_tuple,
            run_id=report_run_id,
            expected_roles={"actual", "reference", "contact_sheet"},
            expected_files={
                "actual": entry.get("export"),
                "reference": entry.get("reference"),
                "contact_sheet": entry.get("contact_sheet"),
            },
            expected_crops={
                "actual": (
                    reference_mapping.get("actual_crop")
                    if isinstance(reference_mapping, dict)
                    else None
                ),
                "reference": (
                    reference_mapping.get("reference_crop")
                    if isinstance(reference_mapping, dict)
                    else None
                ),
            },
            inputs=inputs,
            usages=usages,
            issues=issues,
        )

    for (role, digest), mappings in sorted(usages.items()):
        if role in {"actual", "reference"} and len(mappings) > 1:
            issues.append(
                _issue(
                    "evidence.artifact.reused_non_homologous",
                    "$.screens",
                    f"{role} artifact sha256 {digest} is reused across non-homologous mappings",
                )
            )
    return issues


def _criterion_proof_issues(
    criteria: Any,
    path: str,
    *,
    mapping: tuple[Any, Any, Any, Any],
    run_id: Any,
    expected_roles: set[str],
    expected_files: dict[str, Any],
    expected_crops: dict[str, Any],
    inputs: dict[str, str],
    usages: dict[tuple[str, str], set[tuple[Any, Any, Any, Any]]],
    issues: list[dict[str, Any]],
) -> None:
    if not isinstance(criteria, list):
        return
    seen: set[str] = set()
    for index, criterion in enumerate(criteria):
        if not isinstance(criterion, dict):
            continue
        criterion_path = f"{path}[{index}]"
        category = criterion.get("category")
        if isinstance(category, str) and category in seen:
            issues.append(
                _issue(
                    "evidence.criterion.duplicate",
                    criterion_path,
                    f"required criterion {category!r} must be recorded exactly once",
                )
            )
        if isinstance(category, str):
            seen.add(category)
        if criterion.get("result") != "pass":
            issues.append(
                _issue(
                    "evidence.criterion.not_pass",
                    f"{criterion_path}.result",
                    "required criterion must pass; fail and warning never close the gate",
                )
            )
        if criterion.get("blocking") is not True:
            issues.append(
                _issue(
                    "evidence.criterion.non_blocking",
                    f"{criterion_path}.blocking",
                    "required criterion must be blocking",
                )
            )
        proof = criterion.get("proof")
        if not isinstance(proof, dict):
            issues.append(
                _issue(
                    "evidence.criterion.proof_missing",
                    f"{criterion_path}.proof",
                    "narrative evidence cannot replace structured proof",
                )
            )
            continue
        if _proof_mapping(proof) != mapping:
            issues.append(
                _issue(
                    "evidence.proof.mapping_mismatch",
                    f"{criterion_path}.proof",
                    "proof surface/screen/region/state must match its enclosing mapping",
                )
            )
        if proof.get("run_id") != run_id:
            issues.append(
                _issue(
                    "evidence.proof.run_mismatch",
                    f"{criterion_path}.proof.run_id",
                    "proof must cite the exact vision-report runId",
                )
            )
        region_id = proof.get("region_id")
        if not isinstance(region_id, str) or not any(mark in region_id for mark in (".", ":", "/")):
            issues.append(
                _issue(
                    "evidence.proof.generic_region",
                    f"{criterion_path}.proof.region_id",
                    "region_id must be a specific hierarchical anchor",
                )
            )
        if proof.get("assertion") != category:
            issues.append(
                _issue(
                    "evidence.proof.assertion_mismatch",
                    f"{criterion_path}.proof.assertion",
                    "proof assertion must match its locked criterion category",
                )
            )
        measurement = proof.get("measurement")
        if not isinstance(measurement, dict) or (
            measurement.get("expected") != "pass"
            or measurement.get("actual") != criterion.get("result")
            or measurement.get("unit") != "result"
        ):
            issues.append(
                _issue(
                    "evidence.proof.measurement_mismatch",
                    f"{criterion_path}.proof.measurement",
                    "measurement must record expected=pass and the independently observed result",
                )
            )
        artifacts = proof.get("artifacts")
        if not isinstance(artifacts, list):
            continue
        by_role: dict[str, dict[str, Any]] = {}
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                continue
            role = artifact.get("role")
            if isinstance(role, str):
                by_role[role] = artifact
        if set(by_role) != expected_roles:
            issues.append(
                _issue(
                    "evidence.proof.artifact_roles_invalid",
                    f"{criterion_path}.proof.artifacts",
                    f"proof artifact roles must be exactly {sorted(expected_roles)}",
                )
            )
        for role, artifact in by_role.items():
            file_value = artifact.get("file")
            digest = artifact.get("sha256")
            if file_value != expected_files.get(role):
                issues.append(
                    _issue(
                        "evidence.proof.artifact_mismatch",
                        f"{criterion_path}.proof.artifacts",
                        f"{role} artifact does not match the enclosing evaluated file",
                    )
                )
            if role != "reference" and (
                not isinstance(file_value, str)
                or not isinstance(digest, str)
                or inputs.get(file_value) != digest
            ):
                issues.append(
                    _issue(
                        "evidence.proof.input_receipt_mismatch",
                        f"{criterion_path}.proof.artifacts",
                        f"{role} artifact must match an exact input receipt",
                    )
                )
            if role in expected_crops and artifact.get("crop") != expected_crops[role]:
                issues.append(
                    _issue(
                        "evidence.proof.crop_mismatch",
                        f"{criterion_path}.proof.artifacts",
                        f"{role} crop does not match the declared homologous region",
                    )
                )
            crop = artifact.get("crop")
            if isinstance(crop, dict) and not _crop_is_valid(crop):
                issues.append(
                    _issue(
                        "evidence.proof.crop_invalid",
                        f"{criterion_path}.proof.artifacts",
                        f"{role} crop is outside its declared source dimensions",
                    )
                )
            if isinstance(digest, str):
                usages.setdefault((role, digest), set()).add(mapping)
        actual = by_role.get("actual")
        reference = by_role.get("reference")
        if (
            isinstance(actual, dict)
            and isinstance(reference, dict)
            and (
                actual.get("file") == reference.get("file")
                or actual.get("sha256") == reference.get("sha256")
            )
        ):
            issues.append(
                _issue(
                    "evidence.reference.actual_not_independent",
                    f"{criterion_path}.proof.artifacts",
                    "actual evidence must not copy expected/reference path or bytes",
                )
            )


def _proof_mapping(value: Any) -> tuple[Any, Any, Any, Any]:
    if not isinstance(value, dict):
        return (None, None, None, None)
    return (
        value.get("surface"),
        value.get("screen_id"),
        value.get("region_id"),
        value.get("state"),
    )


def _crop_is_valid(crop: dict[str, Any]) -> bool:
    values = [
        crop.get("x"),
        crop.get("y"),
        crop.get("width"),
        crop.get("height"),
        crop.get("source_width"),
        crop.get("source_height"),
    ]
    if not all(isinstance(value, int) and not isinstance(value, bool) for value in values):
        return False
    x, y, width, height, source_width, source_height = (cast(int, value) for value in values)
    return bool(
        x >= 0
        and y >= 0
        and width > 0
        and height > 0
        and x + width <= source_width
        and y + height <= source_height
    )


def _theme_issues(
    manifest: dict[str, Any] | None, fingerprint: dict[str, str] | None
) -> list[dict[str, Any]]:
    # @spec FR-004: evidence.theme.missing / evidence.theme.stale checks — .specs/features/056-evidence-run-identity-theme-fingerprint/spec.md#fr-004
    """Bind the evidence packet to the theme bytes it was rendered against."""
    if fingerprint is None:
        return []  # gate not armed: zero behavior change (AC-008)
    if manifest is None:
        return []  # missing/unparseable manifest already surfaced its own error
    theme = manifest.get("theme")
    stamped = theme.get("sha256") if isinstance(theme, dict) else None
    if not isinstance(stamped, str):
        # Absent or schema-malformed block: the schema diagnostic (if any)
        # already flags the shape; degrade to one missing-stamp error without
        # duplicating it (the _png_issues no-double-report precedent).
        return [
            _issue(
                "evidence.theme.missing",
                "$.theme",
                "manifest.json has no theme block but the gate is armed with"
                f" --theme-css {fingerprint['path']}",
            )
        ]
    if stamped != fingerprint["sha256"]:
        # Only sha256 binds — theme.path is recording-time traceability metadata.
        return [
            _issue(
                "evidence.theme.stale",
                "$.theme",
                f"manifest theme sha256 {stamped} does not match current"
                f" theme.css sha256 {fingerprint['sha256']}",
            )
        ]
    return []


def _category_issues(vision_report: dict[str, Any] | None) -> list[dict[str, Any]]:
    """A vision pass must answer all five locked categories per screen."""
    if vision_report is None or not isinstance(vision_report.get("screens"), list):
        return []
    issues: list[dict[str, Any]] = []
    for index, screen in enumerate(vision_report["screens"]):
        if not isinstance(screen, dict) or not isinstance(screen.get("criteria"), list):
            continue
        answered = {
            criterion.get("category")
            for criterion in screen["criteria"]
            if isinstance(criterion, dict)
        }
        screen_id = screen.get("screen_id")
        for category in VISION_CATEGORIES:
            if category not in answered:
                issues.append(
                    _issue(
                        "evidence.vision.category_missing",
                        f"$.screens[{index}].criteria",
                        f"screen {screen_id!r} does not answer vision category {category!r}",
                    )
                )
    return issues


def _coherence_issues(
    directory: Path,
    vision_report: dict[str, Any] | None,
    expected_screens: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    # @spec FR-002: Coherence required for multi-screen expected trees — .specs/features/053-cross-mockup-coherence-contact-sheet/spec.md#fr-002
    """Cross-mockup coherence checks (C28) over the contact-sheet section."""
    if vision_report is None:
        return []  # the missing/invalid vision report already surfaced its own error
    coherence = vision_report.get("coherence")
    if not isinstance(coherence, dict):
        # A single mockup has nothing to compare across screens, so the
        # contact-sheet pass only becomes mandatory at >= 2 expected screens.
        if len(expected_screens) >= 2:
            return [
                _issue(
                    "evidence.coherence.missing",
                    "$.coherence",
                    f"expected tree has {len(expected_screens)} screens but"
                    " vision-report.json has no coherence section",
                )
            ]
        return []
    issues = _contact_sheet_issues(directory, coherence)
    issues.extend(_coherence_category_issues(coherence))
    return issues


def _contact_sheet_issues(directory: Path, coherence: dict[str, Any]) -> list[dict[str, Any]]:
    # @spec FR-003: Contact sheet PNG must exist non-empty — .specs/features/053-cross-mockup-coherence-contact-sheet/spec.md#fr-003
    """The contact-sheet PNG must exist non-empty inside the evidence dir."""
    png = coherence.get("contact_sheet_png")
    if not isinstance(png, str) or not png:
        return []  # the vision-report schema already flags the malformed key
    path = directory / png
    json_path = "$.coherence.contact_sheet_png"
    if not path.is_file():
        return [
            _issue(
                "evidence.contact_sheet.missing", json_path, f"contact sheet PNG not found: {png}"
            )
        ]
    if path.stat().st_size == 0:
        return [
            _issue("evidence.contact_sheet.empty", json_path, f"contact sheet PNG is empty: {png}")
        ]
    return []


def _coherence_category_issues(coherence: dict[str, Any]) -> list[dict[str, Any]]:
    """A coherence pass must answer all four locked categories."""
    criteria = coherence.get("criteria")
    if not isinstance(criteria, list):
        return []  # the vision-report schema already flags the malformed section
    answered = {criterion.get("category") for criterion in criteria if isinstance(criterion, dict)}
    return [
        _issue(
            "evidence.coherence.category_missing",
            "$.coherence.criteria",
            f"coherence pass does not answer category {category!r}",
        )
        for category in COHERENCE_CATEGORIES
        if category not in answered
    ]


def _coverage_issues(
    expected_screens: list[dict[str, Any]],
    artifact: dict[str, Any] | None,
    artifact_name: str,
) -> list[dict[str, Any]]:
    """Every expected-tree screen must appear in the evidence artifact."""
    if artifact is None or not isinstance(artifact.get("screens"), list):
        return []  # missing/unparseable artifacts already surfaced their own error
    covered: set[str] = set()
    for screen in artifact["screens"]:
        if isinstance(screen, dict):
            covered.update(_evidence_screen_ids(screen))
    issues: list[dict[str, Any]] = []
    for index, screen in enumerate(expected_screens):
        ids = _expected_screen_ids(screen)
        if ids and not (set(ids) & covered):
            issues.append(
                _issue(
                    "evidence.screen.uncovered",
                    f"$.screens[{index}]",
                    f"expected screen {ids[0]!r} is not covered by {artifact_name}",
                )
            )
    return issues


def _snapshot_issues(
    directory: Path, expected_screens: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    # @spec FR-003: Optional layout snapshot cross-check ±4px — .specs/features/051-vision-report-contract-evidence-validator/spec.md#fr-003
    path = directory / LAYOUT_SNAPSHOT_FILENAME
    if not path.is_file():
        return []
    try:
        snapshot = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        return [_issue("evidence.snapshot.invalid", "$", f"{path.name} is not valid JSON: {error}")]
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("screens"), list):
        return [
            _issue(
                "evidence.snapshot.invalid",
                "$",
                f"{path.name} must be an object with a screens list",
            )
        ]
    issues: list[dict[str, Any]] = []
    for index, screen in enumerate(snapshot["screens"]):
        json_path = f"$.screens[{index}]"
        if not isinstance(screen, dict):
            issues.append(
                _issue("evidence.snapshot.invalid", json_path, "snapshot screen must be an object")
            )
            continue
        screen_id = screen.get("screen_id")
        width = screen.get("width")
        height = screen.get("height")
        if (
            not isinstance(screen_id, str)
            or not _is_finite_number(width)
            or not _is_finite_number(height)
        ):
            issues.append(
                _issue(
                    "evidence.snapshot.invalid",
                    json_path,
                    "snapshot screen requires screen_id (string), width and height (numbers)",
                )
            )
            continue
        snapshot_width = float(width)
        snapshot_height = float(height)
        snapshot_ids = {screen_id}
        pencil_node_id = screen.get("pencil_node_id")
        if isinstance(pencil_node_id, str):
            snapshot_ids.add(pencil_node_id)
        expected_bbox = _matching_expected_bbox(expected_screens, snapshot_ids)
        if expected_bbox is None:
            continue  # unmatched snapshot screens are ignored; coverage is checked elsewhere
        expected_width, expected_height = expected_bbox
        if (
            abs(snapshot_width - expected_width) > SNAPSHOT_TOLERANCE_PX
            or abs(snapshot_height - expected_height) > SNAPSHOT_TOLERANCE_PX
        ):
            issues.append(
                _issue(
                    "evidence.snapshot.bbox_mismatch",
                    json_path,
                    f"snapshot {screen_id!r} is {_fmt(snapshot_width)}x{_fmt(snapshot_height)} but the"
                    f" expected root bbox is {_fmt(expected_width)}x{_fmt(expected_height)}"
                    f" (tolerance {_fmt(SNAPSHOT_TOLERANCE_PX)}px)",
                )
            )
    return issues


def _matching_expected_bbox(
    expected_screens: list[dict[str, Any]], snapshot_ids: set[str]
) -> tuple[float, float] | None:
    """First expected screen (document order) matching the snapshot ids wins."""
    for screen in expected_screens:
        if not (set(_expected_screen_ids(screen)) & snapshot_ids):
            continue
        root = screen.get("root")
        bbox = root.get("bbox") if isinstance(root, dict) else None
        if not isinstance(bbox, dict):
            return None
        width = bbox.get("width")
        height = bbox.get("height")
        if not _is_finite_number(width) or not _is_finite_number(height):
            return None
        if float(width) == 0.0 and float(height) == 0.0:
            return None  # unmeasured drafted screen: nothing to cross-check
        return float(width), float(height)
    return None


def _expected_screen_ids(screen: dict[str, Any]) -> list[str]:
    """Identifier union for a feature 006 expected screen, in stable order."""
    ids: list[str] = []
    for key in ("screen_id", "name", "pencil_id"):
        value = screen.get(key)
        if isinstance(value, str) and value and value not in ids:
            ids.append(value)
    return ids


def _evidence_screen_ids(screen: dict[str, Any]) -> set[str]:
    return {
        value
        for key in ("screen_id", "semantic_id", "pencil_node_id")
        if isinstance(value := screen.get(key), str) and value
    }


def _is_finite_number(value: Any) -> TypeGuard[int | float]:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _fmt(value: float) -> str:
    return str(int(value)) if value == int(value) else str(value)


def _evidence_file_path(directory: Path, file_value: str) -> Path | None:
    candidate = Path(file_value)
    path = candidate if candidate.is_absolute() else directory / candidate
    try:
        path.resolve(strict=False).relative_to(directory.resolve())
    except (OSError, RuntimeError, ValueError):
        return None
    return path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _lineage_file_digest(key: str, source: str | Path | None) -> tuple[str, bool]:
    path = Path(source) if source is not None else None
    if path is not None and path.is_file():
        return _sha256(path), True
    return _canonical_sha256({"source": key, "state": "absent"}), False


def _lineage_value_digest(key: str, value: str | None) -> str:
    return _canonical_sha256({"source": key, "value": value})


def _canonical_sha256(value: dict[str, Any]) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _issue(code: str, path: str, message: str) -> dict[str, Any]:
    return {"code": code, "severity": "error", "path": path, "message": message}


def _issue_sort_key(issue: dict[str, Any]) -> tuple[str, str, str]:
    return (issue["code"], issue["path"], issue["message"])
