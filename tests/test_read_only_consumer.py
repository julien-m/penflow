# @spec FR-017: Read-only Routempo proof — .specs/features/076-exhaustive-bidirectional-semantic-context/spec.md#fr-017
"""No-follow consumer inventory, guard, confinement, and publication tests."""

from __future__ import annotations

import ast
import base64
import json
import os
import sys
from pathlib import Path

import pytest

import penflow.read_only_consumer as consumer_module
from penflow.read_only_consumer import (
    ReadOnlyConsumerError,
    ReadOnlyConsumerFilesystem,
    generate_migration_report,
    run_guard_self_test,
)
from tests.test_semantic_context_coverage import _contract, _pen


def _consumer(root: Path) -> Path:
    root.mkdir()
    (root / "flow-ui-contract").mkdir()
    (root / "flow-ui-contract" / "contract.json").write_text(
        json.dumps(_contract()), encoding="utf-8"
    )
    (root / "ui.pen").write_text(json.dumps(_pen()), encoding="utf-8")
    (root / "pencil-context-map.json").write_text(
        json.dumps(
            {
                "kind": "pencil-context-map",
                "version": 1,
                "status": "PASS",
                "matched": [{"semantic_id": f"node-{index}"} for index in range(3)],
                "ambiguous": [],
                "unmapped": [],
            }
        ),
        encoding="utf-8",
    )
    return root


def test_manifest_is_exhaustive_and_never_follows_symlink(tmp_path: Path) -> None:
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    root = _consumer(tmp_path / "consumer")
    (root / "outside-link").symlink_to(outside)
    filesystem = ReadOnlyConsumerFilesystem(root)

    manifest = filesystem.manifest()
    entries = {entry["path"]: entry for entry in manifest["entries"]}

    assert "." in entries
    assert entries["outside-link"]["type"] == "symlink"
    assert entries["outside-link"]["symlink_target"] == str(outside)
    assert entries["outside-link"]["sha256"] is None
    for entry in entries.values():
        assert {
            "path",
            "type",
            "mode",
            "uid",
            "gid",
            "size",
            "mtime_ns",
            "ctime_ns",
            "birthtime_ns",
            "symlink_target",
            "xattrs",
            "sha256",
        } <= set(entry)


def test_manifest_uses_portable_no_follow_xattr_api(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _consumer(tmp_path / "consumer")
    calls: list[tuple[str, str, bool]] = []

    def list_xattr(path: str, *, follow_symlinks: bool) -> list[str]:
        calls.append(("list", path, follow_symlinks))
        return ["user.penflow"] if path == str(root / "ui.pen") else []

    def get_xattr(path: str, name: str, *, follow_symlinks: bool) -> bytes:
        calls.append((name, path, follow_symlinks))
        return b"portable"

    monkeypatch.setattr(os, "listxattr", list_xattr, raising=False)
    monkeypatch.setattr(os, "getxattr", get_xattr, raising=False)

    entries = {
        entry["path"]: entry for entry in ReadOnlyConsumerFilesystem(root).manifest()["entries"]
    }

    assert entries["ui.pen"]["xattrs"] == [
        {
            "name": "user.penflow",
            "value_base64": base64.b64encode(b"portable").decode("ascii"),
        }
    ]
    assert calls
    assert all(follow_symlinks is False for _, _, follow_symlinks in calls)


def test_manifest_never_uses_macos_xattr_command_on_other_platforms(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _consumer(tmp_path / "consumer")
    filesystem = ReadOnlyConsumerFilesystem(root)

    monkeypatch.delattr(os, "listxattr", raising=False)
    monkeypatch.delattr(os, "getxattr", raising=False)
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(
        filesystem,
        "_command_xattr",
        lambda *arguments: pytest.fail(f"unexpected native xattr call: {arguments}"),
    )

    with pytest.raises(ReadOnlyConsumerError, match="xattr API unavailable"):
        filesystem._xattrs(str(root))


def test_guard_self_test_records_blocked_decoy_and_fresh_guard_stays_empty(
    tmp_path: Path,
) -> None:
    decoy = ReadOnlyConsumerFilesystem(_consumer(tmp_path / "decoy"))

    receipt = run_guard_self_test(decoy)
    fresh = ReadOnlyConsumerFilesystem(_consumer(tmp_path / "fresh"))
    fresh.read_json("ui.pen")

    assert receipt["status"] == "PASS"
    assert receipt["attempts"] == [
        {"operation": "write_and_restore", "path": "guard-self-test.txt"}
    ]
    assert fresh.attempted_mutations == []


def test_live_audit_function_has_no_direct_filesystem_calls() -> None:
    source = Path(consumer_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    audit = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "build_migration_report"
    )

    forbidden = []
    for node in ast.walk(audit):
        if isinstance(node, ast.Name) and node.id in {"Path", "open", "os"}:
            forbidden.append(node.id)
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "os"
        ):
            forbidden.append(f"os.{node.func.attr}")
    assert forbidden == []


@pytest.mark.parametrize("destination", ["consumer", "outside"])
def test_output_confinement_rejects_consumer_and_outside_paths(
    tmp_path: Path, destination: str
) -> None:
    root = _consumer(tmp_path / "consumer")
    feature = tmp_path / "feature"
    feature.mkdir()
    output = root / "report.json" if destination == "consumer" else tmp_path / "report.json"

    with pytest.raises(ReadOnlyConsumerError, match="output"):
        generate_migration_report(root, feature, output)

    assert not output.exists()


def test_report_publishes_only_after_equal_manifests_and_zero_attempts(tmp_path: Path) -> None:
    root = _consumer(tmp_path / "consumer")
    feature = tmp_path / "feature"
    feature.mkdir()
    output = feature / "reports" / "migration.json"

    report = generate_migration_report(root, feature, output)

    assert output.is_file()
    assert report["consumer_immutability"]["manifests_equal"] is True
    assert report["consumer_immutability"]["attempted_mutations"] == []
    assert report["consumer_immutability"]["before"] == report["consumer_immutability"]["after"]
    assert report["historical_forward_evidence"]["matched"] == 3
    assert report["historical_forward_evidence"]["strictly_sufficient"] is False


def test_manifest_mismatch_blocks_publication(tmp_path: Path) -> None:
    root = _consumer(tmp_path / "consumer")
    feature = tmp_path / "feature"
    feature.mkdir()
    output = feature / "report.json"

    class MismatchFilesystem(ReadOnlyConsumerFilesystem):
        calls = 0

        def manifest(self) -> dict:
            result = super().manifest()
            self.calls += 1
            if self.calls == 2:
                result = result | {"digest": "0" * 64}
            return result

    with pytest.raises(ReadOnlyConsumerError, match="manifest changed"):
        generate_migration_report(root, feature, output, filesystem_factory=MismatchFilesystem)

    assert not output.exists()
