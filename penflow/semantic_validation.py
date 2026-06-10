# @spec(FR-002)
"""Semantic UI tree validation."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from .schema_cache import load_schema

INTERACTIVE_ROLES = {"button", "link", "input", "select", "toggle", "form"}
PASSIVE_STRUCTURE_ROLES = {"screen", "container", "component", "section", "shape"}
REPEAT_ROLES = {"list", "list_item"}
BINDING_RE = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
SCHEMA_PATH = Path(__file__).parent / "schemas" / "semantic-ui-tree.schema.json"


@dataclass(slots=True)
class SemanticIssue:
    severity: str
    code: str
    path: str
    message: str
    semantic_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a scriptable issue object."""
        return {key: value for key, value in asdict(self).items() if value is not None}


def validate_semantic_tree(tree: dict[str, Any]) -> list[dict[str, Any]]:
    """Validate a semantic UI tree for schema shape and semantic link coherence.

    Args:
        tree: Parsed semantic UI tree JSON object.

    Returns:
        Deterministic list of issue dictionaries. Empty means valid for feature 030 scope.
    """
    issues: list[SemanticIssue] = []
    if not isinstance(tree, dict):
        return [
            SemanticIssue("error", "semantic.root_type", "$", "tree must be an object").to_dict()
        ]

    issues.extend(_validate_root_shape(tree))
    raw_flows = tree.get("flows")
    raw_screens = tree.get("screens")
    flows: list[Any] = raw_flows if isinstance(raw_flows, list) else []
    screens: list[Any] = raw_screens if isinstance(raw_screens, list) else []
    flow_ids = _collect_unique_ids(flows, "id", "$.flows", "flow_id", issues)
    screen_ids = _collect_unique_ids(screens, "id", "$.screens", "screen_id", issues)
    _validate_flow_links(flows, screen_ids, issues)
    _validate_screen_links(screens, flow_ids, issues)
    _validate_nodes(screens, issues)
    return [issue.to_dict() for issue in issues]


def validate_semantic_tree_file(path: str | Path) -> tuple[bool, list[dict[str, Any]]]:
    """Read and validate a semantic UI tree file."""
    try:
        tree = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        issue = SemanticIssue("error", "semantic.json_invalid", "$", str(error))
        return False, [issue.to_dict()]
    issues = validate_semantic_tree(tree)
    return not _has_errors(issues), issues


def _validate_root_shape(tree: dict[str, Any]) -> list[SemanticIssue]:
    issues: list[SemanticIssue] = []
    required = {"version", "kind", "tree_id", "source", "flows", "screens"}
    for key in sorted(required):
        if key not in tree:
            issues.append(
                SemanticIssue("error", "semantic.root_required", f"$.{key}", f"{key} is required")
            )
    if tree.get("version") != 1:
        issues.append(
            SemanticIssue("error", "semantic.version_invalid", "$.version", "version must be 1")
        )
    if tree.get("kind") != "semantic-ui-tree":
        issues.append(
            SemanticIssue(
                "error", "semantic.kind_invalid", "$.kind", "kind must be semantic-ui-tree"
            )
        )
    if not isinstance(tree.get("flows", []), list):
        issues.append(
            SemanticIssue("error", "semantic.flows_type", "$.flows", "flows must be a list")
        )
    if not isinstance(tree.get("screens", []), list):
        issues.append(
            SemanticIssue("error", "semantic.screens_type", "$.screens", "screens must be a list")
        )
    return issues


def _collect_unique_ids(
    items: list[Any],
    key: str,
    path: str,
    label: str,
    issues: list[SemanticIssue],
) -> set[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            issues.append(
                SemanticIssue(
                    "error",
                    f"semantic.{label}_item_type",
                    f"{path}[{index}]",
                    "item must be an object",
                )
            )
            continue
        value = item.get(key)
        if not isinstance(value, str) or not value:
            issues.append(
                SemanticIssue(
                    "error",
                    f"semantic.{label}_required",
                    f"{path}[{index}].{key}",
                    f"{key} is required",
                )
            )
            continue
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    for duplicate in sorted(duplicates):
        issues.append(
            SemanticIssue(
                "error", f"semantic.{label}_duplicate", path, f"duplicate {label}: {duplicate}"
            )
        )
    return seen


def _validate_flow_links(
    flows: list[Any],
    screen_ids: set[str],
    issues: list[SemanticIssue],
) -> None:
    for flow_index, flow in enumerate(flows):
        if not isinstance(flow, dict):
            continue
        path = f"$.flows[{flow_index}]"
        _validate_source_map(
            flow.get("source_map"),
            f"{path}.source_map",
            "flow",
            issues,
            required_key="flow_spec",
        )
        entry_screen = flow.get("entry_screen")
        if isinstance(entry_screen, str) and entry_screen not in screen_ids:
            issues.append(
                SemanticIssue(
                    "error",
                    "semantic.flow_entry_screen_missing",
                    f"{path}.entry_screen",
                    f"entry_screen does not reference an existing screen: {entry_screen}",
                )
            )
        for step_index, step in enumerate(flow.get("steps", []) or []):
            if isinstance(step, dict) and step.get("screen_id") not in screen_ids:
                issues.append(
                    SemanticIssue(
                        "error",
                        "semantic.flow_step_screen_missing",
                        f"{path}.steps[{step_index}].screen_id",
                        f"step references missing screen: {step.get('screen_id')}",
                    )
                )
        for transition_index, transition in enumerate(flow.get("transitions", []) or []):
            if not isinstance(transition, dict):
                continue
            for key in ("from", "to"):
                if transition.get(key) not in screen_ids:
                    issues.append(
                        SemanticIssue(
                            "error",
                            "semantic.flow_transition_screen_missing",
                            f"{path}.transitions[{transition_index}].{key}",
                            f"transition {key} references missing screen: {transition.get(key)}",
                        )
                    )


def _validate_screen_links(
    screens: list[Any],
    flow_ids: set[str],
    issues: list[SemanticIssue],
) -> None:
    for screen_index, screen in enumerate(screens):
        if not isinstance(screen, dict):
            continue
        _validate_source_map(
            screen.get("source_map"),
            f"$.screens[{screen_index}].source_map",
            "screen",
            issues,
            required_key="screen_spec",
        )
        flow_id = screen.get("flow_id")
        if flow_id not in flow_ids:
            issues.append(
                SemanticIssue(
                    "error",
                    "semantic.screen_flow_missing",
                    f"$.screens[{screen_index}].flow_id",
                    f"screen references missing flow: {flow_id}",
                )
            )


def _validate_nodes(screens: list[Any], issues: list[SemanticIssue]) -> None:
    semantic_ids: set[str] = set()
    duplicate_semantic_ids: set[str] = set()
    test_ids: set[str] = set()
    duplicate_test_ids: set[str] = set()
    allowed_roles = _allowed_roles()
    for screen_index, screen in enumerate(screens):
        if not isinstance(screen, dict):
            continue
        root = screen.get("root")
        if not isinstance(root, dict):
            issues.append(
                SemanticIssue(
                    "error",
                    "semantic.root_node_required",
                    f"$.screens[{screen_index}].root",
                    "root node is required",
                )
            )
            continue
        _walk_node(
            root,
            f"$.screens[{screen_index}].root",
            allowed_roles,
            semantic_ids,
            duplicate_semantic_ids,
            test_ids,
            duplicate_test_ids,
            issues,
        )
    for duplicate in sorted(duplicate_semantic_ids):
        issues.append(
            SemanticIssue(
                "error",
                "semantic.node_id_duplicate",
                "$.screens",
                f"duplicate semantic_id: {duplicate}",
                duplicate,
            )
        )
    for duplicate in sorted(duplicate_test_ids):
        issues.append(
            SemanticIssue(
                "error",
                "semantic.test_id_duplicate",
                "$.screens",
                f"duplicate test_id: {duplicate}",
            )
        )


def _walk_node(
    node: dict[str, Any],
    path: str,
    allowed_roles: set[str],
    semantic_ids: set[str],
    duplicate_semantic_ids: set[str],
    test_ids: set[str],
    duplicate_test_ids: set[str],
    issues: list[SemanticIssue],
) -> None:
    semantic_id = node.get("semantic_id")
    role = node.get("role")
    if not isinstance(semantic_id, str) or not semantic_id:
        issues.append(
            SemanticIssue(
                "error",
                "semantic.node_id_required",
                f"{path}.semantic_id",
                "semantic_id is required",
            )
        )
    elif semantic_id in semantic_ids:
        duplicate_semantic_ids.add(semantic_id)
    else:
        semantic_ids.add(semantic_id)

    if role not in allowed_roles:
        issues.append(
            SemanticIssue(
                "error",
                "semantic.role_invalid",
                f"{path}.role",
                f"invalid role: {role}",
                semantic_id if isinstance(semantic_id, str) else None,
            )
        )
    has_meaningful_behavior = bool(node.get("validations") or node.get("side_effects"))
    requires_intent = role in INTERACTIVE_ROLES or (
        has_meaningful_behavior and role not in PASSIVE_STRUCTURE_ROLES
    )
    if requires_intent and not node.get("intent"):
        issues.append(
            SemanticIssue(
                "error",
                "semantic.intent_required",
                f"{path}.intent",
                f"{role} requires intent",
                semantic_id if isinstance(semantic_id, str) else None,
            )
        )
    if role in REPEAT_ROLES and not node.get("repeat"):
        issues.append(
            SemanticIssue(
                "error",
                "semantic.repeat_required",
                f"{path}.repeat",
                f"{role} requires repeat",
                semantic_id if isinstance(semantic_id, str) else None,
            )
        )
    if node.get("binding") and not BINDING_RE.match(str(node["binding"])):
        issues.append(
            SemanticIssue(
                "error",
                "semantic.binding_format",
                f"{path}.binding",
                "binding must use entity.field syntax",
                semantic_id if isinstance(semantic_id, str) else None,
            )
        )
    if node.get("binding") and not node.get("entity"):
        issues.append(
            SemanticIssue(
                "error",
                "semantic.entity_required",
                f"{path}.entity",
                "nodes with binding require entity",
                semantic_id if isinstance(semantic_id, str) else None,
            )
        )
    _validate_source_map(
        node.get("source_map"),
        f"{path}.source_map",
        "node",
        issues,
        required_key="screen_spec" if role == "screen" else None,
        semantic_id=semantic_id if isinstance(semantic_id, str) else None,
    )

    test_id = node.get("test_id")
    if isinstance(test_id, str) and test_id:
        if test_id in test_ids:
            duplicate_test_ids.add(test_id)
        else:
            test_ids.add(test_id)
    for child_index, child in enumerate(node.get("children", []) or []):
        if isinstance(child, dict):
            _walk_node(
                child,
                f"{path}.children[{child_index}]",
                allowed_roles,
                semantic_ids,
                duplicate_semantic_ids,
                test_ids,
                duplicate_test_ids,
                issues,
            )


def _allowed_roles() -> set[str]:
    schema = load_schema(SCHEMA_PATH.name)
    return set(schema["$defs"]["semanticNode"]["properties"]["role"]["enum"])


def _validate_source_map(
    source_map: Any,
    path: str,
    owner: str,
    issues: list[SemanticIssue],
    *,
    required_key: str | None = None,
    semantic_id: str | None = None,
) -> None:
    if not isinstance(source_map, dict) or not source_map:
        issues.append(
            SemanticIssue(
                "error",
                f"semantic.{owner}_source_map_required",
                path,
                "source_map is required",
                semantic_id,
            )
        )
        return
    if source_map.get("contract") and not source_map.get("contract_path"):
        issues.append(
            SemanticIssue(
                "error",
                f"semantic.{owner}_source_map_contract_path_required",
                f"{path}.contract_path",
                "source_map.contract_path is required",
                semantic_id,
            )
        )
        return
    if required_key and not source_map.get(required_key) and not source_map.get("contract"):
        issues.append(
            SemanticIssue(
                "error",
                f"semantic.{owner}_source_map_{required_key}_required",
                f"{path}.{required_key}",
                f"source_map.{required_key} is required",
                semantic_id,
            )
        )


def _has_errors(issues: list[dict[str, Any]]) -> bool:
    return any(issue.get("severity") == "error" for issue in issues)
