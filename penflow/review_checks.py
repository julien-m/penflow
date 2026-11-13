"""Compose current local diagnostics without a delivery certification dependency."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

from .compare import STRICT_THRESHOLD, compare_trees
from .consistency import check_consistency
from .flow_contract import validate_flow_contract_v2
from .pen import bbox_issues, parse_pen, validate_pen_context_against_contract
from .pen_lifecycle import CanvasLifecycleError
from .theme import theme_from_css
from .token_lint import lint_tokens
from .tree import expected_tree_from_pen, normalize_actual_tree, validate_actual_tree
from .verification_files import InputReader
from .visual_metrics import audit_visual

# Existing validators return heterogeneous JSON dictionaries. Keep their payloads
# intact at this composition boundary rather than translating away findings.
JsonObject = dict[str, Any]
CheckStatus = Literal["PASS", "FAIL", "ERROR", "NOT_RUN"]
_INPUT_ERRORS = (OSError, UnicodeError, ValueError, TypeError, KeyError, AttributeError)
# Per input, including the final recheck; a refusal remains a review finding.
MAX_INPUT_BYTES = 64 * 1024 * 1024


@dataclass(frozen=True)
class CheckResult:
    """One executed diagnostic or an explicit missing prerequisite.

    Attributes:
        name: Stable diagnostic identifier.
        status: Execution outcome, never delivery approval.
        exit_code: Actual diagnostic code; None means not executed.
        issues: Existing validator findings or input/dependency findings.
        details: Diagnostic data, excluding source document contents.
    """

    name: str
    status: CheckStatus
    exit_code: int | None
    issues: list[JsonObject] = field(default_factory=list)
    details: JsonObject = field(default_factory=dict)


class _Checks:
    def __init__(self, reader: InputReader) -> None:
        self.reader = reader
        self.results: list[CheckResult] = []

    def missing(self, name: str, message: str) -> None:
        self.results.append(
            CheckResult(
                name, "NOT_RUN", None, [{"code": "check.input.missing", "message": message}]
            )
        )

    def error(self, name: str, error: BaseException) -> None:
        issues = (
            [finding.to_dict() for finding in error.findings]
            if isinstance(error, CanvasLifecycleError)
            else [{"severity": "error", "code": "check.input.invalid", "message": str(error)}]
        )
        self.results.append(CheckResult(name, "ERROR", 2, issues))

    def object(self, name: str, path: Path) -> JsonObject | None:
        try:
            if not self.reader.lexists(path):
                self.missing(name, f"input not supplied: {path}")
                return None
            return self.reader.object(self.reader.read(path))
        except _INPUT_ERRORS as error:
            self.error(name, error)
            return None

    def run(self, name: str, action: Callable[[], JsonObject]) -> JsonObject | None:
        try:
            report = action()
            issues = report.get("issues", []) + report.get("violations", [])
            code = int(
                report.get("status") in {"FAIL", "FAILED", "BLOCKED"}
                or any(issue.get("severity") in {"error", "warning"} for issue in issues)
            )
            self.results.append(
                CheckResult(
                    name,
                    "FAIL" if code else "PASS",
                    code,
                    issues,
                    {key: value for key, value in report.items() if key != "issues"},
                )
            )
            return report
        except (*_INPUT_ERRORS, CanvasLifecycleError) as error:
            self.error(name, error)
            return None


def check_workspace(
    target: str | Path,
    *,
    project_root: str | Path | None = None,
    theme_css: str | Path | None = None,
) -> JsonObject:
    """Check available current inputs, with no file writes or external execution.

    Args:
        target: Workspace containing ui.pen and optional contract/actual files.
            Relative paths resolve from project_root when supplied, else CWD.
        project_root: Exact input containment boundary, defaulting to workspace.
        theme_css: Optional CSS path relative to workspace; otherwise theme.css
            is used when present. Explicit missing CSS is an error.

    Returns:
        A deterministic report with actual per-check results, aggregate exit,
        and explicit limits. A zero exit never certifies runtime or delivery.

    Raises:
        ValueError: If the workspace is missing or outside the selected project.
        OSError: If the input containment boundary cannot be resolved.
    """
    root = Path(project_root).resolve(strict=True) if project_root is not None else None
    workspace = Path(target)
    if not workspace.is_absolute() and root is not None:
        workspace = root / workspace
    workspace = workspace.resolve(strict=True)
    if not workspace.is_dir():
        raise ValueError(f"target is not a workspace directory: {workspace}")
    reader = InputReader(root or workspace, read_limit=MAX_INPUT_BYTES)
    reader.path(workspace)
    checks = _Checks(reader)
    contract = checks.object("validate-flow-contract", workspace / "flow-ui-contract/contract.json")
    contract_report = (
        checks.run(
            "validate-flow-contract", lambda: {"issues": validate_flow_contract_v2(contract)}
        )
        if contract is not None
        else None
    )
    pen = checks.object("validate-pen", workspace / "ui.pen")
    theme = _read_theme(checks, workspace, theme_css)
    expected = _check_design(checks, workspace, pen, theme)
    if pen is not None and contract is not None and contract_report is not None:
        if any(issue.get("severity") == "error" for issue in contract_report["issues"]):
            checks.missing(
                "contract-context", "contract is invalid; canvas checks remain independent"
            )
        else:
            checks.run(
                "contract-context",
                lambda: {
                    "issues": [
                        asdict(issue)
                        for issue in validate_pen_context_against_contract(parse_pen(pen), contract)
                    ]
                },
            )
    actual = checks.object("validate-actual", workspace / "actual-ui-tree.json")
    if actual is not None:
        checks.run("validate-actual", lambda: {"issues": validate_actual_tree(actual, schema=True)})
    if expected is not None and actual is not None:
        checks.run(
            "compare-tree",
            lambda: compare_trees(
                expected, normalize_actual_tree(actual), threshold=STRICT_THRESHOLD, mandatory=True
            ),
        )
    else:
        checks.missing(
            "compare-tree", "a usable canvas and actual tree are required for comparison"
        )
    # A per-run recheck detects concurrent edits without requiring any archived
    # approval, hash manifest, model declaration or persistent input cache.
    try:
        reader.recheck()
    except _INPUT_ERRORS as error:
        checks.error("input-stability", error)
    exit_code = int(any(result.exit_code for result in checks.results))
    return {
        "kind": "penflow-check-report",
        "version": 1,
        "workspace": str(workspace),
        "certified": False,
        "review_status": "required",
        "status": "FINDINGS" if any(r.status != "PASS" for r in checks.results) else "CHECKED",
        "exit": exit_code,
        "checks": [asdict(result) for result in checks.results],
        "limitations": [
            "Rendered UI appearance has not been observed by this command.",
            "Visual metrics use source geometry; native layout and screenshots are not evaluated.",
            "Runtime interactions, capture freshness and build identity remain unverified; "
            "an actual tree alone does not prove them.",
            "Local checks and their exit codes inform an independent review; "
            "they do not approve delivery or certify historical evidence.",
        ],
    }


def _read_theme(
    checks: _Checks, workspace: Path, theme_css: str | Path | None
) -> JsonObject | None:
    path = Path(theme_css) if theme_css is not None else Path("theme.css")
    if not path.is_absolute():
        path = workspace / path
    try:
        if not checks.reader.lexists(path):
            if theme_css is not None:
                raise ValueError(f"explicit theme not found: {path}")
            checks.missing("theme", "no theme.css supplied; palette/font checks are unavailable")
            return None
        theme = theme_from_css(checks.reader.read(path).decode("utf-8"))
        checks.run("theme", lambda: {"issues": theme.get("issues", []), "path": str(path)})
        return theme
    except _INPUT_ERRORS as error:
        checks.error("theme", error)
        return None


def _check_design(
    checks: _Checks, workspace: Path, pen: JsonObject | None, theme: JsonObject | None
) -> JsonObject | None:
    if pen is None:
        checks.missing(
            "design-checks", "ui.pen could not be read; independent inputs still checked"
        )
        return None
    path = workspace / "ui.pen"
    expected: JsonObject | None = None
    try:
        expected = expected_tree_from_pen(path, pen_data=pen)
    except (*_INPUT_ERRORS, CanvasLifecycleError) as error:
        checks.error("validate-pen", error)
    if expected is not None:
        checks.run(
            "validate-pen",
            lambda: {
                "issues": expected["issues"]
                + [asdict(issue) for issue in bbox_issues(pen)]
                + (
                    []
                    if expected["screens"]
                    else [
                        {
                            "severity": "error",
                            "code": "check.canvas.empty",
                            "message": "No active screens in ui.pen",
                        }
                    ]
                ),
                "screens": len(expected["screens"]),
                "source": str(path),
            },
        )
        checks.run(
            "check-consistency",
            lambda: check_consistency(path, tree_data=expected, shared_identity_only=True),
        )
        checks.run("audit-visual", lambda: audit_visual(path, tree_data=expected, theme=theme))
    checks.run("lint-tokens", lambda: lint_tokens(path, pen_data=pen, theme=theme))
    return expected
