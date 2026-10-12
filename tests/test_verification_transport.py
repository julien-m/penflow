# @spec FR-006: Native geometry accepts the pen.dev execute Print transport (2026-10-10 check gap G1) — .specs/features/077-complete-verification-workflow/spec.md#fr-006
"""Recorded pen.dev `execute` responses become native layout without relaxing identity."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from penflow.verification_files import InputReader, VerificationInputError
from penflow.verification_geometry import load_native_geometry
from penflow.verification_json import digest
from penflow.verification_snapshot import VerificationSnapshot
from penflow.verification_transport import (
    decode_native_observation_text,
    native_layout_children,
)

FIXTURES = Path(__file__).parent / "fixtures" / "pen-mcp"
# SHA-256 of the authentic pen.dev 1.2.16 response cited by the 2026-10-10 077 check.
RECORDED_SHA256 = "c0719c4978eca7be95dfe4ba784e0e18b71b058ff977e5baf5508688eac80098"
EXPECTED_CHILDREN = [
    {
        "id": "o5QKT",
        "x": 0,
        "y": 0,
        "width": 900,
        "height": 680,
        "children": [
            {
                "id": "iTRjC",
                "x": 32,
                "y": 32,
                "width": 836,
                "height": 34,
                "children": [{"id": "vrFnK", "x": 0, "y": 0, "width": 269, "height": 34}],
            }
        ],
    }
]


def recorded_text(name: str = "execute-native-get-layout.json") -> str:
    (block,) = json.loads((FIXTURES / name).read_text(encoding="utf-8"))["content"]
    return block["text"]


def recorded_envelope() -> dict[str, Any]:
    return decode_native_observation_text(recorded_text())


def print_response(*lines: str) -> str:
    return "OK\n\n## Print output\n" + "".join(f"{line}  \n" for line in lines)


def test_recorded_print_response_is_the_authentic_observation() -> None:
    assert digest((FIXTURES / "execute-native-get-layout.json").read_bytes()) == RECORDED_SHA256
    assert recorded_text().startswith("OK\n\n## Print output\n{")


def test_recorded_measurement_envelope_rebuilds_parent_relative_children() -> None:
    assert native_layout_children(recorded_envelope()) == EXPECTED_CHILDREN


def test_printed_children_list_and_legacy_bare_json_decode_identically() -> None:
    printed = decode_native_observation_text(print_response(json.dumps(EXPECTED_CHILDREN)))
    legacy = decode_native_observation_text(json.dumps(EXPECTED_CHILDREN))
    assert native_layout_children(printed) == native_layout_children(legacy) == EXPECTED_CHILDREN


def test_trailing_sections_after_print_output_are_ignored() -> None:
    text = print_response("[]") + "\n## Created nodes\nHeader=abc\n"
    assert decode_native_observation_text(text) == []


@pytest.mark.parametrize(
    "text",
    [
        pytest.param(recorded_text("execute-multi-print-probe.json"), id="recorded-multi-print"),
        pytest.param("Error: A file needs to be open in the editor", id="failed-call"),
        pytest.param("OK\n\nno print section\n", id="no-print-section"),
        pytest.param(print_response("[]") + "## Print output\n[]\n", id="duplicate-section"),
        pytest.param(print_response(), id="empty-print"),
        pytest.param(print_response("[NaN]"), id="non-finite"),
        pytest.param(print_response('{"a": 1, "a": 2}'), id="duplicate-member"),
        pytest.param(print_response("Exported /tmp/x.png"), id="not-json"),
    ],
)
def test_ambiguous_or_failed_transport_is_rejected(text: str) -> None:
    with pytest.raises(VerificationInputError) as raised:
        decode_native_observation_text(text)
    assert str(raised.value) == "verification.geometry.transport_invalid"


def _mutate(change: str) -> dict[str, Any]:
    envelope = deepcopy(recorded_envelope())
    measurements = envelope["measurements"]
    if change == "missing":
        measurements.pop()
    elif change == "extra":
        measurements.append(dict(measurements[-1], id="ghost"))
    elif change == "parent":
        measurements[2]["parent_id"] = "o5QKT"
    elif change == "context":
        measurements[1]["context"] = "classification=semantic;semantic_id=other"
    elif change == "duplicate":
        measurements.append(deepcopy(measurements[0]))
    elif change == "bounds":
        del measurements[0]["bounds"]["width"]
    elif change == "kind":
        envelope["kind"] = "penflow-native-layout"
    elif change == "coordinate_space":
        envelope["coordinate_space"] = "absolute"
    elif change == "duplicate_node":
        envelope["roots"].append(deepcopy(envelope["roots"][0]))
    return envelope


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ("missing", "identity_or_parent_mismatch"),
        ("extra", "identity_or_parent_mismatch"),
        ("parent", "identity_or_parent_mismatch"),
        ("context", "identity_or_parent_mismatch"),
        ("duplicate", "measurement_invalid"),
        ("bounds", "measurement_invalid"),
        ("kind", "native_envelope_invalid"),
        ("coordinate_space", "native_envelope_invalid"),
        ("duplicate_node", "node_invalid_or_duplicate"),
    ],
)
def test_measurement_envelope_defects_block(change: str, code: str) -> None:
    with pytest.raises(VerificationInputError) as raised:
        native_layout_children(_mutate(change))
    assert str(raised.value) == f"verification.geometry.{code}"


def test_scalar_observation_is_not_a_layout() -> None:
    with pytest.raises(VerificationInputError) as raised:
        native_layout_children("o5QKT")
    assert str(raised.value) == "verification.geometry.native_envelope_invalid"


def _workspace(root: Path, children: list[Any]) -> tuple[VerificationSnapshot, dict[str, Any]]:
    document = root / "ui.pen"
    document.write_text("{}")
    observation = root / "observed.json"
    observation.write_bytes((FIXTURES / "execute-native-get-layout.json").read_bytes())
    layout = {
        "kind": "penflow-native-layout",
        "version": 1,
        "coordinate_space": "parent-relative",
        "source": {"path": str(document), "sha256": digest(document.read_bytes())},
        "observation": {"path": str(observation), "sha256": digest(observation.read_bytes())},
        "children": children,
    }
    path = root / ".mockup-validation/visual-evidence/layout-snapshot.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(layout))

    def node(identifier: str, kids: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "pencil_id": identifier,
            "bbox": {"x": 0, "y": 0, "width": 0, "height": 0},
            "children": kids,
        }

    root_node = node("o5QKT", [node("iTRjC", [node("vrFnK", [])])])
    expected = {"screens": [{"screen_id": "microphone", "pencil_id": "o5QKT", "root": root_node}]}
    return VerificationSnapshot(InputReader(root), root, {}, {}, {}), expected


def test_load_native_geometry_accepts_the_recorded_execute_observation(tmp_path: Path) -> None:
    snapshot, expected = _workspace(tmp_path, EXPECTED_CHILDREN)
    load_native_geometry(snapshot, expected)
    title = expected["screens"][0]["root"]["children"][0]["children"][0]
    assert title["bbox"] == {"x": 32.0, "y": 32.0, "width": 269.0, "height": 34.0}
    snapshot.reader.recheck()


def test_load_native_geometry_rejects_children_differing_from_the_observation(
    tmp_path: Path,
) -> None:
    children: list[Any] = deepcopy(EXPECTED_CHILDREN)
    children[0]["children"][0]["width"] = 900
    snapshot, expected = _workspace(tmp_path, children)
    with pytest.raises(VerificationInputError) as raised:
        load_native_geometry(snapshot, expected)
    assert str(raised.value) == "verification.geometry.observation_mismatch"
