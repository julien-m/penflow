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

import json
from pathlib import Path
from typing import Any, TypeGuard

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
    issues.extend(_theme_issues(manifest, theme_fingerprint))
    issues.extend(_category_issues(vision_report))
    issues.extend(_coherence_issues(directory, vision_report, expected_screens))
    if expected_tree_path is not None:
        issues.extend(_coverage_issues(expected_screens, manifest, MANIFEST_FILENAME))
        issues.extend(_coverage_issues(expected_screens, vision_report, VISION_REPORT_FILENAME))
    issues.extend(_snapshot_issues(directory, expected_screens))
    issues.sort(key=_issue_sort_key)
    return issues


def _load_expected_screens(expected_tree_path: str | Path) -> list[dict[str, Any]]:
    tree = load_tree(expected_tree_path)
    if not isinstance(tree, dict) or not isinstance(tree.get("screens"), list):
        raise ValueError(
            f"expected tree must be an object with a screens list: {expected_tree_path}"
        )
    screens: list[dict[str, Any]] = []
    for index, screen in enumerate(tree["screens"]):
        if not isinstance(screen, dict):
            raise ValueError(f"screens[{index}] must be an object: {expected_tree_path}")
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
    """Every manifest screen PNG must exist and be non-empty on disk."""
    if manifest is None or not isinstance(manifest.get("screens"), list):
        return []
    issues: list[dict[str, Any]] = []
    for index, screen in enumerate(manifest["screens"]):
        if not isinstance(screen, dict):
            continue
        png = screen.get("png")
        if not isinstance(png, str) or not png:
            continue  # the manifest schema already flags the malformed entry
        path = directory / png
        json_path = f"$.screens[{index}].png"
        if not path.is_file():
            issues.append(
                _issue("evidence.png.missing", json_path, f"exported PNG not found: {png}")
            )
        elif path.stat().st_size == 0:
            issues.append(_issue("evidence.png.empty", json_path, f"exported PNG is empty: {png}"))
    return issues


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


def _issue(code: str, path: str, message: str) -> dict[str, Any]:
    return {"code": code, "severity": "error", "path": path, "message": message}


def _issue_sort_key(issue: dict[str, Any]) -> tuple[str, str, str]:
    return (issue["code"], issue["path"], issue["message"])
