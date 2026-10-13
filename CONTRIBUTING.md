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

- Maintainers specify features with [LiveSpec](https://github.com/julien-m/livespec); the `.specs/` working tree stays local and is not published. Describe the intended contract in the pull request instead.
- Preserve the runtime-agnostic boundary. External adapters produce runtime observations; Penflow validates local artifacts.
- Never commit credentials, personal data, machine-specific paths, run archives, or consumer evidence. Local agent and spec tooling (`.specs/`, `.agent-sync.local/`, `.claude/`, `.codex/`, `.conventions/`, `AGENTS.md`) is intentionally ignored.
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

Keep changes scoped, explain the contract or user-visible effect, and state the exact checks run. Do not bundle generated run evidence or unrelated cleanup. By contributing, you agree that your contribution is provided under the repository's [MIT License](LICENSE); only submit material you have the right to contribute.
