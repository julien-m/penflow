"""Serialize this test application's measured outcomes, without importing test fixtures."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from observation_facts import guard_trace, navigation, network, storage_facts, ui

SCENARIO_BY_OBLIGATION = {
    "action:submit_payment:allowed": "save",
    "action:edit_amount:allowed": "edit",
    "permission:buyer_can_pay:submit_payment:allowed": "save",
    "permission:buyer_can_pay:submit_payment:denied": "denied",
    "validation:payment_ready:submit_payment:allowed": "save",
    "validation:payment_ready:submit_payment:invalid": "storage_error",
    "validation:payment_failed:submit_payment:allowed": "storage_error",
    "validation:payment_failed:submit_payment:invalid": "save",
    "validation:payment_input_valid:submit_payment:allowed": "save",
    "validation:payment_input_valid:submit_payment:invalid": "invalid",
    "effect:create_payment:submit_payment:success": "save",
    "effect:create_payment:submit_payment:error": "storage_error",
    "result:create_payment:submit_payment:success": "save",
    "result:create_payment:submit_payment:error": "storage_error",
    "transition:payment_success": "save",
    "transition:payment_error": "storage_error",
    "system-return:details_back": "back",
    "system-return:receipt_close": "close",
    "persist-payment": "save",
    "persist-payment-idempotent": "idempotent",
}


def file_ref(path: Path, project: Path) -> dict[str, str]:
    """Bind serialized facts to retained raw evidence within caller scope."""
    return {
        "path": str(path.resolve().relative_to(project)),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def facts(identifier: str, category: str, raw: dict, stored: dict) -> tuple[dict, dict, dict, str]:
    """Derive values from measured events; obligation IDs only select the observation."""
    action = "edit_amount" if raw["scenario_id"] == "edit" else "submit_payment"
    semantic = "checkout.amount" if action == "edit_amount" else "checkout.pay"
    actor = raw["actor_id"]
    result = {"actor_id": actor, "action_id": action, "outcome": "allowed"}
    if identifier.startswith("system-return:"):
        result["action_id"] = identifier.split(":", 1)[1]
        before, after = navigation(raw, result["action_id"])
        reached = (
            after["navigation"]["url"] == before["navigation"]["previous_url"]
            if raw["scenario_id"] == "back"
            else not after["navigation"]["surface_present"]
        )
        result["outcome"] = "success" if reached else "error"
        return before, after, result, "ui"
    if category == "persistence":
        result.update(
            outcome=raw["network"]["response"]["body"]["outcome"],
            readback=storage_facts(stored["readback"]),
            restart=stored["restart"],
        )
        return storage_facts(stored["before"]), storage_facts(stored["after"]), result, "storage"
    if category == "effect":
        before, after = network(raw)
        result.update(actor_id=before["actor_id"], outcome=after["body"]["outcome"])
        return before, after, result, "network"
    before, after = ui(raw["before"], semantic), ui(raw["after"], semantic)
    if category in {"transition", "result"}:
        result["outcome"] = raw["network"]["response"]["body"]["outcome"]
        if category == "result":
            after = ui(raw["after"], "checkout.result")
    elif category == "validation":
        guard_id = identifier.split(":")[1]
        if guard_id == "payment_input_valid":
            result["outcome"] = (
                "allowed" if before["properties"]["payment_input"] == "valid" else "invalid"
            )
        else:
            before, result["outcome"] = guard_trace(raw, guard_id)
    elif category == "permission" and raw["scenario_id"] == "denied":
        result["outcome"] = ui(raw["after"], "checkout.result")["text"]
    else:
        # This application accepts only observed local edits or an actual submitted request.
        observed = (
            before["value"] != after["value"]
            if action == "edit_amount"
            else raw["network"] is not None
        )
        result["outcome"] = "allowed" if observed else "error"
    return before, after, result, "ui"


def convert(
    contract_path: Path, evidence: Path, output: Path, project: Path, build_id: str, invocation: str
) -> list[Path]:
    """Write all supported functional outcomes and refuse unknown or missing captures."""
    contract = json.loads(contract_path.read_text())
    contract_sha = hashlib.sha256(contract_path.read_bytes()).hexdigest()
    output.mkdir(parents=True, exist_ok=False)
    paths = []
    for expected in contract["outcome_expectations"]:
        if expected["category"] == "structure":
            continue
        identifier = expected["obligation_id"]
        scenario = SCENARIO_BY_OBLIGATION.get(identifier)
        if scenario is None:
            raise ValueError(f"BLOCKED: no captured scenario adapter for {identifier}")
        raw_path, storage_path = (
            evidence / f"{scenario}.browser.json",
            evidence / f"{scenario}.storage.json",
        )
        raw, stored = json.loads(raw_path.read_text()), json.loads(storage_path.read_text())
        if (
            any(item["scenario_id"] != scenario for item in (raw, stored))
            or raw["session_id"] != stored["session_id"]
        ):
            raise ValueError("BLOCKED: browser/storage scenario or session identity differs")
        before, after, result, capability = facts(identifier, expected["category"], raw, stored)
        node = next(
            (
                node
                for node in raw["before"]["nodes"]
                if node["context"].get("action") == result["action_id"]
            ),
            None,
        )
        if node is None and not identifier.startswith("system-return:"):
            raise ValueError(f"BLOCKED: action {result['action_id']} was not mapped in actual DOM")
        semantic = node["semantic_id"] if node else raw["before"]["screen_id"]
        observation = {
            "kind": "penflow-outcome-observation",
            "version": 1,
            "contract_sha256": contract_sha,
            "build_id": build_id,
            "producer_invocation_id": invocation,
            "scenario_id": scenario,
            "session_id": raw["session_id"],
            "obligation_id": identifier,
            "screen_id": raw["before"]["screen_id"],
            "semantic_id": semantic,
            "instance_key": None,
            "category": expected["category"],
            "capability": capability,
            "before": before,
            "after": after,
            "result": result,
            "evidence": file_ref(storage_path if capability == "storage" else raw_path, project),
        }
        measured = {
            key: value
            for key, value in observation.items()
            if key not in {"kind", "category", "obligation_id", "evidence"}
        }
        measured.update(
            kind="penflow-runtime-facts",
            raw_evidence=[file_ref(raw_path, project), file_ref(storage_path, project)],
        )
        measured_path = evidence / f"{identifier.replace(':', '--')}.facts.json"
        measured_path.write_text(
            json.dumps(measured, indent=2, sort_keys=True, allow_nan=False) + "\n"
        )
        observation["evidence"] = file_ref(measured_path, project)
        path = output / f"{identifier.replace(':', '--')}.json"
        path.write_text(json.dumps(observation, indent=2, sort_keys=True, allow_nan=False) + "\n")
        paths.append(path)
    return paths
