"""Register the primary read-only check workflow at the CLI boundary."""

from __future__ import annotations

import argparse
from typing import Any

from .cli_reporting import _print
from .review_checks import check_workspace


def check_command(args: argparse.Namespace) -> int:
    """Print real check results; scope errors remain explicit JSON failures.

    Args:
        args: Parsed workspace, optional project/theme and JSON preference.

    Returns:
        Aggregate check exit code, or 2 for an unusable workspace boundary.
    """
    try:
        report = check_workspace(args.target, project_root=args.project, theme_css=args.theme_css)
    except (OSError, ValueError) as error:
        report = {
            "kind": "penflow-check-report",
            "version": 1,
            "certified": False,
            "review_status": "required",
            "status": "ERROR",
            "exit": 2,
            "checks": [],
            "issues": [{"code": "check.workspace.invalid", "message": str(error)}],
            "limitations": ["No local checks executed; workspace boundary is unusable."],
        }
    _print(report, args.json)
    return int(report["exit"])


def register_checks(sub: Any) -> None:
    """Register one check command; argparse adds the shared project selector.

    Args:
        sub: Existing argparse subcommand registry.
    """
    parser = sub.add_parser("check", help="check current local inputs for independent review")
    parser.add_argument("--target", required=True, help="workspace containing ui.pen")
    parser.add_argument("--theme-css", help="optional theme path relative to workspace")
    parser.add_argument("--json", action="store_true", help="print machine-readable results")
    parser.set_defaults(func=check_command)
