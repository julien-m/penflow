"""Strict, finite JSON values at verification boundaries; business null/false/zero remain valid."""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any


# JSON values are heterogeneous; every consumer validates their closed envelope separately.
def decode_json(raw: bytes | str) -> Any:
    """Decode standard JSON, rejecting non-finite constants and ambiguous duplicate keys."""
    try:
        return json.loads(
            raw,
            parse_constant=_reject_constant,
            parse_float=_finite_float,
            object_pairs_hook=_unique_object,
        )
    except RecursionError as error:
        raise ValueError("JSON nesting exceeds the parser's bounded capacity") from error


def canonical_bytes(value: Any) -> bytes:
    """Serialize one unambiguous finite JSON value for canonical identity."""
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def digest(raw: bytes) -> str:
    """Return SHA-256 over exact bytes, without normalization."""
    return hashlib.sha256(raw).hexdigest()


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant: {value}")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON member: {key}")
        result[key] = value
    return result


def _finite_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("JSON numeric value is outside finite range")
    return number
