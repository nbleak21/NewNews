# TASKS

Ordered checklist. Do the FIRST unchecked item, one per session, following the
workflow rules in AGENTS.md. Check a box only when its "Done when" line is true
and `uv run pytest` passes.

<!-- HINT (template): a good task fits in one session, names the files it
touches, and has a "Done when" that a test or a single command can prove.
If a task feels big, split it before starting rather than half-finishing it. -->

- [x] **1. Project skeleton and `uv` setup**
  Confirm `uv sync` works from a clean clone, `uv.lock` is committed, `ruff`
  passes on the stubs, and the commands in AGENTS.md are accurate.
  *Done when:* `uv sync && uv run pytest && uv run ruff check .` all succeed
  from a fresh checkout.

- [x] **2. Config loader and schema validation** (`config.py`)
  Load YAML into frozen dataclasses with a default for every value. Reject
  unknown lean tags, duplicate source ids, `TODO_VERIFY` feed URLs, min / target
  / max out of order, `retain_hours` below `freshness_hours`, a non-positive
  `assumed_bitrate_kbps`, and slots that name unknown sources.
  *Done when:* tests load `config/sources.example.yaml` structure from a
  fixture, cover each rejection case, and cover an empty file giving defaults.

- [x] **3. Feed fetcher with conditional GET** (`fetch.py`)
  httpx client with descriptive User-Agent, `If-None-Match` /
  `If-Modified-Since`, timeouts, one request per feed per run. Errors are
  returned, not raised.
  *Done when:* tests using `httpx.MockTransport` prove 200, 304, 404, timeout,
  header contents, and that each URL is requested exactly once.

- [x] **4. Episode parser and duration handling** (`parse.py`)
  feedparser to `Episode`. Parse `itunes:duration` as seconds, `MM:SS` and
  `HH:MM:SS`. If it is missing, estimate from the enclosure `length` in bytes:
  `seconds ~= bytes * 8 / (assumed_bitrate_kbps * 1000)` (config, default 128),
  commented as an approximation. If `length` is missing or zero, skip.
  *Done when:* tests against hand-written fixture feeds in `tests/fixtures/`
  cover all three duration formats, a missing duration with a usable `length`
  (checked against the formula), a missing duration with missing and with zero
  `length` (skipped), a missing enclosure and a malformed date.

- [x] **5. Selection algorithm** (`select.py`)
  Pure functions: freshness filter, unplayed filter, newest per source,
  priority order with lean mix, fill to target within min..max.
  *Done when:* table-driven tests cover: exact fit, overshoot avoided,
  undershoot (short lineup), nothing fresh, all used, tie on priority, and a
  case showing the lean mix is kept.

- [x] **6. SQLite state** (`state.py`)
  Schema creation, ETag / Last-Modified per source, used episodes, recent items
  for the retained feed, pruning rows older than `retain_hours` (the only
  retention setting).
  *Done when:* tests on a `tmp_path` database prove round-trips for each
  function, that pruning removes only rows older than `retain_hours`, and that
  re-opening the file keeps the data.

- [ ] **7. Feed writer with title and pubDate ordering** (`feedwriter.py`)
  Title prefix, pubDates a few seconds apart, original enclosure URL / type /
  length passed through untouched, `retain_hours` (default 3) of items
  retained, atomic write.
  *Done when:* tests parse the generated XML back and assert titles, order,
  enclosure URLs equal to the inputs, and that old items are dropped.

- [ ] **8. Dry-run command line** (`cli.py`)
  `commute-news build [--config PATH] [--dry-run]` wiring every module
  together. Dry run prints the lineup and total minutes and writes nothing (no
  feed, no state changes).
  *Done when:* a test runs the CLI against fixtures with fetching stubbed,
  checks the printed lineup, and asserts no file was written in dry-run mode.

- [ ] **9. Verify real feed URLs and fill in the config**
  For each source, find the Apple podcast id, call the lookup API, and record
  the returned `feedUrl`. Create `config/sources.yaml`. Save one small trimmed
  sample of each feed as a fixture. This task needs the network; tests still
  must not.
  *Done when:* no `TODO_VERIFY` remains in `config/sources.yaml`, PROGRESS.md
  lists each URL with the lookup id used, and `--dry-run` produces a lineup.

- [ ] **10. launchd plist plus an install script**
  Hourly runs, 7 days a week, 04:15 through 18:15 Central time. Plist template
  whose `StartCalendarInterval` is an array of 15 entries, one per hour
  (`Hour` 4 to 18, `Minute` 15) with no `Weekday` key so every day matches,
  calling `scripts/run.sh`. launchd uses the system time zone, so the install
  script must check the Mac is on America/Chicago and warn if not.
  `scripts/install-launchd.sh` renders paths, copies to
  `~/Library/LaunchAgents/` and loads it; include an uninstall path too.
  *Done when:* `plutil -lint` passes on the rendered plist, a test or script
  check confirms exactly 15 entries (hours 4 to 18 at minute 15, no `Weekday`),
  and the README documents install / uninstall.

- [ ] **11. Static serving setup docs (Funnel vs Cloudflare)**
  `docs/serving.md`: Tailscale Funnel serving `build/` as a static folder, the
  token-in-path layout, how to rotate the token, and a short comparison with
  Cloudflare (Tunnel or R2 / Pages) as the alternative.
  *Done when:* the doc has copy-paste steps for Funnel, states the trade-offs,
  and README links to it.

- [ ] **12. ntfy alerts**
  On failure (exception, zero sources fetched, short lineup) POST to
  `https://ntfy.sh/<topic>`. No topic configured means no request and no error.
  *Done when:* tests with a mocked transport prove a POST happens with a topic,
  nothing happens without one, and an ntfy outage does not fail the run.

- [ ] **13. End-to-end test against fixtures**
  One test that runs the whole pipeline twice from fixture feeds: first run
  writes a valid feed; second run does not repeat episodes.
  *Done when:* the test passes offline and asserts lineup length, order,
  enclosure URLs and state contents.

- [ ] **14. README for adding a new source**
  Step-by-step section: find the feed URL, verify it, add the YAML block, pick
  lean and priority, dry run, add a fixture.
  *Done when:* the README section exists and its steps were followed once for a
  real or fixture source, noted in PROGRESS.md.
