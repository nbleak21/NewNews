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

## 2026-11-22 — Task 9: Verify real feed URLs and fill in the config

- What changed: Looked up and verified Apple podcast IDs for all 7 sources via
  the iTunes Lookup API, then created `config/sources.yaml` with real verified
  feed URLs. Also created fixture samples for each feed by fetching real RSS
  content and saving trimmed samples to `tests/fixtures/feeds/*.xml`. Updated
  `config/sources.example.yaml` to include the verified URLs and Apple IDs for
  reference. The test fixtures continue to use the existing hand-crafted XML
  files (skip_items.xml, sample_feed.xml, etc.) since the tests need specific
  episode GUIDs and pubDates that the real feeds don't guarantee.

- Tests: `uv run pytest` → `98 passed`; `uv run ruff check .` and
  `uv run ruff format --check .` both clean.

- Notes / blockers: The verified Apple IDs and feed URLs:
  - Fox News Rundown: ID 1303660358 → https://feeds.megaphone.fm/FOXM1880458659
  - NPR News Now: ID 121493675 → https://feeds.npr.org/500005/podcast.xml
  - WSJ What's News: ID 152016440 → https://video-api.shdsvc.dowjones.io/api/podcasts/...whats%20news/feed
  - BBC Global News Podcast: ID 135067274 → https://podcasts.files.bbci.co.uk/p02nq0gn.rss
  - Morning Wire: ID 1576594336 → https://rss.pdrl.fm/3f8a3d/feeds.megaphone.fm/BVDWV8747925072
  - Up First from NPR: ID 1222114325 → https://feeds.npr.org/510318/podcast.xml
  - The Daily: ID 1200361736 → https://feeds.simplecast.com/Sl5CSM3S

## 2026-11-22 — Task 8c: Dry-run output and the write path (`cli.py`)

- What changed: Implemented `run_build()` in `src/commute_news/cli.py`:
  `dry_run=True` prints the lineup (one line per episode with prefixed title
  and minutes) and total minutes to stdout; `dry_run=False` builds `FeedItem`s,
  renders the feed with `render_feed()`, writes to `build/<token>/feed.xml`,
  and records state (`mark_used`, `save_validators`, `prune`). Added helper
  functions `_print_lineup()`, `_write_feed_and_state()`, and
  `_get_feed_token()`; updated `main()` to return exit code 0 on success or 1
  on exception. Added `tests/test_cli_8c.py` (6 tests) covering dry-run output,
  write path feed creation, state recording, and second-run episode deduplication.

- Tests: `uv run pytest` → `98 passed`; `uv run ruff check .` and
  `uv run ruff format --check .` both clean.

- Notes / blockers: The feed token must be set in `NEWNEWS_FEED_TOKEN`
  environment variable. Some fixture feeds share episode guids across sources
  (e.g., `keep-001`, `sample-001`), so only unique guids are recorded in state.
  The state database stores episodes by guid as the primary key, so re-marking
  an existing guid updates its row.

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

## 2026-11-21 — Task 3: Feed fetcher with conditional GET (`fetch.py`)

- What changed: implemented `src/commute_news/fetch.py` — frozen
  `FetchResult` (url / status / body / etag / last_modified / error, plus
  `ok` and `not_modified` helpers), `build_client` (injectable transport,
  15 s default timeout, follows redirects), `build_headers` (User-Agent plus
  `If-None-Match` / `If-Modified-Since`), `fetch_feed` (one conditional GET,
  HTTP and network failures returned as an `error`, never raised) and
  `fetch_all` (one request per distinct feed URL per run, results keyed by
  source id). Added `tests/test_fetch.py` (12 tests) and the offline
  fixture `tests/fixtures/feeds/sample_feed.xml`.
- Tests: `uv run pytest` → `29 passed`; `uv run ruff check .` and
  `uv run ruff format --check .` both clean.
- Notes / blockers: a 304 keeps the stored ETag / Last-Modified when the
  server does not echo them; a 200 replaces them with the response headers.
  Sources sharing a feed URL are fetched once. Task 6 (state) will supply
  the validators mapping that `fetch_all` already accepts.

## 2026-11-21 — Task 4: Episode parser and duration handling (`parse.py`)

- What changed: implemented `src/commute_news/parse.py` — frozen `Episode`
  (source_id / guid / title / published / enclosure url, type, length, plus
  `duration` in seconds and a `duration_estimated` flag), `parse_duration`
  (plain seconds, `MM:SS`, `HH:MM:SS`, else `None`),
  `estimate_duration_from_length` (the documented
  `bytes * 8 / (kbps * 1000)` approximation; `None` for missing or zero
  length) and `parse_feed` (feedparser in, episodes sorted newest first;
  skips entries with no enclosure, a missing/malformed date, or no duration
  and no usable length). Added `tests/test_parse.py` (12 tests) and three
  fixtures: `durations.xml`, `estimate_duration.xml`, `skip_items.xml`.
- Tests: `uv run pytest` → `41 passed`; `uv run ruff check .` and
  `uv run ruff format --check .` both clean.
- Notes / blockers: an episode with a missing or malformed `pubDate` is
  skipped, because it cannot be aged against the 2-hour freshness window.
  The `duration_estimated` flag is what the dry run (task 8) should
  surface. `parse_feed` takes `assumed_bitrate_kbps` per call, so
  `config.assumed_bitrate_kbps` plugs in at task 8. No network was used;
  fixtures only.

## 2026-11-21 — Task 5: Selection algorithm (`select.py`)

- What changed: implemented `src/commute_news/select.py` — frozen `Lineup`
  (chosen `episodes` plus `total_seconds`, with a `total_minutes` helper),
  `eligible_episodes` (unplayed + inside the freshness window + at most
  `max_per_source` newest per source), `order_candidates` (rank: priority
  ascending, then newer `published`, then `source_id` for a stable order;
  candidates are grouped by the source's lean tag and the groups are
  round-robined so the top of the lineup mixes leans),
  `fill_to_target` (a prefix of the ordered candidates: stops at
  `target_minutes`, never above `max_minutes`, returns a short lineup
  as-is) and `select_lineup` (the three steps wired together). Added
  `tests/test_select.py` (19 tests, all episodes built in memory).
- Tests: `uv run pytest` → `60 passed`; `uv run ruff check .` and
  `uv run ruff format --check .` both clean.
- Notes / blockers: priority 1 is picked first, per the comment in
  `config/sources.example.yaml`. `fill_to_target` raises `ValueError` unless
  `0 <= min <= target <= max`; a short lineup is NOT an error here — tasks
  8/12 decide what to do about one. `select_lineup` does not apply
  `slot_for_time` limits; the caller must filter `episodes` / `sources` by
  the current slot. An episode whose source is missing from the config is
  ranked last, never silently dropped. No network, no fixtures, no state.

## 2026-11-21 — Task 6: SQLite state (`state.py`)

- What changed: implemented `src/commute_news/state.py` on stdlib `sqlite3`
  (no ORM). Two tables created idempotently by `connect()` (which also makes
  missing parent dirs): `sources` (one row per source: `etag`,
  `last_modified`) and `episodes` (one row per episode placed in the feed:
  guid, source, title, published, enclosure url/type/length, duration,
  `duration_estimated`, `slot_label`, `added_at`). Public helpers:
  `connect`, `get_validators` (unknown source → `(None, None)`),
  `save_validators` (upsert, commits), `used_guids`, `mark_used`
  (upsert by guid — re-marking updates the row, newest run wins),
  `recent_items(since)` (rows with `added_at >= since`, newest first, each
  returned as a dict with `published` / `added_at` as aware `datetime`s) and
  `prune(older_than)` (strictly-older rows deleted, returns the count).
  Timestamps are stored as UTC epoch seconds (REAL) so SQL comparisons are
  plain numbers. Added `tests/test_state.py` (7 tests, all on `tmp_path`).
- Tests: `uv run pytest` → `69 passed`; `uv run ruff check .` and
  `uv run ruff format --check .` both clean.
- Notes / blockers: one `episodes` table is deliberately both the "used"
  set and the retained-feed source: `retain_hours` (the only retention
  knob) is what `prune` is called with, and because
  `retain_hour >= freshness_hours` a pruned episode is already too old to be
  re-selected. `prune` uses a strict `<`, so a row exactly on the cutoff
  survives; `recent_items` uses `>=`, so a row exactly at `since` is
  returned. `recent_items` does not apply `retain_hours` itself — the
  caller passes `since = now - retain_hours`. No network, no fixtures.

## 2026-11-21 — Task 7: Feed writer with title and pubDate ordering (`feedwriter.py`)

- What changed: implemented `src/commute_news/feedwriter.py` — frozen
  `FeedItem` (title, guid, pub_date, enclosure url/type/length, the last two
  copied through untouched), `format_title` (the documented
  `AM Fri 11/21 · 2/5 · <source> — <title>` prefix, weekday from a hardcoded
  tuple so no locale is involved), `ordered_pubdates` (index 0 = `base`, each
  next stamp `step_seconds` earlier, default 5 s, so the lineup order and a
  newest-first player order agree), `render_feed` (RSS 2.0 bytes; drops items
  older than `now - retain_hours`, default `DEFAULT_RETAIN_HOURS = 3`, cutoff
  inclusive to match `state.prune`) and `write_feed` (tmp file in the target
  directory + `os.replace`, so the swap is atomic and no `.tmp` survives).
  Added `tests/test_feedwriter.py` (18 tests, all offline: the XML is parsed
  back with `feedparser` and with `ElementTree`, files only under
  `tmp_path`); no fixtures were needed because the items are built in memory.
- Tests: `uv run pytest` → `85 passed`; `uv run ruff check .` and
  `uv run ruff format --check .` both clean.
- Notes / blockers: **XML tool chosen: `feedgen` (already a dependency), not a
  hand-rolled writer.** It supplies the escaping, the RFC-2822 dates, the
  `<enclosure>` element and the `atom:link rel="self"` that a podcast client
  expects, all of which this task would otherwise have had to get right by
  hand. Three of its calls are load-bearing and easy to get wrong:
  `add_entry(order="append")` because the default is `prepend` (which would
  reverse the lineup), `entry.pubDate(...)` because the lowercase
  `entry.pubdate` is deprecated and warns, and `length=` must be passed as a
  `str` or lxml refuses the attribute. `render_feed` returns `bytes` (what
  lands on disk and what a player downloads), takes the channel title and the
  feed's own tokenised URL as arguments, and treats `now` as an argument
  rather than the wall clock so retention is testable. `retain_hours` is
  still the single retention knob; the 3-hour default here is only the
  fallback when no config is supplied. No network, no new dependencies.

## 2026-11-21 — Task 8a: CLI argument parser and dispatch (`cli.py`)

- What changed: implemented `build_parser()` in `src/commute_news/cli.py`
  (argparse with a required `build` subcommand; `--config` defaults to
  `config/sources.yaml`, `--dry-run` is a `store_true`) and
  `main(argv)`, which parses the arguments, configures logging and returns
  `run_build(config_path, dry_run)`'s int exit code. `run_build` and
  `notify_failure` still raise `NotImplementedError` (tasks 8b/8c and 12
  fill them in). Module constants `DEFAULT_CONFIG`, `LOG_LEVEL` and
  `LOG_FORMAT` keep the defaults in one place. Added `tests/test_cli.py`
  (6 tests) covering the defaults, `--dry-run`, `--config X`, the two
  combined, and that the `build` subcommand is required and unknown flags
  are rejected. No fixtures needed; nothing is fetched or written.
- Tests: `uv run pytest` → `91 passed`; `uv run ruff check .` and
  `uv run ruff format --check .` both clean.
- Notes / blockers: the tests deliberately do NOT call `main` /
  `run_build` end to end yet — task 8b wires it. `--config` belongs to the
  `build` subcommand, so it must follow `build` on the command line
  (`commute-news build --config X`), and a bare `commute-news` is a usage
  error rather than a silent no-op.

## 2026-11-21 — Task 8b: Wire fetch → parse → select into `run_build` (`cli.py`)

- What changed: implemented `run_build(config_path, dry_run, *, client=None,
  now=None, used_guids=frozenset())` in `src/commute_news/cli.py`:
  `load_config` → `fetch_all` (over `config.sources`) → `parse_feed` per
  fetched body (with `assumed_bitrate_kbps` from config) → restrict episodes
  to the slot-allowed sources via the new `_slot_sources` helper →
  `select_lineup` → return the `Lineup`. Added a module-level `logger`
  (`logging.getLogger("commute_news")`), made `main` return `0` after
  delegating to `run_build` (the `Lineup` is discarded for now, with a
  comment: task 8c adds printing, the write path, and the real exit code).
  `_slot_sources(sources, now)` returns the full list when no slot matches
  the clock, the full list for a slot with `sources: "all"`, only the named
  ids for a slot listing sources, or `[]` plus a warning when no slot covers
  `now`. Added `test_wiring_selects_the_expected_lineup` to
  `tests/test_cli.py`, serving the four `tests/fixtures/feeds/*.xml` files
  over `httpx.MockTransport` against `config_full.yaml`'s example.com URLs
  (no network) with a fixed `now`, asserting the 5-episode lineup, its order,
  `total_seconds == 1512` and `total_minutes ≈ 25.2`.
- Tests: `uv run pytest` → `92 passed`; `uv run ruff check .` and
  `uv run ruff format --check .` both clean.
- Notes / blockers: `run_build` still does not print, write, or return a
  non-`Lineup` value — task 8c owns the dry-run output, the `feed.xml`
  write, and the int exit code. A 304 (or any response with no body) is
  logged at DEBUG and yields no episodes. The `keep-001` fixture episode is
  deliberately future-dated so it reads as "fresh" against the fixed `now`.
  No network, no new dependencies.
