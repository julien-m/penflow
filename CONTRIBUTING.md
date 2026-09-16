# Contributing

## Development setup

Penflow requires Python 3.12 or newer and uses `uv` for locked development environments.

```bash
git clone https://github.com/julien-m/penflow.git
cd penflow
uv sync --extra dev --locked
uv run penflow --help
```

## Before changing code

- **Read** [AGENTS.md](AGENTS.md) and [.specs/spec-system.md](.specs/spec-system.md); shipped LiveSpec features keep `spec.md`, `plan.md`, `implementation.md`, `progress.md`, and `changelog.md` synchronized.
- Preserve the runtime-agnostic boundary. External adapters produce runtime observations; Penflow validates local artifacts.
- Never commit credentials, personal data, machine-specific run archives, or consumer evidence. `.specs/features/*/run/` is intentionally ignored.
- Add deterministic tests for behavior changes and update README commands when the public workflow changes.

## Checks

Run the repository checks before opening a pull request:

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy .
uv run python -m pytest
uv build
git diff --check
```

## Pull requests

Keep changes scoped, explain the contract or user-visible effect, identify the LiveSpec feature when applicable, and state the exact checks run. Do not bundle generated run evidence or unrelated cleanup. By contributing, you agree that your contribution is provided under the repository's [MIT License](LICENSE); only submit material you have the right to contribute.
