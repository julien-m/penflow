"""Optional real-browser contract checks for the external DOM measurement adapter."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from penflow.tree import flatten_nodes, validate_actual_tree

ADAPTER = Path(__file__).resolve().parents[1] / "examples/adapters/web-rendered"


@pytest.fixture
def browser_tools() -> tuple[str, str, str]:
    """Select installed external tools; absence skips integration, never declares PASS."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("External Node.js is unavailable")
    module = os.environ.get("PENFLOW_WEB_PLAYWRIGHT", "playwright")
    resolved = subprocess.run(
        [
            node,
            "-e",
            "const p=require.resolve(process.argv[1]); const {chromium}=require(p); "
            "console.log(JSON.stringify({module:p,browser:chromium.executablePath()}));",
            module,
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )
    if resolved.returncode:
        pytest.skip("External Playwright is unavailable; set PENFLOW_WEB_PLAYWRIGHT")
    selected = json.loads(resolved.stdout)
    browser = os.environ.get("PENFLOW_WEB_BROWSER", selected["browser"])
    if not Path(browser).is_file():
        pytest.skip("External browser is unavailable; set PENFLOW_WEB_BROWSER")
    return node, selected["module"], browser


def _capture(
    tools: tuple[str, str, str], page: Path, output: Path, width: int, height: int
) -> subprocess.CompletedProcess[str]:
    node, module, browser = tools
    return subprocess.run(
        [
            node,
            str(ADAPTER / "capture.mjs"),
            page.as_uri(),
            str(output),
            str(width),
            str(height),
            module,
            browser,
        ],
        capture_output=True,
        text=True,
        timeout=45,
    )


@pytest.mark.integration
@pytest.mark.parametrize("viewport", [(317, 233), (823, 517)])
def test_adapter_observes_computed_styles_and_nested_screen_relative_boxes(
    tmp_path: Path, browser_tools: tuple[str, str, str], viewport: tuple[int, int]
) -> None:
    page = tmp_path / "independent.html"
    page.write_text(
        "<!doctype html><style>body{margin:11px}main{padding:16px;display:flex;gap:8px}"
        "section{padding:12px;display:flex;gap:4px}button{font-size:17px;padding:6px 13px}"
        "</style><main data-penflow-screen='report' data-semantic='report'>"
        "<section data-semantic='report.actions'><button data-semantic='report.refresh'>"
        "Refresh report</button><button hidden>Hidden</button></section></main>"
    )
    output = tmp_path / "observed.json"
    result = _capture(browser_tools, page, output, *viewport)
    assert result.returncode == 0, result.stderr
    observed = json.loads(output.read_text())
    assert validate_actual_tree(observed) == []
    screen = observed["screens"][0]
    assert screen["viewport"] == dict(zip(("width", "height"), viewport))
    assert screen["screen_origin"] == {"x": 11, "y": 11}
    root = screen["root"]
    assert root["bbox"]["x"] == root["bbox"]["y"] == 0
    button = root["children"][0]["children"][0]
    assert button["visual"]["fontSize"] == 17
    assert button["visual"]["padding"] == [6, 13, 6, 13]
    assert button["bbox"]["x"] == button["bbox"]["y"] == 28
    assert len(flatten_nodes(root)) == 3
    assert observed["measurement"]["units"] == "css-px"


@pytest.mark.integration
@pytest.mark.parametrize(
    "controls, message",
    [
        ("<button>Unmapped</button>", "missing data-semantic"),
        (
            "<button data-semantic='panel.save'>Save</button>"
            "<button data-semantic='panel.save'>Save again</button>",
            "Duplicate rendered semantic identity",
        ),
    ],
)
def test_adapter_rejects_missing_or_ambiguous_runtime_coverage(
    tmp_path: Path, browser_tools: tuple[str, str, str], controls: str, message: str
) -> None:
    page = tmp_path / "ambiguous.html"
    page.write_text(
        "<!doctype html><main data-penflow-screen='panel' data-semantic='panel'>"
        + controls
        + "</main>"
    )
    output = tmp_path / "rejected.json"
    result = _capture(browser_tools, page, output, 640, 400)
    assert result.returncode != 0
    assert message in result.stderr
    assert not output.exists()


@pytest.mark.integration
@pytest.mark.parametrize("viewport", [(375, 667), (1280, 800)])
def test_adapter_preserves_native_and_aria_landing_heading_navigation_roles(
    tmp_path: Path, browser_tools: tuple[str, str, str], viewport: tuple[int, int]
) -> None:
    page = tmp_path / "landing.html"
    page.write_text(
        "<!doctype html><main role='main' data-penflow-screen='landing' data-semantic='landing'>"
        "<nav aria-label='Product' data-semantic='landing.navigation'>"
        "<a href='#plans' data-semantic='landing.plans'>Plans</a></nav>"
        "<section data-semantic='landing.hero'>"
        "<h1 data-semantic='landing.title'>Manage field inspections</h1>"
        "<div role='heading' aria-level='2' data-semantic='landing.subtitle'>"
        "Review each report with your crew</div></section>"
        "<div role='navigation' aria-label='Resources' data-semantic='landing.resources'>"
        "<a href='#guide' data-semantic='landing.guide'>Inspection guide</a></div></main>"
    )
    output = tmp_path / "landing-observation.json"
    result = _capture(browser_tools, page, output, *viewport)
    assert result.returncode == 0, result.stderr
    observed = json.loads(output.read_text())
    assert validate_actual_tree(observed) == []
    nodes = {item["id"]: item for item in flatten_nodes(observed["screens"][0]["root"])}
    assert nodes["landing"]["role"] == "screen"
    assert nodes["landing.title"]["role"] == nodes["landing.subtitle"]["role"] == "heading"
    assert nodes["landing.navigation"]["role"] == nodes["landing.resources"]["role"] == "navigation"
    assert nodes["landing.plans"]["role"] == nodes["landing.guide"]["role"] == "link"
    assert nodes["landing.title"]["text"] == "Manage field inspections"
    assert "fill" in nodes["landing.title"]["visual"]
    assert nodes["landing.title"]["visual"]["layout"] == "none"
