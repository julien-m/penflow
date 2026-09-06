"""Convert measured external facts to closed C51 values without expected-value input."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit


def ui(snapshot: dict[str, Any], semantic_id: str) -> dict[str, Any]:
    """Project one genuinely captured DOM node into the typed UI capability."""
    node = next(node for node in snapshot["nodes"] if node["semantic_id"] == semantic_id)
    return {
        "screen_id": snapshot["screen_id"],
        "state": snapshot["state"],
        **{
            key: node[key]
            for key in ("semantic_id", "role", "visible", "enabled", "text", "value", "bbox")
        },
        "properties": snapshot["properties"],
    }


def storage_facts(value: dict[str, Any]) -> dict[str, Any]:
    """Retain the actual SELECT process identity, excluding diagnostic row counts."""
    return {key: value[key] for key in ("store_id", "key", "exists", "value", "process_instance")}


def network(raw: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Project the real request URL path and response; retain full URL in raw evidence."""
    request, response = raw["network"]["request"], raw["network"]["response"]
    parsed = urlsplit(request["url"])
    path = parsed.path + (f"?{parsed.query}" if parsed.query else "")
    return (
        {
            "actor_id": request["headers"]["x-actor"],
            "method": request["method"],
            "url": path,
            "body": request["body"],
        },
        {"status": response["status"], "body": response["body"]},
    )


def guard_trace(raw: dict[str, Any], guard_id: str) -> tuple[dict[str, Any], str]:
    """Use actual app guard evaluation captured synchronously before UI transition."""
    (trace,) = raw["pre_transition"]
    if trace["response"] != raw["network"]["response"]["body"]:
        raise ValueError("pre-transition response differs from observed network bytes")
    if trace["snapshot"]["state"] != raw["before"]["state"]:
        raise ValueError("guard trace was not captured before the UI transition")
    return ui(trace["snapshot"], "checkout.pay"), "allowed" if trace["guard_results"][
        guard_id
    ] else "invalid"


def navigation(raw: dict[str, Any], event_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Express real browser history and disappearing surface facts, never a success flag."""
    before = ui(raw["before"], raw["before"]["screen_id"])
    nav = raw["navigation"]
    common = {"event": nav["event"], "event_id": event_id, "context_id": nav["context_id"]}
    before["navigation"] = {
        **common,
        "url": raw["before"]["url"],
        "previous_url": nav.get("previous_url"),
        "surface_present": before["visible"],
    }
    if nav["event"] == "back":
        after = ui(raw["after"], raw["after"]["screen_id"])
        after["navigation"] = {
            **common,
            "url": raw["after"]["url"],
            "previous_url": nav["previous_url"],
            "surface_present": nav["surface_present"],
        }
    else:
        # Identity locates the now-absent target; its unobservable state/geometry stay null.
        after = {
            "screen_id": before["screen_id"],
            "semantic_id": before["semantic_id"],
            "role": before["role"],
            "state": None,
            "bbox": None,
            "enabled": None,
            "text": None,
            "value": None,
            "visible": raw["after"]["visible"],
            "properties": {},
            "navigation": {
                **common,
                "url": raw["after"]["url"],
                "previous_url": None,
                "surface_present": raw["after"]["surface_present"],
            },
        }
    return before, after
