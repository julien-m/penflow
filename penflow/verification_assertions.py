"""Bounded pure predicates over typed observations; no eval, regex execution or truthy coercion."""

from __future__ import annotations

import math
from typing import Any

MISSING = object()
MAX_PATTERN_LENGTH = 128
MAX_INPUT_LENGTH = 4096


def resolve_pointer(value: Any, pointer: str) -> Any:
    """Resolve RFC6901 object/array keys, preserving a missing sentinel."""
    if pointer == "":
        return value
    if not pointer.startswith("/"):
        raise ValueError("JSON pointer must begin with /")
    current = value
    for raw in pointer[1:].split("/"):
        if any(
            index + 1 >= len(raw) or raw[index + 1] not in "01"
            for index, char in enumerate(raw)
            if char == "~"
        ):
            raise ValueError("invalid JSON pointer escape")
        key = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict):
            current = current.get(key, MISSING)
        elif isinstance(current, list) and (
            key == "0" or (key.isascii() and key.isdecimal() and not key.startswith("0"))
        ):
            index = int(key)
            current = current[index] if index < len(current) else MISSING
        else:
            return MISSING
    return current


# @spec FR-008: Evaluate expected typed outcomes — .specs/features/077-complete-verification-workflow/spec.md#fr-008
def evaluate_assertion(assertion: dict[str, Any], observation: dict[str, Any]) -> bool:
    """Evaluate one validated predicate, never a producer-supplied success boolean."""
    if assertion["capability"] != observation.get("capability"):
        return False
    operator, pointer, expected = assertion["operator"], assertion["pointer"], assertion["expected"]
    value = resolve_pointer(observation, pointer)
    if operator == "exists":
        return value is not MISSING
    if operator == "absent":
        return value is MISSING
    if operator in {"changed", "unchanged"}:
        before = resolve_pointer(observation.get("before", {}), pointer)
        after = resolve_pointer(observation.get("after", {}), pointer)
        if before is MISSING or after is MISSING:
            return False
        equal = json_values_equal(before, after)
        return equal if operator == "unchanged" else not equal
    if value is MISSING:
        return False
    if operator == "equals":
        return json_values_equal(value, expected)
    if operator == "not_equals":
        return not json_values_equal(value, expected)
    if operator == "matches":
        return wildcard_matches(expected, value)
    if operator == "contains":
        if isinstance(value, str) and isinstance(expected, str):
            return expected in value
        return isinstance(value, list) and any(json_values_equal(item, expected) for item in value)
    if operator in {"greater_than", "less_than"}:
        if not _number(value) or not _number(expected):
            return False
        return value > expected if operator == "greater_than" else value < expected
    raise ValueError(f"unsupported assertion operator: {operator}")


def wildcard_matches(pattern: str, value: str) -> bool:
    """Match literals, ? and * using bounded iterative dynamic programming."""
    if not isinstance(pattern, str) or not isinstance(value, str):
        return False
    if len(pattern) > MAX_PATTERN_LENGTH or len(value) > MAX_INPUT_LENGTH:
        raise ValueError("wildcard input exceeds declared budget")
    if any(char in pattern for char in "()[]{}|\\+^$"):
        raise ValueError("unsupported wildcard grammar; only literals, ? and * are supported")
    previous = [True] + [False] * len(value)
    for token in pattern:
        current = [previous[0] and token == "*"] + [False] * len(value)
        for index, character in enumerate(value, 1):
            current[index] = (
                (previous[index] or current[index - 1])
                if token == "*"
                else previous[index - 1] and (token == "?" or token == character)
            )
        previous = current
    return previous[-1]


def json_values_equal(left: Any, right: Any) -> bool:
    """Compare JSON values with numeric equivalence and distinct boolean semantics."""
    if _number(left) and _number(right):
        return bool(left == right)
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(
            json_values_equal(left[key], right[key]) for key in left
        )
    if isinstance(left, list):
        return len(left) == len(right) and all(json_values_equal(a, b) for a, b in zip(left, right))
    return bool(left == right)


def _number(value: Any) -> bool:
    return (isinstance(value, int) and not isinstance(value, bool)) or (
        isinstance(value, float) and math.isfinite(value)
    )
