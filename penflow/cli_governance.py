# @spec(FR-001)
# @spec(FR-002)
# @spec(FR-003)
# @spec(FR-004)
# @spec(FR-005)
# @spec(FR-007)
# @spec(FR-008)
# @spec(FR-009)
# @spec FR-001 FR-002 FR-003 FR-004 FR-007: Feature 075 governed project boundary.

import argparse
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from .cli_reporting import _print
from .project_doctor import ProjectContext, resolve_project_context, run_project_doctor
from .run_lifecycle import (
    CleanupState,
    LifecycleBlockedError,
    LifecycleLock,
    LifecyclePhase,
    ManagedRunManifest,
    OwnerIdentity,
    ProducerState,
    allocate_run,
    apply_cleanup_plan,
    build_cleanup_plan,
    capture_owner_identity,
    load_manifest,
    reconcile_manifest_owner,
    save_manifest,
    transition_manifest,
)


class ProjectBoundaryError(ValueError):
    """Report a governed producer path that violates its consumer project."""

    def __init__(self, message: str, *, exit_code: int = 3) -> None:
        """Initialize a coded CLI boundary failure.

        Args:
            message: Actionable explanation of the rejected boundary.
            exit_code: ``2`` for invalid CLI usage or ``3`` for an unsafe
                resolved boundary. Project-health findings are returned by
                Doctor itself with exit code ``1``.
        """

        super().__init__(message)
        self.exit_code = exit_code


_PRODUCER_PATH_ARGUMENTS: dict[str, tuple[str, ...]] = {
    "run": ("target", "theme_css", "references"),
    "pencil-sync": ("pen",),
    "verify-pencil-persistence": ("observation", "document", "out"),
    "verify-export-operation": ("request", "source_pen", "out"),
    "export-expected": ("pen", "out"),
    "export-flow-docs": ("contract", "out"),
    "export-semantic-tree": ("specs_dir", "out"),
    "migrate-flow-contract": ("specs_dir", "out"),
    "draft-pen-from-tree": ("semantic_tree", "out", "theme_css"),
    "enrich-pen": ("pen", "semantic_tree", "out"),
    "map-pencil-context": ("pen", "semantic_tree", "out", "pen_out", "contract", "coverage_out"),
    "audit-context-coverage": ("pen", "contract", "out"),
    "reverse-pen": ("pen", "out"),
    "detect-drift": ("specs_dir", "semantic_tree", "pen", "out", "markdown"),
    "checklist-from-drift": ("drift_report", "out"),
    "compare-tree": ("expected", "actual", "out", "markdown"),
    "check-consistency": ("expected", "out"),
    "audit-visual": ("expected", "theme_css", "layout_snapshot", "out"),
    "flow-to-screens": ("flow", "out_dir"),
    "draft-pen": ("screen", "out"),
    "update-pen": ("pen", "updates", "out"),
    "extract-tokens": ("pen", "out"),
    "lint-tokens": ("pen", "theme_css", "out"),
    "export-ir": ("screen", "expected", "out"),
    "code-ir": ("from_context", "semantic_tree", "context_map", "contract", "out"),
    "codegen": ("ir", "out"),
    "ci": ("pen", "actual"),
    "review-report": ("report", "out"),
    "fix-report": ("report", "out"),
    "demo": ("out",),
}


def _run_governed_producer(args: argparse.Namespace) -> int:
    """Execute one producer under the consumer Doctor and managed-run lock."""
    context = resolve_project_context(args.project)
    owner = capture_owner_identity()
    command = str(args.command)
    with LifecycleLock.acquire(context.project_root, owner, operation=f"producer:{command}"):
        preflight = run_project_doctor(context)
        if preflight.exit_code != 0:
            from .cli_verification import is_verification_request, render_verification_boundary

            if is_verification_request(args):
                return render_verification_boundary(args, str(preflight.report.to_dict()))
            _print(preflight.report.to_dict(), bool(getattr(args, "json", False)))
            return preflight.exit_code
        canonical_relative = preflight.report.stable_result.canonical_pen
        _govern_producer_paths(args, context, canonical_relative)
        if canonical_relative is None:
            raise ProjectBoundaryError("Doctor did not resolve a canonical ui.pen")
        canonical = context.resolve_path(canonical_relative)
        _reconcile_prior_runs(context, canonical)
        return _execute_managed_producer(args, context, owner, command, canonical)


def _run_project_health_checked(args: argparse.Namespace) -> int:
    """Execute a read-only command after the shared consumer health boundary.

    Args:
        args: Parsed command arguments with a resolved ``project`` value.

    Returns:
        The Doctor block code or the read-only command exit code.

    Side effects:
        Doctor inspects the consumer project without allocating, reconciling,
        or cleaning managed lifecycle runs.
    """
    context = resolve_project_context(args.project)
    health = run_project_doctor(context)
    if health.exit_code != 0:
        from .cli_verification import is_verification_request, render_verification_boundary

        if is_verification_request(args):
            return render_verification_boundary(args, str(health.report.to_dict()))
        _print(health.report.to_dict(), bool(getattr(args, "json", False)))
        return health.exit_code
    args.project = str(context.project_root)
    return int(args.func(args) or 0)


def _execute_managed_producer(
    args: argparse.Namespace,
    context: ProjectContext,
    owner: OwnerIdentity,
    command: str,
    canonical: Path,
) -> int:
    now = datetime.now(UTC).isoformat()
    manifest = allocate_run(
        context.project_root,
        run_id=f"{command}-{uuid4().hex}",
        command=command,
        owner=owner,
        created_at=now,
    )
    manifest = transition_manifest(
        manifest,
        producer_state=ProducerState.ACTIVE,
        updated_at=now,
    )
    save_manifest(context.project_root, manifest)
    try:
        producer_exit = int(args.func(args) or 0)
    except BaseException:
        failed = transition_manifest(
            manifest,
            producer_state=ProducerState.FAILED,
            cleanup_state=CleanupState.ELIGIBLE,
            updated_at=datetime.now(UTC).isoformat(),
        )
        save_manifest(context.project_root, failed)
        try:
            _cleanup_current_run(context, canonical, failed, LifecyclePhase.POSTFLIGHT)
        except LifecycleBlockedError:
            pass
        raise
    if producer_exit == 0:
        manifest = transition_manifest(
            manifest,
            producer_state=ProducerState.FINALIZING,
            updated_at=datetime.now(UTC).isoformat(),
        )
        save_manifest(context.project_root, manifest)
    terminal = transition_manifest(
        manifest,
        producer_state=ProducerState.SUCCEEDED if producer_exit == 0 else ProducerState.FAILED,
        cleanup_state=CleanupState.ELIGIBLE,
        updated_at=datetime.now(UTC).isoformat(),
    )
    save_manifest(context.project_root, terminal)
    _cleanup_current_run(context, canonical, terminal, LifecyclePhase.POSTFLIGHT)
    return producer_exit


def _reconcile_prior_runs(context: ProjectContext, canonical: Path) -> None:
    manifests_dir = context.project_root / ".penflow-tmp" / "manifests"
    if not manifests_dir.is_dir():
        return
    for path in sorted(manifests_dir.glob("*.json")):
        manifest = load_manifest(path)
        recovered = reconcile_manifest_owner(manifest)
        if recovered != manifest:
            save_manifest(context.project_root, recovered)
        if recovered.producer_state not in {ProducerState.SUCCEEDED, ProducerState.FAILED}:
            raise LifecycleBlockedError(
                "cleanup.producer_active",
                f"managed run {recovered.run_id} still has a live owner",
            )
        _cleanup_current_run(context, canonical, recovered, LifecyclePhase.PREFLIGHT)


def _cleanup_current_run(
    context: ProjectContext,
    canonical: Path,
    manifest: ManagedRunManifest,
    phase: LifecyclePhase,
) -> None:
    plan = build_cleanup_plan(context, manifest, canonical_pen=canonical)
    receipt = apply_cleanup_plan(context, manifest, plan, phase=phase)
    if receipt.errors or receipt.blocked:
        codes = sorted({finding.code for finding in receipt.errors})
        raise LifecycleBlockedError(
            codes[0] if codes else "cleanup.blocked",
            f"managed run {manifest.run_id} cleanup was blocked",
        )


def _govern_producer_paths(
    args: argparse.Namespace,
    context: ProjectContext,
    canonical_relative: str | None,
) -> None:
    """Resolve producer paths inside one consumer root and reject peer canvases."""
    command = str(args.command)
    for attribute in _PRODUCER_PATH_ARGUMENTS.get(command, ()):
        value = getattr(args, attribute, None)
        if value is None:
            continue
        try:
            resolved = context.resolve_path(value)
        except (FileNotFoundError, ValueError) as error:
            raise ProjectBoundaryError(str(error)) from error
        setattr(args, attribute, str(resolved))

    if canonical_relative is None:
        raise ProjectBoundaryError("Doctor did not resolve a canonical ui.pen")
    canonical = context.resolve_path(canonical_relative)
    pen_arguments: dict[str, tuple[str, ...]] = {
        "draft-pen-from-tree": ("out",),
        "enrich-pen": ("pen", "out"),
        "map-pencil-context": ("pen", "pen_out"),
        "audit-context-coverage": ("pen",),
        "reverse-pen": ("pen",),
        "draft-pen": ("out",),
        "update-pen": ("pen", "out"),
    }
    for attribute in pen_arguments.get(command, ()):
        value = getattr(args, attribute, None)
        if value is None:
            continue
        if Path(value) != canonical:
            raise ProjectBoundaryError(
                f"{command} --{attribute.replace('_', '-')} must resolve to canonical "
                f"{canonical_relative}; peer .pen files are forbidden"
            )
    if command == "demo":
        output_root = Path(args.out)
        if output_root / "ui.pen" != canonical:
            raise ProjectBoundaryError(
                f"demo output must contain the canonical {canonical_relative}; "
                "peer ui.pen files are forbidden"
            )


# @spec FR-011: Scriptable Doctor CLI boundary — .specs/features/074-penflow-doctor-consumer-project-hygiene/spec.md#fr-011
