# @spec(FR-001)
"""Process-wide cache for bundled JSON Schemas and compiled validators.

Bundled schemas under ``penflow/schemas/`` are immutable package data, so each
one is read and parsed at most once per process (contract C29). ``load_schema``
returns a defensive deep copy so callers can never observe shared mutable
state; ``validator_for`` returns one cached compiled ``Draft202012Validator``
per schema name, compiled from the cached parse.
"""

from __future__ import annotations

import copy
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

SCHEMAS_DIR = Path(__file__).parent / "schemas"


@lru_cache(maxsize=None)
def _load(name: str) -> dict[str, Any]:
    """Read and parse one bundled schema, exactly once per process."""
    if Path(name).name != name:  # reject path traversal — only bare bundled names
        raise FileNotFoundError(f"not a bundled schema name: {name!r}")
    parsed = json.loads((SCHEMAS_DIR / name).read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):  # bundled schemas are always objects
        raise ValueError(f"bundled schema is not a JSON object: {name}")
    return parsed


def load_schema(name: str) -> dict[str, Any]:
    """Return a defensive deep copy of the bundled schema ``name``.

    Args:
        name: Schema file name under ``penflow/schemas/`` (for example
            ``"code-ir.schema.json"``).

    Returns:
        A fresh dict per call — mutations never leak into the cache or into
        other callers.

    Raises:
        FileNotFoundError: If no bundled schema has that name.
    """
    return copy.deepcopy(_load(name))


@lru_cache(maxsize=None)
def validator_for(name: str) -> Draft202012Validator:
    """Return the cached compiled draft 2020-12 validator for ``name``.

    The validator is compiled from the cached parse (no copy): jsonschema
    never mutates the schema it validates against.

    Args:
        name: Schema file name under ``penflow/schemas/``.

    Returns:
        The process-wide validator instance for that schema. Treat it as
        read-only — never mutate ``validator.schema``; use ``load_schema``
        when a mutable copy is needed.

    Raises:
        FileNotFoundError: If no bundled schema has that name.
    """
    return Draft202012Validator(_load(name))


def clear_cache() -> None:
    """Drop all cached state (test isolation helper).

    Side effects: clears both process-wide caches — parsed schema dicts and
    compiled validators — so the next access re-reads from disk. Previously
    returned validator instances stay valid but are no longer shared with
    future ``validator_for`` calls.
    """
    _load.cache_clear()
    validator_for.cache_clear()
