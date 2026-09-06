"""File-bound layout evidence rejects malformed references and substituted projections."""

import json
from copy import deepcopy
from pathlib import Path

import pytest

from penflow.verification_files import InputReader, VerificationInputError
from penflow.verification_geometry import load_native_geometry
from penflow.verification_json import digest
from penflow.verification_snapshot import VerificationSnapshot
from penflow.verification_native import bind_evidence_directory


def _fixture(root: Path) -> tuple[VerificationSnapshot, dict, dict]:
    document = root / "ui.pen"
    document.write_text("{}")
    children = [{"id": "native", "x": 100, "y": 0, "width": 400, "height": 300}]
    observation = root / "observed.json"
    observation.write_text(
        json.dumps({"content": [{"type": "text", "text": json.dumps(children)}]})
    )
    layout = {
        "kind": "penflow-native-layout",
        "version": 1,
        "coordinate_space": "parent-relative",
        "source": {"path": str(document), "sha256": digest(document.read_bytes())},
        "observation": {"path": str(observation), "sha256": digest(observation.read_bytes())},
        "children": children,
        "screens": [
            {"screen_id": "logical", "pencil_node_id": "native", "width": 400, "height": 300}
        ],
    }
    expected = {
        "screens": [
            {
                "screen_id": "logical",
                "pencil_id": "native",
                "root": {
                    "pencil_id": "native",
                    "bbox": {"x": 0, "y": 0, "width": 0, "height": 0},
                },
            }
        ]
    }
    snapshot = VerificationSnapshot(InputReader(root), root, {}, {}, {})
    return snapshot, expected, layout


@pytest.mark.parametrize("mutation", [None, "source", "screen", "children", "extra"])
def test_native_layout_joins_exact_files_and_screen_projection(
    tmp_path: Path, mutation: str | None
) -> None:
    """Only the measured source, raw observation and exact derived screen index agree."""
    snapshot, expected, layout = _fixture(tmp_path)
    changed = deepcopy(layout)
    if mutation == "source":
        changed["source"] = {}
    elif mutation == "screen":
        changed["screens"][0]["screen_id"] = "foreign"
    elif mutation == "children":
        changed["children"][0]["width"] = 999
    elif mutation == "extra":
        changed["passed"] = True
    path = tmp_path / ".mockup-validation/visual-evidence/layout-snapshot.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(changed))
    if mutation is None:
        load_native_geometry(snapshot, expected)
        assert expected["screens"][0]["root"]["bbox"]["width"] == 400
        snapshot.reader.recheck()
    else:
        with pytest.raises(VerificationInputError):
            load_native_geometry(snapshot, expected)


@pytest.mark.parametrize("raw", ['[{"screen_id":"screen"}]', "[NaN]"])
def test_evidence_inventory_accepts_json_arrays_without_relaxing_json(
    tmp_path: Path, raw: str
) -> None:
    """Reference manifests are arrays; their dedicated validator owns their shape."""
    path = tmp_path / "references-manifest.json"
    path.write_text(raw)
    snapshot = VerificationSnapshot(InputReader(tmp_path), tmp_path, {}, {}, {})
    if raw == "[NaN]":
        with pytest.raises(ValueError):
            bind_evidence_directory(snapshot, tmp_path)
    else:
        bind_evidence_directory(snapshot, tmp_path)
        snapshot.reader.recheck()
