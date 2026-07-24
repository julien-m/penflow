# @spec(FR-016)
# @spec(FR-017)
# @spec(FR-018)
"""Independent, content-bound provenance receipt validation for actual trees.

Penflow NEVER captures a runtime. An external adapter (SwiftUI / React /
Rust / …) writes `actual-ui-tree.json` and, alongside it, an
`actual-ui-tree.provenance.json` receipt describing *what produced these exact
bytes, when, and for which surface*. This module only validates — from local
files — that the receipt is complete, binds to the actual-tree bytes by
SHA-256, is independent of the design-derived `expected-ui-tree.json`, and does
not let a frozen demo fixture masquerade as a fresh runtime capture. It imports
no browser, simulator, Xcode, Playwright, React Native, or Pencil runtime.
"""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from .schema_cache import validator_for
from .tree import load_tree


class ProvenanceError(ValueError):
    """Raised for an invalid provenance configuration (e.g. a max-age window
    that is not a finite, strictly positive number). It is a configuration
    fault, distinct from a receipt validation issue, and must fail closed
    before any report is produced."""


RECEIPT_KIND = "penflow-actual-provenance"
RECEIPT_VERSION = 1
RECEIPT_SUFFIX = ".provenance.json"

RUNTIME_CAPTURE = "runtime-capture"
STATIC_DEMO_FIXTURE = "static-demo-fixture"
KNOWN_SOURCE_KINDS = (RUNTIME_CAPTURE, STATIC_DEMO_FIXTURE)
# Only a fresh runtime capture is admissible when the caller requires freshness.
FRESH_SOURCE_KINDS = (RUNTIME_CAPTURE,)

# A capture timestamp may lead ``now`` by at most this many seconds before it is
# treated as an impossible future stamp (clock skew tolerance).
FUTURE_SKEW_SECONDS = 60.0

_SCHEMA = "actual-ui-tree-provenance.schema.json"


def actual_provenance_path(actual_path: str | Path) -> Path:
    """Return the sidecar receipt path for an actual tree.

    ``.../actual-ui-tree.json`` → ``.../actual-ui-tree.provenance.json``.
    """
    path = Path(actual_path)
    return path.with_name(path.stem + RECEIPT_SUFFIX)


def ensure_valid_max_age_seconds(value: float | None) -> None:
    """Fail closed unless an explicit freshness window is finite and > 0.

    ``None`` means "no max-age check" and is allowed. Any provided value must be
    a real, finite, strictly positive number: ``nan``, ``inf``, ``-inf``,
    overflowing literals such as ``1e999`` (which parse to ``inf``), ``0``, and
    negatives are rejected so a pathological window can never silently disarm
    (fail-open) or crash the freshness gate. Raises :class:`ProvenanceError`.
    """
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProvenanceError(f"max_age_seconds must be a finite positive number, got {value!r}")
    if not math.isfinite(value) or value <= 0:
        raise ProvenanceError(
            f"max_age_seconds must be finite and strictly positive, got {value!r}"
        )


# @spec(FR-016)
# @spec(FR-017)
# @spec(FR-018)
def validate_actual_provenance(
    actual_path: str | Path,
    *,
    expected_path: str | Path | None = None,
    now: datetime | None = None,
    max_age_seconds: float | None = None,
    require_fresh: bool = False,
    allowed_surfaces: Sequence[str] | None = None,
) -> list[dict[str, Any]]:
    """Validate an actual tree's provenance receipt fail-closed.

    Args:
        actual_path: Path to `actual-ui-tree.json`. Its sidecar receipt is
            resolved with :func:`actual_provenance_path`.
        expected_path: Optional `expected-ui-tree.json`. When present, a
            ``runtime-capture`` whose root is byte-identical to a design-derived
            expected screen root is rejected as derived-from-expected.
        now: Reference UTC time for freshness checks. When ``None`` the future
            and stale checks are skipped so the pipeline gate stays
            deterministic; the CLI passes the current UTC time.
        max_age_seconds: When set (with ``now``), a ``runtime-capture`` older
            than this window is stale. Fixtures are exempt by design.
        require_fresh: When true, only ``runtime-capture`` receipts are
            admissible; a qualified fixture becomes inadmissible.
        allowed_surfaces: When set, ``target.surface`` must be one of these.

    Returns:
        A deterministically sorted list of ``{code, severity, path, message}``
        issues. Empty means the receipt is valid. All issues are ``error``
        severity: provenance is provably present or the actual is rejected.

    Raises:
        ProvenanceError: If ``max_age_seconds`` is provided but is not a finite,
            strictly positive number (fail closed before any file is read).
    """
    ensure_valid_max_age_seconds(max_age_seconds)
    actual = Path(actual_path)
    if not actual.is_file():
        return [_issue("provenance.actual.missing", "$", f"actual tree not found: {actual}")]

    receipt_path = actual_provenance_path(actual)
    if not receipt_path.is_file():
        return [
            _issue(
                "provenance.receipt.missing",
                "$",
                f"provenance receipt not found next to actual tree: {receipt_path.name}",
            )
        ]

    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        return [
            _issue(
                "provenance.receipt.invalid",
                "$",
                f"{receipt_path.name} is not valid JSON: {error}",
            )
        ]
    if not isinstance(receipt, dict):
        return [
            _issue("provenance.receipt.invalid", "$", f"{receipt_path.name} must be a JSON object")
        ]

    issues: list[dict[str, Any]] = _schema_issues(receipt)
    issues.extend(_digest_issues(actual, receipt))
    issues.extend(_content_path_issues(actual, receipt))
    issues.extend(_timestamp_issues(receipt, now, max_age_seconds))
    issues.extend(_admissibility_issues(receipt, require_fresh))
    issues.extend(_surface_issues(receipt, allowed_surfaces))
    issues.extend(_independence_issues(actual, expected_path, receipt))
    issues.sort(key=_issue_sort_key)
    return issues


def _schema_issues(receipt: dict[str, Any]) -> list[dict[str, Any]]:
    """Every structural failure (missing producer, fields, enum, sha pattern,
    unqualified fixture, fixture-on-capture) surfaces as one invalid-receipt
    reason."""
    validator = validator_for(_SCHEMA)
    formatted = [
        _issue("provenance.receipt.invalid", _json_path(error.absolute_path), error.message)
        for error in validator.iter_errors(receipt)
    ]
    formatted.sort(key=_issue_sort_key)
    return formatted


def _digest_issues(actual: Path, receipt: dict[str, Any]) -> list[dict[str, Any]]:
    content = receipt.get("content")
    stamped = content.get("sha256") if isinstance(content, dict) else None
    if not isinstance(stamped, str):
        return []  # the schema already flags the malformed/absent digest
    actual_sha = hashlib.sha256(actual.read_bytes()).hexdigest()
    if actual_sha != stamped:
        return [
            _issue(
                "provenance.digest.mismatch",
                "$.content.sha256",
                f"receipt sha256 {stamped} does not match actual tree bytes {actual_sha}",
            )
        ]
    return []


def _content_path_issues(actual: Path, receipt: dict[str, Any]) -> list[dict[str, Any]]:
    """`content.path` must be a safe relative name for the validated actual file.

    The field is traceability metadata only — the SHA-256 digest remains the
    sole authority over the actual-tree bytes. To stop it becoming a misleading
    or unsafe pointer, an absolute path or a ``..`` traversal is rejected
    (`provenance.content.path_invalid`), and a basename that does not name the
    validated actual file is rejected (`provenance.content.path_mismatch`).
    """
    content = receipt.get("content")
    declared = content.get("path") if isinstance(content, dict) else None
    if not isinstance(declared, str) or not declared:
        return []  # the schema already flags the malformed/absent path
    candidate = Path(declared)
    if candidate.is_absolute() or ".." in candidate.parts:
        return [
            _issue(
                "provenance.content.path_invalid",
                "$.content.path",
                f"receipt content.path {declared!r} must be a relative path without"
                " '..' traversal (the sha256 digest is the authority over the bytes)",
            )
        ]
    if candidate.name != actual.name:
        return [
            _issue(
                "provenance.content.path_mismatch",
                "$.content.path",
                f"receipt content.path {declared!r} does not name the validated"
                f" actual tree {actual.name!r}",
            )
        ]
    return []


def _timestamp_issues(
    receipt: dict[str, Any], now: datetime | None, max_age_seconds: float | None
) -> list[dict[str, Any]]:
    # Freshness is a property of a *fresh capture*. A qualified fixture declares
    # itself frozen and is exempt, so a deterministic demo timestamp never goes
    # stale.
    if receipt.get("sourceKind") != RUNTIME_CAPTURE:
        return []
    captured_at = receipt.get("capturedAt")
    if not isinstance(captured_at, str):
        return []  # the schema already flags the malformed/absent timestamp
    parsed = _parse_iso(captured_at)
    if parsed is None:
        return [
            _issue(
                "provenance.timestamp.invalid",
                "$.capturedAt",
                f"capturedAt is not a parseable ISO-8601 timestamp: {captured_at}",
            )
        ]
    if now is None:
        return []
    reference = _as_utc(now)
    issues: list[dict[str, Any]] = []
    age_seconds = (reference - parsed).total_seconds()
    if age_seconds < -FUTURE_SKEW_SECONDS:
        issues.append(
            _issue(
                "provenance.timestamp.future",
                "$.capturedAt",
                f"capturedAt {captured_at} is in the future relative to {reference.isoformat()}",
            )
        )
    if max_age_seconds is not None and age_seconds > max_age_seconds:
        issues.append(
            _issue(
                "provenance.timestamp.stale",
                "$.capturedAt",
                f"capturedAt {captured_at} is {int(age_seconds)}s old, exceeding the"
                f" {int(max_age_seconds)}s freshness window",
            )
        )
    return issues


def _admissibility_issues(receipt: dict[str, Any], require_fresh: bool) -> list[dict[str, Any]]:
    source_kind = receipt.get("sourceKind")
    if not isinstance(source_kind, str) or source_kind not in KNOWN_SOURCE_KINDS:
        return []  # the schema enum already flags an unknown/absent source kind
    if require_fresh and source_kind not in FRESH_SOURCE_KINDS:
        return [
            _issue(
                "provenance.source_kind.inadmissible",
                "$.sourceKind",
                f"source kind {source_kind!r} is not an admissible fresh runtime capture",
            )
        ]
    return []


def _surface_issues(
    receipt: dict[str, Any], allowed_surfaces: Sequence[str] | None
) -> list[dict[str, Any]]:
    if allowed_surfaces is None:
        return []
    allowed = {surface for surface in allowed_surfaces if isinstance(surface, str)}
    if not allowed:
        return []
    target = receipt.get("target")
    surface = target.get("surface") if isinstance(target, dict) else None
    if isinstance(surface, str) and surface not in allowed:
        return [
            _issue(
                "provenance.target.incompatible",
                "$.target.surface",
                f"capture surface {surface!r} is not compatible with the contract"
                f" surfaces {sorted(allowed)}",
            )
        ]
    return []


def _independence_issues(
    actual: Path, expected_path: str | Path | None, receipt: dict[str, Any]
) -> list[dict[str, Any]]:
    """A fresh runtime capture cannot be byte-identical to the design tree.

    The verifiable invariant is exact: the actual tree root, canonically
    serialized, must not equal any design-derived expected screen root. A
    qualified ``static-demo-fixture`` is explicitly allowed to reuse expected
    bytes; a ``runtime-capture`` is not.
    """
    if expected_path is None or receipt.get("sourceKind") == STATIC_DEMO_FIXTURE:
        return []
    expected_file = Path(expected_path)
    if not expected_file.is_file():
        return []
    try:
        actual_root = _actual_root(load_tree(actual))
        expected_roots = _expected_root_digests(load_tree(expected_file))
    except (ValueError, OSError, json.JSONDecodeError):
        return []
    if actual_root is None or not expected_roots:
        return []
    if _canonical_sha256(actual_root) in expected_roots:
        return [
            _issue(
                "provenance.actual.derived_from_expected",
                "$.root",
                "actual tree root is byte-identical to the design-derived expected tree;"
                " a fresh runtime capture must carry independent measured geometry",
            )
        ]
    return []


def _actual_root(actual: dict[str, Any]) -> dict[str, Any] | None:
    root = actual.get("root")
    if isinstance(root, dict):
        return root
    screens = actual.get("screens")
    if isinstance(screens, list) and screens and isinstance(screens[0], dict):
        first_root = screens[0].get("root")
        if isinstance(first_root, dict):
            return first_root
    return None


def _expected_root_digests(expected: dict[str, Any]) -> set[str]:
    screens = expected.get("screens")
    if not isinstance(screens, list):
        return set()
    digests: set[str] = set()
    for screen in screens:
        if isinstance(screen, dict) and isinstance(screen.get("root"), dict):
            digests.add(_canonical_sha256(screen["root"]))
    return digests


def _parse_iso(value: str) -> datetime | None:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return _as_utc(parsed)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest()


def _json_path(absolute_path: Any) -> str:
    return "$" + "".join(
        f".{part}" if isinstance(part, str) else f"[{part}]" for part in absolute_path
    )


def _issue(code: str, path: str, message: str) -> dict[str, Any]:
    return {"code": code, "severity": "error", "path": path, "message": message}


def _issue_sort_key(issue: dict[str, Any]) -> tuple[str, str, str]:
    return (issue["code"], issue["path"], issue["message"])
