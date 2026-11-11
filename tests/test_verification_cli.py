# @spec AC-018: Given Brainstorm pre-creating closure, when CLI/workspace/C51 design is absent or invalid, then closure blocks; given a valid revalidated design report, then no application-build prerequisite is introduced. — .specs/features/077-complete-verification-workflow/spec.md#ac-018
# @spec AC-017: Given Brainstorm penflow_contract preparation or LiveSpec noncertifying inspection/bootstrap, when workspace is absent or incomplete, then the result is explicitly noncertifying and no future closure report is required. — .specs/features/077-complete-verification-workflow/spec.md#ac-017
"""Real subprocess CLI boundaries, outside pytest's governance injections."""

import ast
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from penflow.verification import produce_verification_report
from penflow.verification_schema import schema_issues
from tests.c51_design_workspace import (
    DesignProject,
    all_delegated_request,
    build_design_project,
    default_delegations,
    review_request,
    uncertified,
)
from tests.c51_review_chain import CONTRACT_PATH, encode, requirement_id, write_review_link


@pytest.mark.parametrize("profile", ["design", "implementation"])
@pytest.mark.parametrize("project_exists", [False, True])
def test_real_cli_governance_failure_uses_c51_wrapper(
    tmp_path: Path, profile: str, project_exists: bool
) -> None:
    project = tmp_path / "consumer"
    if project_exists:
        project.mkdir()
    environment = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1]))
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "penflow",
            "validate-report",
            str(project / "penflow/run-report.json"),
            "--required-profile",
            profile,
            "--project",
            str(project),
            "--schema",
            "--json",
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert not result.stderr
    value = json.loads(result.stdout)
    assert value["status"] == "FAIL"
    assert schema_issues(value, "validation") == []


def test_real_cli_run_failure_uses_closed_report(tmp_path: Path) -> None:
    environment = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1]))
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "penflow",
            "run",
            "--target",
            "penflow",
            "--profile",
            "design",
            "--project",
            str(tmp_path / "missing"),
            "--json",
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert not result.stderr
    assert schema_issues(json.loads(result.stdout), "report") == []


@pytest.mark.parametrize("command", ["run", "validate-report"])
@pytest.mark.parametrize("profile", [None, "design"])
@pytest.mark.parametrize("empty_manifest", [False, True])
def test_real_cli_rejects_build_manifest_without_implementation_before_dispatch(
    tmp_path: Path, command: str, profile: str | None, empty_manifest: bool
) -> None:
    manifest = tmp_path / "build.json"
    report = tmp_path / "run-report.json"
    if not empty_manifest:
        manifest.write_text('{"sentinel": "build"}\n')
    report.write_text('{"sentinel": "report"}\n')
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    arguments = (
        [command, str(report)]
        if command == "validate-report"
        else [command, "--target", str(tmp_path)]
    )
    if profile:
        option = "--required-profile" if command == "validate-report" else "--profile"
        arguments.extend([option, profile])
    manifest_argument = "" if empty_manifest else str(manifest)
    arguments.extend(["--build-manifest", manifest_argument, "--project", str(tmp_path), "--json"])
    result = subprocess.run(
        [sys.executable, "-m", "penflow", *arguments],
        cwd=tmp_path,
        env=dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1])),
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode != 0
    assert "--build-manifest requires" in result.stdout + result.stderr
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before
    if profile:
        assert not result.stderr
        kind = "validation" if command == "validate-report" else "report"
        assert schema_issues(json.loads(result.stdout), kind) == []
    else:
        assert result.returncode == 2
        assert not result.stdout


def _cli(arguments: list[str], project: Path) -> subprocess.CompletedProcess[str]:
    """Run the source-tree CLI on one consumer project in a real subprocess."""
    return subprocess.run(
        [sys.executable, "-m", "penflow", *arguments, "--project", str(project)],
        cwd=project.parent,
        env=dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1])),
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )


# Each case rewrites the reviewed delegation records; only the first one keeps the closed shape.
DELEGATION_SHAPE_CASES = {
    "valid": lambda rows: rows,
    "empty array": lambda rows: [],
    "missing rationale": lambda rows: [
        {key: value for key, value in rows[0].items() if key != "rationale"}
    ],
    "blank rationale": lambda rows: [{**rows[0], "rationale": " \t"}],
    "other owner": lambda rows: [{**rows[0], "acceptance_owner": "another-acceptance"}],
    "additional key": lambda rows: [{**rows[0], "certified": False}],
}


def _contract_verdict(project: Path, contract: dict) -> bool:
    """Tell whether the contract validator accepts the document, from its exit and issues."""
    path = project / CONTRACT_PATH
    path.write_bytes(encode(contract))
    result = _cli(["validate-flow-contract", str(path), "--json"], project)
    errors = [row for row in json.loads(result.stdout)["issues"] if row["severity"] == "error"]
    assert (result.returncode == 0) == (not errors), result.stdout
    return not errors


# @spec AC-001: Closed optional delegations shape — .specs/features/082-reviewed-requirement-delegation-to-upstream-acceptance/spec.md#ac-001
def test_flow_contract_cli_closes_delegation_shape(
    tmp_path: Path, governed_consumer_project
) -> None:
    project = governed_consumer_project(tmp_path / "consumer", None)
    link = write_review_link(project, review_request(delegations=default_delegations()))
    declared = link.contract["requirements"]
    contract_verdicts = {}
    projection_verdicts = {}
    for label, rewrite in DELEGATION_SHAPE_CASES.items():
        value = rewrite(default_delegations())
        contract_verdicts[label] = _contract_verdict(
            project, {**link.contract, "requirements": {**declared, "delegations": value}}
        )
        projection_verdicts[label] = not schema_issues(
            {**link.projection, "delegated": value}, "projection"
        )
    expected = {label: label == "valid" for label in DELEGATION_SHAPE_CASES}
    assert (contract_verdicts, projection_verdicts) == (expected, expected)
    optional = {key: value for key, value in declared.items() if key != "delegations"}
    assert _contract_verdict(project, {**link.contract, "requirements": optional})


def _delegated_design_project(root: Path, govern) -> tuple[DesignProject, list[dict]]:
    """Build the delegated design fixture and the report entries its contract implies."""
    project = build_design_project(root, govern, review_request(delegations=default_delegations()))
    return project, uncertified(project.link.contract["requirements"]["delegations"])


# @spec AC-009: CLI prints delegated requirements — .specs/features/082-reviewed-requirement-delegation-to-upstream-acceptance/spec.md#ac-009
def test_run_cli_prints_delegated_requirements(tmp_path: Path, governed_consumer_project) -> None:
    project, expected = _delegated_design_project(tmp_path / "consumer", governed_consumer_project)

    result = _cli(["run", "--target", str(project.workspace), "--profile", "design"], project.root)

    assert (result.returncode, result.stderr) == (0, ""), result.stdout
    lines = result.stdout.splitlines()
    assert lines[0] == "Status: PASS"
    printed = [
        line.partition(": ")[2] for line in lines if line.startswith("delegated_requirements: ")
    ]
    assert [ast.literal_eval(value) for value in printed] == [expected]


def _edit_stored_report(project: DesignProject, original: bytes, edit) -> tuple[int, str, set[str]]:
    """Store an edited report, revalidate it with the CLI and restore the produced bytes."""
    path = project.workspace / "run-report.json"
    report = json.loads(original)
    report["delegated_requirements"] = edit(report["delegated_requirements"])
    path.write_bytes(encode(report))
    result = _cli(
        ["validate-report", str(path), "--schema", "--required-profile", "design", "--json"],
        project.root,
    )
    path.write_bytes(original)
    value = json.loads(result.stdout)
    return result.returncode, value["status"], {row["code"] for row in value["issues"]}


# A schema-valid edit differs from the recomputation; a shape violation is an invalid source.
STORED_LIST_EDITS = {
    "entry removed": (lambda rows: rows[:1], "verification.source.report_changed"),
    "entry added": (
        lambda rows: [*rows, {**rows[0], "requirement_id": requirement_id("AC-001")}],
        "verification.source.report_changed",
    ),
    "entries reordered": (lambda rows: rows[::-1], "verification.source.report_changed"),
    "certified true": (
        lambda rows: [{**rows[0], "certified": True}, *rows[1:]],
        "verification.source.invalid",
    ),
    "additional key": (
        lambda rows: [{**rows[0], "rationale": "copied"}, *rows[1:]],
        "verification.source.invalid",
    ),
}


def _all_delegated_outcome(root: Path, govern) -> dict:
    """Run the design profile on a contract that delegates everything, with full evidence."""
    project = build_design_project(root, govern, all_delegated_request())
    result = _cli(
        ["run", "--target", str(project.workspace), "--profile", "design", "--json"], project.root
    )
    report = json.loads(result.stdout)
    blocked = [
        gate["id"] for gate in report["gates"] if gate["required"] and gate["status"] != "PASS"
    ]
    return {
        "exit": result.returncode,
        "status": report["status"],
        "incomplete": "verification.obligation.incomplete"
        in {row["code"] for row in report["issues"]},
        "required": report["obligations"]["required"],
        "verified": report["obligations"]["verified"],
        "gates not passing": blocked,
        "delegated": report.get("delegated_requirements"),
        "declared": uncertified(project.link.contract["requirements"]["delegations"]),
    }


# @spec AC-010: Edited delegated list fails revalidation — .specs/features/082-reviewed-requirement-delegation-to-upstream-acceptance/spec.md#ac-010
def test_validate_report_cli_rejects_edited_delegated_list(
    tmp_path: Path, governed_consumer_project
) -> None:
    project, entries = _delegated_design_project(tmp_path / "consumer", governed_consumer_project)
    produced = produce_verification_report(
        project.workspace, project_root=project.root, profile="design"
    )
    assert (produced["status"], produced.get("delegated_requirements")) == ("PASS", entries)
    original = (project.workspace / "run-report.json").read_bytes()
    observed = {
        label: _edit_stored_report(project, original, edit)
        for label, (edit, _) in STORED_LIST_EDITS.items()
    }
    assert observed == {
        label: (1, "FAIL", {code}) for label, (_, code) in STORED_LIST_EDITS.items()
    }

    # The twin without delegation requires one obligation per contract structure record.
    twin_required = produced["obligations"]["required"]
    everything = _all_delegated_outcome(tmp_path / "all-delegated", governed_consumer_project)
    assert everything == {
        "exit": 1,
        "status": "FAIL",
        "incomplete": True,
        "required": twin_required,
        "verified": 0,
        "gates not passing": [],
        "delegated": everything["declared"],
        "declared": everything["declared"],
    }
