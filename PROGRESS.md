# PROGRESS

Append-only log. Newest entry at the bottom. One entry per session.

<!-- HINT (template): agents have no memory between sessions; this file is the
memory. Write what the NEXT session needs to know, not a diary. -->

## Entry template

```
## YYYY-MM-DD — Task N: <task title>
- What changed: <files and behaviour, 1-3 bullets>
- Tests: <command run and result, e.g. `uv run pytest` 14 passed>
- Notes / blockers: <decisions made, anything the next session must know, or "none">
```

## Log

<!-- entries go below this line -->

## 2026-11-21 — Task 1: Project skeleton and `uv` setup
- What changed: Replaced the placeholder test with `tests/test_skeleton.py`
  (3 tests: package version, CLI entry point importable, config API names
  present). Removed `tests/test_placeholder.py`. No source files changed.
- Tests: `uv sync && uv run pytest && uv run ruff check .` all pass —
  `3 passed`, `All checks passed!`, `14 files already formatted`.
- Notes / blockers: none. `uv.lock` was already committed. The whole
  `src/commute_news/` package is still stubs (expected; tasks 2-8 fill them
  in). The skeleton tests only assert that names are importable, so they will
  keep passing as the project grows.
