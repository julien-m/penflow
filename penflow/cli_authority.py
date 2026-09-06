"""Read-only machine transport for automatic authority import and projection."""

import argparse
from typing import Any

from pathlib import Path
from .contract_preparation import prepare_contract_test_ids
from .verification_files import InputReader
from .cli_reporting import _print
from .verification_authority import collect_brainstorm_authority, project_brainstorm_authority


def authority_failure(args: argparse.Namespace, message: str) -> int:
    """Render the same closed envelope at handler and Doctor boundaries."""
    _print(
        {
            "kind": "penflow-authority-result",
            "version": 1,
            "operation": args.operation,
            "status": "FAIL",
            "data": None,
            "issues": [{"code": "authority.input.invalid", "message": message}],
        },
        args.json,
    )
    return 1


def authority_command(args: argparse.Namespace) -> int:
    """Collect validated source bytes or project their locally archived authority."""
    try:
        if args.operation == "collect":
            result = collect_brainstorm_authority(args.input, project_root=args.project)
        elif args.operation == "prepare":
            reader = InputReader(Path(args.project))
            result = prepare_contract_test_ids(reader.object(reader.read(args.input)))
            reader.recheck()
        else:
            if args.contract is None:
                return authority_failure(args, "authority project requires --contract")
            result = project_brainstorm_authority(
                args.input, project_root=args.project, contract_path=args.contract
            )
    except (OSError, UnicodeError, ValueError) as error:
        return authority_failure(args, str(error))
    _print(
        {
            "kind": "penflow-authority-result",
            "version": 1,
            "operation": args.operation,
            "status": "PASS",
            "data": result,
            "issues": [],
        },
        args.json,
    )
    return 0


def register_authority(sub: Any) -> None:
    """Register internal workflow transport without introducing a manual workflow step."""
    parser = sub.add_parser("authority", help="collect or project authenticated upstream authority")
    parser.add_argument("operation", choices=("collect", "project", "prepare"))
    parser.add_argument("input")
    parser.add_argument("--contract")
    parser.add_argument("--json", action="store_true")
    parser.set_defaults(func=authority_command)
