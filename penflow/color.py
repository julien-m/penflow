"""Hex color parsing and pen variable resolution helpers."""

from __future__ import annotations

import re
from typing import Any

# Matches an entire supported hex color literal (#RGB, #RRGGBB, #RRGGBBAA)
# only; partial matches and named/rgb() colors intentionally fail.
_HEX_COLOR_RE = re.compile(r"#(?:[0-9A-Fa-f]{3}|[0-9A-Fa-f]{6}|[0-9A-Fa-f]{8})\Z")


def parse_color(value: str) -> tuple[int, int, int, int] | None:
    # @spec FR-002: Hex color parsing — .specs/features/046-lint-design-tokens/spec.md#fr-002
    """Parse a hex color string into a normalized RGBA tuple.

    Args:
        value: Candidate color string (`#RGB`, `#RRGGBB`, or `#RRGGBBAA`).

    Returns:
        `(r, g, b, a)` with each channel in 0-255, or `None` when the value
        is not a supported hex color.
    """
    if not isinstance(value, str) or not _HEX_COLOR_RE.match(value):
        return None
    digits = value[1:]
    if len(digits) == 3:
        red, green, blue = (int(channel * 2, 16) for channel in digits)
        return (red, green, blue, 255)
    red = int(digits[0:2], 16)
    green = int(digits[2:4], 16)
    blue = int(digits[4:6], 16)
    alpha = int(digits[6:8], 16) if len(digits) == 8 else 255
    return (red, green, blue, alpha)


def resolve_variable(value: Any, variables: dict[str, Any]) -> Any:
    """Resolve a `$name` reference through a pen `variables` block.

    Args:
        value: Raw visual value; only strings starting with `$` are resolved.
        variables: Pen `variables` block mapping names to `{"type", "value"}`
            definitions (or direct scalar values).

    Returns:
        The resolved value for `$name` references, the value unchanged for
        non-reference inputs, or `None` when the reference has no definition.
    """
    if not isinstance(value, str) or not value.startswith("$"):
        return value
    definition = variables.get(value[1:])
    if isinstance(definition, dict):
        return definition.get("value")
    return definition
