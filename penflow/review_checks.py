"""Compose current local diagnostics without a delivery certification dependency."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

from .compare import STRICT_THRESHOLD, compare_trees
from .consistency import check_consistency
from .design_profile import audit_design_profile, resolve_profile
from .expected_constraints import apply_contract_constraints
from .flow_contract import validate_flow_contract_v2
from .pen import bbox_issues, parse_pen, validate_pen_context_against_contract
from .pen_components import resolve_pen_components
from .pen_lifecycle import CanvasLifecycleError
from .rendered_measurements import compare_rendered
from .theme import theme_from_css
from .token_lint import lint_tokens
from .tree import (
    diagnostic_tree_from_pen,
    expected_tree_from_pen,
    normalize_actual_tree,
    validate_actual_tree,
)
from .verification_styles import resolve_design_variables
from .verification_files import InputReader
from .visual_metrics import audit_visual

# Existing validators return heterogeneous JSON dictionaries. Keep their payloads
# intact at this composition boundary rather than translating away findings.
JsonObject = dict[str, Any]
CheckStatus = Literal["PASS", "FAIL", "ERROR", "NOT_RUN", "NOT_OBSERVED"]
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

    def optional(self, name: str, path: Path) -> JsonObject | None:
        """Read an optional object while keeping path/shape failures local."""
        try:
            return self.object(name, path) if self.reader.lexists(path) else None
        except _INPUT_ERRORS as error:
            self.error(name, error)
            return None

    def run(self, name: str, action: Callable[[], JsonObject]) -> JsonObject | None:
        try:
            report = action()
            issues = report.get("issues", []) + report.get("violations", [])
            status = report.get("status")
            code = int(
                status in {"FAIL", "FAILED", "BLOCKED", "MATERIAL_DRIFT", "MEASUREMENT_ERROR"}
                or any(issue.get("severity") in {"error", "warning"} for issue in issues)
            )
            self.results.append(
                CheckResult(
                    name,
                    ("ERROR" if status == "MEASUREMENT_ERROR" else "FAIL")
                    if code
                    else "NOT_OBSERVED"
                    if status == "NOT_OBSERVED"
                    else "PASS",
                    code if code or status != "NOT_OBSERVED" else None,
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
    if pen is not None:
        try:
            pen, component_issues = resolve_pen_components(pen)
            checks.run(
                "resolve-components",
                lambda: {
                    "issues": component_issues,
                    "status": "NOT_OBSERVED"
                    if any(issue.get("outcome") == "NOT_OBSERVED" for issue in component_issues)
                    else "PASS",
                },
            )
        except _INPUT_ERRORS as error:
            checks.error("resolve-components", error)
    theme = _read_theme(checks, workspace, theme_css)
    expected, diagnostic = _check_design(checks, workspace, pen, theme)
    if (
        diagnostic is not None
        and contract_report is not None
        and not any(issue.get("severity") == "error" for issue in contract_report["issues"])
    ):
        # Reuse contract state/repeat/condition projection; design shows alternatives,
        # while runtime captures show one observed state at a time.
        checks.run("contract-constraints", lambda: _apply_constraints(diagnostic, contract))
    _check_profile(checks, workspace, diagnostic, contract)
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
    if actual is not None and "measurement" in actual:
        checks.missing(
            "compare-tree",
            "Qualified captures use the normalized structural comparison in compare-rendered",
        )
    elif expected is not None and actual is not None:
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
    layout = checks.optional("design-layout", workspace / "design-layout.json")
    if diagnostic is not None and actual is not None:
        checks.run(
            "compare-rendered",
            lambda: compare_rendered(diagnostic, actual, design_layout=layout),
        )
    else:
        checks.missing("compare-rendered", "Current design and runtime observations are required")
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
            "Rendered measurements are evaluated only when qualified observations are supplied; "
            "capture metadata alone does not authenticate the producer.",
            "Source metrics and rendered comparisons have separate scope; screenshots and "
            "aesthetic quality are not evaluated.",
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
) -> tuple[JsonObject | None, JsonObject | None]:
    if pen is None:
        checks.missing(
            "design-checks", "ui.pen could not be read; independent inputs still checked"
        )
        return None, None
    path = workspace / "ui.pen"
    expected: JsonObject | None = None
    try:
        expected = expected_tree_from_pen(path, pen_data=pen)
    except (*_INPUT_ERRORS, CanvasLifecycleError) as error:
        checks.error("validate-pen", error)
    diagnostic = expected
    if diagnostic is None:
        try:
            diagnostic = diagnostic_tree_from_pen(path, pen)
        except _INPUT_ERRORS as error:
            checks.error("design-regions", error)
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
    if diagnostic is not None:
        diagnostic["source_sha256"] = checks.reader.observed[path.resolve()]
        # Resolve the same source snapshot once. An unresolved variable remains an
        # error while independent raw-token diagnostics continue below.
        try:
            variables = {
                key: {"value": value} for key, value in (theme or {}).get("variables", {}).items()
            }
            variables.update(pen.get("variables", {}))
            resolve_design_variables(
                diagnostic, variables, pen_data=pen, native_theme_semantics=True
            )
        except _INPUT_ERRORS as error:
            checks.error("resolve-design-variables", error)
        scope = diagnostic.get("scope", "active-regions")
        checks.run(
            "check-consistency",
            lambda: {
                **check_consistency(path, tree_data=diagnostic, shared_identity_only=True),
                "scope": scope,
            },
        )
        checks.run(
            "audit-visual",
            lambda: {
                **audit_visual(path, tree_data=diagnostic, theme=theme, explicit_hit_areas=True),
                "scope": scope,
            },
        )
    checks.run(
        "lint-tokens",
        lambda: {
            **lint_tokens(path, pen_data=pen, theme=theme, diagnostic_regions=expected is None),
            "scope": "active-regions" if expected is not None else "all-physical-regions",
        },
    )
    return expected, diagnostic


def _check_profile(
    checks: _Checks, workspace: Path, expected: JsonObject | None, contract: JsonObject | None
) -> None:
    """Read confined optional policy inputs and record unavailable selection honestly."""
    path = workspace / "design-profile.json"
    config = checks.optional("design-profile-input", path)
    if any(row.name == "design-profile-input" and row.status == "ERROR" for row in checks.results):
        return
    sources: dict[str, bytes] = {}
    try:
        index = checks.reader.root / ".conventions/index.md"
        if checks.reader.lexists(index):
            sources[".conventions/index.md"] = checks.reader.read(index)
        for name in (config or {}).get("sources", []):
            sources[name] = checks.reader.read(workspace / name)
        profile = resolve_profile(config, contract=contract, convention_sources=sources)
    except _INPUT_ERRORS as error:
        checks.error("design-profile", error)
        return
    if expected is None:
        checks.missing("design-profile", "No usable design regions supplied")
        return
    checks.run("design-profile", lambda: audit_design_profile(expected, profile))


def _apply_constraints(expected: JsonObject, contract: JsonObject | None) -> JsonObject:
    """Project already validated behavioral scope into the current design tree."""
    assert contract is not None
    apply_contract_constraints(expected, contract)
    return {"issues": []}
