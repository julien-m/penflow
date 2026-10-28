"""Compare historical requirement projections with an actual old parser process."""

import json
import os
import subprocess
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from penflow.requirement_projection import project_requirements
from penflow.requirement_sources import _current_sources
from penflow.requirement_markdown import semantic_text_sha256
from penflow.verification_files import InputReader, VerificationInputError
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

**configuration_key:** {name}

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
        "from penflow.requirement_markdown import extract_requirement_definitions_text,semantic_text_sha256; "
        "assert mistune.__version__ == '3.2.0'; "
        "source=sys.stdin.read(); "
        "print(json.dumps({'definitions':[asdict(x) for x in "
        "extract_requirement_definitions_text(source,'001-compatibility')],"
        "'semantic_sha256':semantic_text_sha256(source)}))"
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
    oracle = json.loads(result.stdout)
    expected = [
        {key: item[key] for key in ("id", "source_pointer", "text_sha256")}
        for item in oracle["definitions"]
    ]
    snapshot, contract = _archived_project(tmp_path, source, expected)
    actual = project_requirements(InputReader(tmp_path), snapshot, contract)
    assert actual["requirements"] == expected
    _verify_current_sources(tmp_path, source, oracle["semantic_sha256"], snapshot)


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


def _verify_current_sources(
    root: Path, source: str, historical_hash: str, snapshot: dict[str, Any]
) -> None:
    assert semantic_text_sha256(source) != historical_hash
    record = snapshot["inputs"]["sources"][0]
    record["semantic_sha256"] = historical_hash
    spec = root / record["path"]
    spec.parent.mkdir(parents=True)
    spec.write_text(source)
    plan = spec.with_name("plan.md")
    plan.write_text(source)
    snapshot["inputs"]["plans"] = [{**record, "path": plan.relative_to(root).as_posix()}]
    _current_sources(InputReader(root), snapshot)
    for path in (spec, plan):
        path.write_text(source + "\n" + uuid4().hex)
        with pytest.raises(VerificationInputError, match="requirements.source.semantic_changed"):
            _current_sources(InputReader(root), snapshot)
        path.write_text(source)
