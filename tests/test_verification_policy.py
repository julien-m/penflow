# @spec AC-002: Given any missing/skipped/stale/unsupported/nonpassing mandatory gate, when closure runs, then exit is nonzero and no final PASS is emitted. — .specs/features/077-complete-verification-workflow/spec.md#ac-002
"""Every mandatory policy row remains blocking when omitted or warning-bearing."""

import pytest

from penflow.verification_policy import GateBook

REQUIRED = [row["id"] for row in GateBook("implementation").finish() if row["required"]]


@pytest.mark.parametrize("omitted", REQUIRED)
def test_omitting_any_required_gate_never_closes_the_policy(omitted):
    book = GateBook("implementation")
    for gate in REQUIRED:
        if gate != omitted:
            book.evaluate(gate, lambda: [])
    rows = book.finish()
    blocked = [row for row in rows if row["required"] and row["status"] != "PASS"]
    assert [row["id"] for row in blocked] == [omitted]
    assert blocked[0]["issues"][0]["code"] == "verification.gate.unavailable"


@pytest.mark.parametrize("severity", ["warning", "error"])
def test_required_findings_are_not_a_score_or_lenient_decision(severity):
    book = GateBook("implementation")
    book.evaluate(
        "validate-flow-contract",
        lambda: [{"severity": severity, "message": "source contradiction"}],
    )
    assert book.rows["validate-flow-contract"]["status"] == "FAIL"
