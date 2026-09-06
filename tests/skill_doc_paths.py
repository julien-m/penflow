# @spec(AC-007)
# @spec(AC-011)
# @spec(AC-012)
# @spec(AC-013)
# @spec(FR-001)
# @spec(FR-007)
# @spec(FR-008)
# @spec(FR-013)
# @spec(FR-014)
# @spec FR-008 AC-004 AC-005 AC-006: Feature 075 public project-boundary guidance.
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PENFLOW_SKILL = ROOT / ".agent-sync" / "skills" / "penflow" / "SKILL.md"
FLOW_SKILL = ROOT / ".agent-sync" / "skills" / "flow-ui-contract" / "SKILL.md"
FLOW_README = ROOT / ".agent-sync" / "skills" / "flow-ui-contract" / "README.md"
MOCKUP_SKILL = ROOT / ".agent-sync" / "skills" / "mockup-factory" / "SKILL.md"
MOCKUP_README = ROOT / ".agent-sync" / "skills" / "mockup-factory" / "README.md"
MOCKUP_WORKFLOW = ROOT / ".agent-sync" / "skills" / "mockup-factory" / "references" / "workflow.md"
MOCKUP_RUBRIC = (
    ROOT / ".agent-sync" / "skills" / "mockup-factory" / "references" / "audit-rubric.md"
)
MOCKUP_VISUAL = (
    ROOT / ".agent-sync" / "skills" / "mockup-factory" / "references" / "visual-validation.md"
)
MOCKUP_DESIGN_TASTE = (
    ROOT / ".agent-sync" / "skills" / "mockup-factory" / "references" / "design-taste-advisory.md"
)
FLOW_DESIGN_READ = (
    ROOT / ".agent-sync" / "skills" / "flow-ui-contract" / "references" / "design-read.md"
)
EXAMPLE_VISUAL_DIR = ROOT / "examples" / "full" / ".mockup-validation" / "visual-evidence"
SEMANTIC_TREE_REFERENCE = (
    ROOT / ".agent-sync" / "skills" / "flow-ui-contract" / "references" / "semantic-ui-tree.md"
)
README = ROOT / "README.md"
PROJECT_INTEGRATION = ROOT / "docs" / "project-integration.md"
THEME_CONTRACT = ROOT / "docs" / "theme-contract.md"
PENCIL_EXPORT_BATCH_ISSUE = ROOT / "docs" / "pencil-export-nodes-batch-issue.md"


REQUIRED_COMMANDS = (
    "export-semantic-tree",
    "validate-semantic-tree",
    "draft-pen-from-tree",
    "enrich-pen",
    "map-pencil-context",
    "validate-pen",
    "export-expected",
    "code-ir --from-context",
    "reverse-pen",
    "validate-actual actual-ui-tree.json --schema",
    "compare-tree expected-ui-tree.json actual-ui-tree.json",
    "review-report compare-report.json",
    "fix-report compare-report.json",
    "demo --out examples/full",
)

PENFLOW_DEMO_COMMANDS = (
    'demo --out "$fresh"',
    'run --target "$fresh" --json',
)
