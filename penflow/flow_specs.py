"""Validation for flow-ui-contract Markdown directories."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml

from .semantic import semantic_tree_from_specs
from .semantic_validation import validate_semantic_tree


FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
FLOW_REQUIRED_FIELDS = {"flow": str, "title": str, "status": str, "priority": str}
SCREEN_REQUIRED_FIELDS = {"screen": str, "mockup": str, "flow": str}
FLOW_REQUIRED_SECTIONS = [
    "## Input",
    "## User Scenarios & Testing",
    "## Acceptance Criteria",
    "## Functional Requirements",
]
SCREEN_REQUIRED_SECTIONS = [
    "## Données affichées",
    "## Actions",
    "## Validations",
    "## États UI",
    "## Erreurs",
    "## Side effects locaux",
]


@dataclass(slots=True)
class FlowSpecIssue:
    severity: str
    code: str
    path: str
    message: str
    file: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a scriptable issue object."""
        return {key: value for key, value in asdict(self).items() if value is not None}


def validate_flow_specs_dir(specs_dir: str | Path) -> dict[str, Any]:
    """Validate a flow-ui-contract directory without external runtime dependencies.

    Args:
        specs_dir: Directory containing `flows/*.md` and `screens/*.md`.

    Returns:
        Deterministic report with status, issue list, and artifact counts.
    """
    root = Path(specs_dir)
    issues: list[FlowSpecIssue] = []
    flow_files = _markdown_files(root / "flows", issues)
    screen_files = _markdown_files(root / "screens", issues)

    for path in flow_files:
        _validate_markdown_file(path, "flow", issues)
    for path in screen_files:
        _validate_markdown_file(path, "screen", issues)
    if not _has_errors(issues):
        _validate_semantic_export(root, issues)

    issue_dicts = [issue.to_dict() for issue in issues]
    return {
        "status": "PASS" if not _has_errors(issues) else "FAIL",
        "specs_dir": str(root),
        "flows": len(flow_files),
        "screens": len(screen_files),
        "issues": issue_dicts,
    }


def _markdown_files(directory: Path, issues: list[FlowSpecIssue]) -> list[Path]:
    if not directory.is_dir():
        issues.append(
            FlowSpecIssue(
                "error",
                "flow_specs.directory_missing",
                str(directory),
                f"required directory is missing: {directory.name}",
            )
        )
        return []
    files = sorted(directory.glob("*.md"))
    if not files:
        issues.append(
            FlowSpecIssue(
                "error",
                "flow_specs.files_missing",
                str(directory),
                f"no Markdown specs found in {directory.name}",
            )
        )
    return files


def _validate_markdown_file(path: Path, expected_kind: str, issues: list[FlowSpecIssue]) -> None:
    content = path.read_text(encoding="utf-8")
    frontmatter = _parse_frontmatter(path, content, issues)
    if frontmatter is None:
        return
    required = FLOW_REQUIRED_FIELDS if expected_kind == "flow" else SCREEN_REQUIRED_FIELDS
    sections = FLOW_REQUIRED_SECTIONS if expected_kind == "flow" else SCREEN_REQUIRED_SECTIONS
    for field, field_type in required.items():
        value = frontmatter.get(field)
        if not isinstance(value, field_type):
            issues.append(
                FlowSpecIssue(
                    "error",
                    "flow_specs.frontmatter_invalid",
                    f"$.{field}",
                    f"frontmatter field {field} must be {field_type.__name__}",
                    path.as_posix(),
                )
            )
    for section in sections:
        if section not in content:
            issues.append(
                FlowSpecIssue(
                    "error",
                    "flow_specs.section_missing",
                    section,
                    f"required section missing: {section}",
                    path.as_posix(),
                )
            )


def _parse_frontmatter(
    path: Path, content: str, issues: list[FlowSpecIssue]
) -> dict[str, Any] | None:
    match = FRONTMATTER_RE.match(content)
    if not match:
        issues.append(
            FlowSpecIssue(
                "error",
                "flow_specs.frontmatter_missing",
                "$",
                "file must start with YAML frontmatter",
                path.as_posix(),
            )
        )
        return None
    try:
        data = yaml.safe_load(match.group(1))
    except yaml.YAMLError as error:
        issues.append(
            FlowSpecIssue(
                "error",
                "flow_specs.frontmatter_parse_error",
                "$",
                str(error),
                path.as_posix(),
            )
        )
        return None
    if not isinstance(data, dict):
        issues.append(
            FlowSpecIssue(
                "error",
                "flow_specs.frontmatter_type",
                "$",
                "frontmatter must be a mapping",
                path.as_posix(),
            )
        )
        return None
    return data


def _validate_semantic_export(root: Path, issues: list[FlowSpecIssue]) -> None:
    try:
        tree = semantic_tree_from_specs(root)
    except (FileNotFoundError, KeyError, TypeError, ValueError) as error:
        issues.append(
            FlowSpecIssue(
                "error",
                "flow_specs.semantic_export_failed",
                str(root),
                str(error),
            )
        )
        return
    for issue in validate_semantic_tree(tree):
        issues.append(
            FlowSpecIssue(
                "error" if issue["severity"] == "error" else "warning",
                f"flow_specs.{issue['code']}",
                issue["path"],
                issue["message"],
                issue.get("semantic_id"),
            )
        )


def _has_errors(issues: list[FlowSpecIssue]) -> bool:
    return any(issue.severity == "error" for issue in issues)
