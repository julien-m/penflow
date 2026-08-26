# @spec(FR-001)
# @spec(FR-002)
# @spec(FR-003)
# @spec(FR-004)
# @spec(FR-005)
# @spec(FR-007)
# @spec(FR-008)
# @spec(FR-009)

from typing import Any

from .cli_commands_a import (
    cmd_checklist_from_drift,
    cmd_detect_drift,
    cmd_doctor,
    cmd_draft_pen_from_tree,
    cmd_enrich_pen,
    cmd_export_expected,
    cmd_export_semantic_tree,
    cmd_inspect,
    cmd_migrate_flow_contract,
    cmd_pencil_sync,
    cmd_reverse_pen,
    cmd_run,
    cmd_validate_actual,
    cmd_validate_actual_provenance,
    cmd_validate_causal_evidence,
    cmd_validate_flow_contract,
    cmd_validate_flow_specs,
    cmd_validate_pen,
    cmd_validate_semantic_tree,
    cmd_verify_export_operation,
    cmd_verify_pencil_persistence,
)
from .cli_context_parser import (
    register_context_artifact_commands,
    register_context_mapping,
)
from .cli_reporting import _add_lenient


def _register_doctor_run(sub: Any) -> None:
    doctor = sub.add_parser("doctor", help="check or safely repair a consumer Git project")
    doctor.add_argument("--project", default=None, help="consumer project path (default: CWD)")
    doctor.add_argument(
        "--check",
        action="store_true",
        help="explicit read-only check mode (the default when --fix is absent)",
    )
    doctor.add_argument("--fix", action="store_true", help="apply unambiguous safe repairs")
    doctor.add_argument(
        "--dry-run",
        action="store_true",
        help="plan repairs without modifying project bytes",
    )
    doctor.add_argument("--json", action="store_true", help="print machine-readable JSON")
    doctor.set_defaults(func=cmd_doctor)

    run = sub.add_parser("run", help="run the full Penflow gate chain for a workspace")
    run.add_argument("--target", required=True, help="workspace containing Penflow artifacts")
    run.add_argument("--theme-css", default=None, help="optional theme.css path")
    run.add_argument("--references", default=None, help="optional references directory")
    run.add_argument("--strict", action="store_true", help="fail on warning-only gates")
    run.add_argument(
        "--strict-closure",
        action="store_true",
        help="read-only fail-closed validation of same-run persistence, actual,"
        " references, and blocking visual evidence",
    )
    run.add_argument(
        "--actual-max-age-seconds",
        type=float,
        default=None,
        help="freshness window (seconds) for a runtime-capture actual tree in the"
        " provenance gate; default 86400 (24h). static-demo-fixture is exempt",
    )
    run.add_argument("--json", action="store_true", help="print machine-readable JSON")
    run.set_defaults(func=cmd_run)


def _register_inspect_persistence(sub: Any) -> None:
    inspect_cmd = sub.add_parser("inspect", help="inspect a .pen file")
    inspect_cmd.add_argument("--json", action="store_true", help="print machine-readable JSON")
    inspect_cmd.add_argument("pen")
    inspect_cmd.set_defaults(func=cmd_inspect)

    pencil_sync = sub.add_parser("pencil-sync", help="save Pencil editor state and re-inspect disk")
    pencil_sync.add_argument("pen")
    pencil_sync.add_argument("--expect-min-nodes", type=int, default=None)
    pencil_sync.add_argument("--expect-screens", type=int, default=None)
    pencil_sync.add_argument("--json", action="store_true", help="print machine-readable JSON")
    pencil_sync.set_defaults(func=cmd_pencil_sync)

    pencil_persistence = sub.add_parser(
        "verify-pencil-persistence",
        help="verify operator-captured pre/post Pencil bytes and write a receipt",
    )
    pencil_persistence.add_argument("observation")
    pencil_persistence.add_argument("--document", required=True)
    pencil_persistence.add_argument("--run-id", required=True)
    pencil_persistence.add_argument("--operation", required=True)
    pencil_persistence.add_argument("--out", required=True)
    pencil_persistence.add_argument(
        "--json", action="store_true", help="print machine-readable JSON"
    )
    pencil_persistence.set_defaults(func=cmd_verify_pencil_persistence)

    export_operation = sub.add_parser(
        "verify-export-operation",
        help="verify a durable native export_nodes operator request and write a receipt",
    )
    export_operation.add_argument("request")
    export_operation.add_argument("--source-pen", required=True)
    export_operation.add_argument("--run-id", required=True)
    export_operation.add_argument("--out", required=True)
    export_operation.add_argument("--json", action="store_true", help="print machine-readable JSON")
    export_operation.set_defaults(func=cmd_verify_export_operation)


def _register_validation_contracts(sub: Any) -> None:
    validate_pen = sub.add_parser(
        "validate-pen", aliases=["validate"], help="validate .pen context"
    )
    validate_pen.add_argument("--json", action="store_true", help="print machine-readable JSON")
    validate_pen.add_argument("--contract", default=None, help="v2 flow contract.json")
    validate_pen.add_argument("pen")
    _add_lenient(validate_pen)
    validate_pen.set_defaults(func=cmd_validate_pen)
    validate_pen.set_defaults(command="validate-pen")

    expected = sub.add_parser("export-expected", help="export expected UI tree from .pen")
    expected.add_argument("--json", action="store_true", help="print machine-readable JSON")
    expected.add_argument("pen")
    expected.add_argument("-o", "--out", default="expected-ui-tree.json")
    _add_lenient(expected)
    expected.set_defaults(func=cmd_export_expected)

    semantic = sub.add_parser(
        "export-semantic-tree", help="export semantic UI tree from flow-ui-contract specs"
    )
    semantic.add_argument("--json", action="store_true", help="print machine-readable JSON")
    semantic.add_argument("specs_dir")
    semantic.add_argument("-o", "--out", default="semantic-ui-tree.json")
    _add_lenient(semantic)
    semantic.set_defaults(func=cmd_export_semantic_tree)

    validate_flow_specs = sub.add_parser(
        "validate-flow-specs", help="validate flow-ui-contract Markdown specs"
    )
    validate_flow_specs.add_argument(
        "--json", action="store_true", help="print machine-readable JSON"
    )
    validate_flow_specs.add_argument("specs_dir")
    _add_lenient(validate_flow_specs)
    validate_flow_specs.set_defaults(func=cmd_validate_flow_specs)

    validate_flow_contract_cmd = sub.add_parser(
        "validate-flow-contract", help="validate strict v2 flow contract JSON"
    )
    validate_flow_contract_cmd.add_argument(
        "--json", action="store_true", help="print machine-readable JSON"
    )
    validate_flow_contract_cmd.add_argument("contract")
    _add_lenient(validate_flow_contract_cmd)
    validate_flow_contract_cmd.set_defaults(func=cmd_validate_flow_contract)


def _register_causal_migration(sub: Any) -> None:
    causal_evidence_cmd = sub.add_parser(
        "validate-causal-evidence",
        help="validate adapter-produced run-bound causal transition evidence",
    )
    causal_evidence_cmd.add_argument(
        "--json", action="store_true", help="print machine-readable JSON"
    )
    causal_evidence_cmd.add_argument("contract", help="strict v2 flow contract JSON")
    causal_evidence_cmd.add_argument("evidence", help="causal transition evidence JSON")
    causal_evidence_cmd.set_defaults(func=cmd_validate_causal_evidence)

    migrate_flow_contract_cmd = sub.add_parser(
        "migrate-flow-md-to-contract-json",
        help="explicitly migrate legacy Markdown flow specs to review-blocked v2 JSON",
    )
    migrate_flow_contract_cmd.add_argument(
        "--json", action="store_true", help="print machine-readable JSON"
    )
    migrate_flow_contract_cmd.add_argument("specs_dir")
    migrate_flow_contract_cmd.add_argument("--out", required=True)
    migrate_flow_contract_cmd.set_defaults(func=cmd_migrate_flow_contract)
    migrate_flow_contract_cmd.set_defaults(command="migrate-flow-contract")

    validate_semantic = sub.add_parser(
        "validate-semantic-tree", help="validate semantic UI tree contract"
    )
    validate_semantic.add_argument(
        "--json", action="store_true", help="print machine-readable JSON"
    )
    validate_semantic.add_argument("semantic_tree")
    _add_lenient(validate_semantic)
    validate_semantic.set_defaults(func=cmd_validate_semantic_tree)


def _register_semantic_producers(sub: Any) -> None:
    register_context_artifact_commands(sub)

    semantic_draft = sub.add_parser(
        "draft-pen-from-tree", help="generate Pencil draft from semantic UI tree"
    )
    semantic_draft.add_argument("--json", action="store_true", help="print machine-readable JSON")
    semantic_draft.add_argument("semantic_tree")
    semantic_draft.add_argument("-o", "--out", default="ui.pen")
    semantic_draft.add_argument("--theme-css", default=None, help="project theme.css to apply")
    semantic_draft.set_defaults(func=cmd_draft_pen_from_tree)

    enrich = sub.add_parser("enrich-pen", help="enrich existing Pencil file from semantic UI tree")
    enrich.add_argument("--json", action="store_true", help="print machine-readable JSON")
    enrich.add_argument("pen")
    enrich.add_argument("semantic_tree")
    enrich.add_argument("-o", "--out", default="ui.pen")
    enrich.set_defaults(func=cmd_enrich_pen)

    register_context_mapping(sub)

    reverse = sub.add_parser("reverse-pen", help="reverse Pencil file into flow specs")
    reverse.add_argument("--json", action="store_true", help="print machine-readable JSON")
    reverse.add_argument("pen")
    reverse.add_argument("--out", required=True)
    reverse.add_argument("--enrich", action="store_true")
    _add_lenient(reverse)
    reverse.set_defaults(func=cmd_reverse_pen)


def _register_drift(sub: Any) -> None:
    drift = sub.add_parser(
        "detect-drift", help="detect drift across specs, semantic tree, and Pencil"
    )
    drift.add_argument("--json", action="store_true", help="print machine-readable JSON")
    drift.add_argument("specs_dir")
    drift.add_argument("semantic_tree")
    drift.add_argument("pen")
    drift.add_argument("--out", required=True)
    drift.add_argument("--markdown", default=None)
    _add_lenient(drift)
    drift.set_defaults(func=cmd_detect_drift)

    # @spec FR-001: checklist-from-drift subcommand — .specs/features/055-checklist-from-drift-seeding/spec.md#fr-001
    # No _add_lenient: generation command with a fail-closed input contract,
    # not a validating command governed by the 049 exit policy.
    checklist_seed = sub.add_parser(
        "checklist-from-drift", help="seed a Mockup Factory checklist from a drift report"
    )
    checklist_seed.add_argument("--json", action="store_true", help="print machine-readable JSON")
    checklist_seed.add_argument("drift_report")
    checklist_seed.add_argument("--out", required=True)
    checklist_seed.add_argument("--group", default=None)
    checklist_seed.set_defaults(func=cmd_checklist_from_drift)


def _register_actual(sub: Any) -> None:
    actual = sub.add_parser("validate-actual", help="validate actual runtime UI tree")
    actual.add_argument("--json", action="store_true", help="print machine-readable JSON")
    actual.add_argument(
        "--schema",
        action="store_true",
        help="also run JSON Schema validation (draft 2020-12)",
    )
    actual.add_argument("actual")
    _add_lenient(actual)
    actual.set_defaults(func=cmd_validate_actual)

    provenance = sub.add_parser(
        "validate-actual-provenance",
        help="validate the content-bound provenance receipt of an actual UI tree",
    )
    provenance.add_argument("--json", action="store_true", help="print machine-readable JSON")
    provenance.add_argument(
        "target",
        help="workspace directory or actual-ui-tree.json path",
    )
    provenance.add_argument(
        "--actual",
        default=None,
        help="explicit actual-ui-tree.json path (overrides directory resolution)",
    )
    provenance.add_argument(
        "--expected",
        default=None,
        help="expected-ui-tree.json enabling the derived-from-expected independence check",
    )
    provenance.add_argument(
        "--surface",
        action="append",
        default=None,
        help="admissible capture surface; repeatable (e.g. --surface web)",
    )
    provenance.add_argument(
        "--max-age-seconds",
        type=float,
        default=None,
        help="reject a runtime-capture whose capturedAt is older than this window",
    )
    provenance.add_argument(
        "--require-fresh",
        action="store_true",
        help="reject qualified fixtures; only fresh runtime captures are admissible",
    )
    _add_lenient(provenance)
    provenance.set_defaults(func=cmd_validate_actual_provenance)
