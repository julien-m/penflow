# @spec(FR-001)
# @spec(FR-002)
# @spec(FR-003)
# @spec(FR-004)
# @spec(FR-005)
# @spec(FR-007)
# @spec(FR-008)
# @spec(FR-009)
"""Parse Penflow CLI arguments and dispatch commands through project governance."""

import argparse
import sys

from .artifact_policy import CommandClassification, command_policy_for
from .cli_commands_a import CommandDependencies
from .cli_governance import (
    ProjectBoundaryError,
    _PRODUCER_PATH_ARGUMENTS,
    _run_governed_producer,
    _run_project_health_checked,
)
from .cli_parser import build_parser
from .cli_verification import (
    build_manifest_usage_error,
    is_verification_request,
    render_verification_boundary,
)
from .cli_reporting import (
    PenflowError,
    _print,
    _validate_json_schema_subset,
    _validate_report_schema,
)
from .flow_contract import FlowContractValidationError
from .flow_docs import FlowDocsError
from .pen_lifecycle import CanvasLifecycleError
from .pencil_sync import sync_pencil_to_disk
from .project_doctor import ProjectResolutionError
from .run_lifecycle import LifecycleBlockedError
from .run_pipeline import run_pipeline
from .strict_closure import validate_strict_closure
from .semantic_context_report import CoverageInputError

# Public embedding surface; command handlers remain implementation details of
# the focused command modules used by ``cli_parser``.
__all__ = [
    "_PRODUCER_PATH_ARGUMENTS",
    "_validate_json_schema_subset",
    "_validate_report_schema",
    "build_parser",
    "main",
    "run_pipeline",
    "sync_pencil_to_disk",
    "validate_strict_closure",
]


def main(
    argv: list[str] | None = None,
    *,
    dependencies: CommandDependencies | None = None,
) -> int:
    """Run one Penflow command through its stable CLI boundary.

    Args:
        argv: Arguments excluding the executable name. ``None`` reads
            ``sys.argv`` through ``argparse``.
        dependencies: Optional command runtime dependencies for deterministic
            embedding and tests. Defaults bind the production implementations.

    Returns:
        The dispatched command exit code.

    Side effects:
        Structured command and governance results are written to stdout; usage
        and contract-boundary errors are written to stderr. Every non-exempt
        command runs the Doctor health boundary against ``--project`` or the
        current directory; only producers enter the managed-run lifecycle.
    """
    parser = build_parser()
    args = parser.parse_args(argv)
    if message := build_manifest_usage_error(args):
        if is_verification_request(args):
            return render_verification_boundary(args, message)
        parser.error(message)
    try:
        return _dispatch(args, dependencies)
    except LifecycleBlockedError as error:
        if is_verification_request(args):
            return render_verification_boundary(args, error.message)
        _print(
            {
                "status": "BLOCKED",
                "issues": [{"severity": "error", "code": error.code, "message": error.message}],
            },
            bool(getattr(args, "json", False)),
        )
        return 4
    except (ProjectBoundaryError, ProjectResolutionError) as error:
        if is_verification_request(args):
            return render_verification_boundary(args, str(error))
        return _render_project_boundary_error(args, error)
    except CanvasLifecycleError as error:
        if is_verification_request(args):
            return render_verification_boundary(args, str(error))
        issues = [finding.to_dict() for finding in error.findings]
        _print({"status": "FAIL", "issues": issues}, bool(getattr(args, "json", False)))
        return 1
    except (PenflowError, FlowContractValidationError, CoverageInputError, FlowDocsError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


def _dispatch(
    args: argparse.Namespace,
    dependencies: CommandDependencies | None,
) -> int:
    """Inject runtime dependencies and dispatch a parsed command."""
    args.dependencies = dependencies or CommandDependencies(
        run_pipeline=run_pipeline,
        sync_pencil_to_disk=sync_pencil_to_disk,
        validate_strict_closure=validate_strict_closure,
    )
    policy = command_policy_for(str(args.command))
    if policy.category is CommandClassification.LIFECYCLE_EXEMPT:
        return int(args.func(args) or 0)
    if getattr(args, "project", None) is None:
        args.project = "."
    if str(args.command) == "export-flow-docs" and bool(getattr(args, "check", False)):
        return _run_project_health_checked(args)
    if policy.category is CommandClassification.PRODUCER:
        return _run_governed_producer(args)
    return _run_project_health_checked(args)


def _render_project_boundary_error(
    args: argparse.Namespace,
    error: ProjectBoundaryError | ProjectResolutionError,
) -> int:
    """Render one project-selector or unsafe-boundary failure.

    Invalid or missing selectors are CLI usage errors (exit ``2``). Once a
    selector resolves, unsafe Git/path metadata is an operational boundary
    error (exit ``3``). Resolved project-health findings never reach this
    helper: Doctor renders those with exit ``1``.
    """
    if isinstance(error, ProjectBoundaryError):
        exit_code = error.exit_code
        code = "project.path_blocked"
    else:
        exit_code = 2 if error.code in {"project.path_missing", "project.path_invalid"} else 3
        code = error.code
    _print(
        {
            "status": "BLOCKED",
            "issues": [{"severity": "error", "code": code, "message": str(error)}],
        },
        bool(getattr(args, "json", False)),
    )
    return exit_code
