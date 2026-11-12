"""Build LiveSpec review chains for C51 tests the way an upstream producer does.

Every envelope, digest and stored projection is computed here from the written
bytes. The stored projection comes from this module's own oracle and never from
``project_requirements``, so a chain is accepted only when production recomputes
the same canonical bytes.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from penflow.requirement_markdown import extract_requirement_definitions_text, semantic_text_sha256
from penflow.verification_applicability import DECISIONS
from penflow.verification_json import canonical_bytes, digest

# Heterogeneous JSON documents; their closed shape is enforced by the C51 schema under test.
Json = dict[str, Any]

APPROVALS = ".specs/penflow-approvals"
BASELINE_PATH = ".specs/penflow-requirements.json"
CONTRACT_PATH = "penflow/flow-ui-contract/contract.json"
POLICY_SOURCE_PATH = ".specs/penflow-verification-policy-source.json"
WORKFLOW_PATH = ".specs/penflow-workflow.md"
SOURCE_KIND = "livespec-fr-ac-v1"
ACCEPTANCE_OWNER = "livespec-acceptance"
DEFAULT_SLUG = "001-checkout"
PLAN_TEXT = "# Technical Plan\n\nReviewed plan of the selected feature.\n"
SPEC_TEXT = """---
status: Approved
---
# Feature
## Functional Requirements
- **FR-001**: Show the checkout screen. AC-001.
- **FR-002**: Record the audit trail owned by the upstream acceptance. AC-002.
## Acceptance Criteria
| ID | Criterion |
|---|---|
| AC-001 | The checkout screen is visible. |
| AC-002 | The audit trail is accepted upstream. |
"""


@dataclass(frozen=True)
class FeatureSource:
    """One selected feature with its reviewed spec and plan text."""

    slug: str = DEFAULT_SLUG
    spec: str = SPEC_TEXT
    plan: str = PLAN_TEXT


@dataclass(frozen=True)
class ChainOverrides:
    """Single-fact deviations from a consistent chain, used by rejection cases."""

    reviewed_projection: Callable[[Json], Json] | None = None
    projection_sha256: str | None = None
    baseline_projection: Callable[[Json], Json] | None = None
    changes: Callable[[list[Json]], list[Json]] | None = None
    approval_from: ReviewLink | None = None
    oracle_ignores_delegations: bool = False


@dataclass(frozen=True)
class ReviewRequest:
    """Inputs of one reviewed baseline: cumulative features, contract and requirement status."""

    contract: Json
    bindings: tuple[tuple[str, str], ...]
    delegations: object = None
    features: tuple[FeatureSource, ...] = (FeatureSource(),)
    feature: str = DEFAULT_SLUG
    retired: tuple[str, ...] = ()
    previous: ReviewLink | None = None
    overrides: ChainOverrides = field(default_factory=ChainOverrides)
    # LiveSpec adds the identity of the Penflow CLI it invoked to the snapshot and the approval.
    penflow_identity: Json | None = None


@dataclass(frozen=True)
class ReviewLink:
    """One written baseline with the identities a successor or a test needs."""

    root: Path
    baseline: Json
    baseline_ref: Json
    approval_ref: Json
    snapshot: Json
    contract: Json
    projection: Json


def requirement_id(local_id: str, slug: str = DEFAULT_SLUG) -> str:
    """Return the namespaced id of one FR/AC definition of a selected feature."""
    return f"livespec:{slug}:{local_id}"


def delegation(local_id: str, rationale: str, slug: str = DEFAULT_SLUG) -> Json:
    """Build one delegation record as a contract author declares it."""
    return {
        "requirement_id": requirement_id(local_id, slug),
        "acceptance_owner": ACCEPTANCE_OWNER,
        "rationale": rationale,
    }


def bind(local_ids: tuple[str, ...], obligation_ids: list[str]) -> tuple[tuple[str, str], ...]:
    """Bind each listed requirement of the default feature to each listed obligation."""
    return tuple(
        (requirement_id(local_id), obligation_id)
        for local_id in local_ids
        for obligation_id in obligation_ids
    )


def encode(value: object) -> bytes:
    """Serialize one stored JSON artifact; its digest is always taken from these bytes."""
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def write_file(root: Path, relative: str, raw: bytes) -> Json:
    """Write bytes inside the project and return their file reference."""
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return {"path": relative, "sha256": digest(raw)}


def archive(root: Path, kind: str, raw: bytes) -> Json:
    """Write one immutable approval archive named after its own digest."""
    suffix = ".md" if kind == "source" else ".json"
    return write_file(root, f"{APPROVALS}/{kind}-{digest(raw)}{suffix}", raw)


def oracle_projection(
    features: tuple[FeatureSource, ...], contract: Json, *, with_delegations: bool = True
) -> Json:
    """Compute the projection an upstream producer stores, without production projection code."""
    requirements = [
        {"id": item.id, "source_pointer": item.source_pointer, "text_sha256": item.text_sha256}
        for feature in features
        for item in extract_requirement_definitions_text(feature.spec, feature.slug)
    ]
    declared = contract["requirements"]
    outcomes = {item["obligation_id"]: item for item in contract["outcome_expectations"]}
    bindings = [
        {
            **row,
            "category": outcomes[row["obligation_id"]]["category"],
            "expected": outcomes[row["obligation_id"]],
        }
        for row in declared["bindings"]
    ]
    delegated = declared.get("delegations", []) if with_delegations else []
    covered = {row["requirement_id"] for row in [*bindings, *delegated]}
    projection: Json = {
        "source_kind": SOURCE_KIND,
        "sources": declared["source_refs"] if features else [],
        "requirements": requirements,
        "bindings": bindings if features else [],
        "uncovered": sorted({row["id"] for row in requirements} - covered),
    }
    if delegated and features:
        projection["delegated"] = sorted(delegated, key=lambda row: row["requirement_id"])
    return projection


def expected_changes(
    previous: ReviewLink | None, sources: list[Json], projection: Json, contract_sha: str
) -> list[Json]:
    """Compute the reviewed delta a producer records against its predecessor baseline."""
    if previous is None:
        return []
    prior = previous.baseline
    old_sources = {row["path"]: row for row in prior["sources"]}
    new_sources = {row["path"]: row for row in sources}
    old_rows, new_rows = binding_rows(prior["projection"]), binding_rows(projection)
    changed = {
        key for key in old_rows.keys() | new_rows.keys() if old_rows.get(key) != new_rows.get(key)
    }
    removed = sorted(
        {row["id"] for row in prior["projection"]["requirements"]}
        - {row["id"] for row in projection["requirements"]}
    )
    contract_changed = prior["contract"]["sha256"] != contract_sha
    result = []
    for path in sorted(old_sources.keys() | new_sources.keys()):
        before, after = old_sources.get(path), new_sources.get(path)
        if before != after or changed or contract_changed:
            result.append(
                {
                    "source_path": path,
                    "old_sha256": before["sha256"] if before else digest(b""),
                    "new_sha256": after["sha256"] if after else digest(b""),
                    "removed_requirement_ids": removed,
                    "changed_binding_ids": sorted(changed),
                }
            )
    return result


def binding_rows(projection: Json) -> dict[str, Json]:
    """Index the bindings of one projection by their ``requirement:obligation`` key."""
    return {
        f"{row['requirement_id']}:{row['obligation_id']}": row for row in projection["bindings"]
    }


def write_review_link(root: Path, request: ReviewRequest) -> ReviewLink:
    """Write one reviewed baseline, its approval chain files and the current sources."""
    root = root.resolve()
    active = tuple(item for item in request.features if item.slug not in request.retired)
    sources = [_approved_source(root, item, "spec.md") for item in request.features]
    plans = [_approved_source(root, item, "plan.md") for item in request.features]
    contract = _reviewed_contract(request, active, sources)
    contract_ref = archive(root, "contract", encode(contract))
    overrides = request.overrides
    projection = oracle_projection(
        active, contract, with_delegations=not overrides.oracle_ignores_delegations
    )
    if overrides.reviewed_projection is not None:
        projection = overrides.reviewed_projection(projection)
    selection = [item.slug for item in request.features]
    inputs = {
        "sources": sources,
        "plans": plans,
        "contract": contract_ref,
        "projection_sha256": overrides.projection_sha256 or digest(canonical_bytes(projection)),
        "selection_sha256": digest(canonical_bytes(selection)),
        "verification_policy": _policy_source(root, contract["verification_policy"]),
    }
    changes = expected_changes(request.previous, sources, projection, contract_ref["sha256"])
    if overrides.changes is not None:
        changes = overrides.changes(changes)
    envelope = {
        "feature": request.feature,
        "scope": {"project_root": str(root), "workspace": str(root / "penflow")},
        "selection": selection,
        "inputs": inputs,
        "prior_receipt": request.previous.baseline_ref if request.previous else None,
        "changes": changes,
        "disposition": "active" if active else "retired",
        "retired_features": list(request.retired),
    }
    return _write_envelopes(root, request, envelope, contract, projection)


def _write_envelopes(
    root: Path, request: ReviewRequest, envelope: Json, contract: Json, projection: Json
) -> ReviewLink:
    identity = _identity_field(request.penflow_identity)
    snapshot = {
        "kind": "livespec-penflow-review-snapshot",
        "version": 1,
        "command": "spec-plan",
        **envelope,
        "projection": projection,
        **identity,
    }
    snapshot_ref = archive(root, "snapshot", encode(snapshot))
    approval_ref = _approval(root, {**envelope, **identity}, snapshot_ref)
    reused = request.overrides.approval_from
    contract_ref = envelope["inputs"]["contract"]
    edited = request.overrides.baseline_projection
    baseline = {
        "kind": "livespec-penflow-requirements-baseline",
        "version": 1,
        "scope": envelope["scope"],
        "selection": envelope["selection"],
        "approval_receipts": [reused.approval_ref if reused else approval_ref],
        "sources": envelope["inputs"]["sources"],
        # A retired baseline keeps the archived contract; an active one names the current file.
        "contract": contract_ref
        if envelope["disposition"] == "retired"
        else {"path": CONTRACT_PATH, "sha256": contract_ref["sha256"]},
        "projection": edited(projection) if edited else projection,
        "previous": envelope["prior_receipt"],
        "disposition": envelope["disposition"],
        "retired_features": envelope["retired_features"],
    }
    raw = encode(baseline)
    write_file(root, BASELINE_PATH, raw)
    write_file(root, CONTRACT_PATH, encode(contract))
    return ReviewLink(
        root, baseline, archive(root, "baseline", raw), approval_ref, snapshot, contract, projection
    )


def _identity_field(identity: Json | None) -> Json:
    """Write the key only when a Penflow CLI was invoked, as LiveSpec does; never null."""
    return {} if identity is None else {"penflow_identity": identity}


def _approval(root: Path, envelope: Json, snapshot_ref: Json) -> Json:
    output = {
        "invocation_id": f"review-{snapshot_ref['sha256'][:12]}",
        "producer_id": "independent-contract-review",
        "input_sha256": snapshot_ref["sha256"],
        "verdict": "PASS",
        "blocking_count": 0,
        "findings": [],
    }
    approval = {
        "kind": "livespec-penflow-review-approval",
        "version": 1,
        "command": "spec-plan",
        **envelope,
        "review": {**output, "output": archive(root, "review-output", encode(output))},
        "snapshot": snapshot_ref,
    }
    return archive(root, "approval", encode(approval))


def _approved_source(root: Path, feature: FeatureSource, filename: str) -> Json:
    text = feature.spec if filename == "spec.md" else feature.plan
    raw = text.encode("utf-8")
    current = write_file(root, f".specs/features/{feature.slug}/{filename}", raw)
    return {
        **current,
        "semantic_sha256": semantic_text_sha256(text),
        "reviewed_snapshot": archive(root, "source", raw),
    }


def _reviewed_contract(
    request: ReviewRequest, active: tuple[FeatureSource, ...], sources: list[Json]
) -> Json:
    slugs = {item.slug for item in active}
    requirements: Json = {
        "source_kind": SOURCE_KIND,
        "source_refs": [
            {"path": row["path"], "sha256": row["sha256"]}
            for row in sources
            if row["path"].split("/")[-2] in slugs
        ],
        "bindings": [
            {"requirement_id": requirement, "obligation_id": obligation}
            for requirement, obligation in request.bindings
        ],
    }
    if request.delegations is not None:
        requirements["delegations"] = request.delegations
    return {**request.contract, "requirements": requirements}


def _policy_source(root: Path, decisions: Json, inherited: Json | None = None) -> Json:
    """Write the reviewed workflow and the policy source that binds its decisions."""
    frontmatter = yaml.safe_dump({"penflow_verification_policy": {"livespec": decisions}})
    workflow = write_file(root, WORKFLOW_PATH, f"---\n{frontmatter}---\n# Workflow\n".encode())
    source = {
        "kind": "penflow-verification-policy-source",
        "version": 1,
        "workflow": workflow,
        "decisions": decisions,
        "inherited_authority": inherited,
    }
    return write_file(root, POLICY_SOURCE_PATH, encode(source))


IMPORT_WORKSPACE = "imports/brainstorm/penflow"
IMPORT_PACKAGE_PATH = ".specs/penflow-brainstorm-authority-import.json"


@dataclass(frozen=True)
class InheritedAuthority:
    """A LiveSpec projection input whose policy source inherits a Brainstorm authority."""

    root: Path
    snapshot: Json
    contract: Json
    inherited_ids: tuple[str, ...]


def write_inherited_authority(
    root: Path, fixture: Path, *, penflow_identity: Json | None = None
) -> InheritedAuthority:
    """Import the frozen Brainstorm fixture and reuse its records in a LiveSpec contract.

    The import package lists the exact fixture bytes and a synthetic schema-valid
    design report; the real import checks authenticate all of them.
    """
    root = root.resolve()
    provenance = json.loads((fixture / "provenance.json").read_text(encoding="utf-8"))
    origin = Path(provenance["source_root"])
    scope = {"project_root": str(origin), "workspace": str(origin / "handoff/penflow")}
    files = []
    for item in provenance["files"]:
        local = f"{IMPORT_WORKSPACE}/{Path(item['path']).relative_to('handoff/penflow')}"
        reference = write_file(root, local, (fixture / item["path"]).read_bytes())
        files.append({"source_path": str(origin / item["path"]), **reference})
    original = json.loads((root / IMPORT_WORKSPACE / "flow-ui-contract/contract.json").read_text())
    report = write_file(
        root, f"{IMPORT_WORKSPACE}/run-report.json", encode(_origin_report(scope, files, original))
    )
    files.append({"source_path": f"{scope['workspace']}/run-report.json", **report})
    package = {
        "kind": "penflow-brainstorm-authority-import",
        "version": 1,
        "origin_scope": scope,
        "workspace": IMPORT_WORKSPACE,
        "report": report,
        "files": files,
        **_identity_field(penflow_identity),
    }
    package_ref = write_file(root, IMPORT_PACKAGE_PATH, encode(package))
    imported = [package_ref, *({"path": row["path"], "sha256": row["sha256"]} for row in files)]
    return _inherited_inputs(root, original, package_ref, imported)


def _inherited_inputs(
    root: Path, original: Json, package_ref: Json, imported: list[Json]
) -> InheritedAuthority:
    feature = FeatureSource()
    source = _approved_source(root, feature, "spec.md")
    inherited = original["requirements"]["bindings"]
    native = bind(("FR-001", "AC-001"), [original["outcome_expectations"][0]["obligation_id"]])
    requirements = {
        "source_kind": SOURCE_KIND,
        # The projection lists native sources first, then the import package and its files
        # as absolute paths inside the importing project.
        "source_refs": [
            {"path": source["path"], "sha256": source["sha256"]},
            *({"path": str(root / row["path"]), "sha256": row["sha256"]} for row in imported),
        ],
        "bindings": [
            *inherited,
            *({"requirement_id": left, "obligation_id": right} for left, right in native),
        ],
    }
    snapshot = {
        "selection": [feature.slug],
        "retired_features": [],
        "inputs": {
            "sources": [source],
            "verification_policy": _policy_source(root, not_applicable_policy(), package_ref),
        },
        "projection": {
            "requirements": oracle_projection(
                (feature,), {**original, "requirements": requirements}
            )["requirements"]
        },
    }
    return InheritedAuthority(
        root,
        snapshot,
        {**original, "requirements": requirements},
        tuple(dict.fromkeys(row["requirement_id"] for row in inherited)),
    )


def not_applicable_policy() -> Json:
    """Return the reviewed policy declaring every optional design procedure not applicable."""
    return {"version": 1, **dict.fromkeys(DECISIONS, "not_applicable")}


def _origin_report(scope: Json, files: list[Json], contract: Json) -> Json:
    """Build the synthetic stored design report of the originating Brainstorm workspace."""
    sources = [{"path": row["source_path"], "sha256": row["sha256"]} for row in files]
    binding = contract["requirements"]["bindings"][0]
    expected = next(
        item
        for item in contract["outcome_expectations"]
        if item["obligation_id"] == binding["obligation_id"]
    )
    gate = {
        "id": "project-scope",
        "applicable": True,
        "required": True,
        "status": "PASS",
        "source_pointer": "/",
        "reason": "synthetic origin report of the import fixture",
        "evidence": [],
        "issues": [],
    }
    obligation = {
        "id": expected["obligation_id"],
        "category": expected["category"],
        "requirement_ids": [binding["requirement_id"]],
        "status": "PASS",
        "observation_refs": [],
        "issues": [],
        "expected": expected,
    }
    return {
        "kind": "penflow-verification-report",
        "version": 1,
        "profile": "design",
        "status": "PASS",
        "scope": scope,
        "policy_version": 1,
        "sources": sources,
        "gates": [gate],
        "obligations": {"required": 1, "verified": 1, "missing": 0, "items": [obligation]},
        "evidence": sources[:1],
        "build": None,
        "issues": [],
    }
