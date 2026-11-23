# Contributing to NewNews

Thanks for your interest in improving NewNews. It's a small, dependency-light
Python project managed with [uv](https://docs.astral.sh/uv/).

## Development setup

Requires [uv](https://docs.astral.sh/uv/) and Python 3.12.

```sh
git clone https://github.com/nbleak21/NewNews.git
cd NewNews
uv sync                 # creates .venv and installs deps (incl. dev)
uv run pytest           # should pass
uv run ruff check       # lint
```

Run the tool against the example config without writing anything:

```sh
cp config/sources.example.yaml config/sources.yaml   # replace every TODO
uv run commute-news build --dry-run
```

## Project rules

- **Tests must never touch the network.** The end-to-end tests run offline from
  fixtures under `tests/fixtures/`; a global network guard enforces this. When
  you add a source, add a trimmed feed fixture for it (see the README's
  "Adding a new source" section).
- **Every config value has a default** in `config.py`, so a key removed from the
  YAML falls back rather than erroring.
- **No secrets in the repo.** The feed token and ntfy topic live in `.env`
  (gitignored); only `.env.example` and `config/sources.example.yaml` are
  tracked, and they ship empty / `TODO_` placeholders.
- Style: type hints, small pure functions, `logging` not `print`. `ruff` config
  lives in `pyproject.toml`.
- Every Python source carries the 2-line SPDX MIT header; keep it on new files.

Agent contributors (OpenCode / Aider / Qwen loops) follow [AGENTS.md](AGENTS.md),
which is the authority on commands, style and workflow.

## Submitting changes

1. Branch off `main`.
2. Make the change with tests; ensure `uv run pytest` and `uv run ruff check`
   both pass (CI runs both).
3. Open a pull request describing the behaviour affected.

By contributing, you agree your contributions are licensed under the MIT License
(see [`LICENSE`](LICENSE)).
