#!/usr/bin/env python3
# @spec(FR-002)
# @spec FR-012, FR-013, FR-014, FR-015, FR-016, FR-017, FR-018, FR-019, FR-020, FR-021:
#   Validator CLI — structural, ID, mapping, story, Gherkin, Mermaid, mockup, clarification checks
#   — .specs/features/027-define-flow-screen-spec-grammar/spec.md#fr-002
"""flow-ui-contract validator — enforces the grammar contract defined in references/grammar.md.

Usage:
    python3 validator.py <path-to-spec.md>
    python3 validator.py --dir <specs-directory>
    python3 validator.py <path> --manifest <path-to-manifest.json>

Exit codes:
    0 = PASS (no BLOCKING errors)
    1 = FAIL (at least one BLOCKING error)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML is required. Install with: pip install pyyaml", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

SEVERITY_BLOCKING = "BLOCKING"
SEVERITY_WARNING = "WARNING"
SEVERITY_INFO = "INFO"


@dataclass
class Finding:
    severity: str  # BLOCKING | WARNING | INFO
    message: str
    line: Optional[int] = None


# ---------------------------------------------------------------------------
# File type detection
# ---------------------------------------------------------------------------


def detect_file_type(content: str, frontmatter: dict) -> str:
    """Returns 'flow' or 'screen' based on frontmatter keys."""
    if "flow" in frontmatter and "mockups" in frontmatter:
        return "flow"
    if "screen" in frontmatter and "mockup" in frontmatter:
        return "screen"
    # Heuristic fallback
    if content.lstrip().startswith("# Flow Spec:") or content.lstrip().startswith("# Flow Spec:"):
        return "flow"
    if "# Écran —" in content or "# Screen —" in content:
        return "screen"
    return "flow"  # default


# ---------------------------------------------------------------------------
# Frontmatter parsing
# ---------------------------------------------------------------------------

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def parse_frontmatter(content: str) -> tuple[Optional[dict], Optional[str]]:
    """Returns (parsed_dict, error_message). error_message is None on success."""
    match = FRONTMATTER_RE.match(content)
    if not match:
        return None, "No YAML frontmatter found (file must start with ---)"
    try:
        data = yaml.safe_load(match.group(1))
        if not isinstance(data, dict):
            return None, "Frontmatter is not a YAML mapping"
        return data, None
    except yaml.YAMLError as e:
        return None, f"YAML parse error: {e}"


# ---------------------------------------------------------------------------
# Structural checks
# ---------------------------------------------------------------------------

FLOW_REQUIRED_FIELDS: dict[str, type] = {
    "flow": str,
    "title": str,
    "status": str,
    "priority": str,
    "mockups": list,
    "surfaces": list,
    "source": list,
    "generated_at": str,
}

SCREEN_REQUIRED_FIELDS: dict[str, type] = {
    "screen": str,
    "mockup": str,
    "flow": str,
    "generated_at": str,
}

VALID_STATUSES = {"draft", "reviewed", "promoted"}
VALID_PRIORITIES = {"P1", "P2", "P3"}
VALID_SURFACES = {"mobile", "web", "landing", "showcase", "admin"}

FLOW_REQUIRED_SECTIONS = [
    "## Input",
    "## User Scenarios & Testing",
    "## Acceptance Criteria",
    "## Functional Requirements",
    "## Key Entities",
    "## Edge Cases",
    "## Success Criteria",
]

SCREEN_REQUIRED_SECTIONS = [
    "## Données affichées",
    "## Actions",
    "## Validations",
    "## États UI",
    "## Erreurs",
    "## Side effects locaux",
]


def check_structural(fm: dict, content: str, file_type: str) -> list[Finding]:
    findings: list[Finding] = []

    if file_type == "flow":
        required = FLOW_REQUIRED_FIELDS
    else:
        required = SCREEN_REQUIRED_FIELDS

    for field, expected_type in required.items():
        if field not in fm:
            findings.append(
                Finding(SEVERITY_BLOCKING, f"Missing required frontmatter field: '{field}'")
            )
        elif not isinstance(fm[field], expected_type) and fm[field] is not None:
            findings.append(
                Finding(
                    SEVERITY_BLOCKING,
                    f"Frontmatter field '{field}' must be {expected_type.__name__}, got {type(fm[field]).__name__}",
                )
            )

    if file_type == "flow":
        if "status" in fm and fm["status"] not in VALID_STATUSES:
            findings.append(
                Finding(
                    SEVERITY_BLOCKING,
                    f"frontmatter 'status' must be one of {sorted(VALID_STATUSES)}, got '{fm['status']}'",
                )
            )
        if "priority" in fm and fm["priority"] not in VALID_PRIORITIES:
            findings.append(
                Finding(
                    SEVERITY_BLOCKING,
                    f"frontmatter 'priority' must be one of {sorted(VALID_PRIORITIES)}, got '{fm['priority']}'",
                )
            )
        if "surfaces" in fm and isinstance(fm["surfaces"], list):
            for s in fm["surfaces"]:
                if s not in VALID_SURFACES:
                    findings.append(
                        Finding(
                            SEVERITY_BLOCKING,
                            f"frontmatter 'surfaces' contains invalid value '{s}'; must be one of {sorted(VALID_SURFACES)}",
                        )
                    )
        if "mockups" in fm and isinstance(fm["mockups"], list) and len(fm["mockups"]) == 0:
            findings.append(
                Finding(
                    SEVERITY_WARNING,
                    "frontmatter 'mockups' is empty — no mockups mapped to this flow",
                )
            )

    # Section order check
    required_sections = FLOW_REQUIRED_SECTIONS if file_type == "flow" else SCREEN_REQUIRED_SECTIONS
    last_pos = -1
    for section in required_sections:
        pos = content.find(section)
        if pos == -1:
            findings.append(Finding(SEVERITY_BLOCKING, f"Required section missing: '{section}'"))
        elif pos < last_pos:
            findings.append(
                Finding(
                    SEVERITY_BLOCKING,
                    f"Section '{section}' appears out of order (expected after previous section)",
                )
            )
        else:
            last_pos = pos

    # H1 check
    if file_type == "flow":
        if not re.search(r"^# Flow Spec:", content, re.MULTILINE):
            findings.append(
                Finding(SEVERITY_BLOCKING, "H1 must start with '# Flow Spec:' for flow files")
            )
    else:
        if not re.search(r"^# [EÉ]cran —|^# Screen —", content, re.MULTILINE):
            findings.append(
                Finding(
                    SEVERITY_BLOCKING,
                    "H1 must start with '# Écran —' or '# Screen —' for screen files",
                )
            )

    return findings


# ---------------------------------------------------------------------------
# ID checks
# ---------------------------------------------------------------------------

FLOW_ID_RE = re.compile(r"FLOW-[A-Z][A-Z0-9-]*")
SCREEN_ID_RE = re.compile(r"SCREEN-[A-Z][A-Z0-9-]*")
FLOW_ID_STRICT_RE = re.compile(r"^FLOW-[A-Z][A-Z0-9-]*$")
SCREEN_ID_STRICT_RE = re.compile(r"^SCREEN-[A-Z][A-Z0-9-]*$")
AC_ID_RE = re.compile(r"\*\*AC-(\d{3})\*\*")
FR_ID_RE = re.compile(r"\*\*FR-(\d{3})\*\*")
SC_ID_RE = re.compile(r"\*\*SC-(\d{3})\*\*")


def _check_sequential_ids(matches: list[str], prefix: str) -> list[Finding]:
    """Verify IDs are sequential starting at 001 with no gaps."""
    findings = []
    nums = sorted(set(int(n) for n in matches))
    if not nums:
        return findings
    if nums[0] != 1:
        findings.append(
            Finding(
                SEVERITY_BLOCKING,
                f"{prefix} IDs must start at 001, found first ID: {prefix}-{nums[0]:03d}",
            )
        )
    for i, n in enumerate(nums):
        expected = i + 1
        if n != expected:
            findings.append(
                Finding(
                    SEVERITY_BLOCKING,
                    f"{prefix} IDs have a gap: expected {prefix}-{expected:03d}, found {prefix}-{n:03d}",
                )
            )
            break
    return findings


def check_ids(content: str, fm: dict, file_type: str) -> list[Finding]:
    _ = fm  # reserved for future per-file-type ID checks
    findings: list[Finding] = []

    if file_type == "flow":
        # Flow ID in header bullets
        flow_id_match = re.search(r"\*\*Flow ID:\*\*\s*(FLOW-[A-Z0-9-]+)", content)
        if flow_id_match:
            fid = flow_id_match.group(1)
            if not FLOW_ID_STRICT_RE.match(fid):
                findings.append(
                    Finding(
                        SEVERITY_BLOCKING,
                        f"Flow ID '{fid}' does not match pattern ^FLOW-[A-Z][A-Z0-9-]*$",
                    )
                )
        else:
            findings.append(
                Finding(
                    SEVERITY_BLOCKING,
                    "Flow ID not found in header bullets (expected '**Flow ID:** FLOW-...')",
                )
            )

        # AC, FR, SC sequentiality
        ac_nums = AC_ID_RE.findall(content)
        fr_nums = FR_ID_RE.findall(content)
        sc_nums = SC_ID_RE.findall(content)
        findings.extend(_check_sequential_ids(ac_nums, "AC"))
        findings.extend(_check_sequential_ids(fr_nums, "FR"))
        findings.extend(_check_sequential_ids(sc_nums, "SC"))

    return findings


# ---------------------------------------------------------------------------
# AC↔FR mapping checks
# ---------------------------------------------------------------------------

AC_IN_FR_RE = re.compile(r"AC-(\d{3})")


def check_ac_fr_mapping(content: str) -> list[Finding]:
    findings: list[Finding] = []

    # Extract defined ACs
    defined_acs = set(int(n) for n in AC_ID_RE.findall(content))

    # Extract FR section content
    fr_section_match = re.search(
        r"## Functional Requirements\n(.*?)(?=\n## |\Z)", content, re.DOTALL
    )
    if not fr_section_match:
        return findings  # Already caught by structural check

    fr_section = fr_section_match.group(1)

    # Find all AC references inside FR section
    ac_refs_in_frs = set(int(n) for n in AC_IN_FR_RE.findall(fr_section))

    # Each AC must be cited by at least one FR
    uncited_acs = defined_acs - ac_refs_in_frs
    for ac_num in sorted(uncited_acs):
        findings.append(
            Finding(
                SEVERITY_BLOCKING,
                f"AC-{ac_num:03d} is not cited by any FR in '## Functional Requirements'",
            )
        )

    # No FR may cite a non-existent AC
    for ac_num in sorted(ac_refs_in_frs):
        if ac_num not in defined_acs:
            findings.append(
                Finding(
                    SEVERITY_BLOCKING,
                    f"FR cites AC-{ac_num:03d} which does not exist in '## Acceptance Criteria'",
                )
            )

    return findings


# ---------------------------------------------------------------------------
# Story checks
# ---------------------------------------------------------------------------

STORY_HEADING_RE = re.compile(r"^### (P[123]) — (.+)$", re.MULTILINE)
NARRATIVE_RE = re.compile(r"\*\*As a\*\*.*?\*\*I want\*\*.*?\*\*So that\*\*", re.DOTALL)
PRIORITY_REASON_RE = re.compile(r"\*\*Priority reason:\*\*")
INDEPENDENT_TEST_RE = re.compile(r"\*\*Independent test:\*\*")


def check_stories(content: str) -> list[Finding]:
    findings: list[Finding] = []

    stories_section_match = re.search(
        r"## User Scenarios & Testing\n(.*?)(?=\n## |\Z)", content, re.DOTALL
    )
    if not stories_section_match:
        return findings  # Already caught by structural check

    stories_content = stories_section_match.group(1)
    story_headings = STORY_HEADING_RE.findall(stories_content)

    if not story_headings:
        findings.append(
            Finding(
                SEVERITY_BLOCKING,
                "No story headings found in '## User Scenarios & Testing' (expected '### P1 — <title>')",
            )
        )
        return findings

    has_p1 = any(priority == "P1" for priority, _ in story_headings)
    if not has_p1:
        findings.append(
            Finding(
                SEVERITY_BLOCKING,
                "At least one '### P1 — <title>' story is required in '## User Scenarios & Testing'",
            )
        )

    # Split stories content by story heading boundaries
    story_splits = list(STORY_HEADING_RE.finditer(stories_content))
    for i, match in enumerate(story_splits):
        priority, title = match.group(1), match.group(2)
        start = match.start()
        end = story_splits[i + 1].start() if i + 1 < len(story_splits) else len(stories_content)
        story_block = stories_content[start:end]

        if not NARRATIVE_RE.search(story_block):
            findings.append(
                Finding(
                    SEVERITY_BLOCKING,
                    f"Story '### {priority} — {title}': missing 'As a / I want / So that' narrative bullets",
                )
            )
        if not PRIORITY_REASON_RE.search(story_block):
            findings.append(
                Finding(
                    SEVERITY_BLOCKING,
                    f"Story '### {priority} — {title}': missing '**Priority reason:**' field",
                )
            )
        if not INDEPENDENT_TEST_RE.search(story_block):
            findings.append(
                Finding(
                    SEVERITY_BLOCKING,
                    f"Story '### {priority} — {title}': missing '**Independent test:**' field",
                )
            )

    return findings


# ---------------------------------------------------------------------------
# Gherkin checks
# ---------------------------------------------------------------------------

GHERKIN_FENCE_RE = re.compile(r"```gherkin\n(.*?)```", re.DOTALL)
PSEUDO_GHERKIN_RE = re.compile(r"^[ \t]*[-*] +(Given|When|Then|And|But) +", re.MULTILINE)


def check_gherkin(content: str, file_type: str) -> list[Finding]:
    findings: list[Finding] = []
    if file_type != "flow":
        return findings

    stories_section_match = re.search(
        r"## User Scenarios & Testing\n(.*?)(?=\n## |\Z)", content, re.DOTALL
    )
    if not stories_section_match:
        return findings

    stories_content = stories_section_match.group(1)

    gherkin_blocks = GHERKIN_FENCE_RE.findall(stories_content)
    if not gherkin_blocks:
        findings.append(
            Finding(
                SEVERITY_BLOCKING,
                "No fenced ```gherkin block found in '## User Scenarios & Testing'",
            )
        )
        return findings

    for block in gherkin_blocks:
        if "Feature:" not in block:
            findings.append(Finding(SEVERITY_BLOCKING, "Gherkin block missing 'Feature:' keyword"))
        if "Scenario:" not in block:
            findings.append(Finding(SEVERITY_BLOCKING, "Gherkin block missing 'Scenario:' keyword"))

    # Detect pseudo-Gherkin bullets outside of fenced blocks
    # Remove fenced blocks first
    content_no_fences = GHERKIN_FENCE_RE.sub("", content)
    if PSEUDO_GHERKIN_RE.search(content_no_fences):
        findings.append(
            Finding(
                SEVERITY_BLOCKING,
                "Pseudo-Gherkin detected: Gherkin keywords (Given/When/Then/And/But) "
                "used as markdown bullets outside a fenced ```gherkin block",
            )
        )

    return findings


# ---------------------------------------------------------------------------
# Mermaid checks
# ---------------------------------------------------------------------------

MERMAID_FENCE_RE = re.compile(r"```mermaid\n(.*?)```", re.DOTALL)
FLOWCHART_RE = re.compile(r"flowchart\s+(TD|LR|BT|RL)")


def check_mermaid(content: str, file_type: str) -> list[Finding]:
    findings: list[Finding] = []
    if file_type != "flow":
        return findings

    stories_section_match = re.search(
        r"## User Scenarios & Testing\n(.*?)(?=\n## |\Z)", content, re.DOTALL
    )
    if not stories_section_match:
        return findings

    stories_content = stories_section_match.group(1)
    mermaid_blocks = MERMAID_FENCE_RE.findall(stories_content)

    if not mermaid_blocks:
        findings.append(
            Finding(
                SEVERITY_BLOCKING,
                "No fenced ```mermaid block found in '## User Scenarios & Testing'",
            )
        )
        return findings

    for block in mermaid_blocks:
        if not FLOWCHART_RE.search(block):
            findings.append(
                Finding(
                    SEVERITY_BLOCKING,
                    "Mermaid block in flow spec must contain 'flowchart TD' or 'flowchart LR'",
                )
            )

    return findings


# ---------------------------------------------------------------------------
# Mockup existence check (optional — requires manifest)
# ---------------------------------------------------------------------------


def check_mockups(fm: dict, manifest_path: Optional[Path]) -> list[Finding]:
    findings: list[Finding] = []
    if not manifest_path or not manifest_path.exists():
        return findings

    try:
        manifest = json.loads(manifest_path.read_text())
    except (json.JSONDecodeError, OSError):
        findings.append(
            Finding(
                SEVERITY_INFO,
                f"Could not read manifest at {manifest_path} — mockup existence check skipped",
            )
        )
        return findings

    exports = manifest.get("exports", [])
    existing_stems = {Path(e["filename"]).stem for e in exports if "filename" in e}

    declared_mockups = fm.get("mockups", [])
    if isinstance(declared_mockups, list):
        for mockup in declared_mockups:
            stem = Path(str(mockup)).stem if "." in str(mockup) else str(mockup)
            if stem not in existing_stems:
                findings.append(
                    Finding(
                        SEVERITY_BLOCKING,
                        f"Mockup '{mockup}' declared in frontmatter not found in manifest.json exports",
                    )
                )

    return findings


# ---------------------------------------------------------------------------
# NEEDS CLARIFICATION count
# ---------------------------------------------------------------------------

CLARIFICATION_RE = re.compile(r"\[NEEDS CLARIFICATION\]")


def check_needs_clarification(content: str, file_type: str, fm: dict) -> list[Finding]:
    findings: list[Finding] = []
    count = len(CLARIFICATION_RE.findall(content))
    if count > 0:
        findings.append(Finding(SEVERITY_INFO, f"Found {count} [NEEDS CLARIFICATION] marker(s)"))
    if file_type == "flow" and count > 3:
        findings.append(
            Finding(
                SEVERITY_WARNING,
                f"Flow has {count} [NEEDS CLARIFICATION] markers (> 3) — "
                "blocks promotion to 'reviewed'/'promoted' status",
            )
        )
        if fm.get("status") in {"reviewed", "promoted"}:
            findings.append(
                Finding(
                    SEVERITY_BLOCKING,
                    "Flow with more than 3 [NEEDS CLARIFICATION] markers blocks reviewed/promoted status",
                )
            )
    return findings


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------


def format_report(file_path: str, findings: list[Finding]) -> str:
    blocking = [f for f in findings if f.severity == SEVERITY_BLOCKING]
    warnings = [f for f in findings if f.severity == SEVERITY_WARNING]
    infos = [f for f in findings if f.severity == SEVERITY_INFO]

    result = "PASS" if not blocking else "FAIL"
    lines = [
        f"VALIDATION_RESULT: {result}",
        f"FILE: {file_path}",
    ]

    errors = blocking + warnings
    if errors:
        lines.append("ERRORS:")
        for f in errors:
            loc = f" (line {f.line})" if f.line else ""
            lines.append(f"  - [{f.severity}] {f.message}{loc}")
    else:
        lines.append("ERRORS: none")

    if infos:
        lines.append("INFO:")
        for f in infos:
            lines.append(f"  - {f.message}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Full validation pipeline
# ---------------------------------------------------------------------------


def validate_file(
    file_path: Path,
    manifest_path: Optional[Path] = None,
) -> tuple[bool, str]:
    """Returns (passed: bool, report: str)."""
    content = file_path.read_text(encoding="utf-8")
    findings: list[Finding] = []

    fm, parse_error = parse_frontmatter(content)
    if parse_error or fm is None:
        findings.append(Finding(SEVERITY_BLOCKING, parse_error or "missing frontmatter"))
        report = format_report(str(file_path), findings)
        return False, report

    file_type = detect_file_type(content, fm)

    findings.extend(check_structural(fm, content, file_type))
    findings.extend(check_ids(content, fm, file_type))

    if file_type == "flow":
        findings.extend(check_ac_fr_mapping(content))
        findings.extend(check_stories(content))
        findings.extend(check_gherkin(content, file_type))
        findings.extend(check_mermaid(content, file_type))
        findings.extend(check_mockups(fm, manifest_path))

    findings.extend(check_needs_clarification(content, file_type, fm))

    passed = not any(f.severity == SEVERITY_BLOCKING for f in findings)
    report = format_report(str(file_path), findings)
    return passed, report


# ---------------------------------------------------------------------------
# Manifest status mode
# ---------------------------------------------------------------------------


def _parse_timestamp(value: object) -> datetime | None:
    """Parse an ISO-8601 timestamp for deterministic stale/fresh comparison."""
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _status_for_export(export: dict) -> str:
    if not export.get("specStatus") or not export.get("specGeneratedAt"):
        return "unspecified"
    source_generated_at = _parse_timestamp(export.get("sourceGeneratedAt"))
    spec_generated_at = _parse_timestamp(export.get("specGeneratedAt"))
    if source_generated_at and spec_generated_at and source_generated_at > spec_generated_at:
        return "stale"
    return "fresh"


def format_status_report(target: Path) -> tuple[bool, str]:
    """Return the manifest status report for a Penflow flow-ui-contract target."""
    manifest_path = target / "mockups" / "manifest.json"
    if not manifest_path.exists():
        return False, f"STATUS_RESULT: FAIL\nTARGET: {target}\nERROR: manifest.json not found"

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        return (
            False,
            f"STATUS_RESULT: FAIL\nTARGET: {target}\nERROR: invalid manifest.json: {error}",
        )

    exports = manifest.get("exports")
    if not isinstance(exports, list):
        return (
            False,
            f"STATUS_RESULT: FAIL\nTARGET: {target}\nERROR: manifest exports must be a list",
        )

    counts = {"fresh": 0, "stale": 0, "unspecified": 0}
    lines = [
        "STATUS_RESULT: PASS",
        f"TARGET: {target}",
        "SCREENS:",
    ]
    for export in exports:
        if not isinstance(export, dict):
            continue
        filename = str(export.get("filename") or "unknown")
        screen = Path(filename).stem
        status = _status_for_export(export)
        counts[status] += 1
        flow = export.get("specFlow") or "-"
        spec_screen = export.get("specScreen") or "-"
        lines.append(f"  - {screen} | {status} | flow={flow} | spec={spec_screen}")

    lines.extend(
        [
            "SUMMARY:",
            f"  fresh: {counts['fresh']}",
            f"  stale: {counts['stale']}",
            f"  unspecified: {counts['unspecified']}",
        ]
    )
    return True, "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="flow-ui-contract validator — enforce grammar contract on flow/screen specs"
    )
    parser.add_argument("path", nargs="?", help="Path to a single spec file")
    parser.add_argument(
        "--dir", metavar="DIR", help="Directory to validate (batch mode, all *.md files)"
    )
    parser.add_argument(
        "--manifest", metavar="MANIFEST", help="Path to manifest.json for mockup existence check"
    )
    parser.add_argument(
        "--status", action="store_true", help="Report fresh/stale/unspecified status"
    )
    parser.add_argument(
        "--target", metavar="DIR", default=".", help="Target directory for --status"
    )
    args = parser.parse_args()

    if args.status:
        passed, report = format_status_report(Path(args.target))
        print(report)
        sys.exit(0 if passed else 1)

    if not args.path and not args.dir:
        parser.print_help()
        sys.exit(1)

    manifest_path = Path(args.manifest) if args.manifest else None

    if args.dir:
        dir_path = Path(args.dir)
        if not dir_path.is_dir():
            print(f"ERROR: '{args.dir}' is not a directory", file=sys.stderr)
            sys.exit(1)
        files = sorted(dir_path.rglob("*.md"))
        if not files:
            print(f"No .md files found in '{args.dir}'", file=sys.stderr)
            sys.exit(0)

        all_passed = True
        for f in files:
            auto_manifest = manifest_path
            if auto_manifest is None:
                candidate = f.parent.parent.parent / "mockups" / "manifest.json"
                if candidate.exists():
                    auto_manifest = candidate
            passed, report = validate_file(f, auto_manifest)
            print(report)
            print()
            if not passed:
                all_passed = False
        sys.exit(0 if all_passed else 1)

    else:
        file_path = Path(args.path)
        if not file_path.exists():
            print(f"ERROR: file not found: '{args.path}'", file=sys.stderr)
            sys.exit(1)

        auto_manifest = manifest_path
        if auto_manifest is None:
            candidate = file_path.parent.parent.parent / "mockups" / "manifest.json"
            if candidate.exists():
                auto_manifest = candidate

        passed, report = validate_file(file_path, auto_manifest)
        print(report)
        sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
