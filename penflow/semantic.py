# @spec(FR-005)
"""Flow-ui-contract Markdown to semantic UI tree export."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from .flow_contract import (
    FlowContractValidationError,
)

# Re-export the established API so callers keep their existing import path.
from .semantic_contract import semantic_tree_from_contract as semantic_tree_from_contract

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
SECTION_RE = re.compile(r"^(## .+)$", re.MULTILINE)
HEADING_RE = re.compile(r"^# .+$", re.MULTILINE)


def semantic_tree_from_specs(specs_dir: str | Path) -> dict[str, Any]:
    """Build a deterministic semantic UI tree from flow-ui-contract Markdown specs.

    Args:
        specs_dir: Directory containing `flows/*.md` and `screens/*.md`.

    Returns:
        The semantic UI tree dictionary. The caller owns validation and persistence.

    Raises:
        FileNotFoundError: If the specs directory or required child directories are absent.
        ValueError: If no flow or screen specs are found.
    """
    root = Path(specs_dir)
    flows_dir = root / "flows"
    screens_dir = root / "screens"
    if not flows_dir.is_dir():
        raise FileNotFoundError(f"flows directory not found: {flows_dir}")
    if not screens_dir.is_dir():
        raise FileNotFoundError(f"screens directory not found: {screens_dir}")

    flow_files = sorted(flows_dir.glob("*.md"))
    screen_files = sorted(screens_dir.glob("*.md"))
    if not flow_files:
        raise ValueError(f"no flow specs found in {flows_dir}")
    if not screen_files:
        raise ValueError(f"no screen specs found in {screens_dir}")

    screens = [_screen_from_markdown(path) for path in screen_files]
    screens_by_flow = _group_screens_by_flow(screens)
    flows = [
        _flow_from_markdown(path, screens_by_flow.get(_frontmatter(path)["flow"], []))
        for path in flow_files
    ]

    return {
        "version": 1,
        "kind": "semantic-ui-tree",
        "tree_id": root.name,
        "source": {"notes": ["Generated deterministically from flow-ui-contract Markdown specs."]},
        "flows": flows,
        "screens": screens,
    }


def write_semantic_tree(specs_dir: str | Path, out_path: str | Path) -> dict[str, Any]:
    # @spec FR-005: Contract path dispatch for strict v2 export — .specs/features/045-penflow-json-only-strict-contract-v2/spec.md#fr-005
    """Write a strict v2 semantic UI tree JSON file.

    Args:
        specs_dir: Either `flow-ui-contract/contract.json` or a directory containing it.
        out_path: Destination `semantic-ui-tree.json` path.

    Returns:
        The generated semantic UI tree.
    """
    source = Path(specs_dir)
    contract_path = source if source.name == "contract.json" else source / "contract.json"
    if contract_path.is_file():
        tree = semantic_tree_from_contract(contract_path)
    else:
        raise FlowContractValidationError(f"contract.json is required: {contract_path}")
    Path(out_path).write_text(json.dumps(tree, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return tree


def _flow_from_markdown(path: Path, screens: list[dict[str, Any]]) -> dict[str, Any]:
    frontmatter, content = _parse_markdown(path)
    flow_id = str(frontmatter["flow"])
    screen_ids = [screen["id"] for screen in screens]
    mockups = [str(item) for item in frontmatter.get("mockups", [])]
    entry_screen = screen_ids[0] if screen_ids else (mockups[0] if mockups else flow_id)
    return {
        "id": flow_id,
        "title": str(frontmatter.get("title") or _title_from_h1(content) or flow_id),
        "priority": str(frontmatter.get("priority", "P3")),
        "entry_screen": entry_screen,
        "steps": [
            {
                "id": _slug(f"{screen_id}-step"),
                "screen_id": screen_id,
                "intent": _slug(screen_id),
                "actor": _header_value(content, "Primary Actor"),
            }
            for screen_id in screen_ids
        ],
        "transitions": _transitions_from_flow(content, entry_screen),
        "source_map": {
            "flow_spec": _posix(path),
            "notes": ["section: frontmatter", "section: ## User Scenarios & Testing"],
        },
    }


def _screen_from_markdown(path: Path) -> dict[str, Any]:
    frontmatter, content = _parse_markdown(path)
    screen_id = str(frontmatter["screen"])
    surface = _surface_from_frontmatter(frontmatter, screen_id)
    viewport = _viewport_from_frontmatter(frontmatter, surface)
    sections = _sections(content)
    data_nodes = _data_nodes(screen_id, sections.get("## Données affichées", ""), path)
    action_nodes = _action_nodes(screen_id, sections.get("## Actions", ""), path)
    states = [{"name": state} for state in _split_states(sections.get("## États UI", ""))]
    validations = _validations(sections.get("## Validations", ""))
    side_effects = _side_effects(sections.get("## Side effects locaux", ""))

    return {
        "id": screen_id,
        "flow_id": str(frontmatter["flow"]),
        "surface": surface,
        "viewport": viewport,
        "states": states,
        "validations": validations,
        "side_effects": side_effects,
        "source_map": {
            "screen_spec": _posix(path),
            "mockup": str(frontmatter.get("mockup", "")),
            "pencil_node_id": frontmatter.get("sourceNodeId"),
            "notes": ["section: frontmatter"],
        },
        "root": {
            "semantic_id": screen_id,
            "role": "screen",
            "states": states,
            "validations": validations,
            "side_effects": side_effects,
            "source_map": {
                "screen_spec": _posix(path),
                "mockup": str(frontmatter.get("mockup", "")),
                "pencil_node_id": frontmatter.get("sourceNodeId"),
                "notes": ["section: # Écran"],
            },
            "children": data_nodes + action_nodes,
        },
    }


def _parse_markdown(path: Path) -> tuple[dict[str, Any], str]:
    content = path.read_text(encoding="utf-8")
    match = FRONTMATTER_RE.match(content)
    if not match:
        raise ValueError(f"missing YAML frontmatter: {path}")
    frontmatter = yaml.safe_load(match.group(1))
    if not isinstance(frontmatter, dict):
        raise TypeError(f"frontmatter must be a mapping: {path}")
    return frontmatter, content


def _frontmatter(path: Path) -> dict[str, Any]:
    return _parse_markdown(path)[0]


def _sections(content: str) -> dict[str, str]:
    matches = list(SECTION_RE.finditer(content))
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(content)
        sections[match.group(1)] = content[start:end].strip()
    return sections


def _data_nodes(screen_id: str, section: str, path: Path) -> list[dict[str, Any]]:
    nodes = []
    for item in _bullet_items(section):
        semantic_id = f"{screen_id}.{_slug(item)}"
        nodes.append(
            {
                "semantic_id": semantic_id,
                "role": "text",
                "text": item,
                "binding": f"{screen_id}.{_slug(item).replace('-', '_')}",
                "entity": screen_id,
                "source_map": {
                    "screen_spec": _posix(path),
                    "notes": ["section: ## Données affichées"],
                },
            }
        )
    return nodes


def _action_nodes(screen_id: str, section: str, path: Path) -> list[dict[str, Any]]:
    nodes = []
    for element, role, effect in _action_rows(section):
        if _is_non_visual_transition_action(element, role):
            continue
        slug = _slug(element)
        nodes.append(
            {
                "semantic_id": f"{screen_id}.{slug}",
                "role": _role_from_action_type(role),
                "text": element,
                "intent": _slug(effect or element),
                "entity": _entity_from_effect(effect),
                "validations": _action_validations(effect),
                "side_effects": [{"effect": _slug(effect), "target": _entity_from_effect(effect)}],
                "source_map": {
                    "screen_spec": _posix(path),
                    "notes": ["section: ## Actions"],
                },
            }
        )
    return nodes


def _group_screens_by_flow(screens: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for screen in screens:
        grouped.setdefault(screen["flow_id"], []).append(screen)
    for flow_screens in grouped.values():
        flow_screens.sort(key=lambda item: item["id"])
    return grouped


def _surface_from_frontmatter(frontmatter: dict[str, Any], screen_id: str) -> str:
    for key in ("platform", "surface"):
        value = frontmatter.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return _surface_from_screen(screen_id)


def _viewport_from_frontmatter(frontmatter: dict[str, Any], surface: str) -> dict[str, int]:
    value = frontmatter.get("viewport")
    if isinstance(value, dict):
        width = value.get("width")
        height = value.get("height")
        if isinstance(width, int | float) and isinstance(height, int | float):
            return {"width": int(width), "height": int(height)}
    if isinstance(value, str):
        match = re.match(r"^\s*(\d+)\s*x\s*(\d+)\s*$", value)
        if match:
            return {"width": int(match.group(1)), "height": int(match.group(2))}
    if surface == "web-desktop":
        return {"width": 1440, "height": 900}
    return {"width": 390, "height": 844}


def _transitions_from_flow(content: str, entry_screen: str) -> list[dict[str, str]]:
    transitions = []
    mermaid = re.search(r"```mermaid\n(.*?)```", content, re.DOTALL)
    if mermaid:
        for line in mermaid.group(1).splitlines():
            if "--" in line and "-->" in line:
                transitions.append(
                    {"from": entry_screen, "to": entry_screen, "trigger": _slug(line.strip())}
                )
    return transitions


def _bullet_items(section: str) -> list[str]:
    items = []
    for line in section.splitlines():
        stripped = line.strip()
        if stripped.startswith("- ") and not stripped.startswith("- **"):
            items.append(stripped[2:].strip())
    return items


def _action_rows(section: str) -> list[tuple[str, str, str]]:
    rows = []
    for line in section.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or "---" in stripped or "Élément" in stripped:
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) >= 3:
            rows.append((_clean_label(cells[0]), cells[1], cells[2]))
    return rows


def _split_states(section: str) -> list[str]:
    first_content_line = next(
        (
            line.strip()
            for line in section.splitlines()
            if line.strip() and not line.startswith("<!--")
        ),
        "default",
    )
    return [_slug(part.strip()) for part in first_content_line.split("·") if part.strip()]


def _validations(section: str) -> list[dict[str, str]]:
    return [{"rule": _slug(item), "message": item} for item in _bullet_items(section)]


def _side_effects(section: str) -> list[dict[str, str]]:
    return [{"effect": _slug(item), "when": item} for item in _bullet_items(section)]


def _action_validations(effect: str) -> list[dict[str, str]]:
    if "POST" not in effect.upper():
        return []
    return [{"rule": "required-inputs-present", "source": effect}]


def _role_from_action_type(action_type: str) -> str:
    normalized = _slug(action_type).replace("-", "_")
    return {"tap": "component", "button": "button", "link": "link", "input": "input"}.get(
        normalized, "button"
    )


def _is_non_visual_transition_action(element: str, action_type: str) -> bool:
    element_slug = _slug(element)
    action_slug = _slug(action_type)
    non_visual_elements = {
        "escape-key",
        "esc-key",
        "backdrop",
        "backdrop-click",
        "click-backdrop",
    }
    non_visual_types = {"keyboard-event", "flow-transition"}
    return element_slug in non_visual_elements or action_slug in non_visual_types


def _entity_from_effect(effect: str) -> str:
    match = re.search(r"/([a-zA-Z0-9_-]+)", effect)
    if match:
        return match.group(1).replace("-", "_")
    words = _slug(effect).split("-")
    return words[0] if words and words[0] else "ui"


def _surface_from_screen(screen_id: str) -> str:
    prefix = screen_id.split("_", 1)[0].split("-", 1)[0]
    return prefix if prefix in {"mobile", "web", "landing", "showcase", "admin"} else "web"


def _header_value(content: str, label: str) -> str:
    match = re.search(rf"^- \*\*{re.escape(label)}:\*\*\s*(.+)$", content, re.MULTILINE)
    return match.group(1).strip() if match else ""


def _title_from_h1(content: str) -> str:
    match = HEADING_RE.search(content)
    if not match:
        return ""
    return match.group(0).split(":", 1)[-1].strip()


def _clean_label(value: str) -> str:
    return value.replace('"', "").replace("«", "").replace("»", "").strip()


def _slug(value: str) -> str:
    normalized = value.lower()
    normalized = re.sub(r"[^a-z0-9]+", "-", normalized)
    return normalized.strip("-") or "item"


def _posix(path: Path) -> str:
    return path.as_posix()
