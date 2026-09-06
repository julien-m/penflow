# @spec FR-011: Preserve noncertifying preparation/status while enforcing C51 at the consumer's existing closure stage. — .specs/features/077-complete-verification-workflow/spec.md#fr-011
"""Portable Brainstorm authority packages without access to historical source paths."""

from pathlib import Path
from typing import Any

from .product_freeze import load_frozen_product
from .product_mapping import validate_product_mapping
from .product_projection import product_requirements
from .verification_assertions import json_values_equal
from .verification_files import InputReader, VerificationInputError
from .verification_json import digest


def collect_brainstorm_authority(
    report_path: str | Path, *, project_root: str | Path
) -> dict[str, Any]:
    """Collect an exact source inventory only after public design certification succeeds."""
    from .verification import validate_verification_report
    from .verification_snapshot import load_source_snapshot

    validation = validate_verification_report(
        report_path, project_root=project_root, required_profile="design"
    )
    if validation["status"] != "PASS":
        raise VerificationInputError("authority.source.design_not_verified")
    reader = InputReader(Path(project_root))
    report_file = reader.path(report_path)
    report = reader.object(reader.read(report_file), "report")
    snapshot = load_source_snapshot(reader, report_file.parent)
    if "product" not in snapshot.upstream or "baseline" in snapshot.upstream:
        raise VerificationInputError("authority.source.not_brainstorm")
    for reference in report["sources"]:
        reader.reference(reference)
    reader.recheck()
    if digest(reader.read(report_file)) != validation["report_sha256"]:
        raise VerificationInputError("authority.source.report_changed")
    return {
        "scope": report["scope"],
        "workspace": str(snapshot.workspace),
        "report": {"path": str(report_file), "sha256": validation["report_sha256"]},
        "files": [
            {"source_path": str(path), "path": str(path), "sha256": sha}
            for path, sha in sorted(reader.observed.items())
        ],
    }


def read_brainstorm_authority(reader: InputReader, reference: dict[str, str]) -> dict[str, Any]:
    """Authenticate a local import inventory and recompute its frozen product authority."""
    package = reader.object(reader.reference(reference), "brainstorm-authority-import")
    files = _import_files(reader, package)
    workspace = _local_path(reader, package["workspace"])
    original = Path(package["origin_scope"]["workspace"])
    report_path = _local_path(reader, package["report"]["path"])
    report = reader.object(reader.reference(package["report"]), "report")
    if (
        report["scope"] != package["origin_scope"]
        or report["profile"] != "design"
        or report["status"] != "PASS"
        or report["issues"]
    ):
        raise VerificationInputError("authority.import.source_report")
    for item in report["sources"]:
        if files.get(item["path"], {}).get("sha256") != item["sha256"]:
            raise VerificationInputError("authority.import.report_source_missing")
    if files.get(str(original / "run-report.json"), {}).get("path") != str(report_path):
        raise VerificationInputError("authority.import.report_identity")
    product, sources = load_frozen_product(reader, workspace)
    for item in sources:
        relative = Path(item["path"]).relative_to(workspace)
        if files.get(str(original / relative)) != item:
            raise VerificationInputError("authority.import.product_path_mismatch")
    contract_path = workspace / "flow-ui-contract/contract.json"
    original_ref = files.get(str(original / "flow-ui-contract/contract.json"))
    if original_ref is None or original_ref["path"] != str(contract_path):
        raise VerificationInputError("authority.import.contract_missing")
    contract = reader.object(reader.reference(original_ref))
    expected_sources = sorted(
        [
            {
                "path": str(original / Path(item["path"]).relative_to(workspace)),
                "sha256": item["sha256"],
            }
            for item in sources
        ],
        key=lambda item: item["path"],
    )
    if contract.get("requirements", {}).get("source_refs") != expected_sources:
        raise VerificationInputError("authority.import.original_sources")
    archive_ref = {"path": str(reader.path(reference["path"])), "sha256": reference["sha256"]}
    return {
        "product": product,
        "contract": contract,
        "sources": [
            archive_ref,
            *[{"path": item["path"], "sha256": item["sha256"]} for item in files.values()],
        ],
    }


def _local_path(reader: InputReader, value: str) -> Path:
    if Path(value).is_absolute() or ".." in Path(value).parts:
        raise VerificationInputError("authority.import.relative_path_required")
    return reader.path(value)


def _import_files(reader: InputReader, package: dict[str, Any]) -> dict[str, dict[str, str]]:
    files: dict[str, dict[str, str]] = {}
    destinations: set[Path] = set()
    origin = Path(package["origin_scope"]["project_root"])
    for entry in package["files"]:
        source = Path(entry["source_path"])
        path = _local_path(reader, entry["path"])
        if (
            not source.is_absolute()
            or not source.is_relative_to(origin)
            or str(source) in files
            or path in destinations
        ):
            raise VerificationInputError("authority.import.duplicate_or_foreign_file")
        ref = {"path": str(path), "sha256": entry["sha256"]}
        reader.reference(ref)
        files[str(source)] = ref
        destinations.add(path)
    return files


def inherited_projection(
    reader: InputReader, reference: dict[str, str], contract: dict[str, Any]
) -> dict[str, Any]:
    """Project the frozen product denominator onto explicit current C20 bindings."""
    imported = read_brainstorm_authority(reader, reference)
    requirements = product_requirements(imported["product"])
    ids = {row["id"] for row in requirements}
    outcomes = {row["obligation_id"]: row for row in contract.get("outcome_expectations", [])}
    bindings = []
    for row in contract.get("requirements", {}).get("bindings", []):
        if row["requirement_id"] in ids:
            expected = outcomes.get(row["obligation_id"])
            if expected is None:
                raise VerificationInputError("authority.import.binding_missing")
            bindings.append({**row, "category": expected["category"], "expected": expected})
    projection = {
        "source_kind": "brainstorm-product-v1",
        "sources": imported["sources"],
        "requirements": requirements,
        "bindings": bindings,
        "uncovered": sorted(ids - {row["requirement_id"] for row in bindings}),
    }
    if projection["uncovered"]:
        raise VerificationInputError("authority.import.requirements_uncovered")
    validate_product_mapping(imported["product"], contract, projection)
    _preserved_expectations(imported["contract"], projection)
    return {
        **projection,
        "product": imported["product"],
        "verification_policy": imported["contract"].get("verification_policy"),
    }


def _preserved_expectations(original: dict[str, Any], projection: dict[str, Any]) -> None:
    old = {row["obligation_id"]: row for row in original.get("outcome_expectations", [])}
    for binding in original.get("requirements", {}).get("bindings", []):
        expected = old[binding["obligation_id"]]
        candidates = [
            row["expected"]
            for row in projection["bindings"]
            if row["requirement_id"] == binding["requirement_id"]
        ]
        if not any(
            row["category"] == expected["category"]
            and all(
                any(json_values_equal(predicate, candidate) for candidate in row["assertions"])
                for predicate in expected["assertions"]
            )
            for row in candidates
        ):
            raise VerificationInputError("authority.import.weakened_expectations")


def project_brainstorm_authority(
    import_path: str | Path, *, project_root: str | Path, contract_path: str | Path
) -> dict[str, Any]:
    """Expose imported source projection to CLI-only workflow consumers."""
    reader = InputReader(Path(project_root))
    reference = {"path": str(import_path), "sha256": digest(reader.read(import_path))}
    result = inherited_projection(reader, reference, reader.object(reader.read(contract_path)))
    reader.recheck()
    return {
        key: result[key]
        for key in (
            "sources",
            "requirements",
            "bindings",
            "uncovered",
            "product",
            "verification_policy",
        )
    }
