# @spec AC-014 AC-015 FR-012: Feature 074 real-consumer proof.
# @spec FR-010 AC-012: Feature 075 exact-identity compatibility proof.
"""Real-consumer hygiene proof responsibility module."""

from __future__ import annotations

import argparse
import json
import socket
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from tests.consumer_project_hygiene_discovery import capture_project_snapshot, discover_consumers
from tests.consumer_project_hygiene_execution import (
    _atomic_write_json,
    _check_consumer_copy,
    _check_live_consumer,
    _exercise_consumer_copy,
    _inventory_receipt_row,
    _probe_receipt,
    _reject_live_mutation_paths,
    _run_command,
)
from tests.consumer_project_hygiene_types import (
    CommandResult,
    CommandRunner,
    ConsumerMarker,
    CopyExerciser,
    JsonReceipt,
)

__all__ = ("CommandResult", "capture_project_snapshot", "discover_consumers", "run_probe")

SOURCE_PROJECT_ROOT = Path(__file__).resolve().parents[1]


def run_probe(
    *,
    search_roots: Sequence[Path],
    output: Path,
    expected_markers: Sequence[str] = (),
    command_runner: CommandRunner | None = None,
    copy_exerciser: CopyExerciser | None = None,
    temporary_parent: Path | None = None,
    excluded_roots: Sequence[Path] | None = None,
    expected_inventory_receipt: Path | None = None,
) -> JsonReceipt:
    """Prove live hygiene read-only, then exercise mutation only on fresh Git copies."""
    effective_exclusions = (
        tuple(excluded_roots) if excluded_roots is not None else (SOURCE_PROJECT_ROOT,)
    )
    consumers = discover_consumers(search_roots, excluded_roots=effective_exclusions)
    _reject_live_mutation_paths(consumers, output, temporary_parent)
    expected_pairs = (
        _load_expected_identity_pairs(expected_inventory_receipt)
        if expected_inventory_receipt is not None
        else None
    )
    assertions = _initial_assertions(consumers, expected_markers, expected_pairs)
    inventory_rows = [_inventory_receipt_row(consumer) for consumer in consumers]
    diagnostics = _initial_diagnostics(consumers, search_roots, effective_exclusions)
    _write_probe_state(output, "RUNNING", assertions, inventory_rows, [], diagnostics)
    identity_mismatch = any(
        assertion == "authoritative_identity_pairs_exact:FAIL" for assertion in assertions
    )
    if not consumers or identity_mismatch:
        return _write_probe_state(
            output,
            "FAIL",
            assertions,
            inventory_rows,
            [],
            diagnostics | {"finished_at": datetime.now(UTC).isoformat()},
        )

    consumer_results, copy_roots = _run_consumer_checks(
        consumers, command_runner, copy_exerciser, temporary_parent
    )
    assertions.extend(_result_assertions(consumer_results))
    status = "PASS" if all(assertion.endswith(":PASS") for assertion in assertions) else "FAIL"
    diagnostics["copy_roots"] = copy_roots
    diagnostics["finished_at"] = datetime.now(UTC).isoformat()
    return _write_probe_state(
        output,
        status,
        assertions,
        inventory_rows,
        consumer_results,
        diagnostics,
    )


def _write_probe_state(
    output: Path,
    status: str,
    assertions: Sequence[str],
    inventory_rows: Sequence[JsonReceipt],
    consumer_results: Sequence[JsonReceipt],
    diagnostics: JsonReceipt,
) -> JsonReceipt:
    """Persist and return one complete probe state using the shared schema."""

    receipt = _probe_receipt(
        status=status,
        assertions=list(assertions),
        inventory_rows=list(inventory_rows),
        consumer_results=list(consumer_results),
        diagnostics=diagnostics,
    )
    _atomic_write_json(output, receipt)
    return receipt


def _initial_assertions(
    consumers: Sequence[ConsumerMarker],
    expected_markers: Sequence[str],
    expected_pairs: tuple[tuple[str, str], ...] | None = None,
) -> list[str]:
    assertions = [f"inventory_non_empty:{'PASS' if consumers else 'FAIL'}"]
    discovered_paths = {consumer.marker_relative for consumer in consumers}
    assertions.extend(
        f"expected_marker:{expected}:{'PASS' if expected in discovered_paths else 'FAIL'}"
        for expected in sorted(set(expected_markers))
    )
    if expected_pairs is not None:
        actual_pairs = tuple(
            sorted(
                (consumer.marker_relative, consumer.companion_relative) for consumer in consumers
            )
        )
        assertions.append(
            "authoritative_identity_pairs_exact:"
            + ("PASS" if actual_pairs == expected_pairs else "FAIL")
        )
    return assertions


def _load_expected_identity_pairs(receipt_path: Path) -> tuple[tuple[str, str], ...]:
    """Load the immutable Feature 074 marker/companion identity contract."""

    try:
        payload = json.loads(receipt_path.read_text(encoding="utf-8"))
        stable = payload["stable_result"]
        inventory = stable["inventory"]
        if stable["feature"] != "074-penflow-doctor-consumer-project-hygiene":
            raise ValueError("authoritative receipt has the wrong feature marker")
        pairs = tuple(sorted((row["marker"], row["companion"]) for row in inventory))
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as error:
        raise ValueError("authoritative identity receipt is unreadable or malformed") from error
    if len(pairs) != 11 or len(set(pairs)) != 11:
        raise ValueError("authoritative identity receipt must contain exactly 11 unique pairs")
    return pairs


def _initial_diagnostics(
    consumers: Sequence[ConsumerMarker],
    search_roots: Sequence[Path],
    excluded_roots: Sequence[Path],
) -> dict[str, object]:
    return {
        "started_at": datetime.now(UTC).isoformat(),
        "finished_at": None,
        "host": socket.gethostname(),
        "search_roots": [str(Path(root).expanduser().resolve()) for root in search_roots],
        "excluded_roots": [str(Path(root).expanduser().resolve()) for root in excluded_roots],
        "live_project_roots": [
            str(consumer.project_root) if consumer.project_root is not None else None
            for consumer in consumers
        ],
        "copy_roots": [],
    }


def _run_consumer_checks(
    consumers: Sequence[ConsumerMarker],
    command_runner: CommandRunner | None,
    copy_exerciser: CopyExerciser | None,
    temporary_parent: Path | None,
) -> tuple[list[JsonReceipt], list[str]]:
    runner = command_runner or _run_command
    exercise_copy = copy_exerciser or (
        lambda copy_root, copied_marker: _exercise_consumer_copy(copy_root, copied_marker, runner)
    )
    rows: list[JsonReceipt] = []
    copy_roots: list[str] = []
    for consumer in consumers:
        live = _check_live_consumer(consumer, runner)
        copy_result, copy_root = _check_consumer_copy(
            consumer, exercise_copy, temporary_parent=temporary_parent
        )
        copy_roots.append(str(copy_root))
        rows.append(
            {
                "label": consumer.label,
                "marker": consumer.marker_relative,
                "live": live,
                "copy": copy_result,
            }
        )
    return rows, copy_roots


def _result_assertions(rows: Sequence[JsonReceipt]) -> list[str]:
    assertions = [
        f"{row['label']}:live_zero_diff:{'PASS' if row['live']['zero_diff'] else 'FAIL'}"
        for row in rows
    ]
    assertions.extend(
        f"{row['label']}:live_outcome:{'PASS' if row['live']['status'] == 'PASS' else 'FAIL'}"
        for row in rows
    )
    assertions.extend(
        f"{row['label']}:copy:{'PASS' if row['copy'].get('status') == 'PASS' else 'FAIL'}"
        for row in rows
    )
    return assertions


def main(argv: Sequence[str] | None = None) -> int:
    """Parse the closed probe CLI and return zero only for complete PASS evidence."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--search-root", action="append", required=True, type=Path)
    parser.add_argument("--expect-marker", action="append", default=[])
    parser.add_argument("--expected-inventory-receipt", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    receipt = run_probe(
        search_roots=tuple(args.search_root),
        output=args.out,
        expected_markers=tuple(args.expect_marker),
        expected_inventory_receipt=args.expected_inventory_receipt,
    )
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    return 0 if receipt["stable_result"]["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
