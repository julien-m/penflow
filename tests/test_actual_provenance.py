# @spec(FR-016)
# @spec(FR-017)
# @spec(FR-018)
"""Adversarial coverage for `actual-ui-tree` provenance receipts (P0-2 / C2).

Invariant protected: an `actual-ui-tree.json` is only trusted when a complete,
content-bound receipt proves *what produced these exact bytes, when, and for
which surface*, independently of the design-derived expected tree. Every way an
actual can lie — no receipt, forged digest, stale capture, inadmissible source
kind, wrong surface, or a runtime capture copied from expected — must fail
closed with a structured reason, while a qualified static fixture is accepted
and can never masquerade as a fresh capture.
"""

from __future__ import annotations

import ast
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from penflow.actual_provenance import (
    KNOWN_SOURCE_KINDS,
    RECEIPT_KIND,
    RECEIPT_VERSION,
    RUNTIME_CAPTURE,
    STATIC_DEMO_FIXTURE,
    ProvenanceError,
    actual_provenance_path,
    ensure_valid_max_age_seconds,
    validate_actual_provenance,
)

NOW = datetime(2026, 7, 24, 12, 0, 0, tzinfo=timezone.utc)

# Values that must never arm a freshness window: they either fail-open (nan/inf
# make every stale check false) or crash / invert the check (-inf, 0, negatives).
PATHOLOGICAL_MAX_AGE = [
    float("nan"),
    float("inf"),
    float("-inf"),
    1e999,  # overflows to inf on parse
    0.0,
    -1.0,
    -0.0,
]

# A measured runtime root that is NOT byte-identical to the design tree below.
CAPTURED_ROOT: dict[str, Any] = {
    "id": "checkout",
    "role": "screen",
    "bbox": {"x": 0, "y": 0, "width": 390, "height": 844},
    "children": [
        {
            "id": "checkout.pay-now",
            "role": "button",
            "bbox": {"x": 24, "y": 700, "width": 342, "height": 44},
            "children": [],
        }
    ],
}

# The design-derived expected root carries drafted (zero-sized) geometry.
EXPECTED_ROOT: dict[str, Any] = {
    "id": "checkout",
    "role": "screen",
    "bbox": {"x": 0, "y": 0, "width": 390, "height": 844},
    "children": [
        {
            "id": "checkout.pay-now",
            "role": "button",
            "bbox": {"x": 0, "y": 0, "width": 0, "height": 0},
            "children": [],
        }
    ],
}


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_actual(directory: Path, root: dict[str, Any]) -> Path:
    actual_path = directory / "actual-ui-tree.json"
    _write_json(
        actual_path,
        {
            "version": 1,
            "screen_id": "checkout",
            "viewport": {"width": 390, "height": 844},
            "root": root,
        },
    )
    return actual_path


def _write_expected(directory: Path, root: dict[str, Any]) -> Path:
    expected_path = directory / "expected-ui-tree.json"
    _write_json(
        expected_path,
        {"version": 1, "screens": [{"screen_id": "checkout", "root": root}]},
    )
    return expected_path


def _capture_receipt(actual_path: Path, **overrides: Any) -> dict[str, Any]:
    digest = hashlib.sha256(actual_path.read_bytes()).hexdigest()
    receipt: dict[str, Any] = {
        "kind": RECEIPT_KIND,
        "version": RECEIPT_VERSION,
        "sourceKind": RUNTIME_CAPTURE,
        "producer": {"name": "web-dom-adapter", "version": "1.4.0"},
        "capturedAt": "2026-07-24T11:59:00Z",
        "target": {"surface": "web", "screen_id": "checkout"},
        "content": {"path": actual_path.name, "sha256": digest},
        "sessionId": "run-2026-07-24-abc123",
    }
    receipt.update(overrides)
    return receipt


def _write_receipt(actual_path: Path, receipt: dict[str, Any]) -> None:
    _write_json(actual_provenance_path(actual_path), receipt)


def _codes(issues: list[dict[str, Any]]) -> set[str]:
    return {issue["code"] for issue in issues}


# ---------------------------------------------------------------------------
# S1 — independent, content-bound, current provenance for a fresh capture.
# ---------------------------------------------------------------------------
def test_valid_runtime_capture_receipt_passes(tmp_path: Path) -> None:
    actual = _write_actual(tmp_path, CAPTURED_ROOT)
    expected = _write_expected(tmp_path, EXPECTED_ROOT)
    _write_receipt(actual, _capture_receipt(actual))

    issues = validate_actual_provenance(
        actual, expected_path=expected, now=NOW, max_age_seconds=3600, allowed_surfaces=["web"]
    )

    assert issues == []


def test_receipt_path_is_deterministic_sidecar() -> None:
    assert actual_provenance_path(Path("/w/actual-ui-tree.json")) == Path(
        "/w/actual-ui-tree.provenance.json"
    )


def test_all_issues_are_error_severity_and_sorted(tmp_path: Path) -> None:
    actual = _write_actual(tmp_path, CAPTURED_ROOT)
    receipt = _capture_receipt(actual)
    receipt["content"]["sha256"] = "0" * 64
    receipt["target"] = {"surface": "ios"}
    _write_receipt(actual, receipt)

    issues = validate_actual_provenance(actual, now=NOW, allowed_surfaces=["web"])

    assert len(issues) >= 2
    assert all(issue["severity"] == "error" for issue in issues)
    assert issues == sorted(issues, key=lambda i: (i["code"], i["path"], i["message"]))


# ---------------------------------------------------------------------------
# S2 — fail-closed rejection paths.
# ---------------------------------------------------------------------------
def test_missing_actual_tree_fails_closed(tmp_path: Path) -> None:
    assert _codes(validate_actual_provenance(tmp_path / "actual-ui-tree.json", now=NOW)) == {
        "provenance.actual.missing"
    }


def test_missing_receipt_fails_closed(tmp_path: Path) -> None:
    actual = _write_actual(tmp_path, CAPTURED_ROOT)
    assert _codes(validate_actual_provenance(actual, now=NOW)) == {"provenance.receipt.missing"}


def test_non_json_receipt_fails_closed(tmp_path: Path) -> None:
    actual = _write_actual(tmp_path, CAPTURED_ROOT)
    actual_provenance_path(actual).write_text("{not json", encoding="utf-8")
    assert _codes(validate_actual_provenance(actual, now=NOW)) == {"provenance.receipt.invalid"}


def test_incomplete_receipt_missing_producer_fails_closed(tmp_path: Path) -> None:
    actual = _write_actual(tmp_path, CAPTURED_ROOT)
    receipt = _capture_receipt(actual)
    del receipt["producer"]
    _write_receipt(actual, receipt)
    assert "provenance.receipt.invalid" in _codes(validate_actual_provenance(actual, now=NOW))


def test_empty_producer_name_fails_closed(tmp_path: Path) -> None:
    actual = _write_actual(tmp_path, CAPTURED_ROOT)
    receipt = _capture_receipt(actual)
    receipt["producer"] = {"name": ""}
    _write_receipt(actual, receipt)
    assert "provenance.receipt.invalid" in _codes(validate_actual_provenance(actual, now=NOW))


def test_unknown_source_kind_fails_closed(tmp_path: Path) -> None:
    actual = _write_actual(tmp_path, CAPTURED_ROOT)
    receipt = _capture_receipt(actual)
    receipt["sourceKind"] = "hand-written"
    _write_receipt(actual, receipt)
    assert "provenance.receipt.invalid" in _codes(validate_actual_provenance(actual, now=NOW))


def test_malformed_sha_pattern_fails_closed(tmp_path: Path) -> None:
    actual = _write_actual(tmp_path, CAPTURED_ROOT)
    receipt = _capture_receipt(actual)
    receipt["content"]["sha256"] = "NOTHEX"
    _write_receipt(actual, receipt)
    assert "provenance.receipt.invalid" in _codes(validate_actual_provenance(actual, now=NOW))


def test_digest_mismatch_fails_closed(tmp_path: Path) -> None:
    actual = _write_actual(tmp_path, CAPTURED_ROOT)
    receipt = _capture_receipt(actual)
    receipt["content"]["sha256"] = "0" * 64
    _write_receipt(actual, receipt)
    assert "provenance.digest.mismatch" in _codes(validate_actual_provenance(actual, now=NOW))


def test_stale_runtime_capture_fails_closed(tmp_path: Path) -> None:
    actual = _write_actual(tmp_path, CAPTURED_ROOT)
    _write_receipt(actual, _capture_receipt(actual, capturedAt="2026-07-01T00:00:00Z"))
    codes = _codes(validate_actual_provenance(actual, now=NOW, max_age_seconds=3600))
    assert "provenance.timestamp.stale" in codes


def test_future_runtime_capture_fails_closed(tmp_path: Path) -> None:
    actual = _write_actual(tmp_path, CAPTURED_ROOT)
    _write_receipt(actual, _capture_receipt(actual, capturedAt="2027-01-01T00:00:00Z"))
    assert "provenance.timestamp.future" in _codes(validate_actual_provenance(actual, now=NOW))


def test_unparseable_timestamp_fails_closed(tmp_path: Path) -> None:
    actual = _write_actual(tmp_path, CAPTURED_ROOT)
    _write_receipt(actual, _capture_receipt(actual, capturedAt="last tuesday"))
    assert "provenance.timestamp.invalid" in _codes(validate_actual_provenance(actual, now=NOW))


def test_incompatible_surface_fails_closed(tmp_path: Path) -> None:
    actual = _write_actual(tmp_path, CAPTURED_ROOT)
    _write_receipt(actual, _capture_receipt(actual, target={"surface": "ios"}))
    codes = _codes(validate_actual_provenance(actual, now=NOW, allowed_surfaces=["web"]))
    assert codes == {"provenance.target.incompatible"}


def test_content_path_naming_another_file_fails_closed(tmp_path: Path) -> None:
    """content.path must name the validated actual file, not a decoy."""
    actual = _write_actual(tmp_path, CAPTURED_ROOT)
    receipt = _capture_receipt(actual)
    receipt["content"]["path"] = "some-other-tree.json"
    _write_receipt(actual, receipt)
    codes = _codes(validate_actual_provenance(actual, now=NOW))
    assert "provenance.content.path_mismatch" in codes


def test_content_path_matching_basename_passes(tmp_path: Path) -> None:
    """A relative or nested content.path whose basename matches is accepted."""
    actual = _write_actual(tmp_path, CAPTURED_ROOT)
    receipt = _capture_receipt(actual)
    receipt["content"]["path"] = "capture/actual-ui-tree.json"
    _write_receipt(actual, receipt)
    assert "provenance.content.path_mismatch" not in _codes(
        validate_actual_provenance(actual, now=NOW)
    )
    assert "provenance.content.path_invalid" not in _codes(
        validate_actual_provenance(actual, now=NOW)
    )


def test_content_path_absolute_fails_closed(tmp_path: Path) -> None:
    actual = _write_actual(tmp_path, CAPTURED_ROOT)
    receipt = _capture_receipt(actual)
    receipt["content"]["path"] = "/etc/actual-ui-tree.json"
    _write_receipt(actual, receipt)
    assert "provenance.content.path_invalid" in _codes(validate_actual_provenance(actual, now=NOW))


def test_content_path_traversal_fails_closed(tmp_path: Path) -> None:
    actual = _write_actual(tmp_path, CAPTURED_ROOT)
    receipt = _capture_receipt(actual)
    receipt["content"]["path"] = "../actual-ui-tree.json"
    _write_receipt(actual, receipt)
    assert "provenance.content.path_invalid" in _codes(validate_actual_provenance(actual, now=NOW))


# ---------------------------------------------------------------------------
# S9 — a max-age window must be finite and strictly positive everywhere.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("bad", PATHOLOGICAL_MAX_AGE)
def test_ensure_valid_max_age_rejects_pathological(bad: float) -> None:
    with pytest.raises(ProvenanceError):
        ensure_valid_max_age_seconds(bad)


def test_ensure_valid_max_age_rejects_bool() -> None:
    with pytest.raises(ProvenanceError):
        ensure_valid_max_age_seconds(True)  # type: ignore[arg-type]


def test_ensure_valid_max_age_accepts_none_and_positive() -> None:
    ensure_valid_max_age_seconds(None)
    ensure_valid_max_age_seconds(1)
    ensure_valid_max_age_seconds(86400.0)


@pytest.mark.parametrize("bad", PATHOLOGICAL_MAX_AGE)
def test_validate_actual_provenance_raises_on_pathological_max_age(
    tmp_path: Path, bad: float
) -> None:
    """The guard fires before any file is read, so a pathological window can
    never silently disarm freshness or crash on a stale/future runtime capture."""
    actual = _write_actual(tmp_path, CAPTURED_ROOT)
    _write_receipt(actual, _capture_receipt(actual, capturedAt="2020-01-01T00:00:00Z"))
    with pytest.raises(ProvenanceError):
        validate_actual_provenance(actual, now=NOW, max_age_seconds=bad)


def test_runtime_capture_derived_from_expected_is_rejected(tmp_path: Path) -> None:
    """A fresh capture byte-identical to the design tree cannot be independent."""
    actual = _write_actual(tmp_path, EXPECTED_ROOT)
    expected = _write_expected(tmp_path, EXPECTED_ROOT)
    _write_receipt(actual, _capture_receipt(actual))
    codes = _codes(validate_actual_provenance(actual, expected_path=expected, now=NOW))
    assert "provenance.actual.derived_from_expected" in codes


def test_require_fresh_rejects_qualified_fixture(tmp_path: Path) -> None:
    actual = _write_actual(tmp_path, EXPECTED_ROOT)
    _write_receipt(
        actual,
        _capture_receipt(
            actual,
            sourceKind=STATIC_DEMO_FIXTURE,
            fixture={"reason": "packaged example"},
        ),
    )
    codes = _codes(validate_actual_provenance(actual, now=NOW, require_fresh=True))
    assert codes == {"provenance.source_kind.inadmissible"}


def test_unqualified_fixture_fails_closed(tmp_path: Path) -> None:
    """A static-demo-fixture without a fixture reason is not explicitly qualified."""
    actual = _write_actual(tmp_path, EXPECTED_ROOT)
    _write_receipt(actual, _capture_receipt(actual, sourceKind=STATIC_DEMO_FIXTURE))
    assert "provenance.receipt.invalid" in _codes(validate_actual_provenance(actual, now=NOW))


def test_runtime_capture_may_not_declare_a_fixture_block(tmp_path: Path) -> None:
    """A fixture block on a runtime capture is contradictory and rejected."""
    actual = _write_actual(tmp_path, CAPTURED_ROOT)
    _write_receipt(actual, _capture_receipt(actual, fixture={"reason": "masquerade"}))
    assert "provenance.receipt.invalid" in _codes(validate_actual_provenance(actual, now=NOW))


# ---------------------------------------------------------------------------
# S3 — qualified fixture is admissible and exempt from freshness.
# ---------------------------------------------------------------------------
def test_qualified_fixture_derived_from_expected_is_accepted(tmp_path: Path) -> None:
    actual = _write_actual(tmp_path, EXPECTED_ROOT)
    expected = _write_expected(tmp_path, EXPECTED_ROOT)
    _write_receipt(
        actual,
        _capture_receipt(
            actual,
            sourceKind=STATIC_DEMO_FIXTURE,
            capturedAt="2020-01-01T00:00:00Z",
            fixture={"reason": "packaged example, not fresh runtime evidence"},
        ),
    )
    issues = validate_actual_provenance(actual, expected_path=expected, now=NOW, max_age_seconds=1)
    assert issues == []


def test_source_kind_constants_are_locked() -> None:
    assert KNOWN_SOURCE_KINDS == (RUNTIME_CAPTURE, STATIC_DEMO_FIXTURE)


# ---------------------------------------------------------------------------
# S3 — Penflow core stays runtime-agnostic.
# ---------------------------------------------------------------------------
def test_actual_provenance_module_imports_no_runtime() -> None:
    module = Path(__file__).resolve().parent.parent / "penflow" / "actual_provenance.py"
    tree = ast.parse(module.read_text(encoding="utf-8"), filename=str(module))
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
    forbidden = ("appium", "browser_use", "playwright", "selenium", "mcp__pencil")
    for token in forbidden:
        assert all(not name.startswith(token) for name in imports)


@pytest.mark.parametrize("source_kind", KNOWN_SOURCE_KINDS)
def test_digest_binds_every_source_kind(tmp_path: Path, source_kind: str) -> None:
    """Byte tampering of the actual tree is caught regardless of source kind."""
    actual = _write_actual(tmp_path, CAPTURED_ROOT)
    overrides: dict[str, Any] = {"sourceKind": source_kind}
    if source_kind == STATIC_DEMO_FIXTURE:
        overrides["fixture"] = {"reason": "packaged example"}
    _write_receipt(actual, _capture_receipt(actual, **overrides))
    actual.write_text(actual.read_text(encoding="utf-8") + " ", encoding="utf-8")
    assert "provenance.digest.mismatch" in _codes(validate_actual_provenance(actual, now=NOW))
