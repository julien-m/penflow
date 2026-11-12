"""Write a LiveSpec technical continuity revision of an approved baseline (test producer).

It writes what LiveSpec writes after its delivery continuity accepted a technical change:
the archived predecessor baseline, the archived new source bytes and contract, the
archived LiveSpec continuity record, the ``requirements-continuity`` receipt and the new
baseline. Nothing here decides whether the change is acceptable: Penflow re-proves it.
"""

from __future__ import annotations

import copy
from typing import Any

from penflow.requirement_markdown import semantic_text_sha256
from tests.c51_review_chain import (
    BASELINE_PATH,
    CONTRACT_PATH,
    DEFAULT_SLUG,
    SPEC_TEXT,
    ReviewLink,
    archive,
    encode,
    write_file,
)

Json = dict[str, Any]
# The table defines the criteria; detail sections carry their declarations (Atlas form).
SPEC_WITH_SECTIONS = (
    SPEC_TEXT
    + """
## Required evidence level per AC

| Level | ACs |
|---|---|
| native (real browser on the deployed screen) | AC-001 |
| static | AC-002 (report check) |

### AC-001

**Criterion:** The checkout screen is visible.

### AC-002

**Criterion:** The audit trail is accepted upstream.
"""
)
STATIC_LINES = (
    "**Evidence:** static\n"
    "**Static command:** `npm run lint`\n"
    "**Static inputs:** [eslint.config.js](../../../eslint.config.js)\n"
)


def with_static(spec: str, criterion: str, lines: str = STATIC_LINES) -> str:
    """Declare evidence lines under one criterion (static by default, as the Atlas patch)."""
    heading = f"### {criterion}\n\n"
    start = spec.index(heading)
    end = spec.find("\n### ", start + len(heading))
    end = len(spec) if end < 0 else end
    return spec[:end].rstrip("\n") + "\n" + lines + spec[end:]


def write_continuity(
    link: ReviewLink,
    *,
    spec: str | None = None,
    contract: Json | None = None,
    declared: tuple[tuple[str, str, str], ...] = (),
    slug: str = DEFAULT_SLUG,
) -> Json:
    """Republish ``link`` with a changed spec and/or contract; return the new baseline."""
    root = link.root
    baseline = copy.deepcopy(link.baseline)
    changes: list[Json] = []
    if spec is not None:
        raw = spec.encode("utf-8")
        path = f".specs/features/{slug}/spec.md"
        before = next(row for row in baseline["sources"] if row["path"] == path)
        after = {
            **write_file(root, path, raw),
            "semantic_sha256": semantic_text_sha256(spec),
            "reviewed_snapshot": archive(root, "source", raw),
        }
        changes.append(
            {
                "collection": "sources",
                "path": path,
                "before": before,
                "after": after,
                "evidence_changes": [
                    {"requirement": key, "before_level": old, "after_level": new}
                    for key, old, new in declared
                ],
            }
        )
        baseline["sources"] = [after if row["path"] == path else row for row in baseline["sources"]]
        # The contract and the projection name the reviewed source digest: both follow it.
        contract = copy.deepcopy(contract if contract is not None else link.contract)
        for ref in [*contract["requirements"]["source_refs"], *baseline["projection"]["sources"]]:
            if ref["path"] == path:
                ref["sha256"] = after["sha256"]
    contract_link = None
    if contract is not None:
        before_ref = archive(root, "contract", encode(link.contract))
        after_ref = archive(root, "contract", encode(contract))
        write_file(root, CONTRACT_PATH, encode(contract))
        contract_link = {"before": before_ref, "after": after_ref}
        baseline["contract"] = {"path": CONTRACT_PATH, "sha256": after_ref["sha256"]}
    record = archive(root, "continuity-record", encode({"livespec": "delivery continuity"}))
    receipt = {
        "kind": "livespec-penflow-requirements-continuity",
        "version": 1,
        "scope": baseline["scope"],
        "feature": slug,
        "previous": link.baseline_ref,
        "changes": changes,
        "contract": contract_link,
        "livespec_record": record,
    }
    baseline["previous"] = link.baseline_ref
    baseline["continuity"] = archive(root, "continuity", encode(receipt))
    write_file(root, BASELINE_PATH, encode(baseline))
    return baseline
