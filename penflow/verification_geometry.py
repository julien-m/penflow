"""Authenticate native layout and normalize it to the logical-screen coordinate space."""

from typing import Any, cast
import math

from .pen_schema import supports_native_intrinsic_text
from .verification_files import VerificationInputError
from .verification_json import canonical_bytes
from .verification_snapshot import VerificationSnapshot
from .verification_transport import decode_native_observation_text, native_layout_children


def intrinsic_text_ids(pen: dict[str, Any]) -> frozenset[str]:
    """Select native text (version >= 2.14) with an intrinsic dimension (auto width or wrapped height).

    Callers must separately authenticate complete native geometry before using this
    source property to replace a text-width estimate with its measured intrinsic width.
    """
    if not supports_native_intrinsic_text(pen.get("version")):
        return frozenset()
    result = set()
    pending = list(pen.get("children", []))
    while pending:
        node = pending.pop()
        if node.get("type") == "text" and node.get("textGrowth", "auto") in {"auto", "fixed-width"}:
            result.add(node["id"])
        pending.extend(node.get("children", []))
    return frozenset(result)


def load_native_geometry(
    snapshot: VerificationSnapshot, expected: dict[str, Any]
) -> dict[str, Any]:
    """Bind exact native measurements to the current document before any comparison."""
    layout = snapshot.object(".mockup-validation/visual-evidence/layout-snapshot.json")
    keys = {"kind", "version", "coordinate_space", "source", "observation", "children"}
    if (
        set(layout) not in (keys, keys | {"screens"})
        or layout["kind"] != "penflow-native-layout"
        or type(layout["version"]) is not int
        or layout["version"] != 1
        or layout["coordinate_space"] != "parent-relative"
    ):
        raise VerificationInputError("verification.geometry.envelope_invalid")
    snapshot.reader.reference(layout["source"])
    if snapshot.reader.path(layout["source"]["path"]) != snapshot.workspace / "ui.pen":
        raise VerificationInputError("verification.geometry.foreign_document")
    observation = snapshot.reader.object(snapshot.reader.reference(layout["observation"]))
    if not isinstance(observation.get("content"), list):
        raise VerificationInputError("verification.geometry.observation_mismatch")
    texts = [
        item.get("text")
        for item in observation.get("content", [])
        if isinstance(item, dict) and item.get("type") == "text"
    ]
    if len(texts) != 1 or not isinstance(texts[0], str):
        raise VerificationInputError("verification.geometry.observation_mismatch")
    observed = native_layout_children(decode_native_observation_text(texts[0]))
    if canonical_bytes(observed) != canonical_bytes(layout["children"]):
        raise VerificationInputError("verification.geometry.observation_mismatch")
    normalize_native_geometry(expected, layout["children"])
    if "screens" in layout:
        screens = [
            {
                "screen_id": screen["screen_id"],
                "pencil_node_id": screen["pencil_id"],
                "width": screen["root"]["bbox"]["width"],
                "height": screen["root"]["bbox"]["height"],
            }
            for screen in expected["screens"]
        ]
        if layout["screens"] != screens:
            raise VerificationInputError("verification.geometry.screen_projection_mismatch")
    return layout


def normalize_native_geometry(expected: dict[str, Any], observed: Any) -> None:
    """Accumulate observed parent offsets, removing only each root's canvas origin."""
    if not isinstance(observed, list):
        raise VerificationInputError("verification.geometry.roots_invalid")
    native = _native_index(observed)
    expected_ids = set()
    for screen in expected["screens"]:
        pending = [(screen["root"], None)]
        while pending:
            node, parent = pending.pop()
            key = node.get("pencil_id")
            if key in expected_ids or key not in native or native[key][0] != parent:
                raise VerificationInputError("verification.geometry.identity_or_parent_mismatch")
            expected_ids.add(key)
            node["bbox"] = dict(native[key][1])
            pending.extend((child, key) for child in node.get("children", []))
        screen["viewport"] = dict(screen["root"]["bbox"])
    if expected_ids != set(native):
        raise VerificationInputError("verification.geometry.extra_node")


def _native_index(roots: list[Any]) -> dict[str, tuple[str | None, dict[str, float]]]:
    result: dict[str, tuple[str | None, dict[str, float]]] = {}
    pending: list[tuple[Any, str | None, float, float]] = [(node, None, 0.0, 0.0) for node in roots]
    while pending:
        node, parent, x, y = pending.pop()
        if (
            not isinstance(node, dict)
            or not isinstance(node.get("id"), str)
            or not node["id"]
            or node["id"] in result
        ):
            raise VerificationInputError("verification.geometry.node_invalid_or_duplicate")
        bbox = {key: node.get(key) for key in ("x", "y", "width", "height")}
        for key, value in bbox.items():
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or abs(value) > 1e12
                or not math.isfinite(value)
                or (key in {"width", "height"} and value < 0)
            ):
                raise VerificationInputError("verification.geometry.measurement_invalid")
        measured = {key: float(cast(int | float, value)) for key, value in bbox.items()}
        measured["x"] = x + measured["x"] if parent is not None else 0.0
        measured["y"] = y + measured["y"] if parent is not None else 0.0
        if any(not math.isfinite(value) or abs(value) > 1e12 for value in measured.values()):
            raise VerificationInputError("verification.geometry.accumulated_measurement_invalid")
        result[node["id"]] = parent, measured
        children = node.get("children", [])
        if not isinstance(children, list):
            raise VerificationInputError("verification.geometry.children_invalid")
        pending.extend((child, node["id"], measured["x"], measured["y"]) for child in children)
    return result
