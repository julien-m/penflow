"""Decode pen.dev MCP `execute` observations into the native parent-relative layout.

pen.dev 1.2 answers `execute` with Markdown text: a status line (`OK`), a blank line,
`## Print output` and one line per `Print(...)` call. This module stays pure: it never
calls MCP, it only reads the observation text an operator saved.
"""

# @spec FR-006: Print transport accepted for native geometry — .specs/features/077-complete-verification-workflow/spec.md#fr-006
# @spec AC-010: declared normalization of the native transport; ambiguity stays blocking — .specs/features/077-complete-verification-workflow/spec.md#ac-010

from __future__ import annotations

from typing import Any

from .verification_files import VerificationInputError
from .verification_json import decode_json

# Decoded JSON is heterogeneous (`Any`); every shape is validated explicitly before use.
PRINT_HEADER = "## Print output"
EXECUTE_OK = "OK"
NATIVE_GET_LAYOUT_KIND = "penflow-native-get-layout"
_ENVELOPE_KEYS = frozenset({"kind", "version", "coordinate_space", "roots", "measurements"})
_MEASUREMENT_REQUIRED = frozenset({"id", "parent_id", "bounds"})
_MEASUREMENT_ALLOWED = _MEASUREMENT_REQUIRED | {"context", "problems"}
_BOUNDS_KEYS = frozenset({"x", "y", "width", "height"})


def decode_native_observation_text(text: str) -> Any:
    """Return the single JSON value carried by one observation text block.

    Backward compatibility: a bare JSON document (the pre-1.2 `snapshot_layout` response)
    is decoded unchanged. Otherwise the text must be a successful `execute` response whose
    Print output holds exactly one line, and that line must be strict finite JSON.

    Args:
        text: The observation's only text block.

    Returns:
        The decoded JSON value.

    Raises:
        VerificationInputError: ``verification.geometry.transport_invalid`` for a failed,
            sectionless, duplicated or multi-line Print output, or undecodable JSON.
    """
    if text.lstrip().startswith(("{", "[")):
        return _decode(text)
    lines = _print_lines(text)
    if len(lines) != 1:
        raise VerificationInputError("verification.geometry.transport_invalid")
    return _decode(lines[0])


def native_layout_children(value: Any) -> list[Any]:
    """Normalize a decoded observation to the parent-relative `children` list.

    A printed list is already the native layout. A ``penflow-native-get-layout`` envelope
    (document ``roots`` plus per-node ``measurements``) is rebuilt in document order from the
    measured bounds after proving that both sides name exactly the same nodes and parents.

    Raises:
        VerificationInputError: For any other shape or any identity, parent or context mismatch.
    """
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return _children_from_envelope(value)
    raise VerificationInputError("verification.geometry.native_envelope_invalid")


def _decode(raw: str) -> Any:
    try:
        return decode_json(raw)
    except ValueError as error:
        raise VerificationInputError("verification.geometry.transport_invalid") from error


def _print_lines(text: str) -> list[str]:
    """Split one successful execute response into its non-empty Print lines.

    The status must be the first line and `## Print output` the first section heading, so a
    preceding error or warning section blocks. Exactly one Print section is allowed; it ends
    at the next `## ` heading. Each Print line ends with a Markdown hard break (two spaces),
    which is trailing whitespace and therefore stripped.
    """
    rows = text.split("\n")
    if rows[0].strip() != EXECUTE_OK:
        raise VerificationInputError("verification.geometry.transport_invalid")
    headers = [index for index, row in enumerate(rows) if row.strip() == PRINT_HEADER]
    sections = [index for index, row in enumerate(rows) if row.lstrip().startswith("## ")]
    if len(headers) != 1 or sections[0] != headers[0]:
        raise VerificationInputError("verification.geometry.transport_invalid")
    lines = []
    for row in rows[headers[0] + 1 :]:
        if row.startswith("## "):
            break  # The next section (warnings, created ids) is not Print output.
        if row.strip():
            lines.append(row.rstrip())
    return lines


def _children_from_envelope(envelope: dict[str, Any]) -> list[Any]:
    if (
        set(envelope) != _ENVELOPE_KEYS
        or envelope["kind"] != NATIVE_GET_LAYOUT_KIND
        or type(envelope["version"]) is not int
        or envelope["version"] != 1
        or envelope["coordinate_space"] != "parent-relative"
        or not isinstance(envelope["roots"], list)
        or not isinstance(envelope["measurements"], list)
        or not envelope["roots"]
    ):
        raise VerificationInputError("verification.geometry.native_envelope_invalid")
    document = _document_index(envelope["roots"])
    measured = _measurement_index(envelope["measurements"])
    if set(measured) != set(document):
        raise VerificationInputError("verification.geometry.identity_or_parent_mismatch")
    for node_id, (parent, context, _) in document.items():
        measurement = measured[node_id]
        # Context is optional on both sides, but when either side declares it both must agree.
        if measurement["parent_id"] != parent or measurement.get("context") != context:
            raise VerificationInputError("verification.geometry.identity_or_parent_mismatch")
        # pen.dev reports clipping in `problems`; a clipped node is never silently certified.
        if measurement.get("problems") is not None:
            raise VerificationInputError("verification.geometry.native_problem")
    built = {
        node_id: {
            "id": node_id,
            **{key: measured[node_id]["bounds"][key] for key in sorted(_BOUNDS_KEYS)},
        }
        for node_id in document
    }
    for node_id, (_, _, children) in document.items():
        if children:
            built[node_id]["children"] = [built[child] for child in children]
    return [built[root["id"]] for root in envelope["roots"]]


def _document_index(
    roots: list[Any],
) -> dict[str, tuple[str | None, Any, list[str]]]:
    """Index document nodes as ``id -> (parent id, context, ordered child ids)``."""
    index: dict[str, tuple[str | None, Any, list[str]]] = {}
    pending: list[tuple[Any, str | None]] = [(node, None) for node in roots]
    while pending:
        node, parent = pending.pop()
        if (
            not isinstance(node, dict)
            or not isinstance(node.get("id"), str)
            or not node["id"]
            or node["id"] in index
            or not isinstance(node.get("children", []), list)
        ):
            raise VerificationInputError("verification.geometry.node_invalid_or_duplicate")
        children = node.get("children", [])
        # Invalid children are rejected when popped; only well-formed ids are recorded here.
        child_ids = [
            child["id"]
            for child in children
            if isinstance(child, dict) and isinstance(child.get("id"), str)
        ]
        index[node["id"]] = (parent, node.get("context"), child_ids)
        pending.extend((child, node["id"]) for child in children)
    return index


def _measurement_index(measurements: list[Any]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for item in measurements:
        if (
            not isinstance(item, dict)
            or not _MEASUREMENT_REQUIRED <= set(item) <= _MEASUREMENT_ALLOWED
            or not isinstance(item["id"], str)
            or item["id"] in index
            or not (item["parent_id"] is None or isinstance(item["parent_id"], str))
            or not isinstance(item["bounds"], dict)
            or set(item["bounds"]) != _BOUNDS_KEYS
        ):
            raise VerificationInputError("verification.geometry.measurement_invalid")
        index[item["id"]] = item
    return index
