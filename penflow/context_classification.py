"""Exclusive semantic, inherited, and decorative context classification."""

from __future__ import annotations

from typing import Protocol


class ClassificationContext(Protocol):
    """Context fields consumed by classification validation."""

    classification: str | None
    semantic_id: str | None
    test_id: str | None
    role: str | None
    inherits_from: str | None
    relation: str | None
    decorative_owner: str | None
    decorative_reason: str | None
    action: str | None
    binding: str | None
    repeat: str | None


# @spec FR-001: Closed node classifications — .specs/features/076-exhaustive-bidirectional-semantic-context/spec.md#fr-001
def classification_errors(context: ClassificationContext) -> list[tuple[str, str]]:
    """Return stable error codes/messages for one exclusive classification."""
    classification = context.classification
    if classification not in {"semantic", "inherited", "decorative"}:
        return [("pencil.node_unclassified", "explicit classification required")]
    if classification == "semantic":
        return _semantic_errors(context)
    return _owned_errors(context, inherited=classification == "inherited")


def _semantic_errors(context: ClassificationContext) -> list[tuple[str, str]]:
    errors: list[tuple[str, str]] = []
    required = (
        (context.semantic_id, "pencil.semantic_id_missing", "semantic_id is required"),
        (context.test_id, "test_id.missing", "test_id is required"),
        (context.role, "pencil.semantic_role_missing", "role is required"),
    )
    errors.extend((code, message) for value, code, message in required if not value)
    if context.inherits_from or context.decorative_owner or context.decorative_reason:
        errors.append(
            ("pencil.classification_conflict", "semantic classification carries owner keys")
        )
    return errors


def _owned_errors(context: ClassificationContext, *, inherited: bool) -> list[tuple[str, str]]:
    owner = context.inherits_from if inherited else context.decorative_owner
    detail = context.relation if inherited else context.decorative_reason
    errors: list[tuple[str, str]] = []
    if not owner or not detail:
        code = "pencil.inheritance_incomplete" if inherited else "pencil.decoration_incomplete"
        errors.append((code, "owner and relation/reason are required"))
    independent = any(
        (context.semantic_id, context.test_id, context.action, context.binding, context.repeat)
    )
    interactive_decoration = not inherited and context.role in {
        "button",
        "link",
        "input",
        "select",
        "toggle",
    }
    if independent or interactive_decoration:
        errors.append(
            ("pencil.classification_conflict", "owned classification carries independent behavior")
        )
    return errors
