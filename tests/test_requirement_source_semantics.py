"""Reviewed source identity survives a parser upgrade: both sides use one parser.

Observed on a real consumer: the ``semantic_sha256`` recorded at approval time can no
longer be recomputed, even from the authenticated archived bytes, because the recording
parser drifted. Comparing the current source with that recorded value refused every byte
change of the source, even a lifecycle-only one. The archive bytes stay authenticated by
their raw digest; the current source is compared with the archive using the current
parser on both sides.
"""

from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from penflow.requirement_markdown import semantic_text_sha256
from penflow.requirement_sources import _current_sources
from penflow.verification_files import InputReader, VerificationInputError
from penflow.verification_json import digest

SLUG = "001-continuity"


def _source() -> str:
    marker = uuid4().hex
    return f"""---
status: Approved
updated: 2026-11-01
---
# Feature {marker}

## Functional Requirements

- **FR-001:** Keep {marker} (AC-001).

## Acceptance Criteria

### AC-001

**Criterion:** {marker} survives restart.
"""


def _project(root: Path, approved: str) -> dict[str, Any]:
    """An approval snapshot whose recorded semantic hash came from a drifted parser."""
    raw = approved.encode()
    sha = digest(raw)
    archive = root / f".specs/penflow-approvals/source-{sha}.md"
    archive.parent.mkdir(parents=True)
    archive.write_bytes(raw)
    recorded = digest(f"historical-parser:{uuid4().hex}".encode())
    assert recorded != semantic_text_sha256(approved)
    inputs: dict[str, list[dict[str, Any]]] = {}
    for collection, filename in (("sources", "spec.md"), ("plans", "plan.md")):
        path = f".specs/features/{SLUG}/{filename}"
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_bytes(raw)
        inputs[collection] = [
            {
                "path": path,
                "sha256": sha,
                "semantic_sha256": recorded,
                "reviewed_snapshot": {"path": archive.relative_to(root).as_posix(), "sha256": sha},
            }
        ]
    return {"selection": [SLUG], "inputs": inputs}


def test_a_lifecycle_update_is_accepted_although_the_recorded_hash_drifted(
    tmp_path: Path,
) -> None:
    approved = _source()
    snapshot = _project(tmp_path, approved)
    spec = tmp_path / f".specs/features/{SLUG}/spec.md"
    spec.write_text(approved.replace("status: Approved", "status: Implemented"))
    _current_sources(InputReader(tmp_path), snapshot)  # Was requirements.source.semantic_changed.


@pytest.mark.parametrize("change", ["criterion", "archive"])
def test_a_meaning_change_or_an_altered_archive_stays_refused(tmp_path: Path, change: str) -> None:
    approved = _source()
    snapshot = _project(tmp_path, approved)
    if change == "criterion":
        spec = tmp_path / f".specs/features/{SLUG}/spec.md"
        spec.write_text(approved.replace("survives restart", "survives a reboot"))
        expected = "requirements.source.semantic_changed"
    else:
        archive = tmp_path / snapshot["inputs"]["sources"][0]["reviewed_snapshot"]["path"]
        archive.write_text(approved.replace("survives restart", "survives a reboot"))
        expected = "input.stale"
    with pytest.raises(VerificationInputError, match=expected):
        _current_sources(InputReader(tmp_path), snapshot)
