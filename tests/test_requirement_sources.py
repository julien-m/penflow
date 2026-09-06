"""Independent AST requirement identities and narrow lifecycle normalization."""

from pathlib import Path

import pytest

from penflow.requirement_markdown import (
    RequirementSourceError,
    extract_requirement_definitions,
    semantic_source_sha256,
)

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
