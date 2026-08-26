# @spec FR-018: Artifact-only runtime isolation — .specs/features/076-exhaustive-bidirectional-semantic-context/spec.md#fr-018
"""Static isolation proof for feature 076 implementation surfaces."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FEATURE_MODULES = (
    "context.py",
    "pencil_graph.py",
    "semantic_context_coverage.py",
    "semantic_context_report.py",
    "flow_docs.py",
    "read_only_filesystem.py",
    "read_only_consumer.py",
)
PROHIBITED_IMPORTS = {
    "playwright",
    "selenium",
    "appium",
    "xcode",
    "xctest",
    "swiftui",
    "uikit",
    "browser",
    "pencil_mcp",
}


def _tree(name: str) -> ast.Module:
    return ast.parse((ROOT / "penflow" / name).read_text(encoding="utf-8"))


def test_feature_modules_import_no_ui_runtime_or_renderer() -> None:
    imported: set[str] = set()
    for name in FEATURE_MODULES:
        for node in ast.walk(_tree(name)):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".", 1)[0])

    assert imported.isdisjoint(PROHIBITED_IMPORTS)


def test_only_bounded_xattr_subprocess_is_present() -> None:
    calls: list[ast.Call] = []
    for name in FEATURE_MODULES:
        for node in ast.walk(_tree(name)):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "subprocess"
            ):
                calls.append(node)

    assert len(calls) == 1
    argv = calls[0].args[0]
    assert isinstance(argv, ast.List)
    assert isinstance(argv.elts[0], ast.Constant)
    assert argv.elts[0].value == "/usr/bin/xattr"
    keywords = {keyword.arg: keyword.value for keyword in calls[0].keywords}
    assert isinstance(keywords["timeout"], ast.Constant)
    assert keywords["timeout"].value == 10


def test_dependency_manifest_has_no_ui_runtime_dependency() -> None:
    manifest = (ROOT / "pyproject.toml").read_text(encoding="utf-8").lower()

    assert all(f'"{name}' not in manifest for name in PROHIBITED_IMPORTS)
