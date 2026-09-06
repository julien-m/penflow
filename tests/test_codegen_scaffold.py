# @spec AC-022: Given generated scaffold/no-op code, when certification is requested, then scaffold status is explicit and cannot satisfy implementation outcomes. — .specs/features/077-complete-verification-workflow/spec.md#ac-022
# @spec AC-021: Given candidate unused helpers and public legacy APIs, when cleanup is delivered, then only confirmed unreferenced private paths are deleted; supported public consumers migrate or receive explicit deprecation before removal. — .specs/features/077-complete-verification-workflow/spec.md#ac-021
"""Scaffold generation never presents empty handlers as implemented behavior."""

import pytest

from penflow.codegen import react, rust_dioxus, swiftui


@pytest.mark.parametrize("generator", [react, swiftui, rust_dioxus])
def test_generated_output_explicitly_declares_scaffold(generator) -> None:
    """Every supported output carries the limitation before any generated application code."""
    output = generator({"screen": "checkout", "components": [{"id": "save", "role": "button"}]})
    assert output.startswith("// Penflow scaffold:")
    assert "unimplemented handlers" in output.splitlines()[0]
