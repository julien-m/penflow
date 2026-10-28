"""Compare historical requirement projections with an actual old parser process."""

import json
import os
import subprocess
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from penflow.requirement_projection import project_requirements
from penflow.verification_files import InputReader
from penflow.verification_json import digest


@pytest.mark.integration
def test_authenticated_projection_preserves_actual_old_parser_pointers(tmp_path: Path) -> None:
    python = os.environ.get("PENFLOW_LEGACY_PYTHON")
    if not python:
        pytest.skip("Set PENFLOW_LEGACY_PYTHON to an interpreter with Mistune3.2.0")
    name = uuid4().hex
    source = f"""# {name}

| Name | Value |
| --- | --- |
| {name} | {uuid4().hex} |

## Functional Requirements

- **FR-001:** Preserve {name} (AC-001).

## Acceptance Criteria

- **AC-001:** {name} survives restart.
"""
    root = Path(__file__).resolve().parents[1]
    # The oracle runs the unchanged default extractor with the real historical
    # dependency, independently of the compatibility adapter under test.
    code = (
        "import json,sys,mistune; from dataclasses import asdict; "
        "from penflow.requirement_markdown import extract_requirement_definitions_text; "
        "assert mistune.__version__ == '3.2.0'; "
        "print(json.dumps([asdict(x) for x in "
        "extract_requirement_definitions_text(sys.stdin.read(),'001-compatibility')]))"
    )
    result = subprocess.run(
        [python, "-c", code],
        input=source,
        text=True,
        capture_output=True,
        cwd=root,
        check=True,
        timeout=8,
    )
    expected = [
        {key: item[key] for key in ("id", "source_pointer", "text_sha256")}
        for item in json.loads(result.stdout)
    ]
    snapshot, contract = _archived_project(tmp_path, source, expected)
    actual = project_requirements(InputReader(tmp_path), snapshot, contract)
    assert actual["requirements"] == expected


def _archived_project(
    tmp_path: Path, source: str, expected: list[dict[str, str]]
) -> tuple[dict[str, Any], dict[str, Any]]:
    raw = source.encode()
    sha = digest(raw)
    archive = f".specs/penflow-approvals/source-{sha}.md"
    path = tmp_path / archive
    path.parent.mkdir(parents=True)
    path.write_bytes(raw)
    source_path = ".specs/features/001-compatibility/spec.md"
    record = {
        "path": source_path,
        "sha256": sha,
        "reviewed_snapshot": {"path": archive, "sha256": sha},
    }
    snapshot = {
        "selection": ["001-compatibility"],
        "retired_features": [],
        "inputs": {"sources": [record]},
        "projection": {"requirements": expected},
    }
    contract = {
        "requirements": {
            "source_kind": "livespec-fr-ac-v1",
            "source_refs": [{"path": source_path, "sha256": sha}],
            "bindings": [],
        },
        "outcome_expectations": [],
    }
    return snapshot, contract
