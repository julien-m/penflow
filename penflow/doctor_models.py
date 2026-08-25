# @spec FR-001 FR-007: Feature 075 report compatibility.
"""Consumer-project Doctor data contracts."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .doctor_context import ProjectContext, ProjectResolutionError

DOCTOR_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class DoctorFinding:
    """Describe one deterministic consumer-project health finding."""

    code: str
    severity: str
    path: str | None
    git_state: str | None
    details: str
    repair_action: str | None = None

    def to_dict(self) -> dict[str, object]:
        """Serialize the finding using the Doctor report schema."""

        return {
            "code": self.code,
            "severity": self.severity,
            "path": self.path,
            "git_state": self.git_state,
            "details": self.details,
            "repair_action": self.repair_action,
        }


@dataclass(frozen=True)
class DoctorAction:
    """Describe one planned or applied safe Doctor repair."""

    code: str
    path: str | None
    status: str

    def to_dict(self) -> dict[str, object]:
        """Serialize the action using the Doctor report schema."""

        return {"code": self.code, "path": self.path, "status": self.status}


@dataclass(frozen=True)
class GitPathState:
    """Normalize one tracked or staged managed temporary Git path."""

    relative_path: str
    index_state: str
    worktree_state: str
    flags: tuple[str, ...]
    blocking: bool = True

    def to_dict(self) -> dict[str, object]:
        """Serialize one normalized Git path state."""

        return {
            "relative_path": self.relative_path,
            "index_state": self.index_state,
            "worktree_state": self.worktree_state,
            "flags": list(self.flags),
            "blocking": self.blocking,
        }


@dataclass(frozen=True)
class DoctorGitState:
    """Record immutable Git evidence captured around a Doctor operation."""

    index_sha256_before: str | None
    index_sha256_after: str | None
    index_unchanged: bool
    porcelain_sha256_before: str | None
    porcelain_sha256_after: str | None
    porcelain_unchanged: bool
    paths: tuple[GitPathState, ...]

    def to_dict(self) -> dict[str, object]:
        """Serialize Git integrity evidence and managed path states."""

        return {
            "index_sha256_before": self.index_sha256_before,
            "index_sha256_after": self.index_sha256_after,
            "index_unchanged": self.index_unchanged,
            "porcelain_sha256_before": self.porcelain_sha256_before,
            "porcelain_sha256_after": self.porcelain_sha256_after,
            "porcelain_unchanged": self.porcelain_unchanged,
            "paths": [path.to_dict() for path in self.paths],
        }


@dataclass(frozen=True)
class DoctorSummary:
    """Summarize stable Doctor counts and mutation outcome."""

    finding_count: int
    blocking_count: int
    action_count: int
    changed: bool

    def to_dict(self) -> dict[str, object]:
        """Serialize stable Doctor summary counts."""

        return {
            "finding_count": self.finding_count,
            "blocking_count": self.blocking_count,
            "action_count": self.action_count,
            "changed": self.changed,
        }


@dataclass(frozen=True)
class DoctorStableResult:
    """Contain the byte-stable portion of one Doctor report."""

    status: str
    project_root: str | None
    canonical_pen: str | None
    findings: tuple[DoctorFinding, ...]
    actions: tuple[DoctorAction, ...]
    git: DoctorGitState
    runs: tuple[object, ...]
    cleanup: dict[str, object]
    summary: DoctorSummary

    def to_dict(self) -> dict[str, object]:
        """Serialize stable Doctor output without volatile diagnostics."""

        return {
            "status": self.status,
            "project_root": self.project_root,
            "canonical_pen": self.canonical_pen,
            "findings": [finding.to_dict() for finding in self.findings],
            "actions": [action.to_dict() for action in self.actions],
            "git": self.git.to_dict(),
            "runs": list(self.runs),
            "cleanup": dict(self.cleanup),
            "summary": self.summary.to_dict(),
        }


@dataclass(frozen=True)
class DoctorDiagnostics:
    """Contain volatile Doctor observation and platform details."""

    observed_at: str
    invocation_path: str | None
    explicit_project: bool
    repository_kind: str | None
    error: str | None

    def to_dict(self) -> dict[str, object]:
        """Serialize volatile diagnostics separately from stable output."""

        return {
            "observed_at": self.observed_at,
            "invocation_path": self.invocation_path,
            "explicit_project": self.explicit_project,
            "repository_kind": self.repository_kind,
            "error": self.error,
        }


@dataclass(frozen=True)
class DoctorReport:
    """Represent the schema-versioned Doctor JSON envelope."""

    schema_version: int
    stable_result: DoctorStableResult
    diagnostics: DoctorDiagnostics

    def to_dict(self) -> dict[str, object]:
        """Serialize the complete deterministic-plus-diagnostics envelope."""

        return {
            "schema_version": self.schema_version,
            "stable_result": self.stable_result.to_dict(),
            "diagnostics": self.diagnostics.to_dict(),
        }


@dataclass(frozen=True)
class DoctorResult:
    """Return a Doctor report plus its CLI-independent exit classification."""

    report: DoctorReport
    exit_code: int
    context: ProjectContext | None


@dataclass(frozen=True)
class _GitSnapshot:
    index_sha256: str | None
    porcelain: bytes


@dataclass(frozen=True)
class _Repair:
    action_code: str
    relative_path: str
    content: bytes
    expected_identity: tuple[int, int, int, int] | None = None
    mode: int = 0o644


@dataclass(frozen=True)
class _Inspection:
    canonical_pen: str | None
    findings: tuple[DoctorFinding, ...]
    repairs: tuple[_Repair, ...]
    git_paths: tuple[GitPathState, ...]


def _build_result(
    context: ProjectContext,
    *,
    canonical_pen: str | None,
    findings: tuple[DoctorFinding, ...],
    actions: tuple[DoctorAction, ...],
    before: _GitSnapshot,
    after: _GitSnapshot,
    git_paths: tuple[GitPathState, ...],
    changed: bool,
) -> DoctorResult:
    ordered_findings = tuple(
        sorted(findings, key=lambda finding: (finding.severity, finding.code, finding.path or ""))
    )
    blocking_count = sum(finding.severity == "error" for finding in ordered_findings)
    stable = DoctorStableResult(
        status="BLOCKED" if blocking_count else "PASS",
        project_root=os.fspath(context.project_root),
        canonical_pen=canonical_pen,
        findings=ordered_findings,
        actions=actions,
        git=DoctorGitState(
            index_sha256_before=before.index_sha256,
            index_sha256_after=after.index_sha256,
            index_unchanged=before.index_sha256 == after.index_sha256,
            porcelain_sha256_before=_bytes_sha256(before.porcelain),
            porcelain_sha256_after=_bytes_sha256(after.porcelain),
            porcelain_unchanged=before.porcelain == after.porcelain,
            paths=git_paths,
        ),
        runs=(),
        cleanup={"status": "NOT_APPLICABLE"},
        summary=DoctorSummary(
            finding_count=len(ordered_findings),
            blocking_count=blocking_count,
            action_count=len(actions),
            changed=changed,
        ),
    )
    report = DoctorReport(
        schema_version=DOCTOR_SCHEMA_VERSION,
        stable_result=stable,
        diagnostics=_diagnostics(context),
    )
    return DoctorResult(report=report, exit_code=1 if blocking_count else 0, context=context)


def _resolution_failure_result(
    project: str | Path | None,
    cwd: str | Path | None,
    error: ProjectResolutionError,
) -> DoctorResult:
    finding = DoctorFinding(error.code, "error", None, None, str(error), None)
    stable = _empty_stable_result("BLOCKED", (finding,))
    base = Path.cwd() if cwd is None else Path(cwd).expanduser()
    invocation = base if project is None else Path(project).expanduser()
    diagnostics = DoctorDiagnostics(
        observed_at=_observed_at(),
        invocation_path=os.fspath(invocation),
        explicit_project=project is not None,
        repository_kind=None,
        error=str(error),
    )
    report = DoctorReport(DOCTOR_SCHEMA_VERSION, stable, diagnostics)
    return DoctorResult(report=report, exit_code=1, context=None)


def _internal_failure_result(context: ProjectContext, error: Exception) -> DoctorResult:
    finding = DoctorFinding(
        "doctor.internal_error",
        "error",
        None,
        None,
        "Doctor could not produce a trustworthy complete project inventory",
        None,
    )
    stable = _empty_stable_result(
        "ERROR",
        (finding,),
        project_root=os.fspath(context.project_root),
    )
    report = DoctorReport(
        DOCTOR_SCHEMA_VERSION,
        stable,
        DoctorDiagnostics(
            observed_at=_observed_at(),
            invocation_path=os.fspath(context.invocation_path),
            explicit_project=context.explicit_project,
            repository_kind=context.repository_kind,
            error=str(error),
        ),
    )
    return DoctorResult(report=report, exit_code=3, context=context)


def _empty_stable_result(
    status: str,
    findings: tuple[DoctorFinding, ...],
    *,
    project_root: str | None = None,
) -> DoctorStableResult:
    blocking_count = sum(finding.severity == "error" for finding in findings)
    return DoctorStableResult(
        status=status,
        project_root=project_root,
        canonical_pen=None,
        findings=findings,
        actions=(),
        git=DoctorGitState(None, None, True, None, None, True, ()),
        runs=(),
        cleanup={"status": "NOT_APPLICABLE"},
        summary=DoctorSummary(len(findings), blocking_count, 0, False),
    )


def _diagnostics(context: ProjectContext) -> DoctorDiagnostics:
    return DoctorDiagnostics(
        observed_at=_observed_at(),
        invocation_path=os.fspath(context.invocation_path),
        explicit_project=context.explicit_project,
        repository_kind=context.repository_kind,
        error=None,
    )


def _observed_at() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _bytes_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()
