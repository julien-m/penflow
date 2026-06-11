# @spec(AC-001)
# @spec(FR-007)
"""Regression tests for deterministic design-token lint reports and CLI behavior."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from penflow.cli import main
from penflow.color import parse_color, resolve_variable
from penflow.contracts import extract_design_tokens
from penflow.theme import load_theme, parse_css_custom_properties
from penflow.token_lint import (
    DEFAULT_FONTSIZE_SCALE,
    DEFAULT_RADIUS_SCALE,
    DEFAULT_SPACING_SCALE,
    lint_tokens,
)

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "examples" / "demo" / "semantic-ui-tree.json"

THEME_CSS = """:root {
  --background: #f6f4ef;
  --foreground: #25302a;
  --card: #ffffff;
  --primary: #0f5132;
  --primary-foreground: #fffaf0;
  --border: #d7d2c8;
  --muted: #ebe6da;
  --muted-foreground: #6a655c;
  --radius: 0.5rem;
  --font-sans: Inter, system-ui, sans-serif;
}
"""


def _semantic_tree_path(tmp_path: Path) -> Path:
    tree = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    tree["source"].pop("mockup", None)
    for screen in tree["screens"]:
        screen["source_map"].pop("mockup", None)
        stack = [screen["root"]]
        while stack:
            node = stack.pop()
            node.get("source_map", {}).pop("mockup", None)
            stack.extend(node.get("children", []) or [])
    path = tmp_path / "semantic-ui-tree.json"
    path.write_text(json.dumps(tree), encoding="utf-8")
    return path


def _theme_path(tmp_path: Path) -> Path:
    path = tmp_path / "theme.css"
    path.write_text(THEME_CSS, encoding="utf-8")
    return path


def _write_pen(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / "fixture.pen"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _violation_pen(**node_overrides: object) -> dict:
    node: dict[str, object] = {
        "id": "screen1",
        "type": "frame",
        "context": "semantic_id=s1; role=screen",
        "children": [],
    }
    node.update(node_overrides)
    return {
        "version": "2.11",
        "variables": {"pf-primary": {"type": "color", "value": "#0F5132"}},
        "children": [node],
    }


def test_parse_color_normalizes_hex_forms() -> None:
    assert parse_color("#0AF") == (0, 170, 255, 255)
    assert parse_color("#00AAFF") == (0, 170, 255, 255)
    assert parse_color("#00AAFF80") == (0, 170, 255, 128)
    assert parse_color("#00aaff") == (0, 170, 255, 255)
    assert parse_color("blue") is None
    assert parse_color("#12") is None
    assert parse_color("$pf-primary") is None


def test_resolve_variable_resolves_pf_refs() -> None:
    variables = {"pf-primary": {"type": "color", "value": "#0F5132"}}
    assert resolve_variable("$pf-primary", variables) == "#0F5132"
    assert resolve_variable("$pf-missing", variables) is None
    assert resolve_variable("#FFFFFF", variables) == "#FFFFFF"
    assert resolve_variable(12, variables) == 12


def test_load_theme_matches_legacy_shapes(tmp_path: Path) -> None:
    default = load_theme(None)
    assert default["variables"] == {}
    assert default["style"]["primary"] == "#0057FF"
    themed = load_theme(_theme_path(tmp_path))
    assert themed["variables"]["pf-primary"] == {"type": "color", "value": "#0f5132"}
    assert themed["variables"]["pf-radius"] == {"type": "number", "value": 8}
    assert themed["style"]["primary"] == "$pf-primary"
    with pytest.raises(FileNotFoundError):
        load_theme(tmp_path / "missing.css")


DARK_AUGMENTED_THEME_CSS = (
    THEME_CSS
    + """
.dark {
  --background: #0b1120;
  --foreground: #e2e8f0;
  --primary: #3b82f6;
}
"""
)


def test_dark_block_never_overrides_root_light_values(tmp_path: Path) -> None:
    # Invariant: `:root` (light mode) is the canonical palette propagated to
    # drafted pens and lint; a shadcn-style `.dark { ... }` override block must
    # never replace it — otherwise every themed mockup ships the dark palette.
    path = tmp_path / "theme.css"
    path.write_text(DARK_AUGMENTED_THEME_CSS, encoding="utf-8")
    themed = load_theme(path)
    assert themed["variables"]["pf-primary"] == {"type": "color", "value": "#0f5132"}
    assert themed["variables"]["pf-background"] == {"type": "color", "value": "#f6f4ef"}
    assert themed["variables"]["pf-foreground"] == {"type": "color", "value": "#25302a"}


def test_parse_css_custom_properties_without_root_scans_whole_text() -> None:
    # Invariant: token fragments without any `:root` block must keep parsing
    # (backward compatibility with non-shadcn theme files).
    tokens = parse_css_custom_properties("--primary: #123456;\n--radius: 0.5rem;")
    assert tokens == {"primary": "#123456", "radius": "0.5rem"}


def test_parse_css_custom_properties_ignores_commented_root_block() -> None:
    # Invariant: a `:root` block inside a /* comment */ must never open a
    # scope — only the live `:root` declarations feed the draft palette.
    css = """
/* :root { --primary: #DEAD00; } */
:root { --primary: #123456; }
.dark { --primary: #3b82f6; }
"""
    assert parse_css_custom_properties(css) == {"primary": "#123456"}


def test_lint_accepts_root_palette_color_despite_dark_block(tmp_path: Path) -> None:
    # Invariant: a pen legitimately using a light `:root` color must lint clean
    # even when the theme file also declares `.dark` overrides (GAP-046-01:
    # the dark palette used to win and flag `:root` colors as unknown).
    theme_path = tmp_path / "theme.css"
    theme_path.write_text(DARK_AUGMENTED_THEME_CSS, encoding="utf-8")
    pen_path = tmp_path / "ui.pen"
    pen_path.write_text(
        json.dumps(
            {
                "version": 1,
                "children": [
                    {"id": "btn", "type": "frame", "fill": "#0f5132"},
                ],
            }
        ),
        encoding="utf-8",
    )
    report_path = tmp_path / "report.json"
    assert (
        main(
            [
                "lint-tokens",
                str(pen_path),
                "--theme-css",
                str(theme_path),
                "--out",
                str(report_path),
                "--json",
            ]
        )
        == 0
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "PASS"
    assert report["violations"] == []


def test_round_trip_drafted_pen_with_theme_passes(tmp_path: Path) -> None:
    tree_path = _semantic_tree_path(tmp_path)
    theme_path = _theme_path(tmp_path)
    pen_path = tmp_path / "ui.pen"
    report_path = tmp_path / "token-lint-report.json"

    assert (
        main(
            [
                "draft-pen-from-tree",
                str(tree_path),
                "--out",
                str(pen_path),
                "--theme-css",
                str(theme_path),
                "--json",
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "lint-tokens",
                str(pen_path),
                "--theme-css",
                str(theme_path),
                "--out",
                str(report_path),
                "--json",
            ]
        )
        == 0
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "PASS"
    assert report["violations"] == []
    assert report["summary"]["errors"] == 0


def test_round_trip_drafted_pen_without_theme_passes(tmp_path: Path) -> None:
    tree_path = _semantic_tree_path(tmp_path)
    pen_path = tmp_path / "ui.pen"
    report_path = tmp_path / "report.json"

    assert main(["draft-pen-from-tree", str(tree_path), "--out", str(pen_path), "--json"]) == 0
    assert main(["lint-tokens", str(pen_path), "--out", str(report_path), "--json"]) == 0
    assert json.loads(report_path.read_text(encoding="utf-8"))["status"] == "PASS"


def test_off_palette_fill_reports_color_unknown(tmp_path: Path) -> None:
    pen = _write_pen(tmp_path, _violation_pen(fill="#FF00AA"))
    report = lint_tokens(pen, theme=load_theme(_theme_path(tmp_path)))
    assert report["status"] == "FAIL"
    violation = report["violations"][0]
    assert violation["code"] == "token.color.unknown"
    assert violation["severity"] == "error"
    assert violation["node_id"] == "screen1"
    assert violation["semantic_id"] == "s1"
    assert violation["property"] == "fill"
    assert violation["value"] == "#FF00AA"


def test_stroke_object_fill_is_checked_against_palette(tmp_path: Path) -> None:
    pen = _write_pen(tmp_path, _violation_pen(stroke={"fill": "#123456", "thickness": 1}))
    report = lint_tokens(pen, theme=load_theme(_theme_path(tmp_path)))
    assert [v["code"] for v in report["violations"]] == ["token.color.unknown"]
    assert report["violations"][0]["property"] == "stroke"


def test_off_scale_padding_reports_spacing_offscale(tmp_path: Path) -> None:
    pen = _write_pen(tmp_path, _violation_pen(padding=13))
    report = lint_tokens(pen)
    assert [v["code"] for v in report["violations"]] == ["token.spacing.offscale"]
    assert report["violations"][0]["value"] == 13


def test_padding_list_checks_every_element(tmp_path: Path) -> None:
    pen = _write_pen(tmp_path, _violation_pen(padding=[12, 17]))
    report = lint_tokens(pen)
    assert [(v["code"], v["value"]) for v in report["violations"]] == [
        ("token.spacing.offscale", 17)
    ]


def test_spacing_scale_override_is_authoritative(tmp_path: Path) -> None:
    pen = _write_pen(tmp_path, _violation_pen(padding=13))
    report = lint_tokens(pen, spacing_scale=(13, 26))
    assert report["status"] == "PASS"
    assert report["inputs"]["spacing_scale"] == [13, 26]


def test_off_scale_corner_radius_reports_radius_offscale(tmp_path: Path) -> None:
    pen = _write_pen(tmp_path, _violation_pen(cornerRadius=7))
    report = lint_tokens(pen)
    assert [v["code"] for v in report["violations"]] == ["token.radius.offscale"]


def test_theme_radius_is_auto_included_in_radius_scale(tmp_path: Path) -> None:
    theme_path = tmp_path / "theme.css"
    theme_path.write_text(":root { --radius: 0.875rem; }", encoding="utf-8")
    pen = _write_pen(tmp_path, _violation_pen(cornerRadius=14))
    report = lint_tokens(pen, theme=load_theme(theme_path))
    assert report["status"] == "PASS"
    assert 14 in report["inputs"]["radius_scale"]


def test_off_scale_font_size_reports_fontsize_offscale(tmp_path: Path) -> None:
    pen = _write_pen(tmp_path, _violation_pen(fontSize=17))
    report = lint_tokens(pen)
    assert [v["code"] for v in report["violations"]] == ["token.fontsize.offscale"]
    assert report["inputs"]["fontsize_scale"] == list(DEFAULT_FONTSIZE_SCALE)


def test_raw_font_family_reports_fontfamily_mismatch(tmp_path: Path) -> None:
    pen = _write_pen(tmp_path, _violation_pen(fontFamily="Comic Sans MS"))
    report = lint_tokens(pen, theme=load_theme(_theme_path(tmp_path)))
    assert [v["code"] for v in report["violations"]] == ["token.fontfamily.mismatch"]


def test_font_family_not_checked_without_theme_font(tmp_path: Path) -> None:
    pen = _write_pen(tmp_path, _violation_pen(fontFamily="Comic Sans MS"))
    assert lint_tokens(pen)["status"] == "PASS"


def test_unresolved_variable_reports_variable_unresolved(tmp_path: Path) -> None:
    pen = _write_pen(tmp_path, _violation_pen(fill="$pf-missing"))
    report = lint_tokens(pen)
    violation = report["violations"][0]
    assert violation["code"] == "token.variable.unresolved"
    assert violation["severity"] == "error"
    assert violation["value"] == "$pf-missing"


def test_resolved_variable_is_checked_against_palette(tmp_path: Path) -> None:
    data = _violation_pen(fill="$pf-primary")
    data["variables"] = {"pf-primary": {"type": "color", "value": "#FF00AA"}}
    pen = _write_pen(tmp_path, data)
    report = lint_tokens(pen, theme=load_theme(_theme_path(tmp_path)))
    assert [v["code"] for v in report["violations"]] == ["token.color.unknown"]


def test_report_is_deterministic(tmp_path: Path) -> None:
    pen = _write_pen(
        tmp_path, _violation_pen(fill="#FF00AA", padding=13, cornerRadius=7, fontSize=17)
    )
    theme = load_theme(_theme_path(tmp_path))
    first = json.dumps(lint_tokens(pen, theme=theme), sort_keys=True)
    second = json.dumps(lint_tokens(pen, theme=theme), sort_keys=True)
    assert first == second
    violations = lint_tokens(pen, theme=theme)["violations"]
    keys = [(v["node_id"], v["property"], v["code"], str(v["value"])) for v in violations]
    assert keys == sorted(keys)


def test_cli_exit_codes_for_usage_and_io_errors(tmp_path: Path) -> None:
    pen = _write_pen(tmp_path, _violation_pen())
    assert main(["lint-tokens", str(tmp_path / "missing.pen")]) == 2
    assert main(["lint-tokens", str(pen), "--theme-css", str(tmp_path / "missing.css")]) == 2
    assert main(["lint-tokens", str(pen), "--spacing-scale", ""]) == 2
    assert main(["lint-tokens", str(pen), "--spacing-scale", "a,b"]) == 2


def test_cli_fail_exit_code_on_violation(tmp_path: Path) -> None:
    pen = _write_pen(tmp_path, _violation_pen(padding=13))
    report_path = tmp_path / "report.json"
    assert main(["lint-tokens", str(pen), "--out", str(report_path), "--json"]) == 1
    assert json.loads(report_path.read_text(encoding="utf-8"))["status"] == "FAIL"


def test_generated_report_validates_against_bundled_schema(tmp_path: Path) -> None:
    pen = _write_pen(tmp_path, _violation_pen(padding=13))
    report_path = tmp_path / "token-lint-report.json"
    main(["lint-tokens", str(pen), "--out", str(report_path), "--json"])
    assert main(["validate-report", str(report_path), "--schema", "--json"]) == 0


def test_report_schema_fails_closed_on_additional_property(tmp_path: Path) -> None:
    pen = _write_pen(tmp_path, _violation_pen())
    report_path = tmp_path / "token-lint-report.json"
    main(["lint-tokens", str(pen), "--out", str(report_path), "--json"])
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["unexpected"] = True
    report_path.write_text(json.dumps(report), encoding="utf-8")
    assert main(["validate-report", str(report_path), "--schema", "--json"]) == 1


def test_extract_design_tokens_theme_param_adds_violations(tmp_path: Path) -> None:
    pen = _write_pen(tmp_path, _violation_pen(fill="#FF00AA"))
    theme = load_theme(_theme_path(tmp_path))
    legacy = extract_design_tokens(pen)
    assert "violations" not in legacy
    themed = extract_design_tokens(pen, theme=theme)
    assert [v["code"] for v in themed["violations"]] == ["token.color.unknown"]
    assert {key for key in legacy} <= {key for key in themed}


def test_extract_design_tokens_handles_stroke_objects(tmp_path: Path) -> None:
    pen = _write_pen(tmp_path, _violation_pen(stroke={"fill": "#D7D2C8", "thickness": 1}))
    tokens = extract_design_tokens(pen)
    assert "#D7D2C8" in tokens["colors"]


def test_default_scales_match_documented_values() -> None:
    assert DEFAULT_SPACING_SCALE == (2, 4, 8, 12, 16, 24, 32, 40, 48, 64, 80)
    assert DEFAULT_RADIUS_SCALE == (0, 2, 4, 6, 8, 10, 12, 16, 24, 32)
    assert DEFAULT_FONTSIZE_SCALE == (12, 14, 16, 18, 20, 24, 30, 36)
