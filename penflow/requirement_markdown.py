"""Extract selected LiveSpec requirement definitions and their semantic identity."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import cast

import yaml
import mistune
from yaml import YAMLError

# Versioned LiveSpec feature identity, including dotted subfeatures.
SLUG_REGEX = re.compile(r"^\d{3}(\.\d+)?-[a-z0-9]+(-[a-z0-9]+)*$")

Node = dict[str, object]
_IDENTIFIER = re.compile(r"(?:FR|AC)-[0-9]{3}")
_DEFINITION_START = re.compile(r"^(?:FR|AC)-[^\s:]*\s*:")
_REFERENCES = re.compile(r"\bAC-[0-9]{3}\b")
_SECTIONS = {"Functional Requirements": "FR", "Acceptance Criteria": "AC"}
# Generated metadata only; ordinary business status lists remain authoritative.
_LIFECYCLE = re.compile(
    r"Status: (?:Draft|Review|Approved|Implemented|Deprecated|Planned|In Progress)"
)
_FINALIZE = re.compile(r"<!-- finalize:spec-[a-z-]+:[0-9]{4}-[0-9]{2}-[0-9]{2}:[0-9a-f]{8} -->\n?")


class RequirementSourceError(ValueError):
    """A selected source has an ambiguous, incomplete or unreadable requirement set."""


@dataclass(frozen=True)
class RequirementDefinition:
    """One actual FR/AC definition, with source-local and globally namespaced identity."""

    id: str
    local_id: str
    text: str
    text_sha256: str
    source_pointer: str
    references: tuple[str, ...]


def _nodes(value: object) -> list[Node]:
    if not isinstance(value, list):
        return []
    return [cast(Node, node) for node in cast(list[object], value) if isinstance(node, dict)]


def _text(node: Node) -> str:
    if node.get("type") in {"block_code", "block_quote", "block_html"}:
        return ""
    raw = node.get("raw")
    if isinstance(raw, str):
        return " ".join(raw.split())
    return " ".join(part for child in _nodes(node.get("children")) if (part := _text(child)))


def _definition_lines(node: Node) -> str:
    if node.get("type") in {"softbreak", "linebreak"}:
        return "\n"
    raw = node.get("raw")
    if isinstance(raw, str):
        return raw
    return "".join(_definition_lines(child) for child in _nodes(node.get("children")))


def _parse(source: str) -> tuple[dict[str, object], list[Node]]:
    try:
        metadata, content = _frontmatter(source)
        ast = mistune.create_markdown(renderer="ast", plugins=["table"])(content)
    except (OSError, UnicodeError, YAMLError, ValueError) as exc:
        raise RequirementSourceError(f"requirement_source_unreadable: {exc}") from exc
    return metadata, _nodes(ast)


def _source_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise RequirementSourceError(f"requirement_source_unreadable: {path}: {exc}") from exc


def _definition(local_id: str, text: str, pointer: str, slug: str) -> RequirementDefinition:
    if not _IDENTIFIER.fullmatch(local_id) or not text.strip():
        raise RequirementSourceError(f"malformed_requirement_definition: {pointer}")
    normalized = " ".join(text.split())
    references = (
        tuple(dict.fromkeys(_REFERENCES.findall(normalized))) if local_id.startswith("FR-") else ()
    )
    return RequirementDefinition(
        id=f"livespec:{slug}:{local_id}",
        local_id=local_id,
        text=normalized,
        text_sha256=hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
        source_pointer=pointer,
        references=tuple(f"livespec:{slug}:{reference}" for reference in references),
    )


def _section_definitions(
    node: Node, prefix: str, pointer: str, slug: str
) -> list[RequirementDefinition]:
    results: list[RequirementDefinition] = []
    if node.get("type") == "list":
        for index, item in enumerate(_nodes(node.get("children"))):
            text = _text(item)
            if text.startswith(("FR-", "AC-")):
                local_id, separator, definition = text.partition(":")
                local_id = local_id.strip()
                if not separator or not local_id.startswith(prefix + "-"):
                    raise RequirementSourceError(
                        f"malformed_requirement_definition: {pointer}/{index}"
                    )
                results.append(
                    _definition(local_id, definition, f"{pointer}/children/{index}", slug)
                )
    elif node.get("type") == "table":
        for index, body in enumerate(_nodes(node.get("children"))):
            if body.get("type") != "table_body":
                continue
            for row_index, row in enumerate(_nodes(body.get("children"))):
                cells = [_text(cell) for cell in _nodes(row.get("children"))]
                row_pointer = f"{pointer}/children/{index}/children/{row_index}"
                if len(cells) < 2 or not cells[0].startswith(prefix + "-") or not cells[1]:
                    raise RequirementSourceError(f"malformed_requirement_definition: {row_pointer}")
                results.append(_definition(cells[0], " ".join(cells[1:]), row_pointer, slug))
    return results


# @spec FR-007: actual definitions form the selected-source denominator
# — .specs/features/077-complete-verification-workflow/spec.md#fr-007
def extract_requirement_definitions(path: Path, feature_slug: str) -> list[RequirementDefinition]:
    """Extract real FR/AC definitions from one explicitly selected source.

    Args:
        path: Selected feature spec; no other feature or backlog file is read.
        feature_slug: Namespace selected independently by the calling workflow.

    Returns:
        Definitions in AST order; text uses one space between inline text tokens.

    Raises:
        RequirementSourceError: Missing FR/AC denominator, duplicate or malformed
            definition, dangling FR-to-AC reference, or unreadable source.
    """
    return extract_requirement_definitions_text(_source_text(path), feature_slug)


def extract_requirement_definitions_text(
    source: str, feature_slug: str
) -> list[RequirementDefinition]:
    """Extract definitions from the exact authenticated source bytes decoded as UTF-8."""
    if not SLUG_REGEX.fullmatch(feature_slug):
        raise RequirementSourceError("invalid_feature_namespace")
    _, nodes = _parse(source)
    prefix: str | None = None
    results: list[RequirementDefinition] = []
    for index, node in enumerate(nodes):
        if (
            prefix is not None
            and node.get("type") in {"paragraph", "heading"}
            and any(
                _DEFINITION_START.match(line.strip())
                for line in _definition_lines(node).splitlines()
            )
        ):
            raise RequirementSourceError(f"unsupported_requirement_definition: /body/{index}")
        if node.get("type") == "heading":
            attrs = node.get("attrs")
            level = cast(Node, attrs).get("level") if isinstance(attrs, dict) else None
            if isinstance(level, int) and level <= 2:
                prefix = _SECTIONS.get(_text(node)) if level == 2 else None
        elif prefix is not None:
            results.extend(_section_definitions(node, prefix, f"/body/{index}", feature_slug))
    identities = {item.id for item in results}
    if len(identities) != len(results):
        raise RequirementSourceError("duplicate_requirement_definition")
    if not all(
        any(item.local_id.startswith(kind + "-") for item in results) for kind in ("FR", "AC")
    ):
        raise RequirementSourceError(
            "empty_requirement_denominator: both FR and AC definitions required"
        )
    if any(reference not in identities for item in results for reference in item.references):
        raise RequirementSourceError("dangling_requirement_reference")
    return results


def _semantic_body(nodes: list[Node]) -> list[Node]:
    result: list[Node] = []
    metadata_section = True
    for node in nodes:
        if node.get("type") == "blank_line":
            continue
        if node.get("type") == "heading":
            attrs = node.get("attrs")
            level = cast(Node, attrs).get("level") if isinstance(attrs, dict) else None
            if isinstance(level, int) and level == 2:
                metadata_section = _text(node) == "Header"
        if node.get("type") == "block_html" and _FINALIZE.fullmatch(str(node.get("raw", ""))):
            continue
        if metadata_section and node.get("type") == "list" and node.get("bullet") == "-":
            children = [
                item for item in _nodes(node.get("children")) if not _generated_status(item)
            ]
            if not children:
                continue
            node = {**node, "children": children}
        result.append(node)
    return result


def _generated_status(item: Node) -> bool:
    blocks = _nodes(item.get("children"))
    if len(blocks) != 1 or not _LIFECYCLE.fullmatch(_text(item)):
        return False
    inline = _nodes(blocks[0].get("children"))
    return len(inline) == 2 and inline[0].get("type") == "strong" and _text(inline[0]) == "Status:"


def _json_metadata(value: object) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise RequirementSourceError(f"unsupported_source_metadata: {type(value).__name__}")


def semantic_source_sha256(path: Path) -> str:
    """Hash semantic Markdown retaining business content, links, code and visual scope.

    Only frontmatter status/updated, generated preamble/Header status bullets and
    exact generated finalize markers are excluded. Equivalent Markdown syntax is
    normalized through the AST; free comments and business status content remain.
    No file is written and no neighbouring feature is inspected.
    """
    return semantic_text_sha256(_source_text(path))


def semantic_text_sha256(source: str) -> str:
    """Hash an immutable text snapshot using the same versioned source normalization."""
    metadata, nodes = _parse(source)
    payload = {
        "metadata": {
            key: value for key, value in metadata.items() if key not in {"status", "updated"}
        },
        "body": _semantic_body(nodes),
    }
    encoded = json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=_json_metadata
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _frontmatter(source: str) -> tuple[dict[str, object], str]:
    """Use the same YAML-frontmatter delimiter and strip semantics as LiveSpec."""
    content = source.strip()
    metadata: dict[str, object] = {}
    if content.startswith("---"):
        parts = re.split(r"^-{3,}\s*$", content, maxsplit=2, flags=re.MULTILINE)
        if len(parts) == 3 and not parts[0]:
            loaded = yaml.safe_load(parts[1])
            if loaded is not None and not isinstance(loaded, dict):
                raise RequirementSourceError("source_metadata_must_be_object")
            metadata = loaded or {}
            content = parts[2].strip()
    return metadata, content
