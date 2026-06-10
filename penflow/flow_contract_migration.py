# @spec(FR-010)
"""Explicit one-time migration from Markdown flow specs to v2 contract JSON."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml


# @spec FR-010: Explicit migration — .specs/features/045-penflow-json-only-strict-contract-v2/spec.md#fr-010
def migrate_flow_md_to_contract_json(specs_dir: str | Path, out_path: str | Path) -> dict[str, Any]:
    """Convert legacy Markdown specs to review-blocked v2 JSON.

    The normal strict pipeline never calls this helper implicitly; operators invoke
    it explicitly and must resolve `needs_clarification` before validation passes.
    """
    root = Path(specs_dir)
    flows = [_frontmatter(path) for path in sorted((root / "flows").glob("*.md"))]
    screens = [_frontmatter(path) for path in sorted((root / "screens").glob("*.md"))]
    flow_ids = [str(flow.get("flow") or flow.get("id") or "flow") for flow in flows]
    screen_ids = [str(screen.get("screen") or screen.get("id") or "screen") for screen in screens]
    first_flow = flow_ids[0] if flow_ids else "flow"
    first_screen = screen_ids[0] if screen_ids else first_flow
    contract = {
        "version": 2,
        "kind": "penflow-flow-contract",
        "contract_id": f"{first_flow}-contract",
        "actors": [{"id": "actor", "name": "Actor"}],
        "entities": [{"id": first_screen, "fields": [{"id": "title", "type": "string"}]}],
        "screens": [
            {
                "id": screen_id,
                "flow_id": first_flow,
                "title": screen_id.replace("-", " ").title(),
                "surface": "web",
                "viewport": {"width": 1440, "height": 900},
                "states": [{"id": "default"}],
                "root_node": f"{screen_id}.root",
            }
            for screen_id in screen_ids
        ],
        "nodes": [
            {
                "id": f"{screen_id}.root",
                "screen_id": screen_id,
                "semantic_id": screen_id,
                "role": "screen",
                "children": [],
            }
            for screen_id in screen_ids
        ],
        "guards": [],
        "permissions": [],
        "mutations": [],
        "actions": [],
        "flows": [{"id": first_flow, "entry_screen": first_screen}],
        "transitions": [],
        "needs_review": True,
        "needs_clarification": [
            "Review migrated actors, actions, permissions, mutations, guards, and transitions."
        ],
    }
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "status": "PASS",
        "out": str(out),
        "needs_review": True,
        "needs_clarification": contract["needs_clarification"],
    }


def _frontmatter(path: Path) -> dict[str, Any]:
    content = path.read_text(encoding="utf-8")
    if not content.startswith("---\n"):
        return {}
    end = content.find("\n---\n", 4)
    if end == -1:
        return {}
    data = yaml.safe_load(content[4:end])
    return data if isinstance(data, dict) else {}
