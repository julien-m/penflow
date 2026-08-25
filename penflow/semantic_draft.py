# @spec(FR-001)
"""Semantic UI tree to Pencil draft generation."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from .context import format_context_string
from .json_filesystem import write_json_atomically
from .pen_lifecycle import (
    CanvasFinding,
    CanvasLifecycleError,
    CanvasLifecycleResult,
    CanvasState,
    validate_canvas_lifecycle,
)
from .semantic_validation import validate_semantic_tree

# Re-exported for backward compatibility: theme parsing moved to penflow.theme
# (feature 046) without changing draft-pen-from-tree behavior.
from .theme import DEFAULT_STYLE, THEME_TOKEN_MAP, load_theme

__all__ = [
    "DEFAULT_STYLE",
    "THEME_TOKEN_MAP",
    "pen_draft_from_semantic_tree",
    "write_pen_draft_from_semantic_tree",
]

PEN_VERSION = "2.11"
SCREEN_GAP = 16
SCREEN_PADDING = 24
NODE_GAP = 8
# Sixteen SHA-256 hex digits seed a 64-bit deterministic identity for a newly
# created region. Managed replacements preserve that stable region identity;
# this is not a content-version digest.
REVISION_DIGEST_HEX_LENGTH = 16


def pen_draft_from_semantic_tree(
    tree: dict[str, Any], *, theme_css_path: str | Path | None = None
) -> dict[str, Any]:
    """Build a deterministic Pencil draft from a validated semantic UI tree.

    Args:
        tree: Semantic UI tree dictionary.

    Returns:
        Pencil-compatible draft data.

    Raises:
        ValueError: If the semantic UI tree has validation errors.
    """
    issues = validate_semantic_tree(tree)
    if _has_errors(issues):
        raise ValueError(f"semantic UI tree is invalid: {issues[0]['code']}")
    theme = load_theme(theme_css_path)
    screens = [
        _screen_to_pen(screen, index, theme=theme) for index, screen in enumerate(tree["screens"])
    ]
    draft = {"version": PEN_VERSION, "children": screens}
    if theme["variables"]:
        draft["variables"] = theme["variables"]
    return draft


# @spec FR-005: Canonical producer migration — .specs/features/074-penflow-doctor-consumer-project-hygiene/spec.md#fr-005
def write_pen_draft_from_semantic_tree(
    tree_path: str | Path, out_path: str | Path, *, theme_css_path: str | Path | None = None
) -> dict[str, Any]:
    """Read a semantic UI tree and write a deterministic Pencil draft.

    Args:
        tree_path: Path to `semantic-ui-tree.json`.
        out_path: Canonical ``ui.pen`` destination. If it exists, matching
            active roots are replaced while unrelated and historical regions
            remain byte-equivalent as JSON values.

    Returns:
        The generated Pencil draft dictionary.

    Raises:
        CanvasLifecycleError: If the existing canvas lifecycle or variables
            cannot be merged safely.
        OSError: If an input or destination cannot be read or written.
        ValueError: If input JSON or semantic-tree validation is invalid.

    Side effects:
        Atomically creates or replaces canonical ``ui.pen`` while preserving
        unrelated and historical lifecycle regions.
    """
    tree = json.loads(Path(tree_path).read_text(encoding="utf-8"))
    draft = pen_draft_from_semantic_tree(tree, theme_css_path=theme_css_path)
    destination = Path(out_path)
    document = _merge_with_existing_document(destination, draft)
    write_json_atomically(destination, document)
    return document


def _merge_with_existing_document(path: Path, draft: dict[str, Any]) -> dict[str, Any]:
    """Merge generated active roots into an existing canonical canvas."""
    generated = _validated_lifecycle(draft)
    if not path.exists():
        return draft

    existing = _load_existing_document(path)
    existing_result = validate_canvas_lifecycle(existing)
    generated_ids = {region.logical_screen_id for region in generated.active_regions}
    blocking = _blocking_existing_findings(existing_result, generated_ids)
    if blocking:
        raise CanvasLifecycleError(blocking)

    generated_by_id = {
        region.logical_screen_id: copy.deepcopy(dict(region.raw_node))
        for region in generated.active_regions
    }
    merged = copy.deepcopy(existing)
    merged["version"] = draft["version"]
    merged["children"] = _merge_canvas_children(existing, existing_result, generated_by_id)
    _merge_document_variables(merged, existing, draft)
    _validated_lifecycle(merged)
    return merged


def _validated_lifecycle(document: dict[str, Any]) -> CanvasLifecycleResult:
    """Return lifecycle data or raise its stable typed validation error."""
    result = validate_canvas_lifecycle(document)
    if result.findings:
        raise CanvasLifecycleError(result.findings)
    return result


def _load_existing_document(path: Path) -> dict[str, Any]:
    """Load an existing canonical canvas and validate its object boundary."""
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise CanvasLifecycleError(
            (CanvasFinding("canvas.document_invalid", "canvas document must be an object"),)
        )
    _existing_variables(document)
    return document


def _blocking_existing_findings(
    lifecycle: CanvasLifecycleResult,
    generated_ids: set[str],
) -> tuple[CanvasFinding, ...]:
    """Return findings that generated active roots cannot safely repair."""
    # An empty canvas is safe only because the valid draft supplies active
    # roots; active_missing is safe only for the same generated logical screen.
    return tuple(
        finding
        for finding in lifecycle.findings
        if finding.code != "canvas.empty"
        and (
            finding.code != "canvas.active_missing"
            or finding.logical_screen_id not in generated_ids
        )
    )


def _existing_variables(document: dict[str, Any]) -> dict[str, Any]:
    """Return validated existing variables or raise a typed canvas finding."""
    variables = document.get("variables", {})
    if not isinstance(variables, dict):
        raise CanvasLifecycleError(
            (
                CanvasFinding(
                    "canvas.variables_invalid",
                    "document variables must be an object",
                ),
            )
        )
    return variables


def _merge_document_variables(
    merged: dict[str, Any],
    existing: dict[str, Any],
    draft: dict[str, Any],
) -> None:
    """Merge generated theme variables without dropping consumer values."""
    generated_variables = draft.get("variables")
    if generated_variables:
        merged["variables"] = {**_existing_variables(existing), **generated_variables}


def _merge_canvas_children(
    existing: dict[str, Any],
    lifecycle: CanvasLifecycleResult,
    generated_by_id: dict[str, dict[str, Any]],
) -> list[Any]:
    """Replace matching active roots in place, then append new screens."""
    regions_by_index = {region.source_index: region for region in lifecycle.regions}
    remaining = dict(generated_by_id)
    children: list[Any] = []
    for index, child in enumerate(existing.get("children", [])):
        region = regions_by_index.get(index)
        if (
            region is not None
            and region.state is CanvasState.ACTIVE
            and region.logical_screen_id in remaining
        ):
            replacement = remaining.pop(region.logical_screen_id)
            if not region.is_legacy and isinstance(child, dict):
                # Managed replacements retain lifecycle identity and revision;
                # generation changes active content, not canvas history.
                old_penflow = child.get("penflow")
                old_lifecycle = (
                    old_penflow.get("lifecycle") if isinstance(old_penflow, dict) else None
                )
                if isinstance(old_lifecycle, dict):
                    replacement.setdefault("penflow", {})["lifecycle"] = copy.deepcopy(
                        old_lifecycle
                    )
            children.append(replacement)
        else:
            children.append(copy.deepcopy(child))
    children.extend(remaining.values())
    return children


def _screen_to_pen(screen: dict[str, Any], index: int, *, theme: dict[str, Any]) -> dict[str, Any]:
    root = screen["root"]
    viewport = screen.get("viewport", {})
    logical_screen_id = str(screen.get("screen_id") or screen.get("id") or root["semantic_id"])
    node = _semantic_node_to_pen(root, index, is_root=True, theme=theme)
    node.update(
        {
            "x": index * (int(viewport.get("width", 390)) + 80),
            "y": 0,
            "width": viewport.get("width", 390),
            "height": viewport.get("height", 844),
            "layout": "vertical",
            "gap": SCREEN_GAP if int(viewport.get("width", 390)) < 1024 else 24,
            "padding": SCREEN_PADDING,
            "alignItems": "stretch",
            "fill": theme["style"]["background"],
            "source_map": screen.get("source_map", root.get("source_map", {})),
            "penflow": {
                "lifecycle": {
                    "schema_version": 1,
                    "state": "active",
                    "logical_screen_id": logical_screen_id,
                    "revision_id": _generated_revision_id(screen, logical_screen_id),
                }
            },
        }
    )
    return node


def _generated_revision_id(screen: dict[str, Any], logical_screen_id: str) -> str:
    """Return a deterministic initial identity for a newly created region."""
    canonical_screen = json.dumps(screen, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(f"{logical_screen_id}:{canonical_screen}".encode("utf-8")).hexdigest()[
        :REVISION_DIGEST_HEX_LENGTH
    ]
    return f"{logical_screen_id}-r-{digest}"


def _semantic_node_to_pen(
    node: dict[str, Any], index: int, *, is_root: bool = False, theme: dict[str, Any]
) -> dict[str, Any]:
    role = str(node.get("role", "container"))
    semantic_id = str(node["semantic_id"])
    base = {
        "id": _node_id(semantic_id),
        "name": semantic_id,
        "context": _context_from_semantic_node(node),
        "source_map": node.get("source_map", {}),
    }
    if metadata := _semantic_metadata(node):
        base["semantic"] = metadata

    if role in {
        "screen",
        "container",
        "component",
        "form",
        "list",
        "list_item",
        "navigation",
        "tab",
    }:
        frame = {
            **base,
            "type": "frame",
            "layout": "vertical" if role != "navigation" else "horizontal",
            "gap": NODE_GAP,
            "padding": 12 if not is_root else SCREEN_PADDING,
            "alignItems": "stretch",
            "width": "fill_container" if not is_root else 390,
            "height": "fit_content(44)" if not is_root else 844,
            "fill": theme["style"]["background"] if is_root else theme["style"]["card"],
            "cornerRadius": 0 if is_root else theme["style"]["radius"],
            "children": [
                _semantic_node_to_pen(child, child_index, theme=theme)
                for child_index, child in enumerate(node.get("children", []) or [])
            ],
        }
        if not is_root:
            frame["stroke"] = _stroke(theme["style"]["border"])
        return frame
    if role == "button":
        return _button_node(base, node, theme)
    if role in {"input", "select", "toggle"}:
        return _field_node(base, node, role, theme)
    return _text_node(base, node, index, theme)


def _button_node(
    base: dict[str, Any], node: dict[str, Any], theme: dict[str, Any]
) -> dict[str, Any]:
    semantic_id = str(node["semantic_id"])
    return {
        **base,
        "type": "frame",
        "layout": "horizontal",
        "width": "fill_container",
        "height": "fit_content(44)",
        "padding": [12, 16],
        "gap": NODE_GAP,
        "alignItems": "center",
        "justifyContent": "center",
        "cornerRadius": 8,
        "fill": theme["style"]["primary"],
        "children": [
            _label_child(
                semantic_id,
                str(node.get("text") or _label_from_id(semantic_id)),
                theme["style"]["primary_foreground"],
                theme,
            )
        ],
    }


def _field_node(
    base: dict[str, Any], node: dict[str, Any], role: str, theme: dict[str, Any]
) -> dict[str, Any]:
    semantic_id = str(node["semantic_id"])
    return {
        **base,
        "type": "frame",
        "layout": "vertical",
        "width": "fill_container",
        "height": "fit_content(64)",
        "padding": 12,
        "gap": 4,
        "alignItems": "stretch",
        "cornerRadius": theme["style"]["radius"],
        "stroke": _stroke(theme["style"]["input"]),
        "fill": theme["style"]["card"],
        "children": [
            _label_child(
                semantic_id,
                str(node.get("text") or role.title()),
                theme["style"]["foreground"],
                theme,
            )
        ],
    }


def _text_node(
    base: dict[str, Any], node: dict[str, Any], index: int, theme: dict[str, Any]
) -> dict[str, Any]:
    text = {
        **base,
        "type": "text",
        "content": str(node.get("text") or _label_from_id(str(node["semantic_id"]))),
        "textGrowth": "fixed-width",
        "width": "fill_container",
        "fontSize": 24 if index == 0 else 16,
        "fontWeight": "600" if index == 0 else "400",
        "fill": theme["style"]["foreground"] if index == 0 else theme["style"]["muted_foreground"],
    }
    if theme["style"]["font_sans"]:
        text["fontFamily"] = theme["style"]["font_sans"]
    return text


def _label_child(
    parent_semantic_id: str, text: str, fill: str, theme: dict[str, Any]
) -> dict[str, Any]:
    label = {
        "id": _label_node_id(parent_semantic_id),
        "type": "text",
        "content": text,
        "fontSize": 16,
        "fontWeight": "600",
        "fill": fill,
    }
    if theme["style"]["font_sans"]:
        label["fontFamily"] = theme["style"]["font_sans"]
    return label


def _stroke(fill: str) -> dict[str, Any]:
    return {"fill": fill, "thickness": 1}


def _context_from_semantic_node(node: dict[str, Any]) -> str:
    keys = ("semantic_id", "role", "intent", "binding", "repeat", "entity", "test_id")
    return format_context_string({key: node[key] for key in keys if node.get(key)})


def _semantic_metadata(node: dict[str, Any]) -> dict[str, Any]:
    keys = ("states", "validations", "side_effects")
    return {key: node[key] for key in keys if node.get(key)}


def _node_id(semantic_id: str) -> str:
    parts = [part for part in semantic_id.replace("_", "-").replace(".", "-").split("-") if part]
    raw = "".join(part[:1].upper() + part[1:] for part in parts)
    return raw[:1].lower() + raw[1:] if raw else "node"


def _label_node_id(parent_semantic_id: str) -> str:
    return _node_id(f"{parent_semantic_id.rsplit('.', 1)[-1]}.label")


def _label_from_id(semantic_id: str) -> str:
    return semantic_id.rsplit(".", 1)[-1].replace("_", " ").replace("-", " ").title()


def _has_errors(issues: list[dict[str, Any]]) -> bool:
    return any(issue.get("severity") == "error" for issue in issues)
