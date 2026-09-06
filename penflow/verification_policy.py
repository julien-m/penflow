# @spec FR-002: Establish nonempty validated structural cardinality before export/scoring and reject vacuous completion. — .specs/features/077-complete-verification-workflow/spec.md#fr-002
"""Closed cumulative gate registry and source-derived applicability for C51."""

from collections.abc import Callable
from typing import Any

from .verification_files import VerificationInputError
from .verification_schema import issue

GATE_IDS = (
    "project-scope",
    "upstream-requirements",
    "validate-flow-contract",
    "generated-flow-docs",
    "export-semantic-tree",
    "validate-semantic-tree",
    "map-pencil-context",
    "semantic-context-coverage",
    "validate-pen",
    "export-expected",
    "lint-tokens",
    "check-consistency",
    "audit-visual",
    "detect-drift",
    "validate-visual-evidence",
    "validate-reference-fidelity",
    "verify-pencil-persistence",
    "verify-export-operation",
    "code-ir",
    "validate-actual",
    "compare-tree",
    "validate-actual-provenance",
    "validate-causal-evidence",
    "typed-outcome-obligations",
    "source-final-recheck",
    "pencil-sync",
    "historical-strict-closure",
    "design-taste",
)
RUNTIME_GATES = {
    "validate-actual",
    "compare-tree",
    "validate-actual-provenance",
    "validate-causal-evidence",
    "typed-outcome-obligations",
}
ADVISORY_GATES = {"pencil-sync", "design-taste"}


class GateBook:
    """Evaluate every declared gate, preserving failures as required dependent rows."""

    def __init__(self, profile: str) -> None:
        self.rows: dict[str, dict[str, Any]] = {}
        for gate in GATE_IDS:
            row = {
                "id": gate,
                "applicable": True,
                "required": True,
                "status": "BLOCKED",
                "source_pointer": "/",
                "reason": "required by cumulative policy v1",
                "evidence": [],
                "issues": [],
            }
            self.rows[gate] = row
            if gate in ADVISORY_GATES or gate == "historical-strict-closure":
                row.update(
                    applicable=False,
                    required=False,
                    status="HISTORICAL" if gate == "historical-strict-closure" else "ADVISORY",
                    reason="noncertifying operator or historical control",
                )
            elif profile == "design" and gate in RUNTIME_GATES:
                self.not_applicable(
                    gate, "/profile", "design profile does not certify application execution"
                )

    def not_applicable(self, gate: str, pointer: str, reason: str) -> None:
        """Record one actual source-derived inapplicability; missing evidence never calls this."""
        self.rows[gate].update(
            applicable=False,
            required=False,
            status="NOT_APPLICABLE",
            source_pointer=pointer,
            reason=reason,
            issues=[],
        )

    def evaluate(
        self,
        gate: str,
        action: Callable[[], list[dict[str, Any]]],
        *,
        dependencies: tuple[str, ...] = (),
    ) -> None:
        """Run a boundary-validated control or report its exact unmet prerequisite."""
        row = self.rows[gate]
        if not row["required"]:
            return
        failed = [key for key in dependencies if self.rows[key]["status"] != "PASS"]
        if failed:
            self.fail(
                gate,
                "verification.gate.prerequisite",
                "required prerequisites did not pass: " + ", ".join(failed),
            )
            return
        try:
            findings = action()
        except (OSError, UnicodeError, VerificationInputError, ValueError) as error:
            self.fail(gate, "verification.gate.input_invalid", str(error))
            return
        normalized = [
            normalize_issue(value, gate)
            for value in findings
            if value.get("severity", "error") != "info"
        ]
        row.update(status="FAIL" if normalized else "PASS", issues=normalized)

    def fail(self, gate: str, code: str, message: str) -> None:
        """Keep an unavailable required control explicitly blocking."""
        self.rows[gate].update(status="BLOCKED", issues=[issue(code, "/", message, gate_id=gate)])

    def finish(self) -> list[dict[str, Any]]:
        """Return the exhaustive stable registry, including controls whose inputs were missing."""
        for gate, row in self.rows.items():
            if row["required"] and row["status"] == "BLOCKED" and not row["issues"]:
                self.fail(
                    gate, "verification.gate.unavailable", "required source or evidence unavailable"
                )
        return list(self.rows.values())


def normalize_issue(value: dict[str, Any], gate: str) -> dict[str, Any]:
    """Preserve stable legacy codes while emitting the closed cumulative issue format."""
    result = issue(
        str(value.get("code", "verification.gate.failed")),
        str(value.get("path") or "/"),
        str(value.get("message", value.get("details", "required check did not pass"))),
        gate_id=gate,
        obligation_id=value.get("obligation_id"),
    )
    result["severity"] = (
        value.get("severity", "error")
        if value.get("severity") in {"error", "warning", "info"}
        else "error"
    )
    return result
