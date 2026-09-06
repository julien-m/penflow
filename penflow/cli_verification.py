"""C51-specific rendering at the existing CLI and governance boundaries."""

import argparse
from typing import Any

from .cli_reporting import _print
from .verification import (
    produce_verification_report,
    validate_verification_report,
    validation_failure,
)
from .verification_schema import issue


def build_manifest_usage_error(args: argparse.Namespace) -> str | None:
    """Validate caller build binding before legacy dispatch or project governance.

    Args:
        args: Parsed CLI arguments; only run and validate-report accept build identity.

    Returns:
        A usage message for a manifest without an implementation profile, else None.
        Missing implementation manifests remain fail-closed at the verification API.
    """
    profile_options = {"run": "profile", "validate-report": "required_profile"}
    option = profile_options.get(args.command)
    if (
        option
        and getattr(args, "build_manifest", None) is not None
        and getattr(args, option) != "implementation"
    ):
        return f"--build-manifest requires --{option.replace('_', '-')} implementation"
    return None


def is_verification_request(args: argparse.Namespace) -> bool:
    """Identify an explicit C51 profile, preserving every legacy invocation."""
    return bool(
        getattr(args, "command", None) == "authority"
        or getattr(args, "required_profile", None)
        or getattr(args, "profile", None)
    )


def render_verification_boundary(args: argparse.Namespace, message: str) -> int:
    """Return a closed failure even when governance rejects before the command handler."""
    if getattr(args, "command", None) == "authority":
        from .cli_authority import authority_failure

        return authority_failure(args, message)
    if getattr(args, "required_profile", None):
        result = validation_failure(args.required_profile, message=message)
    else:
        result = {
            "kind": "penflow-verification-report",
            "version": 1,
            "profile": args.profile,
            "status": "FAIL",
            "scope": None,
            "policy_version": 1,
            "sources": [],
            "gates": [],
            "obligations": {"required": None, "verified": None, "missing": None, "items": []},
            "evidence": [],
            "build": None,
            "issues": [issue("verification.scope.invalid", "/", message)],
        }
    _print(result, bool(getattr(args, "json", False)))
    return 1


def run_verification_command(args: argparse.Namespace) -> int:
    """Route explicit workflow profiles into the single cumulative producer."""
    if args.strict_closure:
        return render_verification_boundary(
            args, "C47 strict closure cannot be combined with a C51 profile"
        )
    try:
        result = produce_verification_report(
            args.target,
            project_root=args.project,
            profile=args.profile,
            build_manifest_path=args.build_manifest,
        )
    except (OSError, UnicodeError, ValueError) as error:
        return render_verification_boundary(args, str(error))
    _print(result, args.json)
    return int(result["status"] != "PASS")


def validate_verification_command(args: argparse.Namespace) -> int:
    """Revalidate a report using the explicit caller profile, project and build inputs."""
    result: dict[str, Any] = validate_verification_report(
        args.report,
        project_root=args.project,
        required_profile=args.required_profile,
        build_manifest_path=args.build_manifest,
    )
    _print(result, args.json)
    return int(result["status"] != "PASS")
