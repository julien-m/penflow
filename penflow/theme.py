# @spec(FR-001)
"""Theme loading from project CSS custom properties."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

# Maps theme.css custom-property names to pen variable names and types.
THEME_TOKEN_MAP = {
    "background": ("pf-background", "color"),
    "foreground": ("pf-foreground", "color"),
    "card": ("pf-card", "color"),
    "card-foreground": ("pf-card-foreground", "color"),
    "primary": ("pf-primary", "color"),
    "primary-foreground": ("pf-primary-foreground", "color"),
    "border": ("pf-border", "color"),
    "input": ("pf-input", "color"),
    "muted": ("pf-muted", "color"),
    "muted-foreground": ("pf-muted-foreground", "color"),
    "accent": ("pf-accent", "color"),
    "destructive": ("pf-destructive", "color"),
    "ring": ("pf-ring", "color"),
    "radius": ("pf-radius", "number"),
    "font-sans": ("pf-font-sans", "string"),
}

DEFAULT_STYLE = {
    "background": "#FFFFFF",
    "foreground": "#111827",
    "card": "#FFFFFF",
    "card_foreground": "#111827",
    "primary": "#0057FF",
    "primary_foreground": "#FFFFFF",
    "border": "#CBD5E1",
    "input": "#CBD5E1",
    "muted": "#F8FAFC",
    "muted_foreground": "#374151",
    "radius": 8,
    "font_sans": None,
}


def load_theme(theme_css_path: str | Path | None = None) -> dict[str, Any]:
    # @spec FR-001: Public theme loading — .specs/features/046-lint-design-tokens/spec.md#fr-001
    """Load a draft theme from a project theme.css, or the default theme.

    Args:
        theme_css_path: Path to a CSS file declaring `--token: value` custom
            properties. `None` returns the default theme.

    Returns:
        A theme dictionary `{"variables": {...}, "style": {...}}` where
        `variables` holds pen variable definitions and `style` holds per-token
        values (literal defaults or `$pf-*` variable references).

    Raises:
        FileNotFoundError: If `theme_css_path` is provided but missing.
    """
    if theme_css_path is None:
        return {"variables": {}, "style": dict(DEFAULT_STYLE)}
    path = Path(theme_css_path)
    if not path.exists():
        raise FileNotFoundError(f"theme CSS not found: {path}")
    raw_tokens = parse_css_custom_properties(path.read_text(encoding="utf-8"))
    variables: dict[str, dict[str, Any]] = {}
    style = dict(DEFAULT_STYLE)
    for source_name, (variable_name, variable_type) in THEME_TOKEN_MAP.items():
        raw_value = raw_tokens.get(source_name)
        if raw_value is None:
            continue
        value: Any = theme_number(raw_value) if variable_type == "number" else raw_value
        variables[variable_name] = {"type": variable_type, "value": value}
        style_name = source_name.replace("-", "_")
        style[style_name] = f"${variable_name}"
    return {"variables": variables, "style": style}


def parse_css_custom_properties(css: str) -> dict[str, str]:
    """Extract `--name: value` declarations from CSS text."""
    # Matches a CSS custom property declaration up to the value terminator.
    custom_property_re = re.compile(r"--([A-Za-z0-9_-]+)\s*:\s*([^;{}]+)")
    return {name: value.strip() for name, value in custom_property_re.findall(css)}


def theme_number(raw_value: str) -> int | float | str:
    """Convert a CSS numeric value (`rem`/`px`/bare) to pixels, else pass through."""
    value = raw_value.strip()
    if value.endswith("rem"):
        try:
            # 1rem = 16px, the browser default the draft pipeline assumes.
            return round(float(value[:-3]) * 16)
        except ValueError:
            return value
    if value.endswith("px"):
        try:
            return round(float(value[:-2]))
        except ValueError:
            return value
    try:
        return int(value)
    except ValueError:
        return value
