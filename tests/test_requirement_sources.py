"""Independent AST requirement identities and narrow lifecycle normalization."""

from dataclasses import replace
from pathlib import Path

import pytest

from penflow.requirement_approval_history import source_changes
from penflow.requirement_markdown import (
    RequirementSourceError,
    extract_requirement_definitions,
    semantic_source_sha256,
)
from penflow.requirement_projection import project_requirements
from penflow.requirement_sources import load_livespec_requirements
from penflow.verification_files import InputReader, VerificationInputError
from penflow.verification_json import canonical_bytes
from tests.c51_design_workspace import (
    BOUND,
    DELEGABLE,
    default_delegations,
    design_contract,
    obligation_ids,
    review_request,
)
from tests.c51_factory import persistence_expectation
from tests.c51_review_chain import (
    DEFAULT_SLUG,
    ChainOverrides,
    ReviewLink,
    ReviewRequest,
    bind,
    delegation,
    requirement_id,
    write_inherited_authority,
    write_review_link,
)

BRAINSTORM_FIXTURE = Path(__file__).parent / "fixtures" / "c51-brainstorm-source"

SPEC = """---
status: Approved
updated: 2026-09-05
visual: true
---
# Feature
## Header
- **Status:** Approved
## Functional Requirements
- **FR-001**: Persist a document. AC-001.
## Acceptance Criteria
| ID | Criterion |
|---|---|
| AC-001 | Saved content survives restart. |
## Examples
> FR-999: not a definition
```text
AC-999: not a definition
```
"""


def test_only_ast_definitions_enter_the_requirement_denominator(tmp_path: Path) -> None:
    source = tmp_path / "spec.md"
    source.write_text(SPEC)
    definitions = extract_requirement_definitions(source, "001-editor")
    assert [item.id for item in definitions] == [
        "livespec:001-editor:FR-001",
        "livespec:001-editor:AC-001",
    ]


@pytest.mark.parametrize("change", ["frontmatter", "header", "marker"])
def test_generated_lifecycle_update_preserves_semantic_identity(
    tmp_path: Path, change: str
) -> None:
    source = tmp_path / "spec.md"
    source.write_text(SPEC)
    original = semantic_source_sha256(source)
    modified = SPEC
    if change == "frontmatter":
        modified = modified.replace("status: Approved", "status: Implemented")
    elif change == "header":
        modified = modified.replace("**Status:** Approved", "**Status:** Implemented")
    else:
        modified += "\n<!-- finalize:spec-implement:2026-09-05:abcdef12 -->\n"
    source.write_text(modified)
    assert semantic_source_sha256(source) == original


@pytest.mark.parametrize(
    "before, after",
    [
        ("visual: true", "visual: false"),
        ("Persist a document", "Delete a document"),
        ("## Examples", "<!-- ordinary comment -->\n## Examples"),
    ],
)
def test_business_and_visual_changes_invalidate_approval(
    tmp_path: Path, before: str, after: str
) -> None:
    source = tmp_path / "spec.md"
    source.write_text(SPEC)
    original = semantic_source_sha256(source)
    source.write_text(SPEC.replace(before, after))
    assert semantic_source_sha256(source) != original


def test_extended_frontmatter_delimiters_have_identical_semantics(tmp_path: Path) -> None:
    source = tmp_path / "spec.md"
    source.write_text(SPEC)
    original = semantic_source_sha256(source)
    source.write_text(SPEC.replace("---\n", "----\n"))
    assert semantic_source_sha256(source) == original


@pytest.mark.parametrize(
    "definition", ["FR-002: Save", "**FR-002**: Save", "FR-BOGUS: Save", "### FR-002: Save"]
)
def test_unsupported_requirement_definitions_cannot_shrink_denominator(
    tmp_path: Path, definition: str
) -> None:
    source = tmp_path / "spec.md"
    source.write_text(
        SPEC.replace("## Acceptance Criteria", "\n" + definition + "\n\n## Acceptance Criteria")
    )
    with pytest.raises(RequirementSourceError, match="unsupported_requirement_definition"):
        extract_requirement_definitions(source, "001-editor")


def _history_pair(root: Path) -> tuple[ReviewLink, ReviewLink]:
    """Write a predecessor and a successor baseline that only moves one binding."""
    first = review_request()
    predecessor = write_review_link(root, first)
    successor = write_review_link(
        root, replace(first, bindings=first.bindings[:-1], previous=predecessor)
    )
    return predecessor, successor


def test_history_without_delegations_validates_unchanged(tmp_path: Path) -> None:
    predecessor, successor = _history_pair(tmp_path)
    removed = ":".join(review_request().bindings[-1])

    loaded = load_livespec_requirements(InputReader(tmp_path))

    assert canonical_bytes(loaded["projection"]) == canonical_bytes(successor.projection)
    assert set(loaded["projection"]) == set(predecessor.projection)
    assert [row["changed_binding_ids"] for row in successor.snapshot["changes"]] == [[removed]]
    assert successor.snapshot["changes"] == source_changes(
        predecessor.baseline,
        successor.baseline["sources"],
        successor.projection,
        successor.baseline["contract"]["sha256"],
    )


def test_inherited_authority_projects_without_delegations(tmp_path: Path) -> None:
    inherited = write_inherited_authority(tmp_path, BRAINSTORM_FIXTURE)

    projection = project_requirements(
        InputReader(inherited.root), inherited.snapshot, inherited.contract
    )

    assert set(projection) == {"source_kind", "sources", "requirements", "bindings", "uncovered"}
    assert projection["sources"] == inherited.contract["requirements"]["source_refs"]
    assert set(inherited.inherited_ids) < {row["id"] for row in projection["requirements"]}
    assert projection["uncovered"] == sorted(requirement_id(name) for name in ("FR-002", "AC-002"))


def _load_outcome(root: Path) -> dict | str:
    """Load the LiveSpec requirements of one project, or return the blocking code."""
    try:
        return load_livespec_requirements(InputReader(root))
    except VerificationInputError as error:
        return str(error)


def _source_ids(root: Path) -> list[str]:
    spec = root / ".specs/features" / DEFAULT_SLUG / "spec.md"
    return [item.id for item in extract_requirement_definitions(spec, DEFAULT_SLUG)]


# @spec AC-002: Bound and delegated cover the denominator — .specs/features/082-reviewed-requirement-delegation-to-upstream-acceptance/spec.md#ac-002
def test_bound_and_delegated_requirements_cover_denominator(tmp_path: Path) -> None:
    declared = default_delegations()
    link = write_review_link(tmp_path, review_request(delegations=declared))

    loaded = _load_outcome(tmp_path)

    assert isinstance(loaded, dict), loaded
    projection = loaded["projection"]
    assert [row["id"] for row in projection["requirements"]] == _source_ids(tmp_path)
    assert projection["delegated"] == sorted(declared, key=lambda row: row["requirement_id"])
    assert projection["delegated"] != declared
    assert projection["uncovered"] == []
    bound = {row["requirement_id"] for row in projection["bindings"]}
    delegated = {row["requirement_id"] for row in projection["delegated"]}
    assert (bound | delegated, bound & delegated) == (set(_source_ids(tmp_path)), set())
    records = {key: value for key, value in link.contract.items() if key != "requirements"}
    assert records == design_contract()


# One requirement is neither bound nor delegated; the others are bound, or bound and delegated.
UNCOVERED_CASES = {
    "without delegation": (BOUND + ("FR-002",), None),
    "beside a delegation": (BOUND, [delegation("FR-002", "Owned by the upstream acceptance.")]),
}


# @spec AC-004: Neither bound nor delegated stays uncovered — .specs/features/082-reviewed-requirement-delegation-to-upstream-acceptance/spec.md#ac-004
def test_unbound_undelegated_requirement_stays_uncovered(tmp_path: Path) -> None:
    observed = {}
    expected = {}
    for label, (bound, delegations) in UNCOVERED_CASES.items():
        root = tmp_path / label.replace(" ", "-")
        request = review_request(delegations=delegations)
        request = replace(request, bindings=bind(bound, obligation_ids(request.contract)))
        link = write_review_link(root, request)
        covered = {requirement_id(name) for name in bound} | {
            row["requirement_id"] for row in delegations or []
        }
        expected[label] = (sorted(set(_source_ids(root)) - covered), "requirements.uncovered")
        projection = project_requirements(InputReader(root), link.snapshot, link.contract)
        observed[label] = (projection["uncovered"], _load_outcome(root))
    assert observed == expected
    assert all(uncovered == [requirement_id("AC-002")] for uncovered, _ in expected.values())


PERSISTENCE_ID = persistence_expectation()["obligation_id"]


def _delegation_successors(variant: str) -> tuple[ReviewRequest, ReviewRequest]:
    """Return a predecessor binding the later-delegated requirements and its successor.

    ``persistence``: the bindings target the persistence expectation, which the
    successor contract no longer declares. ``plain``: they target a structure
    obligation that the successor still declares.
    """
    base = review_request()
    others = [value for value in obligation_ids(base.contract) if value != PERSISTENCE_ID]
    if variant == "persistence":
        target = [PERSISTENCE_ID]
        expectations = [
            row for row in base.contract["outcome_expectations"] if row["obligation_id"] in others
        ]
        successor_contract = {**base.contract, "outcome_expectations": expectations}
    else:
        target, successor_contract = others[:1], base.contract
    kept = bind(BOUND, others)
    predecessor = replace(base, bindings=kept + bind(DELEGABLE, target))
    successor = replace(
        base, contract=successor_contract, bindings=kept, delegations=default_delegations()
    )
    return predecessor, successor


def _without_bindings(removed: set[str]):
    """Return a delta edit that hides the removed bindings from the recorded changes."""

    def edit(changes: list[dict]) -> list[dict]:
        return [
            {
                **row,
                "changed_binding_ids": [
                    key for key in row["changed_binding_ids"] if key not in removed
                ],
            }
            for row in changes
        ]

    return edit


def _delegation_history(root: Path, variant: str) -> tuple[dict, dict]:
    """Replay the reviewed, the under-declared and the replayed successor of one variant."""
    first, second = _delegation_successors(variant)
    predecessor = write_review_link(root, first)
    second = replace(second, previous=predecessor)
    removed = {":".join(pair) for pair in set(first.bindings) - set(second.bindings)}
    reviewed = write_review_link(root, second)
    loaded = _load_outcome(root)
    recomputed = (
        source_changes(
            predecessor.baseline,
            reviewed.baseline["sources"],
            loaded["projection"],
            reviewed.baseline["contract"]["sha256"],
        )
        if isinstance(loaded, dict)
        else loaded
    )
    write_review_link(
        root, replace(second, overrides=ChainOverrides(changes=_without_bindings(removed)))
    )
    omitted = _load_outcome(root)
    write_review_link(root, replace(second, overrides=ChainOverrides(approval_from=predecessor)))
    observed = {"changes": recomputed, "omitted": omitted, "replayed": _load_outcome(root)}
    expected = {
        "changes": [
            {**row, "changed_binding_ids": sorted(removed)} for row in reviewed.snapshot["changes"]
        ],
        "omitted": "approval.delta.mismatch",
        "replayed": "approval.envelope.identity_mismatch",
    }
    return observed, expected


# @spec AC-008: Bound to delegated needs its own review — .specs/features/082-reviewed-requirement-delegation-to-upstream-acceptance/spec.md#ac-008
def test_bound_to_delegated_needs_reviewed_delta_and_own_approval(tmp_path: Path) -> None:
    observed = {}
    expected = {}
    for variant in ("persistence", "plain"):
        observed[variant], expected[variant] = _delegation_history(tmp_path / variant, variant)
    assert observed == expected
    assert all(
        len(row["changed_binding_ids"]) == len(DELEGABLE)
        for variant in expected.values()
        for row in variant["changes"]
    )
