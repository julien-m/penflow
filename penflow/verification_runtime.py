"""Join captured runtime artifacts and evaluate every approved expected outcome."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .actual_provenance import validate_actual_provenance
from .causal_evidence import validate_causal_evidence
from .verification_comparison import compare_required_trees
from .tree import flatten_nodes, validate_actual_tree
from .verification_build import observation_authority_issues
from .verification_capture import read_ui_snapshot
from .verification_expectations import reconcile_expectations
from .verification_files import VerificationInputError
from .verification_outcomes import evaluate_outcome
from .verification_policy import GateBook
from .verification_schema import issue
from .verification_snapshot import VerificationSnapshot


def evaluate_runtime(
    snapshot: VerificationSnapshot,
    gates: GateBook,
    values: dict[str, Any],
    manifest: dict[str, Any] | None,
) -> dict[str, Any]:
    """Recompute C12/comparison and source obligations without trusting serialized counts."""
    observations: dict[str, tuple[Path, dict[str, Any]]] = {}
    if gates.rows["validate-actual"]["required"]:
        gates.evaluate("validate-actual", lambda: _actual(snapshot, values, manifest))
        gates.evaluate(
            "compare-tree",
            lambda: compare_required_trees(snapshot.contract, values["expected"], values["actual"]),
            dependencies=("validate-actual", "export-expected"),
        )
        values["manifest"] = manifest
        gates.evaluate(
            "validate-actual-provenance",
            lambda: _provenance(snapshot, manifest),
            dependencies=("validate-actual",),
        )
        gates.evaluate(
            "typed-outcome-obligations",
            lambda: _runtime_evidence(snapshot, observations, manifest, values),
            dependencies=("validate-actual-provenance",),
        )
        if any(item.get("causal") for item in snapshot.contract["transitions"]):
            gates.evaluate(
                "validate-causal-evidence",
                lambda: _causal(snapshot, manifest),
                dependencies=("validate-actual-provenance",),
            )
        else:
            gates.not_applicable(
                "validate-causal-evidence",
                "/transitions",
                "no source transition declares historical C44 causal evidence",
            )
    return _obligations(snapshot, gates, values, observations)


def _actual(
    snapshot: VerificationSnapshot, values: dict[str, Any], manifest: dict[str, Any] | None
) -> list[dict[str, Any]]:
    if manifest is None:
        raise VerificationInputError("verification.build.required")
    values["actual"] = snapshot.object("actual-ui-tree.json")
    _runner_file(snapshot, manifest, snapshot.workspace / "actual-ui-tree.json")
    return validate_actual_tree(values["actual"])


def _runner_file(snapshot: VerificationSnapshot, manifest: dict[str, Any], path: Path) -> None:
    refs = {
        str(snapshot.reader.path(item["path"])): item["sha256"] for item in manifest["evidence"]
    }
    if refs.get(str(path)) != snapshot.reader.observed.get(path):
        raise VerificationInputError(f"verification.evidence.not_runner_bound: {path}")


def _provenance(
    snapshot: VerificationSnapshot, manifest: dict[str, Any] | None
) -> list[dict[str, Any]]:
    from .actual_provenance import actual_provenance_path

    if manifest is None:
        raise VerificationInputError("verification.build.required")
    actual = snapshot.workspace / "actual-ui-tree.json"
    path = actual_provenance_path(actual)
    receipt = snapshot.reader.object(snapshot.reader.read(path))
    _runner_file(snapshot, manifest, path)
    if (
        receipt.get("sourceKind") != "runtime-capture"
        or receipt.get("producer", {}).get("name") != manifest["producer"]["id"]
    ):
        raise VerificationInputError("verification.producer.capture_identity")
    # Exact geometry may legitimately equal the design. Independent caller-owned
    # build/evidence authority replaces C47's heuristic rejection of equal roots.
    return validate_actual_provenance(
        actual,
        now=datetime.now(UTC),
        max_age_seconds=86400,
        require_fresh=True,
        allowed_surfaces=sorted({screen["surface"] for screen in snapshot.contract["screens"]}),
    )


def _observations(
    snapshot: VerificationSnapshot,
    observations: dict[str, tuple[Path, dict[str, Any]]],
    manifest: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if manifest is None:
        raise VerificationInputError("verification.build.required")
    findings: list[dict[str, Any]] = []
    directory = snapshot.workspace / "outcome-observations"
    for path in snapshot.reader.files(directory, "*.json"):
        observation = snapshot.reader.object(snapshot.reader.read(path), "observation")
        identity = observation["obligation_id"]
        if identity in observations:
            raise VerificationInputError("verification.obligation.duplicate_observation")
        observations[identity] = (path, observation)
        findings.extend(
            issue(code, str(path), "observation does not match independent runner authority")
            for code in observation_authority_issues(snapshot, manifest, observation, path)
        )
    expected = {item["obligation_id"] for item in snapshot.contract["outcome_expectations"]}
    if set(observations) - expected:
        findings.append(
            issue(
                "verification.obligation.extra_observation",
                str(directory),
                "runtime observations contain unknown source duties",
            )
        )
    return findings


def _causal(
    snapshot: VerificationSnapshot, manifest: dict[str, Any] | None
) -> list[dict[str, Any]]:
    if manifest is None:
        raise VerificationInputError("verification.build.required")
    path = snapshot.workspace / "causal-transition-evidence.json"
    snapshot.reader.object(snapshot.reader.read(path))
    _runner_file(snapshot, manifest, path)
    return validate_causal_evidence(snapshot.workspace / "flow-ui-contract/contract.json", path)[
        "issues"
    ]


def _obligations(
    snapshot: VerificationSnapshot,
    gates: GateBook,
    values: dict[str, Any],
    observations: dict[str, tuple[Path, dict[str, Any]]],
) -> dict[str, Any]:
    implementation = gates.rows["validate-actual"]["required"]
    entries = reconcile_expectations(
        snapshot.contract,
        approved_expectations=tuple(
            binding["expected"] for binding in snapshot.projection["bindings"]
        ),
    )
    items = []
    findings = []
    required = verified = 0
    for entry in entries:
        findings.extend(entry.issues)
        if not implementation and entry.slot.category != "structure":
            continue
        required += 1
        if entry.expected is None:
            continue
        requirement_ids = sorted(
            {
                binding["requirement_id"]
                for binding in snapshot.projection["bindings"]
                if binding["obligation_id"] == entry.expected["obligation_id"]
            }
        )
        if not requirement_ids:
            findings.append(
                issue(
                    "verification.obligation.unbound",
                    entry.slot.source_pointer,
                    "derived duty has no approved source requirement",
                    obligation_id=entry.slot.id,
                )
            )
            continue
        errors, refs = _one_obligation(snapshot, gates, values, observations, entry, implementation)
        verified += int(not errors)
        items.append(
            {
                "id": entry.slot.id,
                "category": entry.slot.category,
                "requirement_ids": requirement_ids,
                "status": "FAIL" if errors else "PASS",
                "observation_refs": refs,
                "issues": errors,
                "expected": entry.expected,
            }
        )
    return {
        "required": required,
        "verified": verified,
        "missing": required - verified,
        "items": items,
        "issues": findings,
    }


def _one_obligation(
    snapshot: VerificationSnapshot,
    gates: GateBook,
    values: dict[str, Any],
    observations: dict[str, tuple[Path, dict[str, Any]]],
    entry: Any,
    implementation: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    errors = list(entry.issues)
    refs: list[dict[str, str]] = []
    if entry.slot.category == "structure":
        dependencies = ("semantic-context-coverage", "export-expected", "code-ir") + (
            (
                "validate-actual",
                "compare-tree",
                "validate-actual-provenance",
                "typed-outcome-obligations",
            )
            if implementation
            else ()
        )
        if any(gates.rows[gate]["status"] != "PASS" for gate in dependencies):
            errors.append(
                issue(
                    "verification.obligation.structure_unverified",
                    entry.slot.source_pointer,
                    "required tree and runtime controls have not passed",
                    obligation_id=entry.slot.id,
                )
            )
        elif implementation:
            errors.extend(
                _runtime_structure(
                    snapshot, entry, values["actual"], observations, values["manifest"]
                )
            )
        return errors, refs
    record = observations.get(entry.expected["obligation_id"])
    if record is None or gates.rows["typed-outcome-obligations"]["status"] != "PASS":
        errors.append(
            issue(
                "verification.obligation.observation_missing",
                entry.slot.source_pointer,
                "independently bound typed observation is required",
                obligation_id=entry.slot.id,
            )
        )
    else:
        path, observation = record
        errors.extend(evaluate_outcome(entry.expected, observation, contract=snapshot.contract))
        refs.append({"path": str(path), "sha256": snapshot.reader.observed[path]})
    return errors, refs


def _runtime_structure(
    snapshot: VerificationSnapshot,
    entry: Any,
    actual: dict[str, Any],
    observations: dict[str, tuple[Path, dict[str, Any]]],
    manifest: dict[str, Any],
) -> list[dict[str, Any]]:
    from .verification_assertions import resolve_pointer

    source = resolve_pointer(snapshot.contract, entry.slot.source_pointer)
    if "semantic_id" in source:
        nodes = [
            node
            for screen in actual["screens"]
            if screen["screen_id"] == source["screen_id"]
            for node in flatten_nodes(screen["root"])
            if node.get("semantic_id") == source["semantic_id"]
        ]
        if nodes and all(
            node["role"] == source["role"]
            and (not isinstance(source.get("text"), str) or node.get("text") == source["text"])
            for node in nodes
        ):
            return []
    else:
        screen_index = int(entry.slot.source_pointer.split("/")[2])
        screen_id = snapshot.contract["screens"][screen_index]["id"]
        for value in actual.get("observed_states", []):
            if (
                value["screen_id"] == screen_id
                and value["state"] == source["id"]
                and _state_evidence(snapshot, value, observations, manifest)
            ):
                return []
    return [
        issue(
            "verification.obligation.structure_not_observed",
            entry.slot.source_pointer,
            "source node, required copy or screen state was not observed",
            obligation_id=entry.slot.id,
        )
    ]


def _state_evidence(
    snapshot: VerificationSnapshot,
    value: dict[str, Any],
    observations: dict[str, tuple[Path, dict[str, Any]]],
    manifest: dict[str, Any],
) -> bool:
    path = snapshot.reader.path(value["evidence"]["path"])
    matches = [
        observation for observed_path, observation in observations.values() if observed_path == path
    ]
    if not matches:
        witness = read_ui_snapshot(snapshot, manifest, value["evidence"])
        return (
            all(witness[key] == value[key] for key in ("scenario_id", "session_id"))
            and witness["facts"]["screen_id"] == value["screen_id"]
            and witness["facts"]["state"] == value["state"]
            and witness["facts"]["visible"]
        )
    if len(matches) != 1 or snapshot.reader.observed.get(path) != value["evidence"]["sha256"]:
        return False
    observation = matches[0]
    if observation["capability"] != "ui" or any(
        observation[key] != value[key] for key in ("scenario_id", "session_id")
    ):
        return False
    return any(
        observation[side]["screen_id"] == value["screen_id"]
        and observation[side]["state"] == value["state"]
        and observation[side]["visible"]
        for side in ("before", "after")
    )


def _runtime_evidence(
    snapshot: VerificationSnapshot,
    observations: dict[str, tuple[Path, dict[str, Any]]],
    manifest: dict[str, Any] | None,
    values: dict[str, Any],
) -> list[dict[str, Any]]:
    findings = _observations(snapshot, observations, manifest)
    if manifest is None:
        return findings
    known = {
        (screen["id"], state["id"])
        for screen in snapshot.contract["screens"]
        for state in screen["states"]
    }
    seen = set()
    for value in values["actual"].get("observed_states", []):
        identity = tuple(value[key] for key in ("screen_id", "state", "scenario_id", "session_id"))
        if (
            identity in seen
            or identity[:2] not in known
            or not _state_evidence(snapshot, value, observations, manifest)
        ):
            findings.append(
                issue(
                    "verification.evidence.state_index_invalid",
                    "/observed_states",
                    "state index must uniquely join a real UI witness of the declared state",
                )
            )
        seen.add(identity)
    return findings
