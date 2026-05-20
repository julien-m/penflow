"""Pencil context grammar parsing and validation."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

ALLOWED_KEYS = {
    "semantic_id",
    "role",
    "intent",
    "binding",
    "repeat",
    "entity",
    "variant",
    "test_id",
    "mask",
    "mask_text",
    "tolerance",
}

ROLE_ALIASES = {
    "frame": "container",
    "text": "text",
    "icon_font": "icon",
    "rectangle": "shape",
    "ellipse": "shape",
    "ref": "component",
}

PLATFORM_WORDS = {
    "swiftui",
    "uikit",
    "react",
    "jsx",
    "tsx",
    "css",
    "android",
    "compose",
    "dioxus",
    "leptos",
    "xcode",
    "playwright",
}

IDENT_RE = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$")
BINDING_RE = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")


@dataclass(slots=True)
class ContextIssue:
    severity: str
    code: str
    message: str
    node_id: str | None = None
    semantic_id: str | None = None


@dataclass(slots=True)
class Context:
    semantic_id: str | None = None
    role: str | None = None
    intent: str | None = None
    binding: str | None = None
    repeat: str | None = None
    entity: str | None = None
    variant: str | None = None
    test_id: str | None = None
    mask: bool | str | None = None
    mask_text: bool | str | None = None
    tolerance: dict[str, Any] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_raw(cls, raw: Any) -> "Context":
        if raw is None:
            return cls()
        if isinstance(raw, str):
            raw = parse_context_string(raw)
        if not isinstance(raw, dict):
            return cls(extra={"_invalid_raw": raw})
        known = {key: raw.get(key) for key in ALLOWED_KEYS if key in raw}
        extra = {key: value for key, value in raw.items() if key not in ALLOWED_KEYS}
        tolerance = known.pop("tolerance", {}) or {}
        if not isinstance(tolerance, dict):
            extra["_invalid_tolerance"] = tolerance
            tolerance = {}
        return cls(**known, tolerance=tolerance, extra=extra)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {}
        for key in sorted(ALLOWED_KEYS - {"tolerance"}):
            value = getattr(self, key)
            if value not in (None, ""):
                data[key] = value
        if self.tolerance:
            data["tolerance"] = self.tolerance
        return data


def parse_context_string(raw: str) -> dict[str, Any]:
    """Parse `key=value; key=value` context shorthand."""

    result: dict[str, Any] = {}
    for part in re.split(r"[;\n]+", raw):
        item = part.strip()
        if not item:
            continue
        if "=" not in item:
            result[item] = True
            continue
        key, value = item.split("=", 1)
        result[key.strip()] = value.strip()
    return result


def infer_role(node_type: str, context: Context) -> str:
    if context.role:
        return str(context.role)
    return ROLE_ALIASES.get(node_type, node_type)


def validate_context(node_id: str, node_type: str, context: Context) -> list[ContextIssue]:
    issues: list[ContextIssue] = []
    semantic_id = context.semantic_id

    if context.extra:
        keys = ", ".join(sorted(context.extra))
        issues.append(ContextIssue("warning", "context.extra_keys", f"unknown context keys: {keys}", node_id))

    if semantic_id and not IDENT_RE.match(str(semantic_id)):
        issues.append(
            ContextIssue(
                "error",
                "context.semantic_id_format",
                "semantic_id must be lowercase dotted/kebab/snake identifier",
                node_id,
                str(semantic_id),
            )
        )

    role = infer_role(node_type, context)
    if role == "button" and not context.intent:
        issues.append(
            ContextIssue(
                "error",
                "context.button_intent_missing",
                "button context requires intent",
                node_id,
                semantic_id,
            )
        )

    if role in {"list", "list_item"} and not context.repeat:
        issues.append(
            ContextIssue(
                "error",
                "context.list_repeat_missing",
                "list context requires repeat",
                node_id,
                semantic_id,
            )
        )

    if context.binding and not BINDING_RE.match(str(context.binding)):
        issues.append(
            ContextIssue(
                "error",
                "context.binding_format",
                "binding must use entity.field syntax",
                node_id,
                semantic_id,
            )
        )

    lowered = " ".join(str(value).lower() for value in context.to_dict().values())
    found_platforms = sorted(word for word in PLATFORM_WORDS if word in lowered)
    if found_platforms:
        issues.append(
            ContextIssue(
                "error",
                "context.platform_coupling",
                f"context must not include platform/runtime code terms: {', '.join(found_platforms)}",
                node_id,
                semantic_id,
            )
        )

    return issues
