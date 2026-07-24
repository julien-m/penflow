# @spec(FR-008)
"""Feature 054 — direct unit coverage for `penflow/demo.py`.

Invariant protected: `build_demo` is a deterministic fixture generator — it
writes the complete C14 artifact set into the target directory, returns a
mapping that lists every written file, produces a PASS compare report at the
strict threshold, and two runs differ only by the output directory path
embedded in source markers.
"""

from __future__ import annotations

import json
from pathlib import Path

from penflow.compare import STRICT_THRESHOLD
from penflow.demo import build_demo
from penflow.evidence import validate_visual_evidence

EXPECTED_FILES = {
    "flow-ui-contract/contract.json",
    "flow-ui-contract/flows/checkout.md",
    "flow-ui-contract/screens/checkout.md",
    "ui.visual.pen",
    "ui.pen",
    "semantic-ui-tree.json",
    "pencil-context-map.json",
    "expected-ui-tree.json",
    "actual-ui-tree.json",
    "actual-ui-tree.provenance.json",
    ".mockup-validation/visual-evidence/checkoutScreen.png",
    ".mockup-validation/visual-evidence/layout-snapshot.json",
    ".mockup-validation/visual-evidence/manifest.json",
    ".mockup-validation/visual-evidence/vision-report.json",
    "code-ir.json",
    "compare-report.json",
    "review-report.json",
    "fix-report.json",
    "Checkout.jsx",
    "CheckoutView.swift",
    "checkout.rs",
}


def test_build_demo_writes_the_full_artifact_set(tmp_path: Path) -> None:
    files = build_demo(tmp_path)
    assert set(files) == EXPECTED_FILES
    for relative, absolute in files.items():
        path = Path(absolute)
        assert path.is_file(), relative
        assert path.relative_to(tmp_path).as_posix() == relative
        assert path.stat().st_size > 0, relative


def test_build_demo_compare_report_passes_at_strict_threshold(tmp_path: Path) -> None:
    build_demo(tmp_path)
    report = json.loads((tmp_path / "compare-report.json").read_text(encoding="utf-8"))
    assert report["status"] == "PASS"
    assert report["score"] >= STRICT_THRESHOLD
    assert report["issues"] == []


def test_build_demo_actual_tree_keeps_the_external_runtime_shape(tmp_path: Path) -> None:
    build_demo(tmp_path)
    actual = json.loads((tmp_path / "actual-ui-tree.json").read_text(encoding="utf-8"))
    assert actual["version"] == 1
    assert actual["screen_id"] == "checkout"
    assert actual["viewport"] == {"width": 390.0, "height": 844.0}
    assert actual["root"]["id"] == "checkout"


def test_build_demo_actual_provenance_receipt_is_qualified_fixture(tmp_path: Path) -> None:
    """Invariant: the demo actual is derived from expected, so its receipt must
    be an explicitly qualified static-demo-fixture bound to the actual bytes and
    accepted by the validator — but rejected the moment freshness is required."""
    import hashlib

    from penflow.actual_provenance import actual_provenance_path, validate_actual_provenance

    build_demo(tmp_path)
    actual_path = tmp_path / "actual-ui-tree.json"
    receipt = json.loads(actual_provenance_path(actual_path).read_text(encoding="utf-8"))

    assert receipt["kind"] == "penflow-actual-provenance"
    assert receipt["sourceKind"] == "static-demo-fixture"
    assert receipt["fixture"]["reason"]
    assert receipt["producer"]["name"] == "penflow.demo"
    assert receipt["target"]["surface"] == "web"
    assert receipt["content"]["sha256"] == hashlib.sha256(actual_path.read_bytes()).hexdigest()

    expected_path = tmp_path / "expected-ui-tree.json"
    assert validate_actual_provenance(actual_path, expected_path=expected_path) == []
    inadmissible = validate_actual_provenance(
        actual_path, expected_path=expected_path, require_fresh=True
    )
    assert [issue["code"] for issue in inadmissible] == ["provenance.source_kind.inadmissible"]


def test_build_demo_visual_evidence_packet_is_self_contained(tmp_path: Path) -> None:
    build_demo(tmp_path)
    evidence = tmp_path / ".mockup-validation" / "visual-evidence"
    manifest = json.loads((evidence / "manifest.json").read_text(encoding="utf-8"))
    vision = json.loads((evidence / "vision-report.json").read_text(encoding="utf-8"))

    assert manifest["renderer"] == "static-demo-fixture"
    assert "Synthetic example data" in manifest["screens"][0]["notes"]
    assert vision["renderer"] == "static-demo-fixture"
    assert vision["model"] == "static-demo-fixture"
    assert vision["generated_by"] == "penflow.demo.static-demo-fixture"
    issues = validate_visual_evidence(
        evidence,
        expected_tree_path=tmp_path / "expected-ui-tree.json",
    )
    assert issues == []


def test_build_demo_visual_evidence_fails_when_packaged_png_is_missing(tmp_path: Path) -> None:
    build_demo(tmp_path)
    evidence = tmp_path / ".mockup-validation" / "visual-evidence"
    (evidence / "checkoutScreen.png").unlink()

    issues = validate_visual_evidence(
        evidence,
        expected_tree_path=tmp_path / "expected-ui-tree.json",
    )

    assert "evidence.png.missing" in {issue["code"] for issue in issues}
    assert "evidence.vision_input.missing" in {issue["code"] for issue in issues}


def test_build_demo_visual_evidence_fails_when_packaged_png_is_corrupt(tmp_path: Path) -> None:
    build_demo(tmp_path)
    evidence = tmp_path / ".mockup-validation" / "visual-evidence"
    (evidence / "checkoutScreen.png").write_bytes(b"corrupt-static-demo-fixture")

    issues = validate_visual_evidence(
        evidence,
        expected_tree_path=tmp_path / "expected-ui-tree.json",
    )

    assert "evidence.png.sha_mismatch" in {issue["code"] for issue in issues}
    assert "evidence.vision_input.sha_mismatch" in {issue["code"] for issue in issues}


def test_build_demo_codegen_files_target_the_checkout_screen(tmp_path: Path) -> None:
    build_demo(tmp_path)
    assert "export function Checkout()" in (tmp_path / "Checkout.jsx").read_text(encoding="utf-8")
    assert "struct CheckoutView: View" in (tmp_path / "CheckoutView.swift").read_text(
        encoding="utf-8"
    )
    assert "pub fn Checkout()" in (tmp_path / "checkout.rs").read_text(encoding="utf-8")


def test_build_demo_is_deterministic_modulo_output_directory(tmp_path: Path) -> None:
    first = tmp_path / "a"
    second = tmp_path / "b"
    files_first = build_demo(first)
    files_second = build_demo(second)
    assert set(files_first) == set(files_second)
    for relative in files_first:
        bytes_first = Path(files_first[relative]).read_bytes()
        bytes_second = Path(files_second[relative]).read_bytes()
        normalized = bytes_second.replace(str(second).encode(), str(first).encode())
        assert normalized == bytes_first, relative


def test_build_demo_reruns_into_same_directory_are_byte_identical(tmp_path: Path) -> None:
    files = build_demo(tmp_path)
    snapshot = {
        relative: Path(absolute).read_bytes() for relative, absolute in sorted(files.items())
    }
    build_demo(tmp_path)
    for relative, content in snapshot.items():
        assert Path(files[relative]).read_bytes() == content, relative
