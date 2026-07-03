# @spec(FR-001)
"""Theme loading from project CSS custom properties."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

# Maps accepted theme.css custom-property names to pen variable names and types.
# CSS callers may use either `--name` or `--pf-name`; the exported pen
# variable name is always `pf-name`.
THEME_TOKEN_MAP = {
    "background": ("pf-background", "color"),
    "foreground": ("pf-foreground", "color"),
    "card": ("pf-card", "color"),
    "card-foreground": ("pf-card-foreground", "color"),
    "panel": ("pf-panel", "color"),
    "panel-2": ("pf-panel-2", "color"),
    "primary": ("pf-primary", "color"),
    "primary-foreground": ("pf-primary-foreground", "color"),
    "border": ("pf-border", "color"),
    "input": ("pf-input", "color"),
    "muted": ("pf-muted", "color"),
    "muted-foreground": ("pf-muted-foreground", "color"),
    "accent": ("pf-accent", "color"),
    "destructive": ("pf-destructive", "color"),
    "success": ("pf-success", "color"),
    "warning": ("pf-warning", "color"),
    "info": ("pf-info", "color"),
    "ring": ("pf-ring", "color"),
    "radius": ("pf-radius", "number"),
    "font-sans": ("pf-font-sans", "string"),
    "font-mono": ("pf-font-mono", "string"),
    "font-size-xs": ("pf-font-size-xs", "number"),
    "font-size-sm": ("pf-font-size-sm", "number"),
    "font-size-base": ("pf-font-size-base", "number"),
    "font-size-lg": ("pf-font-size-lg", "number"),
    "font-size-xl": ("pf-font-size-xl", "number"),
}

DEFAULT_STYLE = {
    "background": "#FFFFFF",
    "foreground": "#111827",
    "card": "#FFFFFF",
    "card_foreground": "#111827",
    "panel": "#FFFFFF",
    "panel_2": "#FFFFFF",
    "primary": "#0057FF",
    "primary_foreground": "#FFFFFF",
    "border": "#CBD5E1",
    "input": "#CBD5E1",
    "muted": "#F8FAFC",
    "muted_foreground": "#374151",
    "success": "#16A34A",
    "warning": "#D97706",
    "info": "#2563EB",
    "radius": 8,
    "font_sans": None,
    "font_mono": None,
    "font_size_xs": None,
    "font_size_sm": None,
    "font_size_base": None,
    "font_size_lg": None,
    "font_size_xl": None,
}


def load_theme(theme_css_path: str | Path | None = None) -> dict[str, Any]:
    # @spec FR-001: Public theme loading — .specs/features/046-lint-design-tokens/spec.md#fr-001
    """Load a draft theme from a project theme.css, or the default theme.

    Args:
        theme_css_path: Path to a CSS file declaring `--token: value` custom
            properties. `None` returns the default theme.

    Returns:
        A theme dictionary `{"variables": {...}, "style": {...}}` where
        `variables` holds pen variable definitions and `style` holds the
        stable format contract consumed by draft and lint callers. Accepted
        CSS names are the keys in `THEME_TOKEN_MAP`, their `--pf-*` aliases,
        and optional `--palette-*`/`--pf-palette-*` color slots.

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
        raw_value = _theme_token_value(raw_tokens, source_name)
        if raw_value is None:
            continue
        value: Any = theme_number(raw_value) if variable_type == "number" else raw_value
        variables[variable_name] = {"type": variable_type, "value": value}
        style_name = source_name.replace("-", "_")
        style[style_name] = f"${variable_name}"
    for source_name, raw_value in _palette_tokens(raw_tokens).items():
        variable_name = f"pf-{source_name}"
        variables[variable_name] = {"type": "color", "value": raw_value}
    for source_name, raw_value in _radius_tokens(raw_tokens).items():
        variable_name = f"pf-{source_name}"
        variables[variable_name] = {"type": "number", "value": theme_number(raw_value)}
    return {"variables": variables, "style": style}


def _theme_token_value(tokens: dict[str, str], source_name: str) -> str | None:
    raw_value = tokens.get(source_name)
    if raw_value is not None:
        return raw_value
    return tokens.get(f"pf-{source_name}")


def _palette_tokens(tokens: dict[str, str]) -> dict[str, str]:
    palette: dict[str, str] = {}
    for name, value in tokens.items():
        normalized = name[3:] if name.startswith("pf-palette-") else name
        if normalized.startswith("palette-"):
            palette[normalized] = value
    return palette


def _radius_tokens(tokens: dict[str, str]) -> dict[str, str]:
    radius: dict[str, str] = {}
    for name, value in tokens.items():
        normalized = name[3:] if name.startswith("pf-radius-") else name
        if normalized.startswith("radius-"):
            radius[normalized] = value
    return radius


def theme_fingerprint(theme_css_path: str | Path) -> dict[str, str]:
    # @spec FR-002: Shared raw-bytes SHA-256 helper — .specs/features/056-evidence-run-identity-theme-fingerprint/spec.md#fr-002
    """Fingerprint a theme CSS file as the SHA-256 of its raw bytes.

    No token parsing, no whitespace or encoding normalization: the digest is
    independently reproducible via ``shasum -a 256`` and any byte change
    (including CRLF/comment edits) changes it by design. Both the
    `theme-fingerprint` subcommand and the `validate-visual-evidence`
    `--theme-css` gate call this single helper.

    Args:
        theme_css_path: Path to the theme CSS file. Any readable file
            fingerprints — content is never validated (0-byte files included).

    Returns:
        ``{"path": <path as passed>, "sha256": <64 lowercase hex chars>}``.

    Raises:
        FileNotFoundError: If the path is missing or not a regular file
            (directories fail here too — fail closed).
        OSError: If the file exists but cannot be read.
    """
    path = Path(theme_css_path)
    if not path.is_file():
        raise FileNotFoundError(f"theme CSS not found: {path}")
    return {
        "path": str(theme_css_path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def parse_css_custom_properties(css: str) -> dict[str, str]:
    """Extract `--name: value` declarations from CSS text.

    Scope-aware: when one or more ``:root { ... }`` blocks exist, only their
    declarations are read so a shadcn-style ``.dark { ... }`` override block
    never replaces the light-mode (default) palette. Without any ``:root``
    block the whole text is scanned (token fragments stay supported). The
    first declaration of a name wins in both modes.
    """
    # Strip /* ... */ comments first so a commented-out `:root` or selector
    # fragment can never open or pollute a scope. Strings are not handled —
    # custom-property values with braces inside quotes are out of scope for
    # the draft palette (shadcn/tailwind themes never produce them).
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)
    # Matches a flat rule whose selector list contains `:root` and captures its
    # body (custom-property values never contain braces, see the regex below).
    root_block_re = re.compile(r"(?m)^[^{}]*:root[^{}]*\{([^}]*)\}")
    # Matches a CSS custom property declaration up to the value terminator.
    custom_property_re = re.compile(r"--([A-Za-z0-9_-]+)\s*:\s*([^;{}]+)")
    scopes = [match.group(1) for match in root_block_re.finditer(css)] or [css]
    tokens: dict[str, str] = {}
    for body in scopes:
        for name, value in custom_property_re.findall(body):
            # First declaration wins — later `.dark`/duplicate overrides are
            # runtime concerns, not part of the canonical draft palette.
            tokens.setdefault(name, value.strip())
    return tokens


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
