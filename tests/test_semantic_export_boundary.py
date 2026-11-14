"""Real CLI contract projection is independent of canvas health and preserves write boundaries."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from tests.contract_factory import valid_contract

ROOT = Path(__file__).resolve().parents[1]


def project(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "consumer"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True, timeout=10)
    contract = root / "flows" / "contract.json"
    contract.parent.mkdir()
    contract.write_text(json.dumps(valid_contract()))
    # This independently invalid canvas must not enter contract-only projection.
    (root / "ui.pen").write_text('{"version":"2.17","children":[{"id":"broken"}]}')
    return root, contract


def run_cli(root: Path, source: Path, out: Path) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONPATH": str(ROOT), "PYTHONDONTWRITEBYTECODE": "1"}
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "penflow",
            "export-semantic-tree",
            str(source),
            "--out",
            str(out),
            "--project",
            str(root),
            "--json",
        ],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )


def test_contract_export_ignores_unrelated_canvas_and_hygiene(tmp_path: Path) -> None:
    root, contract = project(tmp_path)
    subprocess.run(
        ["git", "-C", str(root), "add", str(contract), str(root / "ui.pen")], check=True, timeout=10
    )
    index_before = (root / ".git" / "index").read_bytes()
    canvas_before = (root / "ui.pen").read_bytes()
    source_before = contract.read_bytes()
    out = root / "semantic-ui-tree.json"
    result = run_cli(root, contract, out)
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["status"] == "PASS"
    assert json.loads(out.read_text())["kind"] == "semantic-ui-tree"
    assert (root / "ui.pen").read_bytes() == canvas_before
    assert contract.read_bytes() == source_before
    assert (root / ".git" / "index").read_bytes() == index_before
    assert not (root / ".gitignore").exists()
    assert not (root / ".penflow-tmp" / "manifests").exists()


def test_export_accepts_contract_directory_without_a_canvas(tmp_path: Path) -> None:
    root, contract = project(tmp_path)
    (root / "ui.pen").unlink()
    out = root / "semantic.json"
    assert run_cli(root, contract.parent, out).returncode == 0
    assert not (root / "ui.pen").exists()


def test_peer_canvases_do_not_participate_in_contract_projection(tmp_path: Path) -> None:
    root, contract = project(tmp_path)
    (root / "peer.pen").write_text("unrelated invalid canvas")
    assert run_cli(root, contract, root / "semantic.json").returncode == 0
    assert (root / "peer.pen").read_text() == "unrelated invalid canvas"


def test_invalid_contract_cannot_replace_an_existing_semantic_output(tmp_path: Path) -> None:
    root, contract = project(tmp_path)
    out = root / "semantic.json"
    assert run_cli(root, contract, out).returncode == 0
    before = out.read_bytes()
    data = json.loads(contract.read_text())
    data["screens"][0]["root_node"] = "missing-node"
    contract.write_text(json.dumps(data))
    result = run_cli(root, contract, out)
    assert result.returncode != 0
    assert out.read_bytes() == before


def test_malformed_contract_never_publishes(tmp_path: Path) -> None:
    root, contract = project(tmp_path)
    contract.write_text('{"version":2,"version":2}')
    out = root / "semantic.json"
    assert run_cli(root, contract, out).returncode != 0
    assert not out.exists()


def test_output_outside_project_is_refused(tmp_path: Path) -> None:
    root, contract = project(tmp_path)
    outside = tmp_path / "outside.json"
    result = run_cli(root, contract, outside)
    assert result.returncode == 3
    assert not outside.exists()


def test_input_outside_project_is_refused(tmp_path: Path) -> None:
    root, contract = project(tmp_path)
    outside = tmp_path / "contract.json"
    outside.write_bytes(contract.read_bytes())
    result = run_cli(root, outside, root / "semantic.json")
    assert result.returncode == 3
    assert not (root / "semantic.json").exists()


def test_source_alias_and_hardlink_output_are_preserved(tmp_path: Path) -> None:
    root, contract = project(tmp_path)
    before = contract.read_bytes()
    assert run_cli(root, contract, contract).returncode == 3
    alias = root / "alias.json"
    os.link(contract, alias)
    assert run_cli(root, contract, alias).returncode == 3
    assert contract.read_bytes() == alias.read_bytes() == before


def test_symlink_output_cannot_replace_other_project_data(tmp_path: Path) -> None:
    root, contract = project(tmp_path)
    data = root / "data.json"
    data.write_text('{"personal":"preserve"}')
    alias = root / "semantic.json"
    alias.symlink_to(data)
    assert run_cli(root, contract, alias).returncode == 3
    assert alias.is_symlink()
    assert data.read_text() == '{"personal":"preserve"}'


def test_unowned_output_and_canvas_are_preserved(tmp_path: Path) -> None:
    root, contract = project(tmp_path)
    out = root / "data.json"
    out.write_text('{"kind":"consumer-data"}')
    before = out.read_bytes()
    assert run_cli(root, contract, out).returncode == 3
    assert out.read_bytes() == before
    canvas = root / "ui.pen"
    before_canvas = canvas.read_bytes()
    assert run_cli(root, contract, canvas).returncode == 3
    assert canvas.read_bytes() == before_canvas


def test_owned_semantic_output_can_be_regenerated(tmp_path: Path) -> None:
    root, contract = project(tmp_path)
    out = root / "semantic.json"
    assert run_cli(root, contract, out).returncode == 0
    before = out.read_bytes()
    assert run_cli(root, contract, out).returncode == 0
    assert out.read_bytes() == before


def test_semantic_output_from_another_contract_is_not_overwritten(tmp_path: Path) -> None:
    root, contract = project(tmp_path)
    other = root / "other" / "contract.json"
    other.parent.mkdir()
    other.write_bytes(contract.read_bytes())
    out = root / "semantic.json"
    assert run_cli(root, other, out).returncode == 0
    before = out.read_bytes()
    assert run_cli(root, contract, out).returncode == 3
    assert out.read_bytes() == before


def test_other_canvas_producer_still_uses_doctor(tmp_path: Path) -> None:
    root, _contract = project(tmp_path)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "penflow",
            "export-expected",
            str(root / "ui.pen"),
            "--out",
            str(root / "expected.json"),
            "--project",
            str(root),
            "--json",
        ],
        cwd=root,
        env={**os.environ, "PYTHONPATH": str(ROOT)},
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode != 0
    report = json.loads(result.stdout)
    assert report["stable_result"]["status"] == "BLOCKED"
    assert any(item["code"] == "pen.invalid" for item in report["stable_result"]["findings"])


def test_source_change_during_projection_prevents_publication(tmp_path: Path, monkeypatch) -> None:
    import penflow.cli as cli
    import penflow.semantic_export as export

    root, contract = project(tmp_path)
    out = root / "semantic.json"
    original = export.validate_semantic_tree

    def change_source(tree):
        issues = original(tree)
        contract.write_text(contract.read_text() + "\n")
        return issues

    monkeypatch.setattr(export, "validate_semantic_tree", change_source)
    code = cli.main(
        ["export-semantic-tree", str(contract), "--out", str(out), "--project", str(root), "--json"]
    )
    assert code == 3
    assert not out.exists()


def test_new_foreign_destination_during_projection_is_preserved(
    tmp_path: Path, monkeypatch
) -> None:
    import penflow.cli as cli
    import penflow.semantic_export as export

    root, contract = project(tmp_path)
    out = root / "semantic.json"
    original = export.validate_semantic_tree

    def publish_foreign(tree):
        issues = original(tree)
        out.write_text('{"consumer":"concurrent"}')
        return issues

    monkeypatch.setattr(export, "validate_semantic_tree", publish_foreign)
    code = cli.main(
        ["export-semantic-tree", str(contract), "--out", str(out), "--project", str(root), "--json"]
    )
    assert code == 3
    assert out.read_text() == '{"consumer":"concurrent"}'


def test_redirected_lock_directory_is_refused_before_writing(tmp_path: Path) -> None:
    root, contract = project(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / ".penflow-tmp").symlink_to(outside, target_is_directory=True)
    assert run_cli(root, contract, root / "semantic.json").returncode == 3
    assert list(outside.iterdir()) == []
    assert not (root / "semantic.json").exists()
