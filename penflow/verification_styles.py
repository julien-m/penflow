"""Normalize equivalent measured style representations without changing their values."""

import re
from typing import Any

from .color import parse_color
from .verification_files import VerificationInputError


def resolve_design_variables(
    tree: dict[str, Any], variables: dict[str, Any], *, pen_data: dict[str, Any] | None = None
) -> None:
    """Resolve only exact native variable references from the authenticated Pencil source."""
    themes = _source_themes(pen_data or {})
    pending = [screen["root"] for screen in tree["screens"]]
    while pending:
        node = pending.pop()
        node["visual"] = _resolved_value(
            node.get("visual", {}), variables, set(), themes.get(node.get("pencil_id"), {})
        )
        pending.extend(node.get("children", []))


def _source_themes(pen: dict[str, Any]) -> dict[str, dict[str, str]]:
    """Read explicitly selected node themes; never infer selection from runtime colors."""
    result = {}
    pending = list(pen.get("children", []))
    while pending:
        node = pending.pop()
        theme = node.get("theme", {})
        if not isinstance(theme, dict) or any(
            not isinstance(key, str) or not isinstance(value, str) for key, value in theme.items()
        ):
            raise VerificationInputError("verification.style.theme_invalid")
        result[node["id"]] = theme
        pending.extend(node.get("children", []))
    return result


def _selected_value(value: Any, theme: dict[str, str]) -> Any:
    if not isinstance(value, list):
        return value
    candidates = []
    for entry in value:
        if (
            not isinstance(entry, dict)
            or set(entry) != {"value", "theme"}
            or not isinstance(entry["theme"], dict)
        ):
            raise VerificationInputError("verification.style.themed_value_invalid")
        if entry["theme"] and all(theme.get(key) == item for key, item in entry["theme"].items()):
            candidates.append(entry["value"])
    if len(candidates) != 1:
        raise VerificationInputError("verification.style.variable_unresolved_or_ambiguous")
    return candidates[0]


def _resolved_value(
    value: Any, variables: dict[str, Any], seen: set[str], theme: dict[str, str]
) -> Any:
    if isinstance(value, dict):
        return {key: _resolved_value(item, variables, seen, theme) for key, item in value.items()}
    if isinstance(value, list):
        return [_resolved_value(item, variables, seen, theme) for item in value]
    if not isinstance(value, str) or not value.startswith("$"):
        return value
    name = value[1:]
    record = variables.get(name)
    if name in seen or not isinstance(record, dict) or "value" not in record:
        raise VerificationInputError("verification.style.variable_unresolved_or_ambiguous")
    return _resolved_value(_selected_value(record["value"], theme), variables, seen | {name}, theme)


def normalize_observed_styles(tree: dict[str, Any]) -> None:
    """Canonicalize equivalent CSS/native values on a private comparison copy."""
    pending = [screen["root"] for screen in tree["screens"]]
    while pending:
        node = pending.pop()
        visual = node.get("visual", {})
        _normalize_border(visual)
        for key in ("fill", "stroke"):
            value = visual.get(key)
            if isinstance(value, str):
                color = parse_color(value) or _css_color(value)
                if color is not None:
                    visual[key] = "#" + "".join(f"{channel:02x}" for channel in color)
        family = visual.get("fontFamily")
        if isinstance(family, str):
            visual["fontFamily"] = family.split(",")[0].strip().strip("\"'").casefold()
        weight = visual.get("fontWeight")
        if isinstance(weight, (str, int, float)):
            visual["fontWeight"] = {"normal": "400", "bold": "700"}.get(str(weight), str(weight))
        pending.extend(node.get("children", []))


def _normalize_border(visual: dict[str, Any]) -> None:
    """Preserve equivalent old/new native border widths and reject conflicting aliases."""
    from .verification_assertions import json_values_equal

    stroke = visual.get("stroke")
    widths = [visual[key] for key in ("strokeWidth", "strokeThickness") if key in visual]
    if isinstance(stroke, dict) and set(stroke).issubset({"fill", "thickness"}):
        if "thickness" in stroke:
            widths.append(stroke["thickness"])
        if "fill" in stroke:
            visual["stroke"] = stroke["fill"]
    if widths:
        if any(not json_values_equal(widths[0], value) for value in widths[1:]):
            raise VerificationInputError("verification.style.conflicting_border_width")
        visual["strokeWidth"] = widths[0]
        visual.pop("strokeThickness", None)


def _css_color(value: str) -> tuple[int, int, int, int] | None:
    """Parse the bounded numeric rgb/rgba forms emitted by computed browser styles."""
    if len(value) > 80:
        return None
    matched = re.fullmatch(
        r"rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})(?:\s*,\s*(0(?:\.\d+)?|1(?:\.0+)?))?\s*\)",
        value,
    )
    if matched is None:
        return None
    red, green, blue = (int(matched[index]) for index in (1, 2, 3))
    if max(red, green, blue) > 255:
        return None
    alpha = round(float(matched[4]) * 255) if matched[4] is not None else 255
    return red, green, blue, alpha
