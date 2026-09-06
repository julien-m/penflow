"""Recompute deterministic design projections and existing mandatory design controls."""

from dataclasses import asdict
from typing import Any

from .code_ir import code_ir_from_pen, validate_code_ir
from .consistency import check_consistency
from .drift import canonical_drift_issues
from .flow_contract import validate_flow_contract_v2
from .flow_docs import check_generated_docs
from .json_filesystem import write_json_atomically
from .pen import bbox_issues, parse_pen, validate_pen_context, validate_pen_context_against_contract
from .semantic_contract import semantic_tree_from_contract
from .semantic_context_coverage import audit_semantic_context
from .semantic_mapping import pencil_context_map
from .semantic_validation import validate_semantic_tree
from .theme import theme_from_css
from .token_lint import lint_tokens
from .tree import _screen_to_expected, validate_actual_tree
from .verification_geometry import intrinsic_text_ids, load_native_geometry
from .verification_json import canonical_bytes
from .verification_policy import GateBook
from .verification_schema import issue
from .verification_styles import resolve_design_variables
from .verification_snapshot import VerificationSnapshot
from .visual_metrics import audit_visual


def evaluate_design(
    snapshot: VerificationSnapshot, gates: GateBook, *, produce: bool
) -> dict[str, Any]:
    """Apply the source-before-export order, reusing the same pure projection checks."""
    values: dict[str, Any] = {}
    gates.evaluate("validate-flow-contract", lambda: validate_flow_contract_v2(snapshot.contract))
    gates.evaluate(
        "export-semantic-tree",
        lambda: _semantic(snapshot, values, produce),
        dependencies=("validate-flow-contract",),
    )
    gates.evaluate(
        "validate-semantic-tree",
        lambda: validate_semantic_tree(values["semantic"]),
        dependencies=("export-semantic-tree",),
    )
    gates.evaluate(
        "validate-pen", lambda: _pen(snapshot, values), dependencies=("validate-flow-contract",)
    )
    gates.evaluate(
        "map-pencil-context",
        lambda: _mapping(snapshot, values, produce),
        dependencies=("validate-semantic-tree", "validate-pen"),
    )
    gates.evaluate(
        "semantic-context-coverage",
        lambda: _coverage(snapshot, values),
        dependencies=("map-pencil-context",),
    )
    gates.evaluate(
        "export-expected",
        lambda: _expected(snapshot, values, produce),
        dependencies=("semantic-context-coverage",),
    )
    gates.evaluate(
        "code-ir",
        lambda: _ir(snapshot, values, produce),
        dependencies=("export-expected", "map-pencil-context"),
    )
    gates.evaluate(
        "detect-drift",
        lambda: canonical_drift_issues(values["semantic"], values["pen"]),
        dependencies=("semantic-context-coverage",),
    )
    _human_docs(snapshot, gates)
    _visual_checks(snapshot, gates, values)
    return values


def _projection(
    snapshot: VerificationSnapshot, name: str, expected: dict[str, Any], produce: bool
) -> list[dict[str, Any]]:
    path = snapshot.workspace / name
    if produce:
        snapshot.reader.recheck()
        write_json_atomically(path, expected)
    current = snapshot.object(name)
    return (
        []
        if canonical_bytes(current) == canonical_bytes(expected)
        else [
            issue(
                "verification.source.projection_changed",
                str(path),
                "stored projection differs from its validated source",
            )
        ]
    )


def _semantic(
    snapshot: VerificationSnapshot, values: dict[str, Any], produce: bool
) -> list[dict[str, Any]]:
    semantic = semantic_tree_from_contract(
        snapshot.contract, source_path=str(snapshot.workspace / "flow-ui-contract/contract.json")
    )
    values["semantic"] = semantic
    return _projection(snapshot, "semantic-ui-tree.json", semantic, produce)


def _pen(snapshot: VerificationSnapshot, values: dict[str, Any]) -> list[dict[str, Any]]:
    values["pen"] = snapshot.object("ui.pen")
    roots = parse_pen(values["pen"])
    findings = [asdict(item) for item in validate_pen_context(roots)]
    findings.extend(
        asdict(item) for item in validate_pen_context_against_contract(roots, snapshot.contract)
    )
    findings.extend(asdict(item) for item in bbox_issues(values["pen"]))
    return findings


def _mapping(
    snapshot: VerificationSnapshot, values: dict[str, Any], produce: bool
) -> list[dict[str, Any]]:
    mapping = pencil_context_map(values["pen"], values["semantic"])
    values["mapping"] = mapping
    if mapping["status"] != "PASS":
        return [
            issue(
                "verification.source.partial_mapping", "/", "every semantic node must map uniquely"
            )
        ]
    return _projection(snapshot, "pencil-context-map.json", mapping, produce)


def _coverage(snapshot: VerificationSnapshot, values: dict[str, Any]) -> list[dict[str, Any]]:
    report = audit_semantic_context(
        snapshot.contract,
        values["pen"],
        contract_path=str(snapshot.workspace / "flow-ui-contract/contract.json"),
        pen_path=str(snapshot.workspace / "ui.pen"),
    )
    return [
        finding
        for bucket in report["buckets"].values()
        for finding in bucket
        if finding.get("blocking")
    ]


def _expected(
    snapshot: VerificationSnapshot, values: dict[str, Any], produce: bool
) -> list[dict[str, Any]]:
    roots = parse_pen(values["pen"])
    expected: dict[str, Any] = {
        "version": 1,
        "source": str(snapshot.workspace / "ui.pen"),
        "screens": [_screen_to_expected(root) for root in roots],
        "issues": [asdict(value) for value in validate_pen_context(roots)],
    }
    root_ids = {screen["root_node"] for screen in snapshot.contract["screens"]}
    root_screens = {
        node["semantic_id"]: node["screen_id"]
        for node in snapshot.contract["nodes"]
        if node["id"] in root_ids
    }
    for screen in expected["screens"]:
        screen["screen_id"] = root_screens[screen["root"]["semantic_id"]]
    if snapshot.policy is None:
        raise ValueError("verification.policy.native_geometry_unknown")
    if snapshot.policy["native_geometry"] == "required":
        values["layout"] = load_native_geometry(snapshot, expected)
    resolve_design_variables(expected, values["pen"].get("variables", {}), pen_data=values["pen"])
    values["expected"] = expected
    findings = validate_actual_tree(expected)
    return findings or _projection(snapshot, "expected-ui-tree.json", expected, produce)


def _ir(
    snapshot: VerificationSnapshot, values: dict[str, Any], produce: bool
) -> list[dict[str, Any]]:
    workspace = snapshot.workspace
    ir = code_ir_from_pen(
        workspace / "ui.pen",
        pen_data=values["pen"],
        semantic_tree=values["semantic"],
        context_map=values["mapping"],
        contract=snapshot.contract,
    )
    ir["inputs"] = {
        "semantic_tree": str(workspace / "semantic-ui-tree.json"),
        "context_map": str(workspace / "pencil-context-map.json"),
        "contract": str(workspace / "flow-ui-contract/contract.json"),
    }
    return validate_code_ir(ir) or _projection(snapshot, "code-ir.json", ir, produce)


def _human_docs(snapshot: VerificationSnapshot, gates: GateBook) -> None:
    root = snapshot.workspace / "flow-ui-contract"
    decision = snapshot.policy.get("generated_docs") if snapshot.policy is not None else None
    if decision is None:
        gates.fail(
            "generated-flow-docs",
            "verification.policy.missing",
            "generated documentation applicability has no reviewed workflow source",
        )
        return
    if decision == "not_applicable":
        gates.not_applicable(
            "generated-flow-docs",
            "/verification_policy/generated_docs",
            "reviewed workflow explicitly does not generate human documents",
        )
        return

    def check() -> list[dict[str, Any]]:
        for path in snapshot.reader.files(root, "*.md"):
            snapshot.reader.read(path)
        snapshot.reader.read(root / "generated-docs.json")
        return check_generated_docs(root / "contract.json", root, explicit=True)["issues"]

    gates.evaluate("generated-flow-docs", check)


def _visual_checks(snapshot: VerificationSnapshot, gates: GateBook, values: dict[str, Any]) -> None:
    theme_path = snapshot.workspace / "theme.css"
    theme = None
    if snapshot.reader.exists(theme_path):
        theme = theme_from_css(snapshot.reader.read(theme_path).decode("utf-8"))
    expected = snapshot.workspace / "expected-ui-tree.json"
    layout = snapshot.workspace / ".mockup-validation/visual-evidence/layout-snapshot.json"
    present = snapshot.reader.exists(layout)
    geometry = (
        values.get("expected")
        if "layout" in values
        else (snapshot.reader.object(snapshot.reader.read(layout)) if present else None)
    )
    gates.evaluate(
        "lint-tokens",
        lambda: lint_tokens(snapshot.workspace / "ui.pen", pen_data=values["pen"], theme=theme)[
            "violations"
        ],
        dependencies=("validate-pen",),
    )
    gates.evaluate(
        "check-consistency",
        lambda: check_consistency(
            expected, tree_data=values["expected"], lenient=False, shared_identity_only=True
        )["issues"],
        dependencies=("export-expected",),
    )
    gates.evaluate(
        "audit-visual",
        lambda: audit_visual(
            expected,
            tree_data=values["expected"],
            theme=theme,
            layout_snapshot=geometry,
            intrinsic_text_ids=intrinsic_text_ids(values["pen"])
            if "layout" in values
            else frozenset(),
        )["issues"],
        dependencies=("export-expected",),
    )
