"""Revalidate conversion of real retained captures; this is not a C51 certification."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from convert_observations import convert
from convert_tree import convert as convert_tree
from convert_causal import convert as convert_causal
from penflow.causal_evidence import validate_causal_evidence
from penflow.tree import validate_actual_tree
from penflow.verification_outcomes import evaluate_outcome
from penflow.verification_schema import schema_issues


def _copy_captured_evidence(
    run: Path, destination: Path, project: Path, evidence: list[dict[str, str]]
) -> None:
    """Copy only raw capture bytes authenticated by the retained manifest."""
    destination.mkdir()
    bound = {str((project / row["path"]).resolve()): row["sha256"] for row in evidence}
    for path in (run / "evidence").glob("*.json"):
        if path.name.endswith((".browser.json", ".storage.json")):
            raw = path.read_bytes()
            assert bound.get(str(path.resolve())) == hashlib.sha256(raw).hexdigest()
            (destination / path.name).write_bytes(raw)


def _arguments() -> argparse.Namespace:
    """Parse the retained run, approved contract and isolated test destination."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    """Test real conversion plus independence from intentionally poisoned expectations."""
    args = _arguments()
    manifest = json.loads((args.run / "build-manifest.json").read_text())
    project = Path(manifest["scope"]["project_root"])
    args.output.resolve().relative_to(project)
    args.output.mkdir(parents=True, exist_ok=False)
    captured = args.output / "captured-evidence"
    _copy_captured_evidence(args.run, captured, project, manifest["evidence"])
    contract = json.loads(args.contract.read_text())
    expected = {row["obligation_id"]: row for row in contract["outcome_expectations"]}
    paths = convert(
        args.contract,
        captured,
        args.output / "observations",
        project,
        manifest["build"]["id"],
        manifest["producer"]["invocation_id"],
    )
    issues = {}
    originals = {}
    for path in paths:
        observation = json.loads(path.read_text())
        identifier = observation["obligation_id"]
        found = evaluate_outcome(expected[identifier], observation, contract=contract)
        facts = json.loads((project / observation["evidence"]["path"]).read_text())
        found += schema_issues(facts, "runtime-facts")
        if found:
            issues[identifier] = found
        originals[identifier] = observation
    identity = {
        "contract_sha256": hashlib.sha256(args.contract.read_bytes()).hexdigest(),
        "build_id": manifest["build"]["id"],
        "producer_invocation_id": manifest["producer"]["invocation_id"],
    }
    tree_paths = convert_tree(captured, args.output, project, identity)
    tree = json.loads(tree_paths[0].read_text())
    tree_issues = validate_actual_tree(tree, schema=True)
    for path in captured.glob("*.ui-snapshot.json"):
        tree_issues += schema_issues(json.loads(path.read_text()), "ui-snapshot")
    causal = convert_causal(args.contract, captured, args.output, project)
    causal_issues = validate_causal_evidence(args.contract, causal[0])["issues"] if causal else []
    for row in contract["outcome_expectations"]:
        for assertion in row["assertions"]:
            assertion["expected"] = {"deliberately": "wrong expected output"}
    poisoned = args.output / "poisoned-test-input.json"
    poisoned.write_text(json.dumps(contract))
    poisoned_evidence = args.output / "poisoned-evidence"
    poisoned_evidence.mkdir()
    for path in captured.glob("*.json"):
        if path.name.endswith((".browser.json", ".storage.json")):
            (poisoned_evidence / path.name).write_bytes(path.read_bytes())
    wrong_paths = convert(
        poisoned,
        poisoned_evidence,
        args.output / "poisoned-observations",
        project,
        manifest["build"]["id"],
        manifest["producer"]["invocation_id"],
    )
    for path in wrong_paths:
        wrong = json.loads(path.read_text())
        original = originals[wrong["obligation_id"]]
        assert all(wrong[key] == original[key] for key in ("before", "after", "result"))
    report = {
        "mode": "historical-conversion-test-not-certification",
        "contract_sha256": hashlib.sha256(args.contract.read_bytes()).hexdigest(),
        "observations": len(paths),
        "issues": issues,
        "actual_issues": tree_issues,
        "causal_issues": causal_issues,
        "screens": len(tree["screens"]),
        "states": len(tree["observed_states"]),
        "poisoned_expectations_do_not_change_facts": True,
    }
    output = args.output / "conversion-check.json"
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"report": str(output), **report}))
    raise SystemExit(bool(issues or tree_issues or causal_issues))


if __name__ == "__main__":
    main()
