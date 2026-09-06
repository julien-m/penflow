"""Validate dedicated system navigation without fabricated business actions."""

from typing import Any

from .contract_records import contract_issue


def validate_system_returns(contract: dict[str, Any]) -> list[dict[str, Any]]:
    """Require unique event identities and real owning/destination screens."""
    issues = []
    ids = {action["id"] for action in contract["actions"]}
    screens = {screen["id"]: screen for screen in contract["screens"]}
    for index, item in enumerate(contract.get("system_returns", [])):
        path = f"$.system_returns[{index}]"
        if item["id"] in ids:
            issues.append(
                contract_issue(
                    "error",
                    "contract.system_return.identity",
                    path,
                    "system event IDs must be unique and disjoint from actions",
                )
            )
        ids.add(item["id"])
        if item["screen_id"] not in screens:
            issues.append(
                contract_issue(
                    "error",
                    "contract.system_return.screen",
                    path,
                    "system return owner must be an existing screen",
                )
            )
        destination = item["destination"]
        if destination["kind"] == "screen":
            target = screens.get(destination["screen_id"])
            if target is None or destination["state"] not in {
                state["id"] for state in target["states"]
            }:
                issues.append(
                    contract_issue(
                        "error",
                        "contract.system_return.destination",
                        path,
                        "destination screen/state does not exist",
                    )
                )
        if item["event"] in {"close", "exit"} and destination["kind"] != "closed":
            issues.append(
                contract_issue(
                    "error",
                    "contract.system_return.event",
                    path,
                    "close/exit require disappearance of the owning surface",
                )
            )
        if destination["kind"] == "history" and item["event"] != "back":
            issues.append(
                contract_issue(
                    "error",
                    "contract.system_return.event",
                    path,
                    "only back can consume observed history",
                )
            )
    return issues
