"""Mutable file and symlink identity remain bound through final publication."""

from pathlib import Path

import pytest

from penflow.verification_files import InputReader, VerificationInputError


@pytest.mark.parametrize("same_bytes", [True, False])
def test_retargeted_symlink_is_rejected_even_with_identical_bytes(
    tmp_path: Path, same_bytes: bool
) -> None:
    (tmp_path / "before").write_bytes(b"old")
    (tmp_path / "after").write_bytes(b"old" if same_bytes else b"changed")
    alias = tmp_path / "source"
    alias.symlink_to("before")
    reader = InputReader(tmp_path)
    assert reader.read("source") == b"old"
    alias.unlink()
    alias.symlink_to("after")
    with pytest.raises(VerificationInputError):
        reader.recheck()
