# @spec FR-001: Checklist seeding module — .specs/features/055-checklist-from-drift-seeding/spec.md#fr-001
"""Deterministic Mockup Factory checklist seeding from a drift report (C30).

The first machine consumer of the C24 drift report: every drift issue becomes
one anchored, severity-carrying checklist item (`gate: contract`, C27 shape).
Pure local JSON-to-JSON transformation — no runtimes, no rendering, no LLMs.
Fail-closed: any unreadable, malformed, wrong-kind, or schema-invalid input
raises :class:`ChecklistSeedError` before the output path is ever touched.
"""

from __future__ import annotations

import json
import re
from pathlib import Path, PurePosixPath
from typing import Any

from .drift import _issue_sort_key
from .schema_cache import validator_for

CHECKLIST_VERSION = 1
CHECKLIST_KIND = "penflow-mockup-checklist"
DRIFT_REPORT_KIND = "penflow-drift-report"
DRIFT_REPORT_SCHEMA = "drift-report.schema.json"
CONTRACT_GATE = "contract"
# Documented synthetic screen id for issues not attachable to a single screen
# from the report alone ($.flows, $.screens, pencil:<path> without semantic
# context). Guarantees lossless seeding: no issue is ever dropped.
WORKSPACE_SCREEN_ID = "_workspace"
_DRIFT_CODE_PREFIX = "drift."
_ANCHOR_KEYS = ("semantic_id", "pencil_node_id")
# Strips an optional trailing :<line> suffix from spec paths such as
# "screens/checkout.md:12" — a colon followed by digits only, at end of string.
_LINE_SUFFIX = re.compile(r":\d+$")


class ChecklistSeedError(Exception):
    """Raised on any fail-closed input failure while seeding a checklist."""


# @spec FR-002: Fail-closed input validation — .specs/features/055-checklist-from-drift-seeding/spec.md#fr-002
def _load_valid_drift_report(report_path: str | Path) -> dict[str, Any]:
    """Load a drift report, failing closed before any output is written.

    Validation order: readable, valid JSON, kind ``penflow-drift-report``,
    clean against the bundled drift-report schema (via ``schema_cache``).

    Raises:
        ChecklistSeedError: On the first failing validation step.
    """
    try:
        raw = Path(report_path).read_text(encoding="utf-8")
    except OSError as error:
        raise ChecklistSeedError(f"cannot read drift report {report_path}: {error}") from error
    try:
        report = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ChecklistSeedError(
            f"drift report {report_path} is not valid JSON: {error}"
        ) from error
    if not isinstance(report, dict):
        raise ChecklistSeedError(
            f"{report_path} is not a drift report: top-level JSON value is not an object"
        )
    if report.get("kind") != DRIFT_REPORT_KIND:
        raise ChecklistSeedError(
            f"{report_path} is not a drift report: expected kind "
            f"{DRIFT_REPORT_KIND!r}, got {report.get('kind')!r}"
        )
    schema_errors = sorted(
        validator_for(DRIFT_REPORT_SCHEMA).iter_errors(report),
        key=lambda error: error.json_path,
    )
    if schema_errors:
        first = schema_errors[0]
        raise ChecklistSeedError(
            f"drift report {report_path} violates {DRIFT_REPORT_SCHEMA}: "
            f"{first.message} at {first.json_path}"
        )
    return report


# @spec FR-003: Normalize then sort with imported key — .specs/features/055-checklist-from-drift-seeding/spec.md#fr-003
def _normalized_issues(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Strip null anchors, then sort with the shared ``drift._issue_sort_key``.

    Null-valued ``semantic_id``/``pencil_node_id`` are removed first (the spec
    treats null as absent) so the imported key's ``str()`` never sees ``None``
    — this realizes the spec's ``semantic_id or ""`` semantics without forking
    the function. A no-op for genuine ``detect-drift`` output (already sorted);
    deterministic for hand-edited but schema-valid reports.
    """
    stripped = [
        {key: value for key, value in issue.items() if key not in _ANCHOR_KEYS or value is not None}
        for issue in issues
    ]
    return sorted(stripped, key=_issue_sort_key)


# @spec FR-004: Per-code ordinal item ids — .specs/features/055-checklist-from-drift-seeding/spec.md#fr-004
def _code_suffix(code: str) -> str:
    """Strip the leading ``drift.`` namespace and map remaining ``.`` to ``-``.

    Codes without the ``drift.`` prefix are used verbatim after replacement.
    """
    return code.removeprefix(_DRIFT_CODE_PREFIX).replace(".", "-")


# @spec FR-006: screen_id derivation cascade — .specs/features/055-checklist-from-drift-seeding/spec.md#fr-006
def _screen_id(issue: dict[str, Any]) -> str:
    """Derive the item ``screen_id`` from a normalized issue, first match wins.

    Cascade: (a) non-empty ``semantic_id`` — substring before the first dot
    (the whole value for root screen nodes, per the ``<screen>.<element>``
    grammar); (b) a POSIX path ``…/screens/<stem>.md`` (optional ``:<line>``
    suffix stripped) anchors screen-spec issues to ``<stem>``; (c) the
    documented ``_workspace`` fallback. Screen indices in ``$``-paths are not
    resolvable from the report alone — guessing would break determinism.
    """
    semantic_id = issue.get("semantic_id")
    if isinstance(semantic_id, str) and semantic_id:
        return semantic_id.split(".", 1)[0]
    parts = PurePosixPath(_LINE_SUFFIX.sub("", str(issue.get("path", "")))).parts
    if len(parts) >= 2 and parts[-2] == "screens" and parts[-1].endswith(".md"):
        stem = PurePosixPath(parts[-1]).stem
        if stem:
            return stem
    return WORKSPACE_SCREEN_ID


# @spec FR-005: Item field mapping, FR-007: Top-level fields — .specs/features/055-checklist-from-drift-seeding/spec.md#fr-005
def checklist_from_drift_report(
    report: dict[str, Any], *, source_report: str, group: str | None = None
) -> dict[str, Any]:
    """Map a validated drift report to a fresh checklist dict (pure function).

    Args:
        report: Schema-valid drift report (kind ``penflow-drift-report``).
        source_report: Drift report path exactly as passed on the CLI,
            recorded verbatim in the top-level ``sourceReport`` field.
        group: Optional Mockup Factory group name; the ``group`` field is
            present exactly when provided.

    Returns:
        A checklist dict (kind ``penflow-mockup-checklist``) with one open
        ``gate: contract`` item per issue, status ``PASS`` for zero issues and
        ``OPEN`` otherwise. No timestamps — output is deterministic.
    """
    items: list[dict[str, Any]] = []
    # Per-code ordinal counters: <NNN> is 1-based among issues sharing the
    # same code, in normalized sort order, so ids stay unique and stable.
    ordinals: dict[str, int] = {}
    for issue in _normalized_issues(report["issues"]):
        code = str(issue["code"])
        ordinals[code] = ordinals.get(code, 0) + 1
        item: dict[str, Any] = {
            "id": f"drift-{_code_suffix(code)}-{ordinals[code]:03d}",
            "title": issue["message"],
            "screen_id": _screen_id(issue),
            "gate": CONTRACT_GATE,
            "severity": issue["severity"],
            "blocking": issue["blocking"],
            "status": "open",
            "code": code,
            "evidence": issue["path"],
        }
        for key in _ANCHOR_KEYS:
            if key in issue:  # nulls already stripped by normalization
                item[key] = issue[key]
        items.append(item)
    checklist: dict[str, Any] = {
        "version": CHECKLIST_VERSION,
        "kind": CHECKLIST_KIND,
        # BLOCKED drift reports also seed OPEN: item-level `blocking` carries
        # the signal; top-level transitions belong to the 052 bounded loop.
        "status": "PASS" if not items else "OPEN",
        "sourceReport": source_report,
        "items": items,
    }
    if group is not None:
        checklist["group"] = group
    return checklist


# @spec FR-001: Seeding entrypoint, validate first write last — .specs/features/055-checklist-from-drift-seeding/spec.md#fr-001
def seed_checklist_from_drift(
    report_path: str | Path, out_path: str | Path, *, group: str | None = None
) -> dict[str, Any]:
    """Seed a checklist file from a drift report, fail-closed.

    Validate first, write last: the single ``write_text`` call runs only after
    full input validation, so a failing input never creates or modifies
    ``out_path`` (a pre-existing output stays byte-identical). Serialization
    matches ``drift.py`` (``indent=2, sort_keys=True`` plus trailing newline)
    so reruns over the same report are byte-identical.

    Args:
        report_path: Drift report to read (recorded verbatim in
            ``sourceReport``).
        out_path: Destination checklist path.
        group: Optional Mockup Factory group name.

    Returns:
        The seeded checklist dict.

    Raises:
        ChecklistSeedError: On any fail-closed input failure.
        OSError: When the destination cannot be written.
    """
    report = _load_valid_drift_report(report_path)
    checklist = checklist_from_drift_report(report, source_report=str(report_path), group=group)
    Path(out_path).write_text(
        json.dumps(checklist, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return checklist
