# @spec AC-025: Given a competing lifecycle lock, retained evidence references and unrelated visual bytes, when verification/export/cleanup is attempted, then existing lock conflict behavior applies, retained proof is not deleted and unrelated visual bytes remain identical; dependency/import and subprocess checks prove core launches no application runtime or renderer. — .specs/features/077-complete-verification-workflow/spec.md#ac-025
# @spec FR-018: Artifact-only runtime isolation — .specs/features/076-exhaustive-bidirectional-semantic-context/spec.md#fr-018
"""Static runtime guards for the declared feature 076 and C51 module surfaces.

The C51 scan checks explicit imports, import aliases, and direct OS process calls.
It does not follow transitive local imports or prove arbitrary dynamic behavior.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

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


C51_REQUIRED_MODULES = frozenset(
    {
        "cli_verification.py",
        "cli_authority.py",
        "contract_preparation.py",
        "doctor_authority.py",
        "product_freeze.py",
        "product_mapping.py",
        "product_projection.py",
        "product_sources.py",
        "requirement_approval_history.py",
        "requirement_markdown.py",
        "requirement_projection.py",
        "requirement_sources.py",
        "verification.py",
        "verification_applicability.py",
        "verification_assertions.py",
        "verification_authority.py",
        "verification_build.py",
        "verification_capture.py",
        "verification_comparison.py",
        "verification_design.py",
        "verification_expectations.py",
        "verification_files.py",
        "verification_geometry.py",
        "verification_json.py",
        "verification_native.py",
        "verification_obligations.py",
        "verification_outcomes.py",
        "verification_policy.py",
        "verification_runtime.py",
        "verification_schema.py",
        "verification_snapshot.py",
        "verification_styles.py",
        "verification_system_returns.py",
    }
)


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


# @spec FR-015 AC-025: C51 core remains an artifact-only validator.
# — .specs/features/077-complete-verification-workflow/spec.md#fr-015
def test_c51_modules_have_no_runtime_import_or_process_launch() -> None:
    names = sorted(
        C51_REQUIRED_MODULES
        | {
            path.name
            for prefix in ("verification", "requirement", "product", "doctor_authority")
            for path in (ROOT / "penflow").glob(f"{prefix}*.py")
        }
    )
    assert all((ROOT / "penflow" / name).is_file() for name in C51_REQUIRED_MODULES)
    for name in names:
        assert not _runtime_references(_tree(name)), name


def _runtime_references(tree: ast.Module) -> set[str]:
    """Find prohibited imports and direct process calls, resolving import aliases."""
    aliases: dict[str, str] = {}
    violations: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                aliases[alias.asname or alias.name.split(".")[0]] = alias.name
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            for alias in node.names:
                aliases[alias.asname or alias.name] = node.module + "." + alias.name
    violations.update(
        value
        for value in aliases.values()
        if value.split(".")[0] in PROHIBITED_IMPORTS | {"subprocess"}
    )
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        reference = ast.unparse(node.func)
        base, _, member = reference.partition(".")
        reference = aliases.get(base, base) + ("." + member if member else "")
        if reference.startswith("os."):
            operation = reference.removeprefix("os.")
            if operation in {"system", "popen"} or operation.startswith(
                ("exec", "spawn", "posix_spawn")
            ):
                violations.add(reference)
    return violations


@pytest.mark.parametrize(
    "source",
    [
        "import os as operating; operating.execve('app', [], {})",
        "from os import posix_spawnp as launch; launch('app', [], {})",
        "from os import system as run; run('app')",
        "import subprocess as process; process.run(['app'])",
        "from subprocess import Popen as launch; launch(['app'])",
        "import playwright as runtime",
    ],
)
def test_runtime_scanner_detects_aliased_process_and_runtime_access(source: str) -> None:
    assert _runtime_references(ast.parse(source))
