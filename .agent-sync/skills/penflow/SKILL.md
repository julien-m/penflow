---
name: penflow
description: Use the Penflow CLI for Pencil .pen context validation, expected/actual UI-tree comparison, reports, codegen handoff, and deterministic visual-fix review.
---

# Penflow Skill

Use this skill when a task mentions Penflow, Pencil `.pen`, `context`, expected UI trees, actual UI trees, compare reports, or structural design/runtime validation.

## Preconditions

- Run commands from the Penflow project root.
- Install in editable mode when needed:
  ```bash
  python3 -m pip install -e ".[dev]"
  ```
- Do not launch Xcode, Playwright, browsers, simulators, or app builds from this skill. External frameworks provide actual artifacts.

## Deterministic Commands

```bash
penflow inspect path/to/ui.pen
penflow validate-pen path/to/ui.pen
penflow export-expected path/to/ui.pen -o expected-ui-tree.json
penflow validate-actual actual-ui-tree.json
penflow compare-tree expected-ui-tree.json actual-ui-tree.json --out compare-report.json --markdown compare-report.md
penflow ci path/to/ui.pen actual-ui-tree.json --threshold 0.9
```

## LLM Review Mode

1. **Read** `compare-report.json` and optional `compare-report.md`.
2. **Read** expected and actual UI trees.
3. If screenshots are provided, inspect them as supporting evidence only.
4. Explain each issue by `semantic_id`, severity, likely cause, and whether the fix belongs in code, `.pen`, or upstream actual-tree extraction.

## LLM Fix Mode

1. Fix deterministic errors first: missing nodes, role mismatch, invalid context, broken bindings.
2. Apply code or `.pen` changes only when the report identifies a stable `semantic_id`.
3. Re-run `penflow validate-pen`, `penflow validate-actual`, and `penflow compare-tree`.
4. Stop with the remaining report if the issue requires a runtime artifact not available locally.

## cc-hub Sync

This skill is project-local under `.agent-sync/skills/penflow/` and is ready for cc-hub/agent-sync symlink management.

