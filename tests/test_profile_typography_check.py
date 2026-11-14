"""Exact product typography reaches the ordinary check without hiding independent findings."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from penflow.review_checks import check_workspace

FIXTURE = Path(__file__).resolve().parents[1] / "examples/adapters/web-rendered"


def workspace(tmp_path: Path, *, font_size: float = 13, scale: list | None = None) -> Path:
    for name in ("ui.pen", "design-profile.json"):
        shutil.copyfile(FIXTURE / name, tmp_path / name)
    path = tmp_path / "ui.pen"
    pen = json.loads(path.read_text())
    pending = list(pen["children"])
    while pending:
        node = pending.pop()
        if node["type"] == "text":
            node["fontSize"] = font_size
        pending.extend(node.get("children", []))
    path.write_text(json.dumps(pen))
    if scale is not None:
        profile_path = tmp_path / "design-profile.json"
        profile = json.loads(profile_path.read_text())
        profile["typography"] = {
            "font_size_scale": scale,
            "source": "product-conventions#compact-web-typography",
        }
        profile_path.write_text(json.dumps(profile))
    return tmp_path


def write_theme(path: Path, font_tokens: str) -> None:
    """Keep the fixture's independent palette/fonts complete when testing type policy."""
    (path / "theme.css").write_text(
        ":root { --font-sans: Arial; --primary: #253b53; --foreground: #ffffff; "
        + font_tokens
        + " }"
    )


def checks(path: Path) -> dict:
    return {item["name"]: item for item in check_workspace(path)["checks"]}


@pytest.mark.parametrize("size", [13, 15])
def test_exact_product_scale_accepts_real_native_label(tmp_path: Path, size: float) -> None:
    path = workspace(tmp_path, font_size=size, scale=[size])
    before = {p.name: p.read_bytes() for p in path.iterdir()}
    result = checks(path)
    assert result["lint-tokens"]["status"] == "PASS"
    assert result["lint-tokens"]["details"]["inputs"]["fontsize_scale"] == [size]
    assert {p.name: p.read_bytes() for p in path.iterdir()} == before


@pytest.mark.parametrize("size", [14, 16])
def test_exact_profile_does_not_union_default_or_theme_sizes(tmp_path: Path, size: float) -> None:
    path = workspace(tmp_path, font_size=size, scale=[13])
    write_theme(path, f"--font-size-sm: {size}px;")
    result = checks(path)
    assert result["lint-tokens"]["status"] == "FAIL"
    assert result["lint-tokens"]["details"]["inputs"]["fontsize_scale"] == [13]
    assert any(
        item["code"] == "token.fontsize.offscale" for item in result["lint-tokens"]["issues"]
    )
    assert result["typography-scale"]["status"] == "FAIL"
    issue = result["typography-scale"]["issues"][0]
    assert issue["code"] == "profile.typography.theme_conflict"
    assert issue["value"] == size
    assert issue["allowed_values"] == [13]


def test_theme_conflict_is_explicit_even_when_source_label_is_valid(tmp_path: Path) -> None:
    path = workspace(tmp_path, scale=[13])
    write_theme(path, "--font-size-sm: 14px;")
    report = check_workspace(path)
    result = {item["name"]: item for item in report["checks"]}
    assert result["lint-tokens"]["status"] == "PASS"
    assert result["typography-scale"]["status"] == "FAIL"
    assert report["exit"] == 1


def test_matching_theme_and_profile_share_the_exact_scale(tmp_path: Path) -> None:
    path = workspace(tmp_path, scale=[13, 14])
    write_theme(path, "--font-size-sm: 13px; --font-size-base: 14px;")
    result = checks(path)
    assert result["typography-scale"]["status"] == "PASS"
    assert result["lint-tokens"]["status"] == "PASS"
    assert result["lint-tokens"]["details"]["fontsize_scale_origin"] == "profile-exact"
    assert result["lint-tokens"]["details"]["inputs"]["fontsize_scale"] == [13, 14]


@pytest.mark.parametrize("profile_present", [True, False])
def test_absent_exact_scale_retains_legacy_theme_extension(
    tmp_path: Path, profile_present: bool
) -> None:
    path = workspace(tmp_path)
    if not profile_present:
        (path / "design-profile.json").unlink()
    assert checks(path)["lint-tokens"]["status"] == "FAIL"
    write_theme(path, "--font-size-sm: 13px;")
    result = checks(path)
    assert result["lint-tokens"]["status"] == "PASS"
    assert 13 in result["lint-tokens"]["details"]["inputs"]["fontsize_scale"]
    assert result["lint-tokens"]["details"]["fontsize_scale_origin"] == "theme-plus-defaults"
    assert "typography-scale" not in result


@pytest.mark.parametrize("scale", [[], [0], [-1], [True], ["13"], [13, 13], [13, 13.0], [10**400]])
def test_invalid_scale_never_masks_independent_design_checks(tmp_path: Path, scale: list) -> None:
    path = workspace(tmp_path, font_size=14, scale=scale)
    result = checks(path)
    assert result["design-profile"]["status"] == "ERROR"
    assert result["lint-tokens"]["status"] == "PASS"
    assert (
        result["lint-tokens"]["details"]["fontsize_scale_origin"]
        == "legacy-fallback-invalid-profile"
    )
    assert result["validate-pen"]["status"] == "PASS"
    assert result["check-consistency"]["exit_code"] is not None
    assert result["audit-visual"]["exit_code"] is not None


@pytest.mark.parametrize("number", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_scale_is_rejected_by_json_and_direct_profile_boundary(
    tmp_path: Path, number: float
) -> None:
    from penflow.design_profile import validate_profile

    path = workspace(tmp_path, font_size=14, scale=[number])
    result = checks(path)
    assert result["design-profile-input"]["status"] == "ERROR"
    assert result["lint-tokens"]["status"] == "PASS"
    profile = json.loads((path / "design-profile.json").read_text())
    with pytest.raises(ValueError):
        validate_profile(profile)


def test_invalid_profile_does_not_prevent_actual_validation(tmp_path: Path) -> None:
    path = workspace(tmp_path, font_size=14, scale=[13])
    profile_path = path / "design-profile.json"
    profile = json.loads(profile_path.read_text())
    profile["platform"] = "unknown"
    profile_path.write_text(json.dumps(profile))
    (path / "actual-ui-tree.json").write_text('{"version": 1, "screens": []}')
    result = checks(path)
    assert result["design-profile"]["status"] == "ERROR"
    assert result["lint-tokens"]["status"] == "PASS"
    assert result["validate-actual"]["exit_code"] == 1


def test_missing_scale_or_source_in_typography_is_not_an_implicit_default(tmp_path: Path) -> None:
    path = workspace(tmp_path, font_size=14)
    profile_path = path / "design-profile.json"
    profile = json.loads(profile_path.read_text())
    profile["typography"] = {"source": "product-conventions"}
    profile_path.write_text(json.dumps(profile))
    assert checks(path)["design-profile"]["status"] == "ERROR"
    profile["typography"] = {"font_size_scale": [14]}
    profile_path.write_text(json.dumps(profile))
    assert checks(path)["design-profile"]["status"] == "ERROR"


def test_cli_check_uses_profile_scale_without_a_new_flag(tmp_path: Path, capsys) -> None:
    from penflow.cli import main

    path = workspace(tmp_path, scale=[13])
    assert main(["check", "--target", str(path), "--project", str(path), "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    lint = next(item for item in report["checks"] if item["name"] == "lint-tokens")
    assert lint["status"] == "PASS"
    assert lint["details"]["inputs"]["fontsize_scale"] == [13]


def test_profile_source_confinement_error_does_not_abort_independent_lint(tmp_path: Path) -> None:
    path = workspace(tmp_path, font_size=14, scale=[13])
    profile_path = path / "design-profile.json"
    profile = json.loads(profile_path.read_text())
    profile["sources"] = [str(path.parent / "outside-project-policy.md")]
    profile_path.write_text(json.dumps(profile))
    result = checks(path)
    assert result["design-profile"]["status"] == "ERROR"
    assert "input.outside_project" in result["design-profile"]["issues"][0]["message"]
    assert result["lint-tokens"]["status"] == "PASS"


def test_profile_selection_is_resolved_once_before_lint(tmp_path: Path, monkeypatch) -> None:
    import penflow.review_checks as review

    path = workspace(tmp_path, scale=[13])
    actual_resolver = review.resolve_profile
    selections = []

    def observe(*args, **kwargs):
        selected = actual_resolver(*args, **kwargs)
        selections.append(selected)
        return selected

    monkeypatch.setattr(review, "resolve_profile", observe)
    result = checks(path)
    assert len(selections) == 1
    assert (
        result["lint-tokens"]["details"]["inputs"]["fontsize_scale"]
        == selections[0]["typography"]["font_size_scale"]
    )
