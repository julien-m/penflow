"""Stable visual metric issues and aggregate report serialization."""

from typing import Any

REPORT_KIND = "penflow-visual-metrics-report"
REPORT_VERSION = 1


def visual_metrics_report(
    issues: list[dict[str, Any]], nodes_checked: int, screens_checked: int, inputs: dict[str, Any]
) -> dict[str, Any]:
    """Return the established closed metric report from evaluated findings."""
    errors = sum(1 for issue in issues if issue["severity"] == "error")
    warnings = sum(1 for issue in issues if issue["severity"] == "warning")
    infos = sum(1 for issue in issues if issue["severity"] == "info")
    return {
        "version": REPORT_VERSION,
        "kind": REPORT_KIND,
        "status": "PASS" if errors == 0 else "FAIL",
        "summary": {
            "errors": errors,
            "warnings": warnings,
            "infos": infos,
            "nodes_checked": nodes_checked,
            "screens_checked": screens_checked,
        },
        "inputs": inputs,
        "issues": issues,
    }


def semantic_id(node: dict[str, Any]) -> str | None:
    """Read a flattened node's reporting identity.

    Args:
        node: Flattened node with an optional _semantic_key.

    Returns:
        The semantic key as text, or None when absent.
    """
    key = node.get("_semantic_key")
    return str(key) if key is not None else None


def visual_issue(
    code: str,
    severity: str,
    screen_id: str,
    node: dict[str, Any],
    message: str,
    **extra: Any,
) -> dict[str, Any]:
    """Create a visual diagnostic anchored to a screen and flattened node.

    Args:
        code: Stable diagnostic identifier.
        severity: Diagnostic severity.
        screen_id: Owning screen identity.
        node: Flattened node providing the semantic key.
        message: Human-readable explanation.
        extra: Additional measurement fields merged last into the new issue.

    Returns:
        A structured issue without mutating the supplied node or extra fields.
    """
    return {
        "code": code,
        "severity": severity,
        "screen_id": screen_id,
        "semantic_id": semantic_id(node),
        "message": message,
        **extra,
    }


def issue_sort_key(issue: dict[str, Any]) -> tuple[str, str, str, str]:
    """Provide the deterministic ordering key for visual diagnostics.

    Args:
        issue: Diagnostic containing code, screen identity and message.

    Returns:
        Code, screen ID, textual semantic ID and message in comparison order.
    """
    return (
        issue["code"],
        issue["screen_id"],
        str(issue.get("semantic_id", "")),
        issue["message"],
    )
