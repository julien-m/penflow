# @spec(AC-014)
# @spec(AC-015)
# @spec(FR-012)
# @spec FR-010 AC-012: Feature 075 exact-identity fail-before-probe contract.
"""Contract tests for read-only consumer discovery and isolated-copy proof."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from penflow.artifact_policy import MANAGED_IGNORE_BLOCK
from tests.consumer_project_hygiene_probe import (
    CommandResult,
    capture_project_snapshot,
    discover_consumers,
    run_probe,
)


def _git(project: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    """Run one bounded Git command in a temporary test repository."""
    return subprocess.run(
        ["git", *args],
        cwd=project,
        check=True,
        capture_output=True,
        timeout=10,
    )


def _consumer(project: Path, relative: str = "design") -> Path:
    """Create one valid consumer marker and return its canonical document."""
    marker_root = project / relative
    marker_root.mkdir(parents=True)
    ui_pen = marker_root / "ui.pen"
    ui_pen.write_text('{"children":[],"version":"1.0"}\n', encoding="utf-8")
    contract = marker_root / "flow-ui-contract" / "contract.json"
    contract.parent.mkdir()
    contract.write_text("{}\n", encoding="utf-8")
    return ui_pen


def _repository(path: Path) -> Path:
    """Initialize an isolated Git repository with deterministic local identity."""
    path.mkdir(parents=True)
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "penflow-tests@example.invalid")
    _git(path, "config", "user.name", "Penflow Tests")
    return path


def test_discovery_is_complete_sorted_and_prunes_non_consumers(tmp_path: Path) -> None:
    search_root = tmp_path / "projects"
    first = _repository(search_root / "zeta")
    second = _repository(search_root / "alpha")
    _consumer(first, "handoff")
    _consumer(second, "penflow")
    _consumer(second, "node_modules/ignored")
    orphan = second / "orphan" / "ui.pen"
    orphan.parent.mkdir()
    orphan.write_text("{}\n", encoding="utf-8")

    consumers = discover_consumers((search_root,))

    assert [consumer.label for consumer in consumers] == ["consumer-000", "consumer-001"]
    assert [consumer.marker_relative for consumer in consumers] == [
        "alpha/penflow/ui.pen",
        "zeta/handoff/ui.pen",
    ]
    assert all(consumer.ui_pen.name == "ui.pen" for consumer in consumers)


def test_discovery_rejects_hard_linked_marker(tmp_path: Path) -> None:
    project = _repository(tmp_path / "project")
    ui_pen = _consumer(project)
    os.link(ui_pen, ui_pen.with_name("ui-copy.pen"))

    assert discover_consumers((tmp_path,)) == ()


def test_discovery_accepts_repeatable_roots_and_deduplicates_overlap(tmp_path: Path) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first = _repository(first_root / "consumer")
    second = _repository(second_root / "consumer")
    _consumer(first)
    _consumer(second)

    consumers = discover_consumers((second_root, first_root, first))

    assert len(consumers) == 2
    assert {consumer.ui_pen for consumer in consumers} == {
        first / "design" / "ui.pen",
        second / "design" / "ui.pen",
    }


def test_discovery_excludes_source_repository_fixtures(tmp_path: Path) -> None:
    source = _repository(tmp_path / "penflow-source")
    external = _repository(tmp_path / "consumer")
    _consumer(source, "examples/demo")
    external_ui = _consumer(external, "penflow")

    consumers = discover_consumers((tmp_path,), excluded_roots=(source,))

    assert [consumer.ui_pen for consumer in consumers] == [external_ui]


def test_snapshot_binds_git_and_non_git_bytes(tmp_path: Path) -> None:
    project = _repository(tmp_path / "project")
    _consumer(project)
    _git(project, "add", ".")
    before = capture_project_snapshot(project)
    (project / "notes.txt").write_text("changed\n", encoding="utf-8")
    after = capture_project_snapshot(project)

    assert before.index_sha256 == after.index_sha256
    assert before.porcelain_sha256 != after.porcelain_sha256
    assert before.tree_sha256 != after.tree_sha256
    assert all(not row.path.startswith(".git/") for row in after.files)


def test_probe_never_fixes_live_and_mutates_only_fresh_git_copy(tmp_path: Path) -> None:
    search_root = tmp_path / "projects"
    live_project = _repository(search_root / "consumer")
    live_ui = _consumer(live_project)
    _git(live_project, "add", ".")
    _git(live_project, "commit", "-qm", "fixture")
    live_bytes = live_ui.read_bytes()
    observed_argv: list[tuple[str, ...]] = []

    def command_runner(argv: tuple[str, ...], cwd: Path, timeout: int) -> CommandResult:
        observed_argv.append(argv)
        assert cwd == live_project
        assert timeout == 30
        assert "--check" in argv
        assert "--fix" not in argv
        payload = {"stable_result": {"status": "PASS", "findings": []}}
        return CommandResult(0, json.dumps(payload).encode(), b"doctor PASS\n")

    def copy_exerciser(copy_root: Path, copied_marker: Path) -> dict[str, object]:
        assert copy_root != live_project
        assert (copy_root / ".git").is_dir()
        copied_marker.write_bytes(copied_marker.read_bytes() + b" ")
        return {
            "status": "PASS",
            "doctor_fix_runs": 2,
            "producer_runs": 2,
            "assertions": ["mutation_confined_to_copy:PASS"],
        }

    out = tmp_path / "consumer-proof.json"
    receipt = run_probe(
        search_roots=(search_root,),
        output=out,
        command_runner=command_runner,
        copy_exerciser=copy_exerciser,
        temporary_parent=tmp_path / "copies",
    )

    assert receipt["stable_result"]["status"] == "PASS"
    assert receipt["stable_result"]["inventory_count"] == 1
    assert receipt["stable_result"]["consumers"][0]["live"]["zero_diff"] is True
    assert receipt["stable_result"]["consumers"][0]["copy"]["status"] == "PASS"
    assert live_ui.read_bytes() == live_bytes
    assert len(observed_argv) == 1
    assert json.loads(out.read_text(encoding="utf-8")) == receipt


def test_probe_fails_closed_on_empty_inventory(tmp_path: Path) -> None:
    search_root = tmp_path / "empty"
    search_root.mkdir()

    receipt = run_probe(search_roots=(search_root,), output=tmp_path / "receipt.json")

    assert receipt["stable_result"]["status"] == "FAIL"
    assert receipt["stable_result"]["assertions"] == ["inventory_non_empty:FAIL"]


def test_authoritative_identity_mismatch_fails_before_any_probe(tmp_path: Path) -> None:
    search_root = tmp_path / "projects"
    project = _repository(search_root / "consumer")
    _consumer(project)
    authoritative = tmp_path / "authoritative.json"
    authoritative.write_text(
        json.dumps(
            {
                "stable_result": {
                    "feature": "074-penflow-doctor-consumer-project-hygiene",
                    "inventory": [
                        {
                            "marker": f"expected-{index:02d}/ui.pen",
                            "companion": f"expected-{index:02d}/contract.json",
                        }
                        for index in range(11)
                    ],
                }
            }
        ),
        encoding="utf-8",
    )

    def forbidden_runner(_argv: tuple[str, ...], _cwd: Path, _timeout: int) -> CommandResult:
        pytest.fail("identity mismatch must stop before live or copy probes")

    receipt = run_probe(
        search_roots=(search_root,),
        output=tmp_path / "receipt.json",
        command_runner=forbidden_runner,
        expected_inventory_receipt=authoritative,
    )

    stable = receipt["stable_result"]
    assert stable["status"] == "FAIL"
    assert "authoritative_identity_pairs_exact:FAIL" in stable["assertions"]
    assert stable["consumers"] == []


def test_probe_rejects_receipt_or_copy_paths_inside_live_consumer(tmp_path: Path) -> None:
    search_root = tmp_path / "projects"
    project = _repository(search_root / "consumer")
    ui_pen = _consumer(project)
    original = ui_pen.read_bytes()

    with pytest.raises(ValueError, match="inside live consumer"):
        run_probe(search_roots=(search_root,), output=project / "proof.json")
    with pytest.raises(ValueError, match="inside live consumer"):
        run_probe(
            search_roots=(search_root,),
            output=tmp_path / "proof.json",
            temporary_parent=project / "copies",
        )

    assert ui_pen.read_bytes() == original
    assert not (project / "proof.json").exists()
    assert not (project / "copies").exists()


def test_probe_non_git_marker_is_truthful_and_runs_full_isolated_copy(tmp_path: Path) -> None:
    search_root = tmp_path / "projects"
    standalone_root = search_root / "standalone"
    ui_pen = _consumer(standalone_root)
    original = ui_pen.read_bytes()
    copy_commands: list[tuple[str, ...]] = []

    def command_runner(argv: tuple[str, ...], cwd: Path, _timeout: int) -> CommandResult:
        if cwd == ui_pen.parent:
            assert "--check" in argv and "--fix" not in argv
            return CommandResult(
                1,
                b'{"stable_result":{"status":"BLOCKED","findings":[{"code":"not_git_project"}]}}',
                b"",
            )
        copy_commands.append(argv)
        if "doctor" in argv:
            (cwd / ".gitignore").write_text(MANAGED_IGNORE_BLOCK, encoding="utf-8")
        else:
            Path(argv[argv.index("--out") + 1]).write_text("{}\n", encoding="utf-8")
        return CommandResult(0, b'{"status":"PASS"}\n', b"")

    receipt = run_probe(
        search_roots=(search_root,),
        output=tmp_path / "receipt.json",
        temporary_parent=tmp_path / "copies",
        excluded_roots=(),
        command_runner=command_runner,
    )

    consumer = receipt["stable_result"]["consumers"][0]
    assert receipt["stable_result"]["status"] == "PASS"
    assert consumer["live"]["doctor_status"] == "BLOCKED"
    assert consumer["live"]["finding_codes"] == ["not_git_project"]
    assert consumer["live"]["zero_diff"] is True
    assert consumer["live"]["before"]["git_available"] is False
    assert consumer["copy"]["status"] == "PASS"
    assert consumer["copy"]["doctor_fix_runs"] == 2
    assert consumer["copy"]["producer_runs"] == 2
    assert len(copy_commands) == 4
    assert ui_pen.read_bytes() == original

    with pytest.raises(ValueError, match="inside live consumer"):
        run_probe(
            search_roots=(search_root,),
            output=ui_pen.parent / "proof.json",
            excluded_roots=(),
        )


def test_probe_can_write_source_receipt_after_source_fixture_exclusion(tmp_path: Path) -> None:
    search_root = tmp_path / "projects"
    source = _repository(search_root / "penflow-source")
    external = _repository(search_root / "external")
    _consumer(source, "examples/demo")
    _consumer(source, "examples/full")
    _consumer(external, "penflow")
    output = source / "checks" / "qg6.json"

    receipt = run_probe(
        search_roots=(search_root,),
        output=output,
        excluded_roots=(source,),
        command_runner=lambda _argv, _cwd, _timeout: CommandResult(
            0,
            b'{"stable_result":{"status":"PASS","findings":[]}}',
            b"",
        ),
        copy_exerciser=lambda _root, _marker: {
            "status": "PASS",
            "doctor_fix_runs": 2,
            "producer_runs": 2,
            "assertions": ["isolated_copy:PASS"],
        },
    )

    assert receipt["stable_result"]["status"] == "PASS"
    assert receipt["stable_result"]["inventory_count"] == 1
    assert receipt["stable_result"]["inventory"][0]["marker"].startswith("external/")
    assert output.is_file()


def test_probe_fails_when_expected_marker_is_missing(tmp_path: Path) -> None:
    search_root = tmp_path / "projects"
    project = _repository(search_root / "consumer")
    _consumer(project)

    receipt = run_probe(
        search_roots=(search_root,),
        output=tmp_path / "receipt.json",
        expected_markers=("consumer/missing/ui.pen",),
        copy_exerciser=lambda _root, _marker: {
            "status": "PASS",
            "doctor_fix_runs": 2,
            "producer_runs": 2,
            "assertions": ["isolated_copy:PASS"],
        },
        command_runner=lambda _argv, _cwd, _timeout: CommandResult(
            0,
            b'{"stable_result":{"status":"PASS","findings":[]}}',
            b"",
        ),
    )

    assert receipt["stable_result"]["status"] == "FAIL"
    assert "expected_marker:consumer/missing/ui.pen:FAIL" in receipt["stable_result"]["assertions"]


@pytest.mark.parametrize("doctor_exit", [2, 3, 4])
def test_probe_rejects_untruthful_live_doctor_outcomes(tmp_path: Path, doctor_exit: int) -> None:
    search_root = tmp_path / "projects"
    project = _repository(search_root / "consumer")
    _consumer(project)

    receipt = run_probe(
        search_roots=(search_root,),
        output=tmp_path / "receipt.json",
        command_runner=lambda _argv, _cwd, _timeout: CommandResult(
            doctor_exit,
            b'{"stable_result":{"status":"ERROR","findings":[]}}',
            b"blocked\n",
        ),
        copy_exerciser=lambda _root, _marker: {
            "status": "PASS",
            "doctor_fix_runs": 2,
            "producer_runs": 2,
            "assertions": ["isolated_copy:PASS"],
        },
    )

    live = receipt["stable_result"]["consumers"][0]["live"]
    assert live["status"] == "FAIL"
    assert receipt["stable_result"]["status"] == "FAIL"


def test_probe_rejects_incomplete_copy_hook_evidence(tmp_path: Path) -> None:
    search_root = tmp_path / "projects"
    project = _repository(search_root / "consumer")
    _consumer(project)

    receipt = run_probe(
        search_roots=(search_root,),
        output=tmp_path / "receipt.json",
        command_runner=lambda _argv, _cwd, _timeout: CommandResult(
            0,
            b'{"stable_result":{"status":"PASS","findings":[]}}',
            b"",
        ),
        copy_exerciser=lambda _root, _marker: {"status": "PASS"},
    )

    copy = receipt["stable_result"]["consumers"][0]["copy"]
    assert copy["contract_complete"] is False
    assert copy["status"] == "FAIL"
    assert receipt["stable_result"]["status"] == "FAIL"


def test_probe_default_copy_contract_runs_fix_and_producers_only_on_copy(tmp_path: Path) -> None:
    search_root = tmp_path / "projects"
    project = _repository(search_root / "consumer")
    ui_pen = _consumer(project)
    valid_document = {
        "children": [
            {
                "children": [],
                "context": "semantic_id=home; role=screen",
                "id": "home",
                "name": "Home",
                "type": "frame",
            }
        ],
        "version": "1.0",
    }
    ui_pen.write_text(json.dumps(valid_document, sort_keys=True) + "\n", encoding="utf-8")
    _git(project, "add", ".")
    _git(project, "commit", "-qm", "fixture")
    before = capture_project_snapshot(project)
    copy_argv: list[tuple[str, ...]] = []

    def command_runner(argv: tuple[str, ...], cwd: Path, _timeout: int) -> CommandResult:
        if cwd == project:
            assert "--check" in argv
            return CommandResult(
                1,
                b'{"stable_result":{"status":"BLOCKED","findings":'
                b'[{"code":"gitignore.managed_block_missing"}]}}',
                b"",
            )
        copy_argv.append(argv)
        if "doctor" in argv:
            (cwd / ".gitignore").write_text(MANAGED_IGNORE_BLOCK, encoding="utf-8")
        else:
            output_index = argv.index("--out") + 1
            Path(argv[output_index]).write_text("{}\n", encoding="utf-8")
        return CommandResult(0, b'{"status":"PASS"}\n', b"")

    receipt = run_probe(
        search_roots=(search_root,),
        output=tmp_path / "receipt.json",
        temporary_parent=tmp_path / "copies",
        command_runner=command_runner,
    )

    consumer = receipt["stable_result"]["consumers"][0]
    assert consumer["live"]["status"] == "PASS"
    assert consumer["live"]["zero_diff"] is True
    assert consumer["copy"]["status"] == "PASS"
    assert consumer["copy"]["doctor_fix_runs"] == 2
    assert consumer["copy"]["producer_runs"] == 2
    assert len(copy_argv) == 4
    assert all("--fix" in argv for argv in copy_argv[:2])
    assert all("export-expected" in argv for argv in copy_argv[2:])
    assert capture_project_snapshot(project) == before
    assert json.loads(ui_pen.read_text(encoding="utf-8")) == valid_document
