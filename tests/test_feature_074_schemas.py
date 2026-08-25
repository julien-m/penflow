"""Contract tests for the strict Feature 074 bundled JSON Schemas."""

from collections.abc import Iterator
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from penflow.artifact_policy import PRODUCER_COMMANDS
from penflow.schema_cache import load_schema, validator_for

SCHEMA_NAMES = (
    "doctor-report.schema.json",
    "lifecycle-report.schema.json",
    "managed-run-manifest.schema.json",
    "cleanup-receipt.schema.json",
)


def _doctor_report() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "stable_result": {
            "status": "PASS",
            "project_root": "/tmp/consumer",
            "canonical_pen": "penflow/ui.pen",
            "findings": [],
            "actions": [],
            "git": {
                "index_sha256_before": None,
                "index_sha256_after": None,
                "index_unchanged": True,
                "porcelain_sha256_before": None,
                "porcelain_sha256_after": None,
                "porcelain_unchanged": True,
                "paths": [],
            },
            "runs": [],
            "cleanup": {"status": "NOT_APPLICABLE"},
            "summary": {
                "finding_count": 0,
                "blocking_count": 0,
                "action_count": 0,
                "changed": False,
            },
        },
        "diagnostics": {
            "observed_at": "2026-08-25T10:00:00Z",
            "invocation_path": "/tmp/consumer/nested",
            "explicit_project": False,
            "repository_kind": "worktree",
            "error": None,
        },
    }


def _cleanup_receipt() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "run_id": "run-001",
        "phase": "postflight",
        "cleanup_state": "completed",
        "deleted": [
            {
                "relative_path": ".penflow-tmp/runs/run-001/work.json",
                "logical_bytes": 12,
                "code": None,
            }
        ],
        "preserved": [],
        "blocked": [],
        "errors": [],
        "reclaimed_bytes": 12,
        "preserved_bytes": 0,
        "blocked_bytes": 0,
    }


def _manifest() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "revision": 4,
        "run_id": "run-001",
        "command": "run",
        "producer_state": "succeeded",
        "cleanup_state": "eligible",
        "created_at": "2026-08-25T10:00:00Z",
        "updated_at": "2026-08-25T10:01:00Z",
        "owner": {
            "pid": 123,
            "process_start_token": "987654",
            "host_id": "host-a",
            "boot_id": "boot-a",
            "verification": "LIVE",
        },
        "entries": [
            {
                "relative_path": ".penflow-tmp/runs/run-001/work.json",
                "kind": "regular_file",
                "device": 1,
                "inode": 2,
                "mode": 33188,
                "link_count": 1,
                "logical_bytes": 12,
                "retention": "working",
                "references": [],
                "cleanup_status": "pending",
            }
        ],
        "durable_outputs": [
            {
                "relative_path": "expected-ui-tree.json",
                "sha256": "a" * 64,
                "finalized": True,
                "manifest_revision": 3,
            }
        ],
        "last_cleanup_receipt": None,
        "blocking_findings": [],
    }


def _lifecycle_report() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "stable_result": {
            "status": "PASS",
            "project_root": "/tmp/consumer",
            "canonical_pen": "penflow/ui.pen",
            "findings": [],
            "actions": [],
            "git": {
                "index_sha256_before": "b" * 64,
                "index_sha256_after": "b" * 64,
                "index_unchanged": True,
                "porcelain_sha256_before": "c" * 64,
                "porcelain_sha256_after": "c" * 64,
                "porcelain_unchanged": True,
                "paths": [],
            },
            "runs": [_manifest()],
            "cleanup": _cleanup_receipt(),
            "summary": {
                "finding_count": 0,
                "blocking_count": 0,
                "action_count": 0,
                "run_count": 1,
                "reclaimed_bytes": 12,
                "preserved_bytes": 0,
                "blocked_bytes": 0,
            },
        },
        "diagnostics": {
            "observed_at": "2026-08-25T10:01:00Z",
            "pid": 123,
            "host": "host-a",
            "errors": [],
        },
    }


VALID_DOCUMENTS = {
    "doctor-report.schema.json": _doctor_report,
    "lifecycle-report.schema.json": _lifecycle_report,
    "managed-run-manifest.schema.json": _manifest,
    "cleanup-receipt.schema.json": _cleanup_receipt,
}


def _object_schemas(value: Any, path: str = "$") -> Iterator[tuple[str, dict[str, Any]]]:
    if not isinstance(value, dict):
        return
    schema_type = value.get("type")
    if schema_type == "object" or (isinstance(schema_type, list) and "object" in schema_type):
        yield path, value
    for key in ("properties", "$defs"):
        children = value.get(key)
        if isinstance(children, dict):
            for name, child in children.items():
                yield from _object_schemas(child, f"{path}.{key}.{name}")
    yield from _object_schemas(value.get("items"), f"{path}.items")


# @spec FR-006: Strict versioned schemas — .specs/features/074-penflow-doctor-consumer-project-hygiene/spec.md#fr-006
@pytest.mark.parametrize("schema_name", SCHEMA_NAMES)
def test_feature_074_schema_is_draft_2020_12_and_closes_every_object(
    schema_name: str,
) -> None:
    schema = load_schema(schema_name)
    Draft202012Validator.check_schema(schema)
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    for path, object_schema in _object_schemas(schema):
        assert object_schema.get("additionalProperties") is False, path


@pytest.mark.parametrize("schema_name", SCHEMA_NAMES)
def test_feature_074_schema_accepts_its_normative_document(schema_name: str) -> None:
    validator_for(schema_name).validate(VALID_DOCUMENTS[schema_name]())


@pytest.mark.parametrize("schema_name", SCHEMA_NAMES)
def test_feature_074_schema_rejects_unknown_top_level_properties(schema_name: str) -> None:
    document = VALID_DOCUMENTS[schema_name]()
    document["unexpected"] = True
    with pytest.raises(ValidationError):
        validator_for(schema_name).validate(document)


def test_manifest_rejects_unknown_commands_and_unsafe_paths() -> None:
    unknown_command = _manifest()
    unknown_command["command"] = "future-command"
    with pytest.raises(ValidationError):
        validator_for("managed-run-manifest.schema.json").validate(unknown_command)

    escaped_path = _manifest()
    escaped_path["entries"][0]["relative_path"] = "../ui.pen"
    with pytest.raises(ValidationError):
        validator_for("managed-run-manifest.schema.json").validate(escaped_path)

    control_plane_path = _manifest()
    control_plane_path["entries"][0]["relative_path"] = ".penflow-tmp/manifests/run-001.json"
    with pytest.raises(ValidationError):
        validator_for("managed-run-manifest.schema.json").validate(control_plane_path)


# @spec FR-010: Schema shares the command registry — .specs/features/074-penflow-doctor-consumer-project-hygiene/spec.md#fr-010
def test_manifest_command_enum_matches_the_closed_policy_registry() -> None:
    manifest_schema = load_schema("managed-run-manifest.schema.json")
    lifecycle_schema = load_schema("lifecycle-report.schema.json")
    assert set(manifest_schema["properties"]["command"]["enum"]) == PRODUCER_COMMANDS
    assert set(lifecycle_schema["$defs"]["producer_command"]["enum"]) == PRODUCER_COMMANDS
