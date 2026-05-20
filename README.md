# Penflow

Penflow is a deterministic Python CLI for Pencil `.pen` design contracts. It parses `.pen` JSON, validates `context`, exports expected UI trees, validates external actual UI trees, compares both trees structurally, writes JSON/Markdown reports, and generates simple screen/code artifacts.

## Install

```bash
python -m pip install -e ".[dev]"
```

## Core Commands

```bash
penflow inspect examples/demo/ui.pen
penflow validate-pen examples/demo/ui.pen
penflow export-expected examples/demo/ui.pen -o expected-ui-tree.json
penflow validate-actual examples/demo/actual-ui-tree.json
penflow compare-tree expected-ui-tree.json examples/demo/actual-ui-tree.json --markdown compare-report.md
penflow demo --out examples/generated-demo
```

## Contract

- `.pen` stays JSON-first and runtime-agnostic.
- `context` carries semantic design intent: `semantic_id`, `role`, `intent`, `binding`, `repeat`, `entity`, `variant`, `test_id`, `tolerance`.
- Runtime frameworks provide actual UI trees; Penflow validates and compares those trees.
- The primary validation is structural and semantic, not pixel-perfect.

## Local Skill

**Read** [`.agent-sync/skills/penflow/SKILL.md`](.agent-sync/skills/penflow/SKILL.md) to use the project-local skill interface. It is stored under `.agent-sync/skills/` so cc-hub/agent-sync can symlink it when requested.

