from __future__ import annotations

import subprocess
import sys
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SKILL_DIR = ROOT / ".agent-sync" / "skills" / "flow-ui-contract"


def test_flow_ui_contract_skill_documents_installed_name_and_legacy_wording() -> None:
    skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    readme = (SKILL_DIR / "README.md").read_text(encoding="utf-8")

    assert "name: flow-ui-contract" in skill
    assert "flow-ui-contract` skill" in skill
    assert "specify flows" in skill
    assert "no separate `specify-flows` slash command" in readme
    assert "flow-ui-contract/flows" in skill
    assert "flow-ui-contract/screens" in skill
    assert "references/semantic-ui-tree.md" in skill
    assert (SKILL_DIR / "references" / "semantic-ui-tree.md").exists()
    assert "never write into LiveSpec `.specs/`" in skill
    assert "semantic UI tree" in readme


def test_flow_ui_contract_validator_accepts_migrated_fixtures() -> None:
    validator = SKILL_DIR / "validator.py"
    fixtures = SKILL_DIR / "tests" / "fixtures"

    for fixture_name in ("valid_flow.md", "valid_screen.md"):
        result = subprocess.run(
            [sys.executable, str(validator), str(fixtures / fixture_name)],
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 0, result.stdout + result.stderr
        assert "VALIDATION_RESULT: PASS" in result.stdout


def test_flow_ui_contract_status_mode_reports_manifest_coverage(tmp_path: Path) -> None:
    manifest_dir = tmp_path / "mockups"
    manifest_dir.mkdir()
    shutil.copy(
        SKILL_DIR / "tests" / "fixtures" / "status_manifest.json", manifest_dir / "manifest.json"
    )

    result = subprocess.run(
        [
            sys.executable,
            str(SKILL_DIR / "validator.py"),
            "--status",
            "--target",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "STATUS_RESULT: PASS" in result.stdout
    assert "stale: 1" in result.stdout
