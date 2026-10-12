"""Single source for the pen.dev `.pen` schema versions Penflow writes or requires."""

# @spec FR-004: one module for written and required .pen versions — .specs/features/078-pen-dev-operator-compatibility/spec.md#fr-004

from __future__ import annotations

import re

# Penflow writers emit the 2.11 document structure. pen.dev 1.2.16 opens it and saves its own
# current version (2.17 observed), so claiming a newer version here would misdescribe the bytes.
PEN_WRITE_VERSION = "2.11"

# pen.dev 2.14 introduced measured intrinsic text sizing (`textGrowth`); later versions keep it.
NATIVE_INTRINSIC_TEXT_MIN_VERSION: tuple[int, int] = (2, 14)

# Exactly "<major>.<minor>" with decimal digits; anything else is not a comparable version.
_VERSION = re.compile(r"(\d+)\.(\d+)")


def parse_pen_version(value: object) -> tuple[int, int] | None:
    """Return ``(major, minor)`` for a ``"M.m"`` version string, otherwise ``None``.

    Args:
        value: The raw ``version`` member of a `.pen` document.

    Returns:
        The numeric version, or ``None`` for missing, non-string or malformed values.
    """
    if not isinstance(value, str):
        return None
    match = _VERSION.fullmatch(value)
    if match is None:
        return None
    return int(match.group(1)), int(match.group(2))


def supports_native_intrinsic_text(value: object) -> bool:
    """Tell whether a document version carries native intrinsic text sizing.

    Args:
        value: The raw ``version`` member of a `.pen` document.

    Returns:
        ``True`` only for parseable versions at or above the intrinsic-text minimum.
    """
    version = parse_pen_version(value)
    return version is not None and version >= NATIVE_INTRINSIC_TEXT_MIN_VERSION
