"""Historical Mistune3.2 table grammar for authenticated approval archives.
Adapted from Mistune3.2.0,(c)2014 Hsiaoming Yang,BSD-3-Clause; see third-party-notices.md.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Match, Optional, Tuple, Union

from mistune import BlockParser, BlockState, Markdown
from mistune.helpers import PREVENT_BACKSLASH

# @spec FR-007: Preserve authenticated requirement identities.
# — .specs/features/077-complete-verification-workflow/spec.md#fr-007
TABLE_PATTERN = (
    r"^ {0,3}\|(?P<table_head>.+)\|[ \t]*\n"
    r" {0,3}\|(?P<table_align> *[-:]+[-| :]*)\|[ \t]*\n"
    r"(?P<table_body>(?: {0,3}\|.*\|[ \t]*(?:\n|$))*)\n*"
)
NP_TABLE_PATTERN = (
    r"^ {0,3}(?P<nptable_head>\S.*\|.*)\n"
    r" {0,3}(?P<nptable_align>[-:]+ *\|[-| :]*)\n"
    r"(?P<nptable_body>(?:.*\|.*(?:\n|$))*)\n*"
)

TABLE_CELL = re.compile(r"^ {0,3}\|(.+)\|[ \t]*$")
CELL_SPLIT = re.compile(r" *" + PREVENT_BACKSLASH + r"\| *")
ALIGN_CENTER = re.compile(r"^ *:-+: *$")
ALIGN_LEFT = re.compile(r"^ *:-+ *$")
ALIGN_RIGHT = re.compile(r"^ *-+: *$")


def parse_table(block: "BlockParser", m: Match[str], state: "BlockState") -> Optional[int]:
    pos = m.end()
    header = m.group("table_head")
    align = m.group("table_align")
    thead, aligns = _process_thead(header, align)
    if not thead:
        return None
    assert aligns is not None

    rows = []
    body = m.group("table_body")
    for text in body.splitlines():
        m2 = TABLE_CELL.match(text)
        if not m2:  # pragma: no cover
            return None
        row = _process_row(m2.group(1), aligns)
        if not row:
            return None
        rows.append(row)

    children = [thead, {"type": "table_body", "children": rows}]
    state.append_token({"type": "table", "children": children})
    return pos


def parse_nptable(block: "BlockParser", m: Match[str], state: "BlockState") -> Optional[int]:
    header = m.group("nptable_head")
    align = m.group("nptable_align")
    thead, aligns = _process_thead(header, align)
    if not thead:
        return None
    assert aligns is not None

    rows = []
    body = m.group("nptable_body")
    for text in body.splitlines():
        row = _process_row(text, aligns)
        if not row:
            return None
        rows.append(row)

    children = [thead, {"type": "table_body", "children": rows}]
    state.append_token({"type": "table", "children": children})
    return m.end()


def _process_thead(
    header: str, align: str
) -> Union[Tuple[None, None], Tuple[Dict[str, Any], List[str]]]:
    headers = CELL_SPLIT.split(header)
    aligns = CELL_SPLIT.split(align)
    if len(headers) != len(aligns):
        return None, None

    for i, v in enumerate(aligns):
        if ALIGN_CENTER.match(v):
            aligns[i] = "center"
        elif ALIGN_LEFT.match(v):
            aligns[i] = "left"
        elif ALIGN_RIGHT.match(v):
            aligns[i] = "right"
        else:
            aligns[i] = None

    children = [
        {"type": "table_cell", "text": text.strip(), "attrs": {"align": aligns[i], "head": True}}
        for i, text in enumerate(headers)
    ]
    thead = {"type": "table_head", "children": children}
    return thead, aligns


def _process_row(text: str, aligns: List[str]) -> Optional[Dict[str, Any]]:
    cells = CELL_SPLIT.split(text)
    if len(cells) != len(aligns):
        return None

    children = [
        {"type": "table_cell", "text": text.strip(), "attrs": {"align": aligns[i], "head": False}}
        for i, text in enumerate(cells)
    ]
    return {"type": "table_row", "children": children}


def legacy_table(md: Markdown) -> None:
    """Register the historical table grammar for an AST-only reader."""
    md.block.register("table", TABLE_PATTERN, parse_table, before="paragraph")
    md.block.register("nptable", NP_TABLE_PATTERN, parse_nptable, before="paragraph")
