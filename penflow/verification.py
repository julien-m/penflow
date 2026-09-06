# @spec FR-016: Synchronize canonical docs/skills and demonstrate no added manual steps, cross-consumer compatibility, and a real application pilot before the 10/10 claim. — .specs/features/077-complete-verification-workflow/spec.md#fr-016
# @spec FR-012: Execute adversarial omission/replay/mutation and positive compatibility tests across real public boundaries and installed distribution. — .specs/features/077-complete-verification-workflow/spec.md#fr-012
# @spec FR-010: Expose one public live revalidation service shared by CLI/API and consumers, with exact caller-root/workspace and independently expected build. — .specs/features/077-complete-verification-workflow/spec.md#fr-010
# @spec FR-003: Preserve explicit historical C47 behavior while preventing legacy/unknown formats from certifying C51. — .specs/features/077-complete-verification-workflow/spec.md#fr-003
# @spec FR-001: Compose every mandatory validation into one versioned profile-aware verdict using the existing run entry. — .specs/features/077-complete-verification-workflow/spec.md#fr-001
"""Public C51 production and live revalidation using one cumulative policy."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .json_filesystem import write_json_atomically
from .project_doctor import run_project_doctor
from .verification_build import load_build_manifest
from .verification_design import evaluate_design
from .verification_files import InputReader, VerificationInputError
from .verification_json import canonical_bytes, digest
from .verification_native import evaluate_native
from .verification_policy import GateBook
from .verification_runtime import evaluate_runtime
from .verification_schema import issue, schema_issues
from .verification_snapshot import VerificationSnapshot, load_source_snapshot

PROFILES = {"design", "implementation"}


def produce_verification_report(
    target: str | Path,
    *,
    project_root: str | Path,
    profile: str,
    build_manifest_path: str | Path | None = None,
) -> dict[str, Any]:
    """Produce one cumulative report after validating sources, projections and evidence.

    Args:
        target: Exact caller-selected Penflow workspace.
        project_root: Independent consumer project authority.
        profile: Design or implementation, selected by the workflow.
        build_manifest_path: Caller-owned runner authority required for implementation.
    """
    reader = InputReader(Path(project_root))
    workspace = reader.path(target)
    report = evaluate_verification(reader, workspace, profile, build_manifest_path, produce=True)
    reader.recheck()
    if workspace.is_dir():
        write_json_atomically(workspace / "run-report.json", report)
    return report


def validate_verification_report(
    report_path: str | Path,
    *,
    project_root: str | Path,
    required_profile: str,
    build_manifest_path: str | Path | None = None,
) -> dict[str, Any]:
    """Revalidate current sources and runner authority; serialized PASS never certifies itself.

    Args:
        report_path: Existing workspace/run-report.json to authenticate and revalidate.
        project_root: Independent caller project; never selected from report contents.
        required_profile: Exact workflow-required design or implementation profile.
        build_manifest_path: Independent caller-selected manifest for implementation.

    Returns:
        Closed penflow-verification-validation wrapper with exact known identities.
    """
    if required_profile not in PROFILES:
        raise VerificationInputError("verification.profile.unknown_required_profile")
    result = validation_failure(required_profile)
    try:
        reader = InputReader(Path(project_root))
        path = reader.path(report_path)
        if path.name != "run-report.json":
            raise VerificationInputError("verification.scope.report_name")
        raw = reader.read(path)
        result["report_sha256"] = digest(raw)
        report = reader.object(raw, "report")
        result["profile"] = report["profile"]
        result["scope"] = {"project_root": str(reader.root), "workspace": str(path.parent)}
        fresh = evaluate_verification(
            reader,
            path.parent,
            required_profile,
            build_manifest_path,
            produce=False,
            report_path=path,
        )
        result["build_manifest"] = fresh["build"]
        result["issues"] = _report_issues(report, fresh, required_profile)
        reader.recheck()
    except (OSError, UnicodeError, ValueError) as error:
        result["issues"].append(issue("verification.source.invalid", str(report_path), str(error)))
    result["status"] = "FAIL" if result["issues"] else "PASS"
    return result


def validation_failure(required_profile: str, *, message: str | None = None) -> dict[str, Any]:
    """Build the exact failure wrapper for parsed CLI requests failing before their handler."""
    return {
        "kind": "penflow-verification-validation",
        "version": 1,
        "status": "FAIL",
        "required_profile": required_profile,
        "profile": None,
        "report_sha256": None,
        "scope": None,
        "build_manifest": None,
        "issues": [] if message is None else [issue("verification.scope.invalid", "/", message)],
    }


def evaluate_verification(
    reader: InputReader,
    workspace: Path,
    profile: str,
    manifest_path: str | Path | None,
    *,
    produce: bool,
    report_path: Path | None = None,
) -> dict[str, Any]:
    """Apply the same source/gate/obligation policy for production and live validation."""
    gates = GateBook(profile)
    report = _empty_report(profile, reader, workspace)
    gates.evaluate("project-scope", lambda: _doctor(reader, workspace))
    try:
        if profile not in PROFILES:
            raise VerificationInputError("verification.profile.required")
        snapshot = load_source_snapshot(reader, workspace)
    except (OSError, UnicodeError, ValueError) as error:
        gates.fail("upstream-requirements", "verification.source.invalid", str(error))
        return _finish_report(report, gates)
    gates.evaluate(
        "upstream-requirements",
        lambda: (
            []
            if snapshot.policy is not None
            else [
                issue(
                    "verification.policy.missing",
                    "/verification_policy",
                    "workflow applicability requires an authenticated source and a fresh review",
                )
            ]
        ),
    )
    manifest = _verification_manifest(snapshot, profile, manifest_path, report)
    values = evaluate_design(
        snapshot, gates, produce=produce and gates.rows["project-scope"]["status"] == "PASS"
    )
    evaluate_native(snapshot, gates)
    obligations = evaluate_runtime(snapshot, gates, values, manifest)
    report["issues"].extend(obligations.pop("issues"))
    report["obligations"] = obligations
    gates.evaluate("source-final-recheck", lambda: _recheck(snapshot))
    report["sources"] = snapshot.sources(excluding={report_path} if report_path else set())
    report["evidence"] = _evidence_references(snapshot, report["sources"])
    return _finish_report(report, gates)


def _doctor(reader: InputReader, workspace: Path) -> list[dict[str, Any]]:
    result = run_project_doctor(reader.root)
    if result.exit_code:
        return [
            issue(
                "verification.scope.doctor_failed", str(reader.root), str(result.report.to_dict())
            )
        ]
    if result.context is None or result.context.project_root != reader.root:
        return [
            issue(
                "verification.scope.doctor_mismatch",
                str(reader.root),
                "Doctor resolved a different consumer project",
            )
        ]
    if not workspace.is_dir():
        return [
            issue(
                "verification.scope.workspace_missing",
                str(workspace),
                "selected workspace is absent",
            )
        ]
    return []


def _recheck(snapshot: VerificationSnapshot) -> list[dict[str, Any]]:
    snapshot.reader.recheck()
    return []


def _empty_report(profile: str, reader: InputReader, workspace: Path) -> dict[str, Any]:
    return {
        "kind": "penflow-verification-report",
        "version": 1,
        "profile": profile if profile in PROFILES else None,
        "status": "FAIL",
        "scope": {"project_root": str(reader.root), "workspace": str(workspace)},
        "policy_version": 1,
        "sources": [],
        "gates": [],
        "obligations": {"required": None, "verified": None, "missing": None, "items": []},
        "evidence": [],
        "build": None,
        "issues": [],
    }


def _finish_report(report: dict[str, Any], gates: GateBook) -> dict[str, Any]:
    report["gates"] = gates.finish()
    report["issues"].extend(finding for gate in report["gates"] for finding in gate["issues"])
    report["issues"].extend(
        finding for obligation in report["obligations"]["items"] for finding in obligation["issues"]
    )
    if not report["obligations"]["required"]:
        report["issues"].append(
            issue(
                "verification.obligation.empty",
                "/obligations",
                "a known nonempty source denominator is required",
            )
        )
    if report["obligations"]["missing"]:
        report["issues"].append(
            issue(
                "verification.obligation.incomplete",
                "/obligations",
                "some source duties remain unverified",
            )
        )
    report["issues"].sort(key=lambda value: (value["code"], value["path"], value["message"]))
    report["status"] = "FAIL" if report["issues"] else "PASS"
    return report


def _evidence_references(
    snapshot: VerificationSnapshot, sources: list[dict[str, str]]
) -> list[dict[str, str]]:
    return [
        reference
        for reference in sources
        if Path(reference["path"]).is_relative_to(snapshot.workspace)
        and Path(reference["path"]).name != "contract.json"
    ]


def _report_issues(
    report: dict[str, Any], fresh: dict[str, Any], required_profile: str
) -> list[dict[str, Any]]:
    findings = list(fresh["issues"])
    if report["profile"] != required_profile:
        findings.append(
            issue(
                "verification.profile.mismatch",
                "/profile",
                "report must use exactly the caller-required profile",
            )
        )
    if canonical_bytes(report) != canonical_bytes(fresh):
        findings.append(
            issue(
                "verification.source.report_changed",
                "/",
                "report does not equal the independently recomputed current result",
            )
        )
    findings.extend(schema_issues(fresh, "report"))
    return findings


def _verification_manifest(
    snapshot: VerificationSnapshot,
    profile: str,
    manifest_path: str | Path | None,
    report: dict[str, Any],
) -> dict[str, Any] | None:
    manifest = None
    if profile == "implementation":
        try:
            if manifest_path is None:
                raise VerificationInputError("verification.build.manifest_required")
            manifest, report["build"] = load_build_manifest(snapshot, manifest_path)
        except (OSError, UnicodeError, ValueError) as error:
            report["issues"].append(issue("verification.build.invalid", "/build", str(error)))
    elif manifest_path is not None:
        report["issues"].append(
            issue(
                "verification.build.unexpected",
                "/build",
                "design does not accept implementation build authority",
            )
        )
    return manifest
