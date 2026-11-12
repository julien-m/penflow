"""LiveSpec records that name the Penflow CLI which produced them.

LiveSpec adds an optional ``penflow_identity`` (version text, executable path and
executable SHA-256) to the review snapshot, the review approval and the Brainstorm
authority import when its flow invoked Penflow. Historical records omit the key and
must keep validating; a present key must be a complete, closed identity.
"""

import copy
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from penflow.requirement_projection import project_requirements
from penflow.requirement_sources import load_livespec_requirements
from penflow.verification import produce_verification_report
from penflow.verification_files import InputReader, VerificationInputError
from penflow.verification_schema import schema_issues
from tests.c51_design_workspace import (
    build_design_project,
    default_delegations,
    review_request,
    uncertified,
)
from tests.c51_review_chain import (
    BASELINE_PATH,
    ReviewRequest,
    requirement_id,
    write_inherited_authority,
    write_review_link,
)

BRAINSTORM_FIXTURE = Path(__file__).parent / "fixtures" / "c51-brainstorm-source"
IDENTITY_DEFINITIONS = ("review-snapshot", "review-approval", "brainstorm-authority-import")
# The shape LiveSpec's PenflowIdentity serializes; the values are synthetic.
IDENTITY = {
    "executable": "/opt/penflow/bin/penflow",
    "executable_sha256": "0db30d81a9cbe6485a224087209cb169555dd6d43b5c015bae4700fbe3f1a3d5",
    "version": "penflow 0.1.0",
}
MALFORMED_IDENTITIES: list[object] = [
    None,
    {},
    "penflow 0.1.0",
    [IDENTITY],
    {key: value for key, value in IDENTITY.items() if key != "version"},
    {key: value for key, value in IDENTITY.items() if key != "executable"},
    {key: value for key, value in IDENTITY.items() if key != "executable_sha256"},
    {**IDENTITY, "unexpected": True},
    {**IDENTITY, "version": ""},
    {**IDENTITY, "executable": ""},
    {**IDENTITY, "executable": 1},
    {**IDENTITY, "executable_sha256": IDENTITY["executable_sha256"].upper()},
    {**IDENTITY, "executable_sha256": IDENTITY["executable_sha256"][:63]},
]


def _identity_request(identity: dict[str, Any] | None = IDENTITY) -> ReviewRequest:
    """Delegate the two published requirements and record the Penflow identity."""
    return replace(review_request(delegations=default_delegations()), penflow_identity=identity)


def _archived(root: Path, reference: dict[str, str]) -> dict[str, Any]:
    return json.loads((root / reference["path"]).read_text(encoding="utf-8"))


def _records(
    tmp_path: Path, identity: dict[str, Any] | None = IDENTITY
) -> dict[str, dict[str, Any]]:
    """Return the three LiveSpec record kinds, each written by the shared chain helpers."""
    link = write_review_link(tmp_path / "chain", _identity_request(identity))
    approval = _archived(link.root, link.approval_ref)
    inherited = write_inherited_authority(
        tmp_path / "inherited", BRAINSTORM_FIXTURE, penflow_identity=identity
    )
    package = json.loads(
        (inherited.root / inherited.contract["requirements"]["source_refs"][1]["path"]).read_text(
            encoding="utf-8"
        )
    )
    return {
        "review-snapshot": _archived(link.root, approval["snapshot"]),
        "review-approval": approval,
        "brainstorm-authority-import": package,
    }


def test_identity_bearing_chain_passes_design_with_published_delegations(
    tmp_path: Path, governed_consumer_project
) -> None:
    project = build_design_project(
        tmp_path / "consumer", governed_consumer_project, _identity_request()
    )
    approval = _archived(project.root, project.link.baseline["approval_receipts"][0])
    assert approval["penflow_identity"] == IDENTITY
    assert _archived(project.root, approval["snapshot"])["penflow_identity"] == IDENTITY

    report = produce_verification_report(
        project.workspace, project_root=project.root, profile="design"
    )

    assert report["status"] == "PASS", report["issues"]
    declared = project.link.contract["requirements"]["delegations"]
    assert [row["requirement_id"] for row in declared] == [
        requirement_id("FR-002"),
        requirement_id("AC-002"),
    ]
    assert report["delegated_requirements"] == uncertified(declared)


@pytest.mark.parametrize("identity", [IDENTITY, None])
def test_records_with_and_without_identity_load_identically(
    tmp_path: Path, identity: dict[str, str] | None
) -> None:
    link = write_review_link(tmp_path, _identity_request(identity))
    approval = _archived(link.root, link.approval_ref)
    assert ("penflow_identity" in approval) is (identity is not None)

    loaded = load_livespec_requirements(InputReader(link.root))

    assert loaded["projection"] == link.projection


def test_identity_bearing_authority_import_projects(tmp_path: Path) -> None:
    inherited = write_inherited_authority(tmp_path, BRAINSTORM_FIXTURE, penflow_identity=IDENTITY)

    projection = project_requirements(
        InputReader(inherited.root), inherited.snapshot, inherited.contract
    )

    assert set(inherited.inherited_ids) < {row["id"] for row in projection["requirements"]}


@pytest.mark.parametrize("definition", IDENTITY_DEFINITIONS)
def test_schema_accepts_omitted_and_complete_identity(tmp_path: Path, definition: str) -> None:
    record = _records(tmp_path)[definition]
    assert schema_issues(record, definition) == []
    historical = {key: value for key, value in record.items() if key != "penflow_identity"}
    assert schema_issues(historical, definition) == []


@pytest.mark.parametrize("definition", IDENTITY_DEFINITIONS)
@pytest.mark.parametrize("identity", MALFORMED_IDENTITIES)
def test_schema_refuses_malformed_identity(
    tmp_path: Path, definition: str, identity: object
) -> None:
    record = copy.deepcopy(_records(tmp_path)[definition])
    record["penflow_identity"] = identity
    assert schema_issues(record, definition) != []


@pytest.mark.parametrize("definition", IDENTITY_DEFINITIONS)
def test_identity_leaves_other_keys_closed(tmp_path: Path, definition: str) -> None:
    record = _records(tmp_path)[definition]
    assert schema_issues({**record, "unexpected": True}, definition) != []
    assert schema_issues({**record, "identity": IDENTITY}, definition) != []


def test_malformed_identity_blocks_upstream_requirements(tmp_path: Path) -> None:
    link = write_review_link(tmp_path, _identity_request({**IDENTITY, "unexpected": True}))
    assert (link.root / BASELINE_PATH).is_file()

    with pytest.raises(VerificationInputError, match="review-approval"):
        load_livespec_requirements(InputReader(link.root))
