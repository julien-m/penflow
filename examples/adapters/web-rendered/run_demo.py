"""Exercise the authored design against two independent live browser observations."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from penflow.review_checks import check_workspace
from penflow.tree import expected_tree_from_pen, flatten_nodes


def run_demo(output: Path, *, node: str, playwright: str, browser: str | None) -> dict[str, Any]:
    """Capture deliberately bad and corrected DOM, compare and save local reports.

    Args:
        output: Caller-owned destination for the two captures and comparison reports.
        node: Existing Node.js executable.
        playwright: Existing Playwright module name or entrypoint path.
        browser: Optional existing Chromium-compatible executable.
    Returns:
        Observed metrics, real comparison outcomes, and unresolved observations.
    Raises:
        CalledProcessError: A browser capture failed; no observation is invented.
        TimeoutExpired: The external capture exceeded its bounded execution window.
        ValueError: Expected bad-to-corrected behavior was not observed.
    """
    # Local JSON is the repository's heterogeneous C12 report boundary, not an SDK object.
    fixture = Path(__file__).resolve().parent
    if output == fixture or fixture in output.parents:
        raise ValueError("Demo outputs must be outside the authored fixture directory")
    output.mkdir(parents=True, exist_ok=True)
    design = expected_tree_from_pen(fixture / "ui.pen")
    typography_ids = {
        item.get("semantic_id") or item["id"]
        for screen in design["screens"]
        for item in flatten_nodes(screen["root"])
        if "fontSize" in item.get("visual", {})
    }
    results: dict[str, Any] = {}
    for name, query in (("oversized", "?oversized"), ("corrected", "")):
        workspace = output / name
        workspace.mkdir(exist_ok=True)
        for source in ("ui.pen", "design-profile.json"):
            shutil.copyfile(fixture / source, workspace / source)
        actual_path = workspace / "actual-ui-tree.json"
        command = [
            node,
            str(fixture / "capture.mjs"),
            (fixture / "index.html").as_uri() + query,
            str(actual_path),
            "640",
            "400",
            playwright,
        ]
        if browser is not None:
            command.append(browser)
        subprocess.run(command, check=True, timeout=45, capture_output=True, text=True)
        actual = json.loads(actual_path.read_text())
        check = check_workspace(workspace, project_root=output)
        (workspace / "check-report.json").write_text(json.dumps(check, indent=2) + "\n")
        rendered = next(item for item in check["checks"] if item["name"] == "compare-rendered")
        report = {**rendered["details"], "issues": rendered["issues"]}
        results[name] = {
            "status": report["status"],
            "check_exit": check["exit"],
            "checks": {
                item["name"]: {"status": item["status"], "exit": item["exit_code"]}
                for item in check["checks"]
            },
            "material_codes": [
                item["code"] for item in report["issues"] if item.get("outcome") == "MATERIAL_DRIFT"
            ],
            "material_findings": [
                {"code": item["code"], "semantic_id": item.get("semantic_id")}
                for item in report["issues"]
                if item.get("outcome") == "MATERIAL_DRIFT"
            ],
            "unverified_codes": [
                item["code"] for item in report["issues"] if item.get("outcome") == "NOT_OBSERVED"
            ],
            "controls": [
                {"id": item["id"], "bbox": item["bbox"], "visual": item["visual"]}
                for screen in actual["screens"]
                for item in flatten_nodes(screen["root"])
                if item["role"] == "button"
            ],
            "capture": actual["capture"],
        }
    if results["oversized"]["status"] != "MATERIAL_DRIFT":
        raise ValueError("The deliberately oversized rendered control was not detected")
    if not any(
        item["code"] == "node.visual.fontSize" and item["semantic_id"] in typography_ids
        for item in results["oversized"]["material_findings"]
    ):
        raise ValueError("The native text label's rendered typography fault was not detected")
    if results["corrected"]["status"] not in {"CONFORMING", "NOT_OBSERVED"}:
        raise ValueError("The corrected rendered control still has material or measurement errors")
    if results["corrected"]["material_codes"]:
        raise ValueError("The corrected rendered control still has material findings")
    if results["oversized"]["check_exit"] != 1 or results["corrected"]["check_exit"] != 0:
        raise ValueError(
            "The normal workspace check did not reject the fault and accept correction"
        )
    summary = {"kind": "penflow-web-rendered-demo", "version": 1, "results": results}
    (output / "demo-result.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def main() -> None:
    """Parse explicit output/tool choices and print the observed comparison summary."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--node", default="node")
    parser.add_argument("--playwright", default="playwright")
    parser.add_argument("--browser")
    args = parser.parse_args()
    print(
        json.dumps(
            run_demo(
                args.out.resolve(), node=args.node, playwright=args.playwright, browser=args.browser
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
