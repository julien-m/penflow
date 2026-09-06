"""Produce C12 and its state index solely from captured DOM and typed observations."""

from __future__ import annotations

import json
import shutil
from copy import deepcopy
from pathlib import Path
from typing import Any

from convert_observations import file_ref
from observation_facts import ui


def screen(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Preserve measured semantic hierarchy rather than looking up an expected tree."""
    nodes = {}
    for raw in snapshot["nodes"]:
        key = raw["semantic_id"]
        if key in nodes:
            raise ValueError(f"duplicate captured semantic ID: {key}")
        nodes[key] = {
            field: deepcopy(raw[field])
            for field in ("id", "semantic_id", "role", "bbox", "text", "visual", "context")
        }
        nodes[key]["children"] = []
    roots = []
    for raw in snapshot["nodes"]:
        if raw["parent_semantic_id"] is None:
            roots.append(nodes[raw["semantic_id"]])
        else:
            nodes[raw["parent_semantic_id"]]["children"].append(nodes[raw["semantic_id"]])
    if len(roots) != 1:
        raise ValueError("capture must contain exactly one actual screen root")
    return {"screen_id": snapshot["screen_id"], "viewport": snapshot["viewport"], "root": roots[0]}


def state_index(
    evidence: Path, project: Path, identity: dict[str, str]
) -> tuple[list[dict[str, Any]], list[Path]]:
    """Index authentic UI witnesses without inventing actions for static screens."""
    index: dict[tuple[str, str], dict[str, Any]] = {}
    paths = []
    for path in sorted(evidence.glob("*.browser.json")):
        capture = json.loads(path.read_text())
        for side in ("before", "after"):
            snapshot = capture[side]
            if "nodes" not in snapshot:
                continue
            facts = ui(snapshot, snapshot["screen_id"])
            key = (facts["screen_id"], facts["state"])
            witness = {
                "kind": "penflow-runtime-ui-snapshot",
                "version": 1,
                **identity,
                "scenario_id": capture["scenario_id"],
                "session_id": capture["session_id"],
                "facts": facts,
                "raw_evidence": [file_ref(path, project)],
            }
            witness_path = evidence / f"{capture['scenario_id']}.{side}.ui-snapshot.json"
            witness_path.write_text(
                json.dumps(witness, indent=2, sort_keys=True, allow_nan=False) + "\n"
            )
            paths.append(witness_path)
            index.setdefault(
                key,
                {
                    "screen_id": key[0],
                    "state": key[1],
                    "scenario_id": capture["scenario_id"],
                    "session_id": capture["session_id"],
                    "evidence": file_ref(witness_path, project),
                },
            )
    return [index[key] for key in sorted(index)], paths


def convert(evidence: Path, workspace: Path, project: Path, identity: dict[str, str]) -> list[Path]:
    """Publish independently observed default screens and source-linked dynamic states."""
    captures = [
        json.loads((evidence / f"{scenario}.browser.json").read_text())
        for scenario in ("save", "back", "close")
    ]
    states, _ = state_index(evidence, project, identity)
    tree = {
        "version": 1,
        "screens": [screen(raw["before"]) for raw in captures],
        "observed_states": states,
    }
    output = workspace / "actual-ui-tree.json"
    if output.is_symlink():
        raise ValueError("actual tree destination is a symlink")
    if output.exists():
        shutil.copyfile(output, evidence.parent / "previous-actual-ui-tree.json")
    output.write_text(json.dumps(tree, indent=2, sort_keys=True, allow_nan=False) + "\n")
    provenance = {
        "kind": "penflow-actual-provenance",
        "version": 1,
        "sourceKind": "runtime-capture",
        "producer": {"name": "penflow-test-payment-browser", "version": "1"},
        "capturedAt": max(raw["captured_at"] for raw in captures),
        "target": {"surface": "web-desktop"},
        "content": {"path": output.name, "sha256": file_ref(output, project)["sha256"]},
    }
    receipt = workspace / "actual-ui-tree.provenance.json"
    if receipt.is_symlink():
        raise ValueError("actual provenance destination is a symlink")
    if receipt.exists():
        shutil.copyfile(receipt, evidence.parent / "previous-actual-ui-tree.provenance.json")
    receipt.write_text(json.dumps(provenance, indent=2, sort_keys=True) + "\n")
    return [output, receipt]
