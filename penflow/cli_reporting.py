# @spec(FR-001)
# @spec(FR-002)
# @spec(FR-003)
# @spec(FR-004)
# @spec(FR-005)
# @spec(FR-007)
# @spec(FR-008)
# @spec(FR-009)

import argparse
import json
import re
from pathlib import Path
from typing import Any

from .compare import LENIENT_THRESHOLD, STRICT_THRESHOLD
from .export_operator import validate_export_operation_receipt
from .pencil_persistence import validate_pencil_persistence_receipt
from .schema_cache import load_schema, validator_for
from .strict_closure import validate_strict_closure_report


def _add_lenient(sub_parser: argparse.ArgumentParser) -> None:
    """Mirror the global --lenient flag so it works before or after the subcommand."""
    sub_parser.add_argument(
        "--lenient",
        action="store_true",
        help="do not fail on warning-severity issues (strict is the default)",
    )


def _is_lenient(args: argparse.Namespace) -> bool:
    return bool(getattr(args, "lenient_global", False) or getattr(args, "lenient", False))


def _exit_code(issues: list[dict[str, Any]], lenient: bool) -> int:
    """Strict-by-default exit policy (feature 049).

    Errors always fail; warnings fail unless ``lenient`` is set.
    """
    severities = {issue.get("severity") for issue in issues}
    if "error" in severities:
        return 1
    if "warning" in severities and not lenient:
        return 1
    return 0


def _status(exit_code: int) -> str:
    return "PASS" if exit_code == 0 else "FAIL"


def _print(data: dict[str, Any], as_json: bool) -> None:
    if as_json:
        # allow_nan=False: never print non-standard JSON (NaN/Infinity).
        print(json.dumps(data, indent=2, sort_keys=True, allow_nan=False))
        return
    if "status" in data:
        print(f"Status: {data['status']}")
    for key, value in data.items():
        if key == "status":
            continue
        print(f"{key}: {value}")


def _has_errors(issues: list[dict[str, Any]]) -> bool:
    return any(issue.get("severity") == "error" for issue in issues)


def _resolve_threshold(explicit: float | None, lenient: bool) -> float:
    """An explicit --threshold always wins; otherwise the mode picks the default."""
    if explicit is not None:
        return explicit
    return LENIENT_THRESHOLD if lenient else STRICT_THRESHOLD


_SUPPORTED_REPORT_SCHEMA_KEYWORDS = frozenset(
    {
        "$comment",
        "$defs",
        "$id",
        "$ref",
        "$schema",
        "additionalProperties",
        "const",
        "dependentRequired",
        "description",
        "enum",
        "items",
        "minItems",
        "minLength",
        "minimum",
        "pattern",
        "properties",
        "required",
        "title",
        "type",
    }
)


def _validate_report_schema(report: Any, report_path: str | Path) -> list[dict[str, Any]]:
    if not isinstance(report, dict):
        return [{"severity": "error", "path": "$", "message": "report must be an object"}]
    schema_name = _report_schema_name(report, Path(report_path).name)
    schema = load_schema(schema_name)
    issues = _unsupported_schema_keyword_issues(schema, "$")
    if not issues:
        issues = [
            {
                "severity": "error",
                "path": _json_schema_error_path(error.absolute_path),
                "message": error.message,
            }
            for error in validator_for(schema_name).iter_errors(report)
        ]
    if report.get("kind") == "penflow-mockup-audit":
        issues.extend(_validate_mockup_audit_receipts(report, Path(report_path)))
    if report.get("kind") == "penflow-pencil-persistence-receipt":
        issues.extend(validate_pencil_persistence_receipt(report))
    if report.get("kind") == "penflow-export-operator-receipt":
        issues.extend(validate_export_operation_receipt(report))
    if report.get("kind") == "penflow-strict-closure-report":
        issues.extend(validate_strict_closure_report(report, report_path))
    return sorted(issues, key=lambda item: (item["path"], item["message"]))


def _json_schema_error_path(absolute_path: Any) -> str:
    return "$" + "".join(
        f".{part}" if isinstance(part, str) else f"[{part}]" for part in absolute_path
    )


def _validate_mockup_audit_receipts(
    report: dict[str, Any], report_path: Path
) -> list[dict[str, Any]]:
    gates = report.get("gates")
    if not isinstance(gates, list):
        return []
    base = report_path.parent
    issues: list[dict[str, Any]] = []
    for index, gate in enumerate(gates):
        if not isinstance(gate, dict):
            continue
        result = gate.get("result")
        exit_code = gate.get("exit_code")
        referenced_report = gate.get("report_path")
        path_prefix = f"$.gates[{index}]"
        if result == "not_run":
            if exit_code is not None or referenced_report is not None:
                issues.append(
                    {
                        "severity": "error",
                        "path": path_prefix,
                        "message": "not_run gates must use null exit_code and null report_path",
                    }
                )
            continue
        if result == "pass" and exit_code != 0:
            issues.append(
                {
                    "severity": "error",
                    "path": f"{path_prefix}.exit_code",
                    "message": "pass gate must have exit_code 0",
                }
            )
        if result == "fail" and (not isinstance(exit_code, int) or exit_code == 0):
            issues.append(
                {
                    "severity": "error",
                    "path": f"{path_prefix}.exit_code",
                    "message": "fail gate must have a non-zero exit_code",
                }
            )
        if not isinstance(referenced_report, str) or not referenced_report:
            issues.append(
                {
                    "severity": "error",
                    "path": f"{path_prefix}.report_path",
                    "message": "executed gates must reference an existing report_path",
                }
            )
            continue
        resolved_report = (
            Path(referenced_report)
            if Path(referenced_report).is_absolute()
            else base / referenced_report
        )
        if not resolved_report.is_file():
            issues.append(
                {
                    "severity": "error",
                    "path": f"{path_prefix}.report_path",
                    "message": f"referenced report_path does not exist: {referenced_report}",
                }
            )
    return issues


def _validate_json_schema_subset(
    value: Any, schema: dict[str, Any], path: str
) -> list[dict[str, Any]]:
    """Validate the strict subset used by bundled report schemas."""
    issues = _unsupported_schema_keyword_issues(schema, path)
    if issues:
        return issues
    expected_type = schema.get("type")
    if expected_type and not _matches_json_type(value, expected_type):
        issues.append({"severity": "error", "path": path, "message": f"expected {expected_type}"})
        return issues
    if "const" in schema and value != schema["const"]:
        issues.append(
            {"severity": "error", "path": path, "message": f"expected {schema['const']!r}"}
        )
    if "enum" in schema and value not in schema["enum"]:
        issues.append(
            {"severity": "error", "path": path, "message": f"expected one of {schema['enum']}"}
        )
    if "minLength" in schema and isinstance(value, str) and len(value) < schema["minLength"]:
        issues.append(
            {
                "severity": "error",
                "path": path,
                "message": f"expected at least {schema['minLength']} characters",
            }
        )
    # @spec FR-001: validate-report path accepts the new schema — .specs/features/056-evidence-run-identity-theme-fingerprint/spec.md#fr-001
    # re.search is the JSON Schema `pattern` semantics; anchored patterns
    # (^...$, like the manifest sha256) therefore behave as exact matches.
    if "pattern" in schema and isinstance(value, str):
        pattern = schema["pattern"]
        if not isinstance(pattern, str):
            # Fail-closed on malformed bundled schemas: report deterministically
            # instead of crashing the validator on a non-string pattern.
            issues.append(
                {
                    "severity": "error",
                    "path": f"{path}.__schema__.pattern",
                    "message": "schema pattern must be a string",
                }
            )
        else:
            try:
                matched = re.search(pattern, value)
            except re.error as exc:
                issues.append(
                    {
                        "severity": "error",
                        "path": f"{path}.__schema__.pattern",
                        "message": f"schema pattern is not a valid regex: {exc}",
                    }
                )
            else:
                if matched is None:
                    issues.append(
                        {
                            "severity": "error",
                            "path": path,
                            "message": f"expected string matching {pattern}",
                        }
                    )
    if isinstance(value, dict):
        # @spec FR-009: A lineage stamp is one atomic versioned identity —
        # .specs/features/067-wp2-9-run-pipeline/spec.md#fr-009
        dependent_required = schema.get("dependentRequired")
        if isinstance(dependent_required, dict):
            for trigger, dependencies in dependent_required.items():
                if trigger not in value or not isinstance(dependencies, list):
                    continue
                for dependency in dependencies:
                    if isinstance(dependency, str) and dependency not in value:
                        issues.append(
                            {
                                "severity": "error",
                                "path": f"{path}.{dependency}",
                                "message": f"{dependency} is required when {trigger} is present",
                            }
                        )
        for key in schema.get("required", []) or []:
            if key not in value:
                issues.append(
                    {"severity": "error", "path": f"{path}.{key}", "message": f"{key} is required"}
                )
        properties = (
            schema.get("properties", {}) if isinstance(schema.get("properties"), dict) else {}
        )
        if schema.get("additionalProperties") is False:
            for key in sorted(set(value) - set(properties)):
                issues.append(
                    {
                        "severity": "error",
                        "path": f"{path}.{key}",
                        "message": "additional property is not allowed",
                    }
                )
        for key, child_schema in properties.items():
            if key in value and isinstance(child_schema, dict):
                issues.extend(
                    _validate_json_schema_subset(value[key], child_schema, f"{path}.{key}")
                )
    elif isinstance(value, list) and isinstance(schema.get("items"), dict):
        for index, item in enumerate(value):
            issues.extend(_validate_json_schema_subset(item, schema["items"], f"{path}[{index}]"))
    return issues


def _unsupported_schema_keyword_issues(schema: dict[str, Any], path: str) -> list[dict[str, Any]]:
    issues = [
        {
            "severity": "error",
            "path": f"{path}.__schema__.{keyword}",
            "message": f"unsupported schema keyword: {keyword}",
        }
        for keyword in sorted(set(schema) - _SUPPORTED_REPORT_SCHEMA_KEYWORDS)
    ]
    properties = schema.get("properties", {})
    if isinstance(properties, dict):
        for key, child_schema in properties.items():
            if isinstance(child_schema, dict):
                issues.extend(_unsupported_schema_keyword_issues(child_schema, f"{path}.{key}"))
    items = schema.get("items")
    if isinstance(items, dict):
        issues.extend(_unsupported_schema_keyword_issues(items, f"{path}[]"))
    additional_properties = schema.get("additionalProperties")
    if isinstance(additional_properties, dict):
        issues.extend(_unsupported_schema_keyword_issues(additional_properties, f"{path}.*"))
    return issues


def _matches_json_type(value: Any, expected: str | list[str]) -> bool:
    expected_types = [expected] if isinstance(expected, str) else expected
    checks = {
        "object": lambda item: isinstance(item, dict),
        "array": lambda item: isinstance(item, list),
        "string": lambda item: isinstance(item, str),
        "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
        "number": lambda item: isinstance(item, (int, float)) and not isinstance(item, bool),
        "boolean": lambda item: isinstance(item, bool),
        "null": lambda item: item is None,
    }
    return any(
        checks[schema_type](value) for schema_type in expected_types if schema_type in checks
    )


def _report_schema_name(report: dict[str, Any], filename: str) -> str:
    feature_074_schemas = {
        "doctor-report.json": "doctor-report.schema.json",
        "lifecycle-report.json": "lifecycle-report.schema.json",
        "managed-run-manifest.json": "managed-run-manifest.schema.json",
        "cleanup-receipt.json": "cleanup-receipt.schema.json",
    }
    if filename in feature_074_schemas:
        return feature_074_schemas[filename]
    kind = report.get("kind")
    if kind == "penflow-review-report":
        return "review-report.schema.json"
    if kind == "penflow-fix-report":
        return "fix-report.schema.json"
    if kind == "penflow-drift-report":
        return "drift-report.schema.json"
    if kind == "penflow-token-lint-report":
        # @spec FR-005: Strict report schema registration — .specs/features/046-lint-design-tokens/spec.md#fr-005
        return "token-lint-report.schema.json"
    if kind == "penflow-consistency-report":
        # @spec FR-004: Strict consistency report schema registration — .specs/features/047-cross-screen-consistency-check/spec.md#fr-004
        return "consistency-report.schema.json"
    if kind == "penflow-visual-metrics-report":
        # @spec FR-007: Strict visual metrics report schema registration — .specs/features/050-deterministic-visual-metrics-audit/spec.md#fr-007
        # Must match by kind: the filename heuristic below would route
        # "visual-metrics-report.json" to the mockup visual-report schema.
        return "visual-metrics-report.schema.json"
    if kind == "penflow-vision-report":
        # @spec FR-005: Strict vision report schema registration — .specs/features/051-vision-report-contract-evidence-validator/spec.md#fr-005
        return "vision-report.schema.json"
    if kind == "penflow-mockup-audit":
        # @spec FR-003: Hardened audit report schema registration — .specs/features/052-prescriptive-rubric-bounded-fix-loop/spec.md#fr-003
        return "mockup-validation-audit.schema.json"
    if kind == "penflow-mockup-checklist":
        # @spec FR-003: Hardened checklist schema registration — .specs/features/052-prescriptive-rubric-bounded-fix-loop/spec.md#fr-003
        return "mockup-validation-checklist.schema.json"
    if kind == "penflow-pencil-persistence-receipt":
        return "pencil-persistence-receipt.schema.json"
    if kind == "penflow-export-operator-receipt":
        return "export-operator-receipt.schema.json"
    if kind == "penflow-strict-closure-report":
        return "strict-closure-report.schema.json"
    if kind == "penflow-semantic-context-coverage":
        # @spec FR-008: Strict coverage schema registration — .specs/features/076-exhaustive-bidirectional-semantic-context/spec.md#fr-008
        return "semantic-context-coverage.schema.json"
    if kind == "penflow-generated-docs":
        # @spec FR-012: Generated-docs manifest schema — .specs/features/076-exhaustive-bidirectional-semantic-context/spec.md#fr-012
        return "generated-docs.schema.json"
    if "compare" in filename or {"score", "summary", "issues"}.issubset(report):
        return "compare-report.schema.json"
    if "visual" in filename:
        return "mockup-validation-visual-report.schema.json"
    if "checklist" in filename:
        return "mockup-validation-checklist.schema.json"
    if "audit" in filename:
        return "mockup-validation-audit.schema.json"
    if "manifest" in filename:
        return "mockup-validation-manifest.schema.json"
    raise PenflowError(f"Unknown report schema for {filename}")


class PenflowError(RuntimeError):
    pass
