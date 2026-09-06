# @spec(FR-013)
"""Derive historical, explicitly synthetic visual reports from copied demo bytes."""

from __future__ import annotations

from typing import Any

# These descriptions belong to the frozen example, never to a fresh vision pass.
CRITERIA = {
    "visual_balance": "checkoutScreen.png uses one left-aligned content column with consistent margins and whitespace.",
    "rendering_artifacts": "checkoutScreen.png has no clipping, missing glyphs, broken images, or stray frame borders.",
    "readability": "All three visible labels in checkoutScreen.png are legible at one-to-one display scale.",
    "perceived_hierarchy": "checkoutScreen.png presents the title, supporting payment text, then the bright primary action.",
    "imagery_quality": "checkoutScreen.png contains crisp text and vector-style shapes with no low-quality photographic imagery.",
}


def visual_reports(
    screen: dict[str, Any], image_name: str, image_digest: str
) -> dict[str, dict[str, Any]]:
    """Build package-owned fixture envelopes bound to the copied image bytes.

    Args:
        screen: Demo expected screen, including Pencil identity and dimensions.
        image_name: Copied image's basename within the evidence directory.
        image_digest: SHA256 of those actual copied bytes.
    """
    bbox = screen["root"]["bbox"]
    identity = {
        "screen_id": screen["screen_id"],
        "semantic_id": screen["root"]["semantic_id"],
        "pencil_node_id": screen["pencil_id"],
        "surface": "web",
        "state": "default",
    }
    crop = {
        "x": 0,
        "y": 0,
        "width": int(bbox["width"]),
        "height": int(bbox["height"]),
        "source_width": int(bbox["width"]),
        "source_height": int(bbox["height"]),
    }
    context = {
        "identity": identity,
        "crop": crop,
        "image_name": image_name,
        "image_digest": image_digest,
        "run_id": f"static-demo-{image_digest[:24]}",
        "region_id": f"{screen['screen_id']}.main",
    }
    layout = {
        "screens": [
            {
                "screen_id": screen["screen_id"],
                "pencil_node_id": screen["pencil_id"],
                "width": bbox["width"],
                "height": bbox["height"],
            }
        ]
    }
    return {
        "manifest.json": _manifest(context),
        "layout-snapshot.json": layout,
        "vision-report.json": _vision(context),
    }


def _manifest(context: dict[str, Any]) -> dict[str, Any]:
    return {
        "renderer": "static-demo-fixture",
        "sourceFile": "ui.pen",
        "status": "PASS",
        "validatedAt": "2026-07-24",
        "runId": context["run_id"],
        "screens": [
            {
                **context["identity"],
                "regions": [{"region_id": context["region_id"], "crop": context["crop"]}],
                "png": context["image_name"],
                "sha256": context["image_digest"],
                "layout_checked": True,
                "screenshot_checked": True,
                "notes": "Synthetic example data packaged with Penflow as an immutable static-demo-fixture; not fresh runtime evidence.",
            }
        ],
    }


def _proof(context: dict[str, Any], category: str) -> dict[str, Any]:
    return {
        "run_id": context["run_id"],
        "surface": "web",
        "screen_id": context["identity"]["screen_id"],
        "region_id": context["region_id"],
        "state": "default",
        "assertion": category,
        "measurement": {"expected": "pass", "actual": "pass", "unit": "result"},
        "artifacts": [
            {
                "role": "actual",
                "file": context["image_name"],
                "sha256": context["image_digest"],
                "crop": context["crop"],
            }
        ],
    }


def _vision(context: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": 1,
        "kind": "penflow-vision-report",
        "status": "PASS",
        "runId": context["run_id"],
        "renderer": "static-demo-fixture",
        "sourceFile": "ui.pen",
        "model": "static-demo-fixture",
        "generated_by": "penflow.demo.static-demo-fixture",
        "inputs": [{"file": context["image_name"], "sha256": context["image_digest"]}],
        "validatedAt": "2026-07-24",
        "screens": [
            {
                **context["identity"],
                "region_id": context["region_id"],
                "png": context["image_name"],
                "criteria": [
                    {
                        "category": category,
                        "result": "pass",
                        "evidence": text,
                        "blocking": True,
                        "proof": _proof(context, category),
                    }
                    for category, text in CRITERIA.items()
                ],
            }
        ],
    }
