"""Deterministic C20 producer preparation and separate non-mutating certification guards."""

from collections import Counter
from copy import deepcopy
import re
from typing import Any

from .flow_contract import validate_flow_contract_v2
from .verification_files import VerificationInputError
from .verification_json import digest


def contract_test_id_issues(contract: dict[str, Any]) -> list[dict[str, Any]]:
    """Require explicit unique test IDs before review/Pencil without modifying the source."""
    issues = []
    seen = set()
    for index, node in enumerate(contract.get("nodes", [])):
        value = node.get("test_id")
        if not isinstance(value, str) or not value.strip() or value in seen:
            issues.append(
                {
                    "severity": "error",
                    "code": "contract.test_id.required_or_duplicate",
                    "path": f"/nodes/{index}/test_id",
                    "message": "certification requires an explicit unique test_id prepared before source review",
                }
            )
        if isinstance(value, str):
            seen.add(value)
    return issues


def prepare_contract_test_ids(contract: dict[str, Any]) -> dict[str, Any]:
    """Return a prepared copy, retaining authored identities and stable collision resolution."""
    if validate_flow_contract_v2(contract):
        raise VerificationInputError("contract.preparation.invalid_source")
    result = deepcopy(contract)
    existing = {node["test_id"] for node in result["nodes"] if "test_id" in node}
    missing = [node for node in result["nodes"] if "test_id" not in node]
    bases = {
        node["semantic_id"]: "pf-" + re.sub(r"[^a-zA-Z0-9._-]", "-", node["semantic_id"])
        for node in missing
    }
    counts = Counter(bases.values())
    for node in missing:
        identity = node["semantic_id"]
        candidate = bases[identity]
        if candidate in existing or counts[candidate] > 1:
            candidate += "-" + digest(identity.encode("utf-8"))[:16]
        node["test_id"] = candidate
    if contract_test_id_issues(result):
        raise VerificationInputError("contract.preparation.test_id_collision")
    return result
