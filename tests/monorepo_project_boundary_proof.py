# @spec FR-008 FR-009 AC-010 AC-011
"""Prove live read-only and isolated-copy Project Brainstorm boundaries."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from penflow.artifact_policy import MANAGED_IGNORE_BLOCK_LINES
from penflow.doctor_context import SubprocessGitGateway
from penflow.doctor_git import _capture_git_snapshot
from penflow.project_doctor import resolve_project_context, run_project_doctor
from penflow.run_manifest import atomic_write_json

FEATURE_ID = "075-penflow-doctor-monorepo-project-boundary"
COMMAND_TIMEOUT_SECONDS = 120
PRUNED_NAMES = frozenset(
    {
        ".git",
        ".penflow-tmp",
        ".penflow-run",
        ".mockup-validation",
        "__pycache__",
        "archives",
        "node_modules",
    }
)


@dataclass(frozen=True, slots=True)
class ConsumerSelection:
    """Bind one exact selected consumer beneath a caller-owned search root."""

    search_root: Path
    project_root: Path
    ui_pen: Path


def run_proof(
    *,
    live_project: Path,
    sibling: Path,
    output: Path,
) -> dict[str, Any]:
    """Run zero-mutation live probes and mutation-only isolated-copy probes."""

    source_root = Path(__file__).resolve().parents[1]
    target_selection = _discover_selection(live_project)
    sibling_selection = _discover_selection(sibling)
    _reject_live_output(output, (target_selection, sibling_selection))
    live_rows = tuple(_live_probe(selection) for selection in (target_selection, sibling_selection))
    with tempfile.TemporaryDirectory(prefix="penflow-075-proof-") as temporary:
        copy_row = _isolated_copy_probe(
            target_selection,
            sibling_selection,
            # macOS exposes the default temporary directory through ``/var`` ->
            # ``/private/var``.  Resolve that OS alias before handing an exact
            # project selector to Doctor; consumer paths themselves must never
            # traverse a symlink component.
            Path(temporary).resolve(),
            source_root=source_root,
        )
    assertions = {
        "live_target_zero_diff": live_rows[0]["zero_diff"] is True,
        "live_sibling_zero_diff": live_rows[1]["zero_diff"] is True,
        "live_target_truthful": live_rows[0]["truthful"] is True,
        "live_sibling_truthful": live_rows[1]["truthful"] is True,
        "copy_commands_zero": copy_row["commands_zero"] is True,
        "copy_target_one_canvas": copy_row["target_pen_paths"] == ["ui.pen"],
        "copy_target_one_ignore_block": copy_row["target_ignore_block_count"] == 1,
        "copy_no_completed_run": copy_row["completed_run_count"] == 0,
        "copy_sibling_unchanged": copy_row["sibling_unchanged"] is True,
        "copy_index_unchanged": copy_row["index_unchanged"] is True,
        "copy_git_lock_restored": copy_row["git_lock_restored"] is True,
    }
    status = "PASS" if all(assertions.values()) else "FAIL"
    receipt: dict[str, object] = {
        "schema_version": 1,
        "stable_result": {
            "feature": FEATURE_ID,
            "status": status,
            "target": _selection_row(target_selection),
            "sibling": _selection_row(sibling_selection),
            "live": list(live_rows),
            "copy": copy_row,
            "assertions": [
                f"{name}:{'PASS' if passed else 'FAIL'}"
                for name, passed in sorted(assertions.items())
            ],
        },
        "diagnostics": {"mutations_confined_to_temporary_copy": True},
    }
    atomic_write_json(output, receipt, revision=1)
    return receipt


def _discover_selection(search_root: Path) -> ConsumerSelection:
    root = search_root.expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"consumer search root is not a directory: {search_root}")
    candidates: list[Path] = []
    for current, directory_names, file_names in os.walk(root, followlinks=False):
        directory_names[:] = sorted(name for name in directory_names if name not in PRUNED_NAMES)
        if "ui.pen" not in file_names:
            continue
        candidate = Path(current) / "ui.pen"
        metadata = candidate.lstat()
        if stat.S_ISREG(metadata.st_mode) and metadata.st_nlink == 1 and _valid_pen(candidate):
            candidates.append(candidate)
    if len(candidates) != 1:
        paths = ", ".join(path.relative_to(root).as_posix() for path in sorted(candidates))
        raise ValueError(f"expected one exact consumer ui.pen below {root}; found: {paths}")
    ui_pen = candidates[0].resolve()
    return ConsumerSelection(root, ui_pen.parent, ui_pen)


def _valid_pen(path: Path) -> bool:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    return isinstance(payload, dict) and isinstance(payload.get("children"), list)


def _live_probe(selection: ConsumerSelection) -> dict[str, object]:
    before = _project_snapshot(selection.project_root)
    result = run_project_doctor(selection.project_root)
    after = _project_snapshot(selection.project_root)
    truthful = result.exit_code in {0, 1} and result.context is not None
    return {
        "project_root": selection.project_root.as_posix(),
        "doctor_exit": result.exit_code,
        "doctor_status": result.report.stable_result.status,
        "finding_codes": sorted(finding.code for finding in result.report.stable_result.findings),
        "zero_diff": before == after,
        "truthful": truthful,
        "before": before,
        "after": after,
    }


def _project_snapshot(project_root: Path) -> dict[str, object]:
    context = resolve_project_context(project_root)
    git = _capture_git_snapshot(context, SubprocessGitGateway())
    inventory = tuple(_inventory_tree(project_root))
    encoded_inventory = json.dumps(
        inventory,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return {
        "index_sha256": git.index_sha256,
        "porcelain_sha256": _sha256_bytes(git.porcelain),
        "files_sha256": _sha256_bytes(encoded_inventory),
        "file_count": len(inventory),
    }


def _isolated_copy_probe(
    target: ConsumerSelection,
    sibling: ConsumerSelection,
    temporary_root: Path,
    *,
    source_root: Path,
) -> dict[str, object]:
    repository = temporary_root / "collective-repository"
    copied_target = repository / "projects" / "target"
    copied_sibling = repository / "projects" / "sibling"
    copied_target.parent.mkdir(parents=True)
    shutil.copytree(target.project_root, copied_target, ignore=_copy_ignore)
    shutil.copytree(sibling.project_root, copied_sibling, ignore=_copy_ignore)
    _git(repository, "init", "-q")
    _git(repository, "config", "user.email", "penflow-proof@example.invalid")
    _git(repository, "config", "user.name", "Penflow Feature 075 Proof")
    _git(repository, "add", "--all")
    _git(repository, "commit", "-qm", "isolated complete target and sibling")
    sibling_before = _tree_digest(copied_sibling)
    index_path = repository / ".git" / "index"
    index_before = index_path.read_bytes()
    porcelain_before = _git(repository, "status", "--porcelain=v2", "-z")
    commands = _copy_commands(copied_target, source_root=source_root)
    porcelain_after = _git(repository, "status", "--porcelain=v2", "-z")
    target_pen_paths = sorted(
        path.relative_to(copied_target).as_posix()
        for path in copied_target.rglob("*.pen")
        if not any(part in PRUNED_NAMES for part in path.relative_to(copied_target).parts)
    )
    gitignore = copied_target / ".gitignore"
    ignore_count = (
        gitignore.read_text(encoding="utf-8").count(MANAGED_IGNORE_BLOCK_LINES[0])
        if gitignore.is_file()
        else 0
    )
    manifests = copied_target / ".penflow-tmp" / "manifests"
    completed_runs = tuple(manifests.glob("*.json")) if manifests.is_dir() else ()
    return {
        "commands": commands,
        "commands_zero": all(row["exit_code"] == 0 for row in commands),
        "target_pen_paths": target_pen_paths,
        "target_ignore_block_count": ignore_count,
        "completed_run_count": len(completed_runs),
        "sibling_unchanged": _tree_digest(copied_sibling) == sibling_before,
        "index_unchanged": index_path.read_bytes() == index_before,
        "git_lock_restored": not (repository / ".git" / "index.lock").exists(),
        "porcelain_before_sha256": _sha256_bytes(porcelain_before),
        "porcelain_after_sha256": _sha256_bytes(porcelain_after),
    }


def _copy_commands(target: Path, *, source_root: Path) -> list[dict[str, object]]:
    commands = (
        ("doctor-fix-1", "doctor", "--project", str(target), "--fix", "--json"),
        ("doctor-fix-2", "doctor", "--project", str(target), "--fix", "--json"),
        (
            "producer-1",
            "export-expected",
            "--project",
            str(target),
            str(target / "ui.pen"),
            "--out",
            str(target / "expected-ui-tree.json"),
            "--json",
        ),
        (
            "producer-2",
            "export-expected",
            "--project",
            str(target),
            str(target / "ui.pen"),
            "--out",
            str(target / "expected-ui-tree.json"),
            "--json",
        ),
    )
    rows: list[dict[str, object]] = []
    for name, *arguments in commands:
        completed = subprocess.run(
            [sys.executable, "-m", "penflow", *arguments],
            cwd=target,
            check=False,
            capture_output=True,
            timeout=COMMAND_TIMEOUT_SECONDS,
            env={**os.environ, "PYTHONPATH": str(source_root), "GIT_TERMINAL_PROMPT": "0"},
        )
        rows.append(
            {
                "name": name,
                "exit_code": completed.returncode,
                "stdout_sha256": _sha256_bytes(completed.stdout),
                "stderr_sha256": _sha256_bytes(completed.stderr),
            }
        )
    return rows


def _copy_ignore(_directory: str, names: list[str]) -> set[str]:
    return {name for name in names if name in PRUNED_NAMES}


def _inventory_tree(root: Path) -> Iterable[dict[str, object]]:
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if any(part == ".git" for part in relative.parts):
            continue
        metadata = path.lstat()
        if stat.S_ISREG(metadata.st_mode):
            yield {
                "path": relative.as_posix(),
                "kind": "file",
                "sha256": _sha256_file(path),
                "bytes": metadata.st_size,
            }
        elif stat.S_ISDIR(metadata.st_mode):
            yield {"path": relative.as_posix(), "kind": "directory"}
        elif stat.S_ISLNK(metadata.st_mode):
            yield {
                "path": relative.as_posix(),
                "kind": "symlink",
                "target": os.readlink(path),
            }


def _tree_digest(root: Path) -> str:
    encoded = json.dumps(
        tuple(_inventory_tree(root)),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return _sha256_bytes(encoded)


def _selection_row(selection: ConsumerSelection) -> dict[str, str]:
    return {
        "search_root": selection.search_root.as_posix(),
        "project_root": selection.project_root.as_posix(),
        "ui_pen": selection.ui_pen.relative_to(selection.search_root).as_posix(),
        "ui_pen_sha256": _sha256_file(selection.ui_pen),
    }


def _reject_live_output(output: Path, selections: Sequence[ConsumerSelection]) -> None:
    resolved = output.resolve(strict=False)
    for selection in selections:
        live = selection.search_root
        if resolved == live or resolved.is_relative_to(live):
            raise ValueError(f"proof output is inside live consumer root: {resolved}")


def _git(repository: Path, *arguments: str) -> bytes:
    completed = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=False,
        capture_output=True,
        timeout=30,
        env={**os.environ, "LC_ALL": "C", "GIT_TERMINAL_PROMPT": "0"},
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.decode("utf-8", errors="replace"))
    return completed.stdout


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def main(argv: Sequence[str] | None = None) -> int:
    """Parse exact live roots and persist the copy-isolated proof receipt."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-project", required=True, type=Path)
    parser.add_argument("--sibling", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        receipt = run_proof(
            live_project=args.live_project,
            sibling=args.sibling,
            output=args.out,
        )
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    return 0 if receipt["stable_result"]["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
