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
penflow review-report compare-report.json --out review.md
penflow fix-report compare-report.json --out fix.md
penflow demo --out examples/generated-demo
```

## Contract

- `.pen` stays JSON-first and runtime-agnostic.
- `context` carries semantic design intent: `semantic_id`, `role`, `intent`, `binding`, `repeat`, `entity`, `variant`, `test_id`, `tolerance`.
- Runtime frameworks provide actual UI trees; Penflow validates and compares those trees.
- The primary validation is structural and semantic, not pixel-perfect.
- Demo `.pen` files use Pencil document schema `2.11` with context shorthand strings so they can be opened in Pencil and parsed by Penflow.

## Local Skill

**Read** [`.agent-sync/skills/penflow/SKILL.md`](.agent-sync/skills/penflow/SKILL.md) to use the project-local skill interface. It is stored under `.agent-sync/skills/` so cc-hub/agent-sync can symlink it when requested.

## Conventions

Project conventions are generated from the LiveSpec stack in [`.conventions/index.md`](.conventions/index.md) and [`.conventions/manifest.yaml`](.conventions/manifest.yaml).
The stack refresh also installs the generated Python pre-commit hook in [`.githooks/pre-commit`](.githooks/pre-commit) and GitHub Actions workflows in [`.github/workflows/ci.yml`](.github/workflows/ci.yml) and [`.github/workflows/security.yml`](.github/workflows/security.yml).
