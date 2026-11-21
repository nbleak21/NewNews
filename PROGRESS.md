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

## 2026-11-21 — Task 2: Config loader and schema validation (`config.py`)

- What changed: implemented `src/commute_news/config.py` (frozen `Source`,
  `Slot`, `Schedule`, `Config` dataclasses with a default for every value;
  `load_config` / `validate_config` / `slot_for_time` / `ConfigError`).
  Rejects unknown lean tags, duplicate source ids, `TODO_VERIFY` feed URLs,
  min/target/max out of order, `retain_hour < freshness_hours`, non-positive
  `assumed_bitrate_kbps`, and slots naming unknown sources. Added
  `tests/test_config.py` (14 tests) plus fixtures
  `tests/fixtures/config_full.yaml` (mirrors
  `config/sources.example.yaml` with example.com URLs, never fetched) and
  `tests/fixtures/config_empty.yaml`.
- Tests: `uv run ruff check . && uv run ruff format --check .` and
  `uv run pytest` both pass — `17 passed`, `All checks passed!`,
  `15 files already formatted`.
- Notes / blockers: `slot_for_time` is implemented (HH:MM windows, inclusive
  both ends, `None` outside every slot) and covered by a test; the other
  modules in `src/commute_news/` are still stubs. The fixture uses
  `example.com` URLs on purpose: no real feed URL was guessed.
