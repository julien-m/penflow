# @spec AC-004: writers share the pen_schema write version — .specs/features/078-pen-dev-operator-compatibility/spec.md#ac-004
# @spec AC-005: intrinsic text uses an integer major/minor minimum — .specs/features/078-pen-dev-operator-compatibility/spec.md#ac-005
"""One module owns every `.pen` version Penflow writes or requires."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from penflow import pen_schema
from penflow.contracts import pencil_draft_from_screen
from penflow.demo_data import visual_pen
from penflow.doctor_files import EMPTY_PEN_BYTES
from penflow.semantic_draft import PEN_VERSION
from penflow.verification_geometry import intrinsic_text_ids

PENFLOW_DIR = Path(__file__).resolve().parents[1] / "penflow"


def test_doctor_draft_demo_and_contract_writers_share_the_write_version() -> None:
    assert json.loads(EMPTY_PEN_BYTES)["version"] == pen_schema.PEN_WRITE_VERSION
    assert PEN_VERSION == pen_schema.PEN_WRITE_VERSION
    assert visual_pen()["version"] == pen_schema.PEN_WRITE_VERSION
    assert pencil_draft_from_screen({"id": "root"})["version"] == pen_schema.PEN_WRITE_VERSION


@pytest.mark.parametrize(
    "module",
    [
        "doctor_files.py",
        "semantic_draft.py",
        "demo_data.py",
        "contracts.py",
        "verification_geometry.py",
    ],
)
def test_writers_carry_no_private_version_literal(module: str) -> None:
    source = (PENFLOW_DIR / module).read_text(encoding="utf-8")
    for literal in ('"1.0"', '"2.11"', '"2.14"', '"2.17"'):
        assert literal not in source


@pytest.mark.parametrize(
    ("version", "expected"),
    [
        ("2.9", False),
        ("2.11", False),
        ("2.14", True),
        ("2.17", True),
        ("3.0", True),
        ("beta", False),
        ("2.14.1", False),
        (2.14, False),
        (None, False),
    ],
    ids=["2.9", "2.11", "2.14", "2.17", "3.0", "beta", "2.14.1", "float-2.14", "missing"],
)
def test_native_intrinsic_text_minimum_compares_integer_major_minor(
    version: object, expected: bool
) -> None:
    assert pen_schema.supports_native_intrinsic_text(version) is expected
    pen: dict[str, object] = {"children": [{"id": "label", "type": "text"}]}
    if version is not None:
        pen["version"] = version
    assert bool(intrinsic_text_ids(pen)) is expected


def test_parse_pen_version_orders_two_digit_minors_numerically() -> None:
    assert pen_schema.parse_pen_version("2.9") == (2, 9)
    assert (
        (2, 9)
        < pen_schema.NATIVE_INTRINSIC_TEXT_MIN_VERSION
        == pen_schema.parse_pen_version("2.14")
    )
