"""Emit existing C44 receipts from real captured click and resulting UI state."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from convert_observations import file_ref


def state(snapshot: dict) -> dict:
    """Use the visible result text as the independently observed state value."""
    result = next(node for node in snapshot["nodes"] if node["semantic_id"] == "checkout.result")
    return {"screen": snapshot["screen_id"], "state": snapshot["state"], "value": result["text"]}


def convert(contract_path: Path, evidence: Path, workspace: Path, project: Path) -> list[Path]:
    """Bind distinct actual success/error captures without copying declared destinations."""
    contract = json.loads(contract_path.read_text())
    mapping = {"payment_success": "save", "payment_error": "storage_error"}
    receipt_dir = workspace / "causal-receipts"
    if receipt_dir.is_symlink():
        raise ValueError("causal receipt destination is a symlink")
    if receipt_dir.exists():
        receipt_dir.rename(evidence.parent / "previous-causal-receipts")
    receipt_dir.mkdir()
    observations, runs, paths = [], [], []
    adapter = {"name": "penflow-test-payment-browser", "version": "1"}
    for transition in contract["transitions"]:
        if not transition.get("causal"):
            continue
        scenario = mapping.get(transition["id"])
        if scenario is None:
            raise ValueError(f"BLOCKED: no actual causal capture for {transition['id']}")
        raw = json.loads((evidence / f"{scenario}.browser.json").read_text())
        (action,) = [event for event in raw["actions"] if event["semantic_id"] == "checkout.pay"]
        node = next(
            node
            for node in action["snapshot"]["nodes"]
            if node["semantic_id"] == action["semantic_id"]
        )
        if not action["is_trusted"] or not node["visible"]:
            raise ValueError("causal action was not actually visible and browser dispatched")
        pre, post = state(action["snapshot"]), state(raw["after"])
        observed_action = {
            "id": action["action_id"],
            "test_id": action["test_id"],
            "event": action["event"],
            "visible": node["visible"],
        }
        outcome = raw["network"]["response"]["body"]["outcome"]
        identifier = f"{scenario}-causal"
        capture = {
            "kind": "runtime-event",
            "action": observed_action,
            "pre_state": pre,
            "post_state": post,
            "destination": {"screen": post["screen"], "state": post["state"]},
            "outcome": outcome,
        }
        receipt = {
            "kind": "penflow-causal-runtime-receipt",
            "version": 1,
            "run_id": raw["session_id"],
            "transition_id": transition["id"],
            "observation_id": identifier,
            "outcome": outcome,
            "adapter": adapter,
            "surface": "web-desktop",
            "capture": capture,
        }
        path = receipt_dir / f"{scenario}.json"
        path.write_text(json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False) + "\n")
        paths.append(path)
        observations.append(
            {
                "id": identifier,
                "transition_id": transition["id"],
                "run_id": raw["session_id"],
                **{key: value for key, value in capture.items() if key != "kind"},
                "evidence": [
                    {
                        "id": f"{scenario}-receipt",
                        "run_id": raw["session_id"],
                        "kind": "runtime-event",
                        "path": str(path.relative_to(workspace)),
                        "sha256": file_ref(path, project)["sha256"],
                    }
                ],
            }
        )
        runs.append({"id": raw["session_id"], "adapter": adapter, "surface": "web-desktop"})
    if not observations:
        return []
    bundle = {
        "kind": "penflow-causal-transition-evidence",
        "version": 1,
        "contract": {
            "id": contract["contract_id"],
            "version": contract["version"],
            "sha256": hashlib.sha256(contract_path.read_bytes()).hexdigest(),
        },
        "runs": runs,
        "observations": observations,
    }
    path = workspace / "causal-transition-evidence.json"
    if path.is_symlink():
        raise ValueError("causal evidence destination is a symlink")
    if path.exists():
        path.rename(evidence.parent / "previous-causal-transition-evidence.json")
    path.write_text(json.dumps(bundle, indent=2, sort_keys=True, allow_nan=False) + "\n")
    return [path, *paths]
