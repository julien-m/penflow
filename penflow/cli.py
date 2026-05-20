"""Penflow command line interface."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .codegen import react, rust_dioxus, swiftui
from .compare import compare_tree_files
from .contracts import (
    code_ir_from_contract,
    extract_design_tokens,
    screen_contracts_from_flow,
    update_pencil,
    validate_flow_contract,
    validate_screen_contract,
    write_pencil_draft,
)
from .demo import build_demo
from .llm import fix_compare_report, review_compare_report
from .pen import inspect_pen, parse_pen, validate_pen_context
from .tree import load_tree, validate_actual_tree, write_expected_tree


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except PenflowError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="penflow")
    parser.add_argument(
        "--json", action="store_true", help="print machine-readable JSON when supported"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    inspect_cmd = sub.add_parser("inspect", help="inspect a .pen file")
    inspect_cmd.add_argument("--json", action="store_true", help="print machine-readable JSON")
    inspect_cmd.add_argument("pen")
    inspect_cmd.set_defaults(func=cmd_inspect)

    validate_pen = sub.add_parser(
        "validate-pen", aliases=["validate"], help="validate .pen context"
    )
    validate_pen.add_argument("--json", action="store_true", help="print machine-readable JSON")
    validate_pen.add_argument("pen")
    validate_pen.set_defaults(func=cmd_validate_pen)

    expected = sub.add_parser("export-expected", help="export expected UI tree from .pen")
    expected.add_argument("--json", action="store_true", help="print machine-readable JSON")
    expected.add_argument("pen")
    expected.add_argument("-o", "--out", default="expected-ui-tree.json")
    expected.set_defaults(func=cmd_export_expected)

    actual = sub.add_parser("validate-actual", help="validate actual runtime UI tree")
    actual.add_argument("--json", action="store_true", help="print machine-readable JSON")
    actual.add_argument("actual")
    actual.set_defaults(func=cmd_validate_actual)

    compare = sub.add_parser("compare-tree", help="compare expected and actual UI trees")
    compare.add_argument("--json", action="store_true", help="print machine-readable JSON")
    compare.add_argument("expected")
    compare.add_argument("actual")
    compare.add_argument("--out", default="compare-report.json")
    compare.add_argument("--markdown", default=None)
    compare.add_argument("--threshold", type=float, default=0.9)
    compare.set_defaults(func=cmd_compare_tree)

    flow = sub.add_parser("validate-flow", help="validate flow contract")
    flow.add_argument("--json", action="store_true", help="print machine-readable JSON")
    flow.add_argument("flow")
    flow.set_defaults(func=cmd_validate_flow)

    screen = sub.add_parser("validate-screen", help="validate screen contract")
    screen.add_argument("--json", action="store_true", help="print machine-readable JSON")
    screen.add_argument("screen")
    screen.set_defaults(func=cmd_validate_screen)

    flow_to_screen = sub.add_parser("flow-to-screens", help="generate screen contracts from flow")
    flow_to_screen.add_argument("--json", action="store_true", help="print machine-readable JSON")
    flow_to_screen.add_argument("flow")
    flow_to_screen.add_argument("--out-dir", default="screen-contracts")
    flow_to_screen.set_defaults(func=cmd_flow_to_screens)

    draft = sub.add_parser("draft-pen", help="generate Pencil draft from screen contract")
    draft.add_argument("--json", action="store_true", help="print machine-readable JSON")
    draft.add_argument("screen")
    draft.add_argument("-o", "--out", default="draft.pen")
    draft.set_defaults(func=cmd_draft_pen)

    update = sub.add_parser("update-pen", help="update .pen nodes by semantic_id")
    update.add_argument("--json", action="store_true", help="print machine-readable JSON")
    update.add_argument("pen")
    update.add_argument("updates")
    update.add_argument("-o", "--out", required=True)
    update.set_defaults(func=cmd_update_pen)

    tokens = sub.add_parser("extract-tokens", help="extract design tokens from .pen")
    tokens.add_argument("--json", action="store_true", help="print machine-readable JSON")
    tokens.add_argument("pen")
    tokens.add_argument("-o", "--out", default=None)
    tokens.set_defaults(func=cmd_extract_tokens)

    ir = sub.add_parser("export-ir", help="export code IR from screen contract")
    ir.add_argument("--json", action="store_true", help="print machine-readable JSON")
    ir.add_argument("screen")
    ir.add_argument("--expected", default=None)
    ir.add_argument("-o", "--out", default="code-ir.json")
    ir.set_defaults(func=cmd_export_ir)

    codegen = sub.add_parser("codegen", help="generate SwiftUI, React, or Rust Dioxus code from IR")
    codegen.add_argument("--json", action="store_true", help="print machine-readable JSON")
    codegen.add_argument("target", choices=["swiftui", "react", "rust"])
    codegen.add_argument("ir")
    codegen.add_argument("-o", "--out", required=True)
    codegen.set_defaults(func=cmd_codegen)

    ci = sub.add_parser("ci", help="run CI-style validation")
    ci.add_argument("--json", action="store_true", help="print machine-readable JSON")
    ci.add_argument("pen")
    ci.add_argument("actual")
    ci.add_argument("--threshold", type=float, default=0.9)
    ci.set_defaults(func=cmd_ci)

    review = sub.add_parser("review-report", help="explain a compare report in stable Markdown")
    review.add_argument("--json", action="store_true", help="print machine-readable JSON")
    review.add_argument("report")
    review.add_argument("-o", "--out", default=None)
    review.set_defaults(func=cmd_review_report)

    fix = sub.add_parser(
        "fix-report", help="suggest fixes from a compare report in stable Markdown"
    )
    fix.add_argument("--json", action="store_true", help="print machine-readable JSON")
    fix.add_argument("report")
    fix.add_argument("-o", "--out", default=None)
    fix.set_defaults(func=cmd_fix_report)

    demo = sub.add_parser("demo", help="write an end-to-end demo project")
    demo.add_argument("--json", action="store_true", help="print machine-readable JSON")
    demo.add_argument("--out", default="examples/generated-demo")
    demo.set_defaults(func=cmd_demo)
    return parser


def cmd_inspect(args: argparse.Namespace) -> int:
    result = inspect_pen(args.pen)
    _print(result, args.json)
    return 1 if result["errors"] else 0


def cmd_validate_pen(args: argparse.Namespace) -> int:
    issues = [asdict(issue) for issue in validate_pen_context(parse_pen(args.pen))]
    _print({"status": "PASS" if not _has_errors(issues) else "FAIL", "issues": issues}, args.json)
    return 1 if _has_errors(issues) else 0


def cmd_export_expected(args: argparse.Namespace) -> int:
    tree = write_expected_tree(args.pen, args.out)
    _print(
        {"out": args.out, "screens": len(tree["screens"]), "issues": len(tree["issues"])}, args.json
    )
    return 1 if _has_errors(tree["issues"]) else 0


def cmd_validate_actual(args: argparse.Namespace) -> int:
    issues = validate_actual_tree(load_tree(args.actual))
    _print({"status": "PASS" if not _has_errors(issues) else "FAIL", "issues": issues}, args.json)
    return 1 if _has_errors(issues) else 0


def cmd_compare_tree(args: argparse.Namespace) -> int:
    report = compare_tree_files(
        args.expected,
        args.actual,
        json_out=args.out,
        markdown_out=args.markdown,
        threshold=args.threshold,
    )
    _print(
        {
            "status": report["status"],
            "score": report["score"],
            "out": args.out,
            "markdown": args.markdown,
        },
        args.json,
    )
    return 0 if report["status"] == "PASS" else 1


def cmd_validate_flow(args: argparse.Namespace) -> int:
    issues = validate_flow_contract(load_tree(args.flow))
    _print({"status": "PASS" if not _has_errors(issues) else "FAIL", "issues": issues}, args.json)
    return 1 if _has_errors(issues) else 0


def cmd_validate_screen(args: argparse.Namespace) -> int:
    issues = validate_screen_contract(load_tree(args.screen))
    _print({"status": "PASS" if not _has_errors(issues) else "FAIL", "issues": issues}, args.json)
    return 1 if _has_errors(issues) else 0


def cmd_flow_to_screens(args: argparse.Namespace) -> int:
    flow = load_tree(args.flow)
    issues = validate_flow_contract(flow)
    if _has_errors(issues):
        _print({"status": "FAIL", "issues": issues}, args.json)
        return 1
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    for screen in screen_contracts_from_flow(flow):
        path = out / f"{screen['id']}.json"
        path.write_text(json.dumps(screen, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        paths.append(str(path))
    _print({"status": "PASS", "screens": paths}, args.json)
    return 0


def cmd_draft_pen(args: argparse.Namespace) -> int:
    write_pencil_draft(args.screen, args.out)
    _print({"status": "PASS", "out": args.out}, args.json)
    return 0


def cmd_update_pen(args: argparse.Namespace) -> int:
    update_pencil(args.pen, args.updates, args.out)
    _print({"status": "PASS", "out": args.out}, args.json)
    return 0


def cmd_extract_tokens(args: argparse.Namespace) -> int:
    tokens = extract_design_tokens(args.pen)
    if args.out:
        Path(args.out).write_text(
            json.dumps(tokens, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    _print(tokens | ({"out": args.out} if args.out else {}), args.json)
    return 0


def cmd_export_ir(args: argparse.Namespace) -> int:
    screen = load_tree(args.screen)
    expected = load_tree(args.expected) if args.expected else None
    ir = code_ir_from_contract(screen, expected)
    Path(args.out).write_text(json.dumps(ir, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _print({"status": "PASS", "out": args.out}, args.json)
    return 0


def cmd_codegen(args: argparse.Namespace) -> int:
    ir = load_tree(args.ir)
    generators = {"swiftui": swiftui, "react": react, "rust": rust_dioxus}
    Path(args.out).write_text(generators[args.target](ir), encoding="utf-8")
    _print({"status": "PASS", "out": args.out}, args.json)
    return 0


def cmd_ci(args: argparse.Namespace) -> int:
    expected_path = Path("expected-ui-tree.json")
    write_expected_tree(args.pen, expected_path)
    report = compare_tree_files(
        expected_path,
        args.actual,
        json_out="compare-report.json",
        markdown_out="compare-report.md",
        threshold=args.threshold,
    )
    _print({"status": report["status"], "score": report["score"]}, args.json)
    return 0 if report["status"] == "PASS" else 1


def cmd_review_report(args: argparse.Namespace) -> int:
    markdown = review_compare_report(args.report)
    if args.out:
        Path(args.out).write_text(markdown, encoding="utf-8")
    _print({"status": "PASS", "out": args.out, "markdown": markdown}, args.json)
    return 0


def cmd_fix_report(args: argparse.Namespace) -> int:
    markdown = fix_compare_report(args.report)
    if args.out:
        Path(args.out).write_text(markdown, encoding="utf-8")
    _print({"status": "PASS", "out": args.out, "markdown": markdown}, args.json)
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    files = build_demo(args.out)
    _print({"status": "PASS", "files": files}, args.json)
    return 0


def _print(data: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(data, indent=2, sort_keys=True))
        return
    if "status" in data:
        print(f"Status: {data['status']}")
    for key, value in data.items():
        if key == "status":
            continue
        print(f"{key}: {value}")


def _has_errors(issues: list[dict[str, Any]]) -> bool:
    return any(issue.get("severity") == "error" for issue in issues)


class PenflowError(RuntimeError):
    pass
