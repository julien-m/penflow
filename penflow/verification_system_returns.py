"""Evaluate typed external navigation facts for source-defined system events."""

from typing import Any

from .verification_schema import issue


def system_return_issues(
    observation: dict[str, Any], source: dict[str, Any]
) -> list[dict[str, Any]]:
    """Require observed disappearance, destination or real captured browser history."""
    before, after = observation["before"], observation["after"]
    old, new = before.get("navigation"), after.get("navigation")
    if observation["capability"] != "ui" or not isinstance(old, dict) or not isinstance(new, dict):
        return [
            issue(
                "outcome.system.navigation_missing",
                "navigation",
                "typed navigation facts are required",
            )
        ]
    if (
        any(
            value["event"] != source["event"] or value["event_id"] != source["id"]
            for value in (old, new)
        )
        or old["context_id"] != new["context_id"]
        or not old["surface_present"]
        or not before["visible"]
        or before["screen_id"] != source["screen_id"]
        or observation["result"]["outcome"] != "success"
    ):
        return [
            issue(
                "outcome.system.identity",
                "navigation",
                "observed event and source/context identity differ",
            )
        ]
    return _destination_issues(source, after, old, new)


def _destination_issues(
    source: dict[str, Any], after: dict[str, Any], old: dict[str, Any], new: dict[str, Any]
) -> list[dict[str, Any]]:
    destination = source["destination"]
    if destination["kind"] == "closed":
        passed = not after["visible"] and not new["surface_present"] and new["url"] is None
    elif destination["kind"] == "history":
        passed = (
            isinstance(old["previous_url"], str)
            and bool(old["previous_url"])
            and new["url"] == old["previous_url"]
            and new["surface_present"]
            and after["visible"]
        )
    else:
        passed = (
            new["surface_present"]
            and after["visible"]
            and after["screen_id"] == destination["screen_id"]
            and after["state"] == destination["state"]
        )
    return (
        []
        if passed
        else [
            issue(
                "outcome.system.destination",
                "after/navigation",
                "observed navigation did not reach its required destination",
            )
        ]
    )
