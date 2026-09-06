# @spec(FR-002)
# @spec(FR-003)
"""Strict v2 JSON flow contract loading and validation."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .contract_references import validate_references
from .contract_records import (
    record_items,
    records_by_id,
    has_errors,
    contract_issue,
    interactive_binding_kind,
)
from .schema_cache import validator_for
from .contract_graph import validate_containment
from .contract_system_returns import validate_system_returns

ID_RE = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$")
BINDING_RE = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
INTERACTIVE_ROLES = {"button", "link", "input", "select", "toggle", "form", "component"}
VISUALLY_INTERACTIVE_ROLES = {"button", "link", "input"}
HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}
NON_CAUSAL_GUARD_VARIABLES = {
    "destination",
    "entry_state",
    "from_screen",
    "target_screen",
    "to_screen",
    "to_state",
}
CAUSAL_TRANSITION_FIELDS = ("kind", "label", "causal")
SCHEMA_PATH = Path(__file__).parent / "schemas" / "flow-contract-v2.schema.json"


class FlowContractValidationError(ValueError):
    """Raised when a strict v2 flow contract fails validation."""


def load_flow_contract_v2(path: str | Path) -> dict[str, Any]:
    """Load a v2 `flow-ui-contract/contract.json` document."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


# @spec FR-001: Strict schema, FR-003: References — .specs/features/045-penflow-json-only-strict-contract-v2/spec.md#fr-001
def validate_flow_contract_v2(contract: Any) -> list[dict[str, Any]]:
    """Validate a strict v2 contract with closed schema and referential checks."""
    issues: list[dict[str, Any]] = []
    if not isinstance(contract, dict):
        return [contract_issue("error", "contract.schema.type", "$", "contract must be object")]
    _validate_schema(contract, issues)
    if not has_errors(issues):
        validate_references(
            contract, contract_registries(contract), _transition_triggers(contract), issues
        )
        _interactive_screen_coverage_issues(contract, issues)
        issues.extend(validate_containment(contract))
        issues.extend(validate_system_returns(contract))
    return sorted(issues, key=lambda issue: (issue["path"], issue["code"], issue["message"]))


def interactive_coverage_report(contract: Any) -> dict[str, Any]:
    """Return per-screen interactive action coverage for a strict v2 contract."""
    if not isinstance(contract, dict):
        return {"screens": [], "summary": {"covered": 0, "static": 0, "total": 0, "uncovered": 0}}
    transition_triggers = _transition_triggers(contract)
    screens = []
    for screen in record_items(contract, "screens"):
        screen_id = str(screen.get("id", ""))
        actions = []
        for node in record_items(contract, "nodes"):
            if (
                node.get("screen_id") != screen_id
                or node.get("role") not in VISUALLY_INTERACTIVE_ROLES
            ):
                continue
            binding_kind = interactive_binding_kind(node, transition_triggers)
            if binding_kind is None:
                continue
            actions.append(
                {
                    "node": str(node.get("id")),
                    "semantic_id": str(node.get("semantic_id")),
                    "role": str(node.get("role")),
                    "binding": binding_kind,
                }
            )
        static = screen.get("static") is True
        static_reason = screen.get("static_reason")
        is_static_justified = (
            static and isinstance(static_reason, str) and bool(static_reason.strip())
        )
        status = "covered" if actions else "static" if is_static_justified else "uncovered"
        screens.append(
            {
                "screen_id": screen_id,
                "interactive_actions": actions,
                "static": static,
                "static_reason": static_reason if isinstance(static_reason, str) else None,
                "status": status,
                "root_node": screen.get("root_node"),
            }
        )
    return {
        "screens": screens,
        "summary": {
            "covered": sum(1 for screen in screens if screen["status"] == "covered"),
            "static": sum(1 for screen in screens if screen["status"] == "static"),
            "total": len(screens),
            "uncovered": sum(1 for screen in screens if screen["status"] == "uncovered"),
        },
    }


def contract_registries(contract: dict[str, Any]) -> dict[str, Any]:
    """Return id registries used by downstream artifact validators."""
    nodes = records_by_id(contract, "nodes")
    return {
        "actors": records_by_id(contract, "actors"),
        "entities": records_by_id(contract, "entities"),
        "screens": records_by_id(contract, "screens"),
        "nodes": nodes,
        "guards": records_by_id(contract, "guards"),
        "permissions": records_by_id(contract, "permissions"),
        "mutations": records_by_id(contract, "mutations"),
        "actions": records_by_id(contract, "actions"),
        "flows": records_by_id(contract, "flows"),
        "transitions": records_by_id(contract, "transitions"),
        "relations": records_by_id(contract, "relations"),
        "semantic_ids": {
            str(node["semantic_id"]): node
            for node in nodes.values()
            if isinstance(node.get("semantic_id"), str)
        },
        "test_ids": {
            str(node["test_id"]): node
            for node in nodes.values()
            if isinstance(node.get("test_id"), str)
        },
        "fields": {
            f"{entity['id']}.{field['id']}"
            for entity in record_items(contract, "entities")
            for field in entity.get("fields", []) or []
            if isinstance(field, dict) and isinstance(field.get("id"), str)
        },
    }


def _validate_schema(contract: dict[str, Any], issues: list[dict[str, Any]]) -> None:
    for error in validator_for(SCHEMA_PATH.name).iter_errors(contract):
        path = "$" + "".join(
            f"[{part}]" if isinstance(part, int) else f".{part}" for part in error.absolute_path
        )
        keyword = (
            "additional_property" if error.validator == "additionalProperties" else error.validator
        )
        if error.validator == "additionalProperties":
            for key in sorted(set(error.instance) - set(error.schema.get("properties", {}))):
                issues.append(
                    contract_issue(
                        "error", f"contract.schema.{keyword}", f"{path}.{key}", error.message
                    )
                )
        elif error.validator == "required":
            for key in error.validator_value:
                if key not in error.instance:
                    issues.append(
                        contract_issue(
                            "error", f"contract.schema.{keyword}", f"{path}.{key}", error.message
                        )
                    )
        else:
            issues.append(
                contract_issue("error", f"contract.schema.{keyword}", path, error.message)
            )


def _interactive_screen_coverage_issues(
    contract: dict[str, Any], issues: list[dict[str, Any]]
) -> None:
    coverage = interactive_coverage_report(contract)
    for index, screen in enumerate(coverage["screens"]):
        if screen["status"] != "uncovered":
            continue
        path = f"$.screens[{index}]"
        message = "screen requires a mapped interactive action or static justification"
        if screen["static"] is True:
            path = f"{path}.static_reason"
            message = "static screen justification must be a non-empty static_reason"
        issues.append(contract_issue("error", "contract.interactive_unbound", path, message))


def _transition_triggers(contract: dict[str, Any]) -> set[str]:
    return {
        str(transition["trigger"])
        for transition in record_items(contract, "transitions")
        if isinstance(transition.get("trigger"), str)
    }
