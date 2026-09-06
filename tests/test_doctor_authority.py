"""Archive classification must not hide unregistered or malformed design sources."""

import json
from pathlib import Path

import pytest

from penflow.doctor_authority import archived_authority_canvas
from penflow.doctor_files import _inventory_pen_paths
from penflow.doctor_files import _plan_pen_initialization
from penflow.doctor_models import DoctorFinding, _Repair
from penflow.product_freeze import load_frozen_product
from penflow.verification_files import InputReader
from tests.test_product_sources_adversarial import FIXTURE, WORKSPACE, _copy_consumer


@pytest.mark.parametrize("pointer", [{}, {"path": "missing.json", "sha256": "0" * 64}])
def test_malformed_authority_does_not_hide_canvas(tmp_path: Path, pointer: dict) -> None:
    archive = tmp_path / ".specs/penflow-authority/unregistered/ui.pen"
    archive.parent.mkdir(parents=True)
    archive.write_text('{"children":[]}')
    (tmp_path / ".specs/penflow-brainstorm-authority.json").write_text(json.dumps(pointer))
    ignored, findings = archived_authority_canvas(tmp_path)
    assert not ignored
    assert findings[0].code == "pen.authority_archive_invalid"
    assert archive in _inventory_pen_paths(tmp_path)[0]


def test_unregistered_archive_directory_remains_in_inventory(tmp_path: Path) -> None:
    archive = tmp_path / ".specs/penflow-authority/arbitrary/ui.pen"
    archive.parent.mkdir(parents=True)
    archive.write_text('{"children":[]}')
    assert archived_authority_canvas(tmp_path) == (frozenset(), ())
    assert archive in _inventory_pen_paths(tmp_path)[0]


def test_product_inventory_is_not_polluted_by_prior_workflow_reads(tmp_path: Path) -> None:
    root = _copy_consumer(FIXTURE, tmp_path)
    workspace = root / WORKSPACE
    workflow = workspace / "product-contract/.workflow-history/source.md"
    workflow.parent.mkdir()
    workflow.write_text("actual workflow authority")
    reader = InputReader(root)
    reader.read(workflow)
    _, sources = load_frozen_product(reader, workspace)
    assert str(workflow) not in {item["path"] for item in sources}
    assert workflow in reader.observed
    assert len(sources) == 6
    reader.recheck()


def test_initialization_uses_the_only_prepared_handoff_workspace(tmp_path: Path) -> None:
    (tmp_path / "handoff/penflow").mkdir(parents=True)
    repair = _plan_pen_initialization(tmp_path)
    assert isinstance(repair, _Repair)
    assert repair.relative_path == "handoff/penflow/ui.pen"


def test_two_prepared_workspaces_block_initialization(tmp_path: Path) -> None:
    (tmp_path / "handoff/penflow").mkdir(parents=True)
    (tmp_path / "penflow").mkdir()
    finding = _plan_pen_initialization(tmp_path)
    assert isinstance(finding, DoctorFinding)
    assert finding.code == "pen.initialization_workspace_ambiguous"


def test_handoff_symlink_does_not_redirect_initialization(tmp_path: Path) -> None:
    external = tmp_path / "external"
    (external / "penflow").mkdir(parents=True)
    (tmp_path / "handoff").symlink_to(external, target_is_directory=True)
    finding = _plan_pen_initialization(tmp_path)
    assert isinstance(finding, DoctorFinding)
    assert finding.code == "pen.initialization_parent_unsafe"
