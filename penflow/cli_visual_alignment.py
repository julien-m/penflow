"""Expose a read-only Markdown artifact over existing visual comparison evidence."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from .visual_alignment import load_review
from .visual_alignment_markdown import format_review


def _visual_alignment(args: argparse.Namespace) -> int:
    root = args.evidence_root or args.project
    try:
        locale, cases = load_review(Path(args.manifest), Path(root) if root else None)
    except (OSError, ValueError, RuntimeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    sys.stdout.write(format_review(locale, cases))
    return 0


def register_visual_alignment(sub: Any) -> None:
    """Register the manifest-driven visual alignment report command."""
    parser = sub.add_parser("visual-alignment", help="review paired mockup and runtime evidence")
    parser.add_argument("manifest", help="versioned review manifest JSON")
    parser.add_argument("--evidence-root", help="resolve evidence paths inside this directory")
    parser.set_defaults(func=_visual_alignment)
