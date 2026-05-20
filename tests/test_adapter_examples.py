# @spec FR-007: Parametrised in-process pytest module — .specs/features/038-runtime-adapter-guides/spec.md#fr-007
"""In-process validation of the C13 adapter example fixtures (feature 038).

Constraints (enforced by FR-007 + AC-008):

- No ``subprocess`` — Penflow CLI is never spawned, no browser / simulator /
  Node / Metro is started. The test only reads JSON from disk and calls
  in-process Python functions from :mod:`penflow.tree`.
- No new Python dependency — uses only ``pytest`` (existing), ``pathlib``
  (stdlib), ``json`` (stdlib) and ``penflow.tree`` (shipped by feature 037).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from penflow.tree import load_tree, validate_actual_tree

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = [
    ROOT / "examples" / "adapters" / "web-dom" / "actual-ui-tree.json",
    ROOT / "examples" / "adapters" / "swiftui-xctest" / "actual-ui-tree.json",
    ROOT / "examples" / "adapters" / "react-native" / "actual-ui-tree.json",
]


# @spec FR-004: web-dom fixture validation, FR-005: SwiftUI fixture validation, FR-006: RN fixture validation — .specs/features/038-runtime-adapter-guides/spec.md#fr-004
@pytest.mark.parametrize("fixture", FIXTURES, ids=lambda p: p.parent.name)
def test_adapter_example_passes_schema_validation(fixture: Path) -> None:
    assert fixture.exists(), f"missing adapter fixture: {fixture}"
    tree = load_tree(fixture)
    assert validate_actual_tree(tree, schema=True) == []


@pytest.mark.parametrize("fixture", FIXTURES, ids=lambda p: p.parent.name)
def test_adapter_example_passes_structural_validation(fixture: Path) -> None:
    tree = load_tree(fixture)
    assert validate_actual_tree(tree) == []


# @spec FR-004: deterministic fixture bytes — .specs/features/038-runtime-adapter-guides/spec.md#fr-004
@pytest.mark.parametrize("fixture", FIXTURES, ids=lambda p: p.parent.name)
def test_adapter_example_is_byte_deterministic(fixture: Path) -> None:
    """Re-serialising the fixture (sorted keys, indent=2, trailing newline)
    must round-trip to byte-identical content on disk. Guards against
    accidental drift from the C12 determinism rule (feature 037)."""
    original = fixture.read_bytes()
    tree = json.loads(original.decode("utf-8"))
    reserialised = (json.dumps(tree, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode(
        "utf-8"
    )
    assert original == reserialised, f"non-deterministic fixture: {fixture}"
