"""Check that the C51 workflow guide states the reviewed delegation contract."""

from __future__ import annotations

import re
from pathlib import Path

GUIDE = Path(__file__).resolve().parents[1] / "docs" / "verification-workflow.md"

# Every documented name of the delegation contract, as the guide must spell it.
DOCUMENTED_NAMES = (
    "`requirements.delegations`",
    "`requirement_id`",
    "`acceptance_owner`",
    "`rationale`",
    "`projection.delegated`",
    "`delegated_requirements`",
    "`certified: false`",
    "`requirements.delegation.invalid`",
    "`product.delegation.forbidden`",
)
# Statements a reader must find, compared on lower-cased text with collapsed whitespace.
REQUIRED_STATEMENTS = (
    "bind every source requirement that carries a ui-contract obligation",
    "or declare a reviewed delegation",
    "certifies the ui-contract obligations only",
    "claims no upstream or future application execution",
    "observable on screen, including keyboard and focus behaviour, is bound and not delegated",
    "typed `storage` or `network` evidence is bound and not delegated",
    "refuse a delegation that removes a persistence expectation",
)
LEGACY_INSTRUCTION = "bind every source requirement to the appropriate obligation"


def _normalized_guide() -> str:
    return " ".join(GUIDE.read_text(encoding="utf-8").lower().split())


# @spec AC-013: Guide documents reviewed delegation — .specs/features/082-reviewed-requirement-delegation-to-upstream-acceptance/spec.md#ac-013
def test_guide_documents_reviewed_delegation() -> None:
    guide = _normalized_guide()
    assert [name for name in DOCUMENTED_NAMES if name not in guide] == []
    assert [text for text in REQUIRED_STATEMENTS if text not in guide] == []
    # A sentence that tells the author to bind every requirement must offer the delegation.
    unconditional = [
        sentence
        for sentence in re.split(r"(?<=[.;])\s", guide)
        if "bind every source requirement" in sentence and "delegation" not in sentence
    ]
    assert unconditional == []
    assert LEGACY_INSTRUCTION not in guide
