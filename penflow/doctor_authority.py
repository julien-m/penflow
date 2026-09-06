# @spec FR-015: Preserve core runtime isolation, existing project locks/artifact retention and lossless unrelated visual updates. — .specs/features/077-complete-verification-workflow/spec.md#fr-015
"""Distinguish one authenticated imported design from the active consumer canvas."""

from pathlib import Path

from .doctor_models import DoctorFinding
from .verification_authority import read_brainstorm_authority
from .verification_files import InputReader, VerificationInputError


def archived_authority_canvas(root: Path) -> tuple[frozenset[Path], tuple[DoctorFinding, ...]]:
    """Authenticate the fixed import pointer before excluding its exact historical canvas.

    Other files in the archive directory remain ordinary inventory candidates. This
    does not certify the current design or waive the independent C51 import checks.
    """
    pointer = root / ".specs/penflow-brainstorm-authority.json"
    if not pointer.exists() and not pointer.is_symlink():
        return frozenset(), ()
    try:
        reader = InputReader(root)
        reference = reader.object(reader.read(pointer), "file")
        raw = reader.reference(reference, archive="authority")
        package = reader.object(raw, "brainstorm-authority-import")
        imported = read_brainstorm_authority(reader, reference)
        canvas = reader.path(Path(package["workspace"]) / "ui.pen")
        archive_root = root / ".specs/penflow-authority"
        if not canvas.is_relative_to(archive_root) or not any(
            reader.path(item["path"]) == canvas for item in imported["sources"]
        ):
            raise VerificationInputError("authority.import.canvas_not_archived")
        reader.recheck()
        return frozenset({canvas}), ()
    except (OSError, ValueError) as error:
        finding = DoctorFinding(
            "pen.authority_archive_invalid",
            "error",
            pointer.relative_to(root).as_posix(),
            None,
            f"imported canvas authority cannot be authenticated: {error}",
        )
        return frozenset(), (finding,)
