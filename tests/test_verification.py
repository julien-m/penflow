# @spec AC-016: Given artifact/source mutation, missing source or changed required evidence after report creation, when `validate-report --schema --required-profile` processes C51, then live recomputation rejects stale serialized PASS/counts. — .specs/features/077-complete-verification-workflow/spec.md#ac-016
# @spec AC-015: Given report-provided scope/build paths differ from independently caller-supplied expectations, when the public revalidation service runs, then it rejects them and accesses no sibling/out-of-bound source, including symlink escapes. — .specs/features/077-complete-verification-workflow/spec.md#ac-015
# @spec AC-005: Given a C47-only or unknown-version receipt, when C51 is required, then it cannot certify; historical inspection remains explicitly identified. — .specs/features/077-complete-verification-workflow/spec.md#ac-005
# @spec AC-003: Given implementation is required and runtime is absent, when verification runs, then it cannot downgrade to design; design requests do not require an app build. Given an absent/ambiguous resolved profile, C51 certification blocks explicitly rather than defaulting to design. — .specs/features/077-complete-verification-workflow/spec.md#ac-003
# @spec AC-001: Given a valid complete chain, when `penflow run` uses a caller-required profile, then it publishes one closed C51 report with that exact profile and every mandatory result. — .specs/features/077-complete-verification-workflow/spec.md#ac-001
"""Public C51 validation refuses unavailable and self-declared authorities."""

from pathlib import Path

import pytest

from penflow.verification import validate_verification_report
from penflow.verification_schema import schema_issues


@pytest.mark.parametrize(
    "content", [None, "{}", '{"status":"PASS"}', '{"version":999}', '{"value":1e400}']
)
def test_public_validation_returns_closed_failure_for_invalid_report(
    tmp_path: Path, content: str | None
) -> None:
    workspace = tmp_path / "penflow"
    workspace.mkdir()
    report = workspace / "run-report.json"
    if content is not None:
        report.write_text(content)
    result = validate_verification_report(report, project_root=tmp_path, required_profile="design")
    assert result["status"] == "FAIL"
    assert result["issues"]
    assert schema_issues(result, "validation") == []


def test_public_validation_does_not_take_project_scope_from_report(tmp_path: Path) -> None:
    result = validate_verification_report(
        tmp_path / "run-report.json",
        project_root=tmp_path / "missing",
        required_profile="implementation",
    )
    assert result["status"] == "FAIL"
    assert result["scope"] is None
    assert result["build_manifest"] is None
    assert schema_issues(result, "validation") == []
