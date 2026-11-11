"""Build a governed consumer project able to reach a C51 design verdict in tests.

The contract, the Pencil document and every evidence file are explicitly
synthetic test data. They are checked by the real Penflow validators; no
validator is replaced or mocked.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

from penflow.evidence import VISION_CATEGORIES
from penflow.pencil_persistence import verify_pencil_persistence
from tests.c51_factory import outcome_contract
from tests.c51_review_chain import (
    SPEC_TEXT,
    ChainOverrides,
    FeatureSource,
    Json,
    ReviewLink,
    ReviewRequest,
    bind,
    delegation,
    encode,
    not_applicable_policy,
    write_review_link,
)
from tests.strict_closure_fixtures import RUN_ID, _crop, _png, _proof, _sha
from tests.test_semantic_context_coverage import _contract, _pen

RETIRED_SLUG = "002-archive"
BOUND = ("FR-001", "AC-001")
DELEGABLE = ("FR-002", "AC-002")
SAVE_OPERATION = "save-current-pencil-document"
EVIDENCE_DIRECTORY = ".mockup-validation/visual-evidence"
# The 8x8 capture written by the shared PNG helper; any opaque colour is valid evidence bytes.
CAPTURE_COLOR = (32, 96, 160)

Govern = Callable[[Path, Path | None], Path]


@dataclass(frozen=True)
class DesignProject:
    """One governed consumer project with its workspace and reviewed baseline."""

    root: Path
    workspace: Path
    link: ReviewLink


def design_contract() -> Json:
    """Return the C20 records of the fixture, with every design procedure not applicable."""
    contract = outcome_contract(_contract())
    contract["verification_policy"] = not_applicable_policy()
    return contract


def obligation_ids(contract: Json) -> list[str]:
    """List the outcome expectation ids a requirement of the fixture can be bound to."""
    return [item["obligation_id"] for item in contract["outcome_expectations"]]


def default_delegations() -> list[Json]:
    """Delegate the two requirements of the fixture that carry no UI-contract obligation."""
    return [
        delegation("FR-002", "Audit trail retention has no UI-contract obligation."),
        delegation("AC-002", "Accepted by the upstream acceptance, not observable on screen."),
    ]


def review_request(
    *, delegations: object = None, overrides: ChainOverrides | None = None
) -> ReviewRequest:
    """Bind every requirement, or bind the UI duties and delegate the others when asked."""
    contract = design_contract()
    bound = BOUND if delegations is not None else BOUND + DELEGABLE
    return ReviewRequest(
        contract=contract,
        bindings=bind(bound, obligation_ids(contract)),
        delegations=delegations,
        overrides=overrides or ChainOverrides(),
    )


def invalid_delegation_request(
    delegations: object, *, bound: tuple[str, ...] = BOUND, spec: str = SPEC_TEXT
) -> ReviewRequest:
    """Declare an invalid delegations value inside an otherwise consistent chain.

    The stored projection omits the invalid declaration, as a closed review
    snapshot would reject a copy of it; only the replayed projection can refuse it.
    """
    contract = design_contract()
    return ReviewRequest(
        contract=contract,
        bindings=bind(bound, obligation_ids(contract)),
        delegations=delegations,
        features=(FeatureSource(spec=spec),),
        overrides=ChainOverrides(oracle_ignores_delegations=True),
    )


def unknown_delegation_request() -> ReviewRequest:
    """Delegate, beside the valid records, an id that no reviewed source defines."""
    return invalid_delegation_request(
        [*default_delegations(), delegation("AC-009", "No source defines it.")]
    )


def retired_feature_delegation_request(root: Path) -> ReviewRequest:
    """Add a second feature, retire it, then delegate one of its requirements.

    Writes the two predecessor baselines into ``root``; the returned request is
    the retiring baseline, whose contract names a requirement that left the
    active denominator.
    """
    features = (FeatureSource(), FeatureSource(slug=RETIRED_SLUG))
    first = review_request()
    selected = replace(first, features=features, feature=RETIRED_SLUG)
    added = write_review_link(root, replace(selected, previous=write_review_link(root, first)))
    retired = delegation("AC-001", "Declared for a feature that was retired.", RETIRED_SLUG)
    return replace(
        invalid_delegation_request([*default_delegations(), retired]),
        features=features,
        feature=RETIRED_SLUG,
        retired=(RETIRED_SLUG,),
        previous=added,
    )


def all_delegated_request() -> ReviewRequest:
    """Delegate every source requirement and declare no outcome expectation."""
    return ReviewRequest(
        contract={**design_contract(), "outcome_expectations": []},
        bindings=(),
        delegations=[
            delegation(local_id, "Declared without any UI-contract obligation.")
            for local_id in BOUND + DELEGABLE
        ],
    )


def uncertified(delegations: list[Json]) -> list[Json]:
    """Project reviewed delegation records to the report entries a consumer reads."""
    return sorted(
        (
            {
                "requirement_id": row["requirement_id"],
                "acceptance_owner": row["acceptance_owner"],
                "certified": False,
            }
            for row in delegations
        ),
        key=lambda row: row["requirement_id"],
    )


def build_design_project(
    root: Path, govern: Govern, request: ReviewRequest | None = None
) -> DesignProject:
    """Write the governed project, its native design evidence and its reviewed baseline."""
    root.mkdir(parents=True, exist_ok=True)
    root = root.resolve()
    workspace = root / "penflow"
    document = workspace / "ui.pen"
    document.parent.mkdir(parents=True, exist_ok=True)
    document.write_bytes(encode(_pen()))
    govern(root, document)
    _persistence_receipt(workspace, document)
    _visual_packet(workspace, json.loads(document.read_text(encoding="utf-8")))
    link = write_review_link(root, request or review_request())
    return DesignProject(root, workspace, link)


def _persistence_receipt(workspace: Path, document: Path) -> None:
    """Record distinct pre/post snapshots and let the real verifier close persistence."""
    pre = workspace / "pre.snapshot.json"
    post = workspace / "post.snapshot.json"
    pre.write_bytes(encode({"version": 1, "children": []}))
    post.write_bytes(document.read_bytes())
    observation = workspace / "pencil-observation.json"
    observation.write_bytes(
        encode(
            {
                "kind": "penflow-pencil-persistence-observation",
                "version": 1,
                "run_id": RUN_ID,
                "document": {
                    "path": document.name,
                    "pre": {"path": pre.name, "sha256": _sha(pre)},
                    "post": {"path": post.name, "sha256": _sha(post)},
                },
                "operation": SAVE_OPERATION,
                "trigger": {"provider": "pencil-operator", "status": "triggered"},
            }
        )
    )
    verify_pencil_persistence(
        observation,
        document=document,
        run_id=RUN_ID,
        operation=SAVE_OPERATION,
        out=workspace / ".penflow-run/pencil-persistence-receipt.json",
    )


def _visual_packet(workspace: Path, pen: Json) -> None:
    """Write a single-screen structured vision packet bound to one exported capture."""
    evidence = workspace / EVIDENCE_DIRECTORY
    evidence.mkdir(parents=True, exist_ok=True)
    root_node = pen["children"][0]
    export = evidence / f"{root_node['id']}.png"
    _png(export, CAPTURE_COLOR)
    screen = {
        "screen_id": root_node["context"]["semantic_id"],
        "semantic_id": root_node["context"]["semantic_id"],
        "pencil_node_id": root_node["id"],
        "surface": "web",
        "state": "default",
        "png": export.name,
    }
    manifest = {
        "renderer": "pencil-mcp",
        "sourceFile": "ui.pen",
        "status": "PASS",
        "validatedAt": "2026-07-24",
        "runId": RUN_ID,
        "screens": [
            {
                **screen,
                "regions": [{"region_id": "checkout.main", "crop": _crop()}],
                "sha256": _sha(export),
                "layout_checked": True,
                "screenshot_checked": True,
            }
        ],
    }
    criteria = [
        _proof(category, role="actual", file=export.name, digest=_sha(export))
        for category in VISION_CATEGORIES
    ]
    report = {
        "version": 1,
        "kind": "penflow-vision-report",
        "status": "PASS",
        "runId": RUN_ID,
        "renderer": "pencil-mcp",
        "sourceFile": "ui.pen",
        "model": "test-vision-model",
        "generated_by": "pytest-c51-design-workspace",
        "inputs": [{"file": export.name, "sha256": _sha(export)}],
        "screens": [{**screen, "region_id": "checkout.main", "criteria": criteria}],
    }
    (evidence / "manifest.json").write_bytes(encode(manifest))
    (evidence / "vision-report.json").write_bytes(encode(report))
