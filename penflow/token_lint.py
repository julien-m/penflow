# @spec(FR-003)
# @spec(FR-011)
"""Deterministic design-token lint for .pen files."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .color import parse_color, resolve_variable
from .models import PenNode
from .pen import all_nodes, load_pen, parse_pen

REPORT_KIND = "penflow-token-lint-report"
REPORT_VERSION = 1

# Documented default scales; penflow stays project-agnostic, so callers
# override these via CLI flags. Spacing matches the shared semantic spacing
# token scale (2xs..5xl); typography matches the common modular type ramp.
DEFAULT_SPACING_SCALE: tuple[float, ...] = (2, 4, 8, 12, 16, 24, 32, 40, 48, 64, 80)
DEFAULT_RADIUS_SCALE: tuple[float, ...] = (0, 2, 4, 6, 8, 10, 12, 16, 24, 32)
DEFAULT_FONTSIZE_SCALE: tuple[float, ...] = (12, 14, 16, 18, 20, 24, 30, 36)

_COLOR_PROPERTIES = ("fill", "stroke")
_SPACING_PROPERTIES = ("gap", "padding")


def lint_tokens(
    pen_path: str | Path,
    *,
    theme: dict[str, Any] | None = None,
    theme_css: str | None = None,
    spacing_scale: tuple[float, ...] | list[float] | None = None,
    radius_scale: tuple[float, ...] | list[float] | None = None,
    fontsize_scale: tuple[float, ...] | list[float] | None = None,
) -> dict[str, Any]:
    # @spec FR-003: Deterministic token lint engine — .specs/features/046-lint-design-tokens/spec.md#fr-003
    # @spec FR-007: Round-trip guarantee with drafted pens — .specs/features/046-lint-design-tokens/spec.md#fr-007
    """Lint a `.pen` file's visual values against a theme and numeric scales.

    Args:
        pen_path: Path to the `.pen` file.
        theme: Loaded theme (`penflow.theme.load_theme` shape). `None` disables
            palette and fontFamily checks.
        theme_css: Theme CSS path recorded in the report inputs.
        spacing_scale: Allowed gap/padding values; defaults to
            `DEFAULT_SPACING_SCALE`.
        radius_scale: Allowed cornerRadius values; defaults to
            `DEFAULT_RADIUS_SCALE` (resolved theme radius is always included).
        fontsize_scale: Allowed fontSize values; defaults to
            `DEFAULT_FONTSIZE_SCALE`.

    Returns:
        A strict token-lint report dictionary (`token-lint-report.schema.json`).
    """
    raw = load_pen(pen_path)
    raw_variables = raw.get("variables")
    variables: dict[str, Any] = raw_variables if isinstance(raw_variables, dict) else {}
    nodes = all_nodes(parse_pen(raw))
    spacing = tuple(spacing_scale) if spacing_scale is not None else DEFAULT_SPACING_SCALE
    radius = tuple(radius_scale) if radius_scale is not None else DEFAULT_RADIUS_SCALE
    fontsize = tuple(fontsize_scale) if fontsize_scale is not None else DEFAULT_FONTSIZE_SCALE
    palette, theme_font, theme_radius = _resolve_theme(theme)
    if theme_radius is not None and theme_radius not in radius:
        # Themed drafts must never flag their own radius token (round-trip rule).
        radius = (*radius, theme_radius)

    violations: list[dict[str, Any]] = _theme_violations(theme)
    for node in nodes:
        violations.extend(
            _node_violations(
                node,
                variables=variables,
                palette=palette,
                theme_font=theme_font,
                check_palette=theme is not None,
                spacing=spacing,
                radius=radius,
                fontsize=fontsize,
            )
        )
    violations.sort(
        key=lambda item: (item["node_id"], item["property"], item["code"], str(item["value"]))
    )
    errors = sum(1 for violation in violations if violation["severity"] == "error")
    warnings = sum(1 for violation in violations if violation["severity"] == "warning")
    return {
        "version": REPORT_VERSION,
        "kind": REPORT_KIND,
        "status": "PASS" if errors == 0 else "FAIL",
        "summary": {"errors": errors, "warnings": warnings, "nodes_checked": len(nodes)},
        "inputs": {
            "pen": str(pen_path),
            "theme_css": theme_css,
            "spacing_scale": [_scale_item(value) for value in spacing],
            "radius_scale": [_scale_item(value) for value in radius],
            "fontsize_scale": [_scale_item(value) for value in fontsize],
        },
        "violations": violations,
    }


def _theme_violations(theme: dict[str, Any] | None) -> list[dict[str, Any]]:
    # @spec FR-011: surface unparsable theme dimensions — .specs/features/049-strict-mode-default-blocking-drift/spec.md#fr-011
    """Warn when a numeric theme variable kept a raw string value.

    ``theme.theme_number`` falls back to the raw string when a CSS dimension
    cannot be parsed; that silent fallback surfaces here as a
    ``theme.value.unparsed`` warning violation.
    """
    if theme is None:
        return []
    raw_variables = theme.get("variables")
    variables: dict[str, Any] = raw_variables if isinstance(raw_variables, dict) else {}
    violations: list[dict[str, Any]] = []
    for name in sorted(variables):
        definition = variables[name]
        if (
            isinstance(definition, dict)
            and definition.get("type") == "number"
            and isinstance(definition.get("value"), str)
        ):
            violations.append(
                {
                    "code": "theme.value.unparsed",
                    "severity": "warning",
                    "node_id": "theme",
                    "semantic_id": None,
                    "property": name,
                    "value": definition["value"],
                    "message": f"theme variable {name} has an unparsable numeric value:"
                    f" {definition['value']!r}",
                }
            )
    return violations


def _resolve_theme(
    theme: dict[str, Any] | None,
) -> tuple[set[tuple[int, int, int, int]], str | None, float | None]:
    """Resolve a loaded theme into a color palette, reference font, and radius."""
    if theme is None:
        return set(), None, None
    raw_theme_variables = theme.get("variables")
    theme_variables: dict[str, Any] = (
        raw_theme_variables if isinstance(raw_theme_variables, dict) else {}
    )
    palette: set[tuple[int, int, int, int]] = set()
    theme_font: str | None = None
    theme_radius: float | None = None
    style = theme.get("style")
    for token, value in style.items() if isinstance(style, dict) else []:
        # Theme style values are `$pf-*` refs when sourced from theme.css.
        resolved = resolve_variable(value, theme_variables)
        if token == "font_sans":
            theme_font = resolved if isinstance(resolved, str) else None
            continue
        if token == "radius":
            theme_radius = float(resolved) if isinstance(resolved, (int, float)) else None
            continue
        if isinstance(resolved, str):
            parsed = parse_color(resolved)
            if parsed is not None:
                palette.add(parsed)
    return palette, theme_font, theme_radius


def _node_violations(
    node: PenNode,
    *,
    variables: dict[str, Any],
    palette: set[tuple[int, int, int, int]],
    theme_font: str | None,
    check_palette: bool,
    spacing: tuple[float, ...],
    radius: tuple[float, ...],
    fontsize: tuple[float, ...],
) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []

    def add(code: str, prop: str, value: Any, message: str) -> None:
        violations.append(
            {
                "code": code,
                "severity": "error",
                "node_id": node.id,
                "semantic_id": node.semantic_id,
                "property": prop,
                "value": value,
                "message": message,
            }
        )

    def resolve(prop: str, value: Any) -> Any:
        # Variable refs resolve through the pen variables block before any
        # palette/scale check; a miss is itself the violation and stops checks.
        if isinstance(value, str) and value.startswith("$"):
            resolved = resolve_variable(value, variables)
            if resolved is None:
                add(
                    "token.variable.unresolved",
                    prop,
                    value,
                    f"variable reference {value} has no definition in the pen variables block",
                )
            return resolved
        return value

    for prop in _COLOR_PROPERTIES:
        if prop not in node.visual:
            continue
        raw_value = node.visual[prop]
        # Drafted strokes are objects {"fill": ..., "thickness": ...}.
        color_value = raw_value.get("fill") if isinstance(raw_value, dict) else raw_value
        resolved = resolve(prop, color_value)
        if not check_palette or not isinstance(resolved, str):
            continue
        parsed = parse_color(resolved)
        if parsed is not None and parsed not in palette:
            add(
                "token.color.unknown",
                prop,
                color_value,
                f"color {resolved} is not in the resolved theme palette",
            )

    for prop in _SPACING_PROPERTIES:
        if prop not in node.visual:
            continue
        for value in _numeric_values(resolve(prop, node.visual[prop])):
            if value not in spacing:
                add(
                    "token.spacing.offscale",
                    prop,
                    value,
                    f"{prop} value {value} is not in the spacing scale",
                )

    if "cornerRadius" in node.visual:
        for value in _numeric_values(resolve("cornerRadius", node.visual["cornerRadius"])):
            if value not in radius:
                add(
                    "token.radius.offscale",
                    "cornerRadius",
                    value,
                    f"cornerRadius value {value} is not in the radius scale",
                )

    if "fontSize" in node.visual:
        for value in _numeric_values(resolve("fontSize", node.visual["fontSize"])):
            if value not in fontsize:
                add(
                    "token.fontsize.offscale",
                    "fontSize",
                    value,
                    f"fontSize value {value} is not in the typography scale",
                )

    if "fontFamily" in node.visual:
        resolved = resolve("fontFamily", node.visual["fontFamily"])
        if theme_font is not None and isinstance(resolved, str) and resolved != theme_font:
            add(
                "token.fontfamily.mismatch",
                "fontFamily",
                node.visual["fontFamily"],
                f"fontFamily {resolved!r} does not match the theme font {theme_font!r}",
            )

    return violations


def _numeric_values(value: Any) -> list[float]:
    if isinstance(value, bool):
        return []
    if isinstance(value, (int, float)):
        return [value]
    if isinstance(value, list):
        return [
            item for item in value if isinstance(item, (int, float)) and not isinstance(item, bool)
        ]
    return []


def _scale_item(value: float) -> int | float:
    # Report scales as ints when integral so JSON output stays stable.
    return int(value) if float(value).is_integer() else float(value)
