"""Cached validators for the versioned C51 envelope definitions."""

from functools import lru_cache
from typing import Any

from jsonschema import Draft202012Validator

from .schema_cache import validator_for
from .verification_json import canonical_bytes


@lru_cache(maxsize=None)
def c51_validator(definition: str) -> Draft202012Validator:
    """Compile an immutable packaged definition without resolving remote schemas."""
    parent = validator_for("c51-contracts.schema.json")
    if definition not in parent.schema["$defs"]:
        raise ValueError(f"unknown C51 definition: {definition}")
    return parent.evolve(schema={"$ref": f"#/$defs/{definition}", "$defs": parent.schema["$defs"]})


def schema_issues(value: Any, definition: str) -> list[dict[str, Any]]:
    """Return closed structured issues before trusting shape, numbers or identity."""
    try:
        canonical_bytes(value)
    except (ValueError, TypeError, RecursionError) as exc:
        return [issue("verification.source.json", "$", str(exc))]
    return [
        issue(
            "verification.source.schema",
            "$" + "".join(f"/{part}" for part in error.absolute_path),
            error.message,
        )
        for error in c51_validator(definition).iter_errors(value)
    ]


def issue(
    code: str,
    path: str,
    message: str,
    *,
    gate_id: str | None = None,
    obligation_id: str | None = None,
) -> dict[str, Any]:
    """Build the one public issue shape used by API, CLI and consumers."""
    return {
        "code": code,
        "severity": "error",
        "path": path,
        "message": message,
        "gate_id": gate_id,
        "obligation_id": obligation_id,
    }
