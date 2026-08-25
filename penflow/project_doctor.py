# @spec FR-001 FR-002 FR-003 FR-007: Feature 075 project-boundary Doctor services.
# @spec FR-001 FR-002 FR-003 FR-011: Feature 074 Doctor services.
"""Public consumer-project Doctor orchestration boundary."""

from __future__ import annotations

import json
from pathlib import Path

from .doctor_context import (
    GitCommandError,
    GitGateway,
    ProjectContext,
    ProjectResolutionError,
    SubprocessGitGateway,
    _resolve_project_context,
)
from .doctor_files import _atomic_write, _inspect_project
from .doctor_git import _capture_git_snapshot
from .doctor_models import (
    DoctorAction,
    DoctorFinding,
    DoctorResult,
    _GitSnapshot,
    _Inspection,
    _build_result,
    _internal_failure_result,
    _resolution_failure_result,
)


class ProjectDoctor:
    """Inspect and safely repair one resolved consumer Git worktree."""

    def __init__(self, git_gateway: GitGateway | None = None) -> None:
        """Initialize Doctor with an injectable narrow Git gateway.

        Args:
            git_gateway: Optional fake or subprocess-backed Git boundary.
        """

        self._git = git_gateway or SubprocessGitGateway()

    def resolve_project_context(
        self,
        project: str | Path | None = None,
        *,
        cwd: str | Path | None = None,
    ) -> ProjectContext:
        """Resolve the nearest containing non-bare Git worktree."""

        return _resolve_project_context(project, cwd=cwd, git_gateway=self._git)

    def run(
        self,
        project: str | Path | ProjectContext | None = None,
        *,
        cwd: str | Path | None = None,
        fix: bool = False,
        dry_run: bool = False,
    ) -> DoctorResult:
        """Check or safely repair a consumer project.

        Args:
            project: Pre-resolved context, explicit consumer path, or ``None`` for CWD.
            cwd: Injectable current directory used for deterministic resolution.
            fix: Apply unambiguous canonical-file and ignore-block repairs.
            dry_run: Plan repairs but never mutate files.

        Returns:
            Typed report and documented exit classification.
        """

        if isinstance(project, ProjectContext):
            context = project
        else:
            try:
                context = self.resolve_project_context(project, cwd=cwd)
            except ProjectResolutionError as error:
                return _resolution_failure_result(project, cwd, error)
        try:
            return self._run_resolved(context, fix=fix, dry_run=dry_run)
        except (GitCommandError, OSError, UnicodeError, ValueError, json.JSONDecodeError) as error:
            return _internal_failure_result(context, error)

    def _run_resolved(
        self,
        context: ProjectContext,
        *,
        fix: bool,
        dry_run: bool,
    ) -> DoctorResult:
        before = _capture_git_snapshot(context, self._git)
        inspection = _inspect_project(context, self._git)
        inspection, actions, changed = _apply_repairs_if_allowed(
            context,
            self._git,
            inspection,
            fix=fix,
            dry_run=dry_run,
        )
        after = _capture_git_snapshot(context, self._git)
        findings = _integrity_findings(inspection.findings, before, after, check_only=not fix)
        return _build_result(
            context,
            canonical_pen=inspection.canonical_pen,
            findings=tuple(findings),
            actions=actions,
            before=before,
            after=after,
            git_paths=inspection.git_paths,
            changed=changed,
        )


def _apply_repairs_if_allowed(
    context: ProjectContext,
    gateway: GitGateway,
    inspection: _Inspection,
    *,
    fix: bool,
    dry_run: bool,
) -> tuple[_Inspection, tuple[DoctorAction, ...], bool]:
    has_unsafe_finding = any(finding.repair_action is None for finding in inspection.findings)
    if not fix or not inspection.repairs or has_unsafe_finding:
        return inspection, (), False
    status = "planned" if dry_run else "applied"
    actions = tuple(
        DoctorAction(repair.action_code, repair.relative_path, status)
        for repair in inspection.repairs
    )
    if dry_run:
        return inspection, actions, False
    for repair in inspection.repairs:
        _atomic_write(
            context.project_root / repair.relative_path,
            repair.content,
            expected_identity=repair.expected_identity,
            mode=repair.mode,
        )
    return _inspect_project(context, gateway), actions, True


def _integrity_findings(
    findings: tuple[DoctorFinding, ...],
    before: _GitSnapshot,
    after: _GitSnapshot,
    *,
    check_only: bool,
) -> tuple[DoctorFinding, ...]:
    additions: list[DoctorFinding] = []
    if before.index_sha256 != after.index_sha256:
        additions.append(
            DoctorFinding(
                "git.index_changed",
                "error",
                None,
                "index_changed",
                "Git index bytes changed during Doctor execution",
            )
        )
    if check_only and before.porcelain != after.porcelain:
        additions.append(
            DoctorFinding(
                "git.worktree_changed_during_check",
                "error",
                None,
                "worktree_changed",
                "Git worktree status changed during the read-only check",
            )
        )
    return (*findings, *additions)


def resolve_project_context(
    project: str | Path | None = None,
    *,
    cwd: str | Path | None = None,
) -> ProjectContext:
    """Resolve a consumer path to its nearest containing Git worktree.

    Args:
        project: Explicit directory/file path, or ``None`` to use CWD.
        cwd: Injectable CWD used for relative paths and tests.

    Returns:
        Immutable consumer project context.

    Raises:
        ProjectResolutionError: If the target is missing, unsafe, bare, or non-Git.
    """

    return _resolve_project_context(project, cwd=cwd, git_gateway=SubprocessGitGateway())


def run_project_doctor(
    project: str | Path | ProjectContext | None = None,
    *,
    cwd: str | Path | None = None,
    fix: bool = False,
    dry_run: bool = False,
) -> DoctorResult:
    """Run CLI-independent Doctor check/fix behavior.

    Args:
        project: Pre-resolved context, explicit consumer path, or ``None`` for CWD.
        cwd: Injectable current directory used for resolution.
        fix: Apply unambiguous safe repairs.
        dry_run: Return planned repairs without filesystem mutation.

    Returns:
        Doctor result with ``exit_code`` and serializable report.
    """

    return ProjectDoctor().run(project, cwd=cwd, fix=fix, dry_run=dry_run)
