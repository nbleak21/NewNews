# AGENTS.md

Standing instructions. Every agent session reads this file first.

<!-- HINT (template): keep this file short and imperative. Agents re-read it
every session, so each extra paragraph costs context on every run. Put history
in PROGRESS.md and work items in TASKS.md, not here. -->

## Project summary

NewNews builds one private podcast RSS feed (`feed.xml`) for a commute. Every
hour from about 4:15am to 6:15pm America/Chicago, all seven days of the week, a
script reads a list of news
podcast RSS feeds from a config file, takes the newest unplayed episode of each
show published within a freshness window (default 2 hours), and adds episodes
in priority order until the lineup runs about 25 minutes (range 20 to 30) while
keeping a mix of outlets (each source is tagged left / center-left / center /
right / international). The owner subscribes to the feed once in Overcast and
plays it through CarPlay.

## Hard rules (product)

1. **Link only.** Each item's enclosure is the original `<enclosure>` URL.
   Never download, re-host, cut or re-encode audio.
2. **Titles are prefixed** so they sort and read well in the car, e.g.
   `AM Fri 11/21 · 2/5 · Fox News Rundown — <original title>`. Item pubDates
   are a few seconds apart so the player keeps the intended order.
3. **Keep about 3 hours of items** in the feed. Older ones drop off.
   `retain_hours` (default 3) is the single retention control for both the feed
   and the SQLite state. There is no `retain_days`.
4. **Duration** comes from `<itunes:duration>`. If missing, estimate it from
   the enclosure `length` (bytes):
   `seconds ~= bytes * 8 / (assumed_bitrate_kbps * 1000)`, default 128 kbps.
   This is an approximation. If `length` is also missing or zero, skip the
   episode. Never download audio to measure it.
5. **Be polite to publishers:** descriptive User-Agent, conditional GET
   (ETag / Last-Modified), and each feed fetched at most once per run.
6. **Public but unguessable URL:** the feed is served at a path containing a
   long random token, because Overcast and Pocket Casts fetch from their own
   servers and cannot reach a Tailscale-only URL. Plan for Tailscale Funnel
   serving a static folder.
7. **Never guess feed URLs.** Verify each one; the Apple lookup API
   `https://itunes.apple.com/lookup?id=<id>&entity=podcast` returns `feedUrl`.
8. **Tests never touch the network.** Use saved feeds in `tests/fixtures/`.

## Repo layout

```
AGENTS.md                    this file
TASKS.md                     ordered checklist; one item per session
PROGRESS.md                  dated log, append only
README.md                    human quick start, Overcast setup
Prompt.md                    the original brief (reference only)
opencode.json                OpenCode permissions for this repo
pyproject.toml, uv.lock      Python 3.12 project managed by uv
.env.example                 copy to .env (gitignored) for token / ntfy topic
config/sources.example.yaml  config schema; copy to config/sources.yaml
src/commute_news/
  config.py                  load + validate YAML, defaults
  fetch.py                   conditional-GET feed fetcher
  parse.py                   feed XML -> Episode, duration handling
  select.py                  lineup selection (pure)
  state.py                   SQLite: used episodes, ETags
  feedwriter.py              render + atomically write feed.xml
  cli.py                     `commute-news` entry point
tests/                       pytest; fixtures in tests/fixtures/
scripts/run.sh               one build, logs to logs/YYYY-MM-DD.log
scripts/agent-loop.sh        unattended OpenCode loop over TASKS.md
state/  logs/  build/        runtime output, gitignored (created on demand)
```

## Commands

```sh
uv sync                                   # set up the environment (.venv, Python 3.12)
uv run pytest                             # run the full test suite
uv run commute-news build                 # run once (writes build/<token>/feed.xml)
uv run commute-news build --dry-run       # print lineup + total minutes, write nothing
uv run ruff check . && uv run ruff format --check .   # lint
uv run ruff format .                      # auto-format
scripts/run.sh                            # what launchd runs; logs to logs/
```

`build` and `--dry-run` do not exist until TASKS.md task 8 is done; until then
they raise `NotImplementedError`.

<!-- HINT (template): list only commands that really work, exactly as typed.
Agents copy these verbatim; a wrong command here wastes a whole session. -->

## Workflow rules

1. Do exactly ONE unchecked task from TASKS.md per session: the first one.
2. Write or update tests first.
3. Run the full test suite (`uv run pytest`).
4. Only check the task off (`- [x]`) if the tests pass.
5. Append a dated entry to PROGRESS.md (template at the top of that file).
6. Make small commits with clear messages.

## Safety rules

- Stay inside this repo.
- No `git push`.
- No `rm -rf` outside `build/` or `state/`.
- No installing global packages. (`uv sync` into `.venv` is fine; adding a new
  dependency with `uv add` needs approval.)
- Never commit secrets or the feed token. Use `.env`, which is gitignored.
- If blocked, write the blocker in PROGRESS.md and stop. Don't guess.

## Style

- Type hints everywhere.
- Small pure functions; keep I/O at the edges (`fetch.py`, `state.py`, `cli.py`).
- `logging`, not `print` (the dry-run lineup output is the one exception).
- Every config value has a default.

## Decisions (settled by the owner on 2026-11-20; do not reopen)

<!-- HINT (template): when the owner answers an open question, move it here
with the date, so later sessions do not re-ask or silently choose differently. -->

1. **Schedule: hourly, every day.** One run per hour from 4:15am to 6:15pm
   America/Chicago (04:15, 05:15, ... 18:15; 15 runs a day), all seven days.
   launchd `StartCalendarInterval` has one entry per hour and no `Weekday` key.
   The brief's other line ("weekdays at 6:15 and 16:15") is discarded.
2. **Retention: `retain_hours` only.** Default 3. It controls both how long
   items stay in the feed and how long rows stay in SQLite state. `retain_days`
   does not exist. `retain_hours` must be at least `freshness_hours`, so a
   pruned episode is always too old to be picked again.
3. **Duration fallback: estimate from bytes.** Prefer `<itunes:duration>`. If
   missing, `seconds ~= bytes * 8 / (assumed_bitrate_kbps * 1000)` using the
   enclosure `length`, with `assumed_bitrate_kbps` configurable (default 128).
   It is an approximation and must be commented as one. If `length` is missing
   or zero, skip the episode.
4. **Freshness: 2 hour window accepted as is.** Once-a-day shows (The Daily,
   Up First, Morning Wire) are intentionally eligible only for about 2 hours
   after they publish. No change.

## Open questions (ask the owner; do not resolve by guessing)

<!-- HINT (template): this section is where an agent parks ambiguity instead of
inventing an answer. Move entries to "Decisions" as the owner settles them. -->

None at the moment.

## Notes on opencode.json

<!-- HINT (template): record what was verified about tool config here, so the
next person knows which parts are checked and which are assumptions. -->

Written for OpenCode v2.3.0 and checked on 2026-11-20 against the published
schema (`https://opencode.ai/config.json`), the docs pages for permissions,
agents and config, and `opencode debug agents` (which showed the rules merged
into the `build` agent).

- V2 schema: `permissions` is an ordered list of `{action, resource, effect}`.
  The LAST matching rule wins, so broad `allow` rules come first and the `ask`
  / `deny` rules after them. Agent rules are appended after the top-level ones.
- Top-level rules cover every agent, including subagents (`general`,
  `explore`), which do not inherit from the agent that spawned them. `build`
  repeats the list explicitly; `plan` is denied edits.
- The file is plain JSON with no comments on purpose. The docs say JSONC is
  supported, but that was not tested for a file named `opencode.json`.
- NOT verified: what `opencode run` does when a rule resolves to `ask` in a
  non-interactive run. The docs do not say. It may wait, so
  `scripts/agent-loop.sh` has a per-iteration timeout.
- NOT verified: that the `ask` patterns catch every form of install command.
  They are prefix patterns (`uv add *`, `pip install *`, `brew install *`,
  `npm install *`, ...). An install written another way would be allowed.
  `uv sync` and `uv run` are deliberately allowed although they can download
  the packages already pinned in `uv.lock`.
- `git push` is denied by pattern (`git push *`, `git * push *`). The schema's
  separate `policies` key (hard deny layer) was not used because its actions
  are tool-level (`tool.use`), not command-level.
- `opencode run --auto` approves everything that is not explicitly denied,
  which turns all `ask` rules into `allow`. The loop does not pass it unless
  `AGENT_LOOP_AUTO=1`.
