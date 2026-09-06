# @spec(FR-001)
# @spec(FR-002)
# @spec(FR-003)
"""Expected and actual UI tree normalization."""

from __future__ import annotations

import json
import math
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .models import PenNode
from .pen import parse_pen, validate_pen_context
from .schema_cache import validator_for
from .verification_json import canonical_bytes

REQUIRED_ACTUAL_NODE_KEYS = {"id", "role", "bbox"}
REQUIRED_BBOX_KEYS = {"x", "y", "width", "height"}
# Measurement safety bound, far beyond practical UI coordinates: reject huge JSON
# integers before float conversion can overflow. Business JSON values remain unrestricted.
MAX_ABSOLUTE_OBSERVATION = 1e12


def expected_tree_from_pen(path: str | Path) -> dict[str, Any]:
    roots = parse_pen(path)
    issues = validate_pen_context(roots)
    return {
        "version": 1,
        "source": str(path),
        "screens": [_screen_to_expected(root) for root in roots],
        "issues": [asdict(issue) for issue in issues],
    }


def _screen_to_expected(root: PenNode) -> dict[str, Any]:
    return {
        "screen_id": root.semantic_id or root.id,
        "pencil_id": root.id,
        "name": root.name,
        "viewport": root.bbox.to_dict(),
        "root": root.to_expected(),
    }


def write_expected_tree(pen_path: str | Path, out_path: str | Path) -> dict[str, Any]:
    tree = expected_tree_from_pen(pen_path)
    Path(out_path).write_text(json.dumps(tree, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return tree


def load_tree(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def validate_actual_tree(tree: dict[str, Any], *, schema: bool = False) -> list[dict[str, Any]]:
    """Validate an actual UI tree.

    Args:
        tree: Actual UI tree dict (contract C12).
        schema: Retained for CLI/API compatibility. Complete schema validation
            is unconditional since C51; the flag never weakens certification.

    Returns:
        List of structured issues ``{severity, path, message}``. Empty list
        means the tree is valid.
    """
    if not isinstance(tree, dict):
        return [_issue("error", "$", "actual tree must be an object")]
    try:
        canonical_bytes(tree)
    except (ValueError, TypeError, RecursionError) as exc:
        return [_issue("error", "$", f"invalid finite JSON tree: {exc}")]
    canonical = normalize_actual_tree(tree)
    issues = _validate_actual_tree_schema(canonical)
    if issues:
        return issues
    return _tree_identity_issues(canonical)


def _validate_actual_tree_schema(tree: Any) -> list[dict[str, Any]]:
    """Run the JSON Schema (draft 2020-12) validator on an actual UI tree.

    ``jsonschema`` is a hard dependency (feature 049); the full draft 2020-12
    validator is the only validation path. Errors are sorted deterministically
    by ``(absolute_path, message)`` so the merged list is reproducible across
    runs.
    """
    if not isinstance(tree, dict):
        return [_issue("error", "$", "actual tree must be an object")]
    validator = validator_for("actual-ui-tree.schema.json")
    raw_errors = list(validator.iter_errors(tree))
    formatted: list[dict[str, Any]] = []
    for error in raw_errors:
        path = "$" + "".join(
            f".{part}" if isinstance(part, str) else f"[{part}]" for part in error.absolute_path
        )
        if error.validator == "required":
            for key in error.validator_value:
                if key not in error.instance:
                    formatted.append(_issue("error", f"{path}.{key}", f"{key} is required"))
        else:
            formatted.append(_issue("error", path, error.message))
    formatted.sort(key=lambda item: (item["path"], item["message"]))
    return formatted


def normalize_actual_tree(tree: dict[str, Any]) -> dict[str, Any]:
    if "screens" in tree:
        return tree
    return {
        "version": tree.get("version"),
        "screens": [
            {
                "screen_id": tree.get("screen_id", "screen"),
                **({"viewport": tree["viewport"]} if "viewport" in tree else {}),
                "root": tree.get("root")
                or {"id": "root", "role": "container", "children": tree.get("nodes", [])},
            }
        ],
    }


def flatten_nodes(
    node: dict[str, Any], parent_id: str | None = None, order: int = 0
) -> list[dict[str, Any]]:
    """Flatten a node subtree in depth-first preorder without mutating its records.

    Args:
        node: Root node whose children retain their declared sibling order.
        parent_id: Semantic key of the root's parent, or None for a screen root.
        order: Root's sibling position; descendants use their child-list indexes.

    Returns:
        Shallow node copies without children, annotated with _semantic_key (semantic
        ID or node ID, plus ::instance_id when present), _parent_key and _order.
        Nested property values remain shared with the input.
    """
    flattened: list[dict[str, Any]] = []
    pending = [(node, parent_id, order)]
    while pending:
        current, parent, position = pending.pop()
        key = current.get("semantic_id") or current.get("id")
        instance = current.get("instance_id")
        if instance:
            key = f"{key}::{instance}"
        item = dict(current)
        children = item.pop("children", []) or []
        item.update(_semantic_key=key, _parent_key=parent, _order=position)
        flattened.append(item)
        pending.extend((child, key, i) for i, child in reversed(list(enumerate(children))))
    return flattened


# @spec FR-006: Unique typed observations — .specs/features/077-complete-verification-workflow/spec.md#fr-006
def _tree_identity_issues(tree: dict[str, Any]) -> list[dict[str, Any]]:
    # Check each screen's unique identities, finite geometry, then typed numeric observations.
    issues: list[dict[str, Any]] = []
    screens: set[str] = set()
    for index, screen in enumerate(tree["screens"]):
        path = f"$.screens[{index}]"
        if screen["screen_id"] in screens:
            issues.append(_issue("error", path, "duplicate screen identity"))
        screens.add(screen["screen_id"])
        for key, value in screen.get("viewport", {}).items():
            if isinstance(value, (int, float)) and (
                abs(value) > MAX_ABSOLUTE_OBSERVATION or not math.isfinite(value)
            ):
                issues.append(_issue("error", f"{path}.viewport.{key}", "viewport must be finite"))
        identities: set[str] = set()
        node_ids: set[str] = set()
        for node in flatten_nodes(screen["root"]):
            key = node["_semantic_key"]
            if key in identities or node["id"] in node_ids:
                issues.append(_issue("error", path, f"duplicate node identity: {key}"))
            identities.add(key)
            node_ids.add(node["id"])
            for property_name, value in node["bbox"].items():
                if isinstance(value, (int, float)) and (
                    abs(value) > MAX_ABSOLUTE_OBSERVATION or not math.isfinite(value)
                ):
                    issues.append(_issue("error", path, f"non-finite bbox {property_name}"))
            issues.extend(_numeric_observation_issues(node, path))
    return issues


def _issue(severity: str, path: str, message: str) -> dict[str, Any]:
    return {"severity": severity, "path": path, "message": message}


def _numeric_observation_issues(node: dict[str, Any], path: str) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    tolerance = node.get("context", {}).get("tolerance", {})
    if not isinstance(tolerance, dict):
        return [_issue("error", path, "tolerance must be an object")]
    for key, value in tolerance.items():
        if key == "color" and value == "exact":
            continue
        if key not in {
            "bbox_px",
            "radius_px",
            "font_px",
            "spacing_px",
            "order",
        } or not _finite_nonnegative(value):
            issues.append(_issue("error", path, f"invalid tolerance {key}"))
    visual = node.get("visual", {})
    stroke = visual.get("stroke")
    if isinstance(stroke, dict):
        thickness = stroke.get("thickness")
        if not _finite_nonnegative(thickness) or (
            "strokeThickness" in visual and visual["strokeThickness"] != thickness
        ):
            issues.append(_issue("error", path, "invalid or contradictory stroke thickness"))
    for key in ("fontSize", "cornerRadius", "gap", "padding", "strokeThickness", "strokeWidth"):
        if key not in visual:
            continue
        raw = visual[key]
        values = (
            list(raw.values()) if isinstance(raw, dict) else raw if isinstance(raw, list) else [raw]
        )
        if any(not _finite_nonnegative(value) for value in values):
            issues.append(_issue("error", path, f"invalid visual {key}"))
    return issues


def _finite_nonnegative(value: Any) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and abs(value) <= MAX_ABSOLUTE_OBSERVATION
        and math.isfinite(value)
        and value >= 0
    )
