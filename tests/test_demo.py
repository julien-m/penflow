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
        text_first = Path(files_first[relative]).read_text(encoding="utf-8")
        text_second = Path(files_second[relative]).read_text(encoding="utf-8")
        normalized = text_second.replace(str(second), str(first))
        assert normalized == text_first, relative


def test_build_demo_reruns_into_same_directory_are_byte_identical(tmp_path: Path) -> None:
    files = build_demo(tmp_path)
    snapshot = {
        relative: Path(absolute).read_bytes() for relative, absolute in sorted(files.items())
    }
    build_demo(tmp_path)
    for relative, content in snapshot.items():
        assert Path(files[relative]).read_bytes() == content, relative
