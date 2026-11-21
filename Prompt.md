You are setting up a new project called **NewNews** on my Mac Studio (Apple Silicon, macOS). Your job in THIS session is to create the project scaffold and planning files only — not to build the whole app. Later sessions will work through the task list one item at a time.

This will also act as the template for future AI augmented projects, so ensure concise hints/tips are added throughout the project files, which are commented out and can be readily deleted without impacting performance. 

## What the finished project does

Every day of the week, starting from ~4:15am to ~6:15pm, America/Chicago time, each hour a script:
1. Reads a list of news podcast RSS feeds from a config file.
2. Picks the newest unplayed episode from each show, published within a freshness window (default 2 hours).
3. Adds episodes in priority order until the total runtime is about 25 minutes (target 25 min, allowed range 20 to 30), keeping a mix of outlets (each source is tagged, e.g. left / center / right / international).
4. Writes ONE private podcast RSS feed (`feed.xml`) that I subscribe to once in Overcast on my phone and play through CarPlay.

Hard rules for the product:
- The feed only LINKS to each episode's original audio URL (the original `<enclosure>`). Never download, re-host, cut or re-encode audio.
- Episode titles in my feed are prefixed so they sort and read well in the car, e.g. `AM Fri 11/21 · 2/5 · Fox News Rundown — <original title>`. Set each item's pubDate a few seconds apart so the player keeps them in the intended order.
- Keep about 3 hours of items in the feed. Older ones drop off.
- Get each episode's length from `<itunes:duration>`. If that's missing, use the enclosure's `length` attribute or skip the episode. Don't download the audio to measure it.
- Be polite to publishers: send a descriptive User-Agent, use conditional GET (ETag/Last-Modified), and fetch each feed at most once per run.
- The feed is served through a public-but-unguessable URL (a long random token in the path). The reason: Overcast and Pocket Casts fetch feeds from their own servers, so a URL that only works inside my Tailscale network will NOT work. Plan for Tailscale Funnel serving a static folder. 

Initial sources (you MUST look up and verify the real RSS feed URLs during implementation, never guess them; the Apple lookup API `https://itunes.apple.com/lookup?id=<id>&entity=podcast` returns `feedUrl`):
- Fox News Rundown (right), priority 1
- NPR News Now (center-left; hourly ~5 min), priority 1
- WSJ What's News (center), priority 2
- BBC Global News Podcast (international), priority 2
- Morning Wire (right), priority 3
- Up First from NPR (center-left), priority 3
- The Daily from NYT (center-left), priority 4

## Tech choices
- Python 3.12, managed with `uv`. Libraries: `feedparser`, `httpx`, `pyyaml`, `feedgen` (or hand-rolled XML if simpler), `pytest`.
- State (which episodes have already gone into my feed, plus ETags) in a small SQLite file under `state/`.
- Scheduling with a **launchd** plist (not cron), weekdays at 6:15 and 16:15 local time.
- Optional failure alert through ntfy.sh (topic set in config). If it's not configured, the script still runs.
- Tests never touch the network: use saved fixture feeds in `tests/fixtures/`.

## Create these files now

1. **AGENTS.md**: the standing instructions every future agent session reads first. Include:
   - A one-paragraph project summary and the hard rules above
   - Repo layout
   - Exact commands: set up the environment, run tests, run once, dry run (prints the chosen lineup and total minutes without writing the feed), lint
   - Workflow rules:
     - Do exactly ONE unchecked task from TASKS.md per session.
     - Write or update tests first.
     - Run the full test suite.
     - Only check the task off if the tests pass.
     - Append a dated entry to PROGRESS.md.
     - Make small commits with clear messages.
   - Safety rules:
     - Stay inside this repo.
     - No `git push`.
     - No `rm -rf` outside `build/` or `state/`.
     - No installing global packages.
     - Never commit secrets or the feed token. Use `.env`, gitignored.
     - If blocked, write the blocker in PROGRESS.md and stop. Don't guess.
   - Style: type hints, small pure functions, logging rather than print statements, every config value has a default.

2. **TASKS.md**: an ordered checklist of small tasks, each one doable in a single session and each with a clear "done when" line. Suggested order:
   - Project skeleton and `uv` setup
   - Config loader and schema validation
   - Feed fetcher with conditional GET
   - Episode parser and duration handling
   - Selection algorithm (priority, freshness, source mix, fill to target)
   - SQLite state
   - Feed writer with title and pubDate ordering
   - Dry-run command line
   - Verify real feed URLs and fill in the config
   - launchd plist plus an install script
   - Static serving setup docs (Funnel vs Cloudflare)
   - ntfy alerts
   - An end-to-end test against fixtures
   - README for adding a new source

3. **PROGRESS.md**: an empty log with a template for entries (date, task, what changed, tests status, notes or blockers).

4. **README.md**: what the project is, a quick start, and how to subscribe in Overcast. Overcast: Add URL. Also suggest an Overcast Smart Playlist (this feed only, unplayed, oldest first) so CarPlay plays the lineup in order.

5. **config/sources.example.yaml**: the schema with the sources above. Put `TODO_VERIFY` placeholders where feed URLs go. Also include settings: `target_minutes`, `min_minutes`, `max_minutes`, `freshness_hours`, `max_per_source`, `slots` (am/pm with times and which sources each slot is allowed to use), `feed_title`, `public_base_url`, `retain_days`, `ntfy_topic`.

6. **Skeleton code** with empty function stubs and docstrings (no real logic yet) under `src/commute_news/`: `config.py`, `fetch.py`, `parse.py`, `select.py`, `state.py`, `feedwriter.py`, `cli.py`. Also add `tests/` with one placeholder test that passes and an empty `tests/fixtures/` folder.

7. **scripts/run.sh**: activates the environment, runs one build, and logs to `logs/` with dated files.

8. **scripts/agent-loop.sh**: an unattended loop for building out the project. For each run it should:
   - Stop when TASKS.md has no unchecked items, or after a max-iterations cap (default 15).
   - Run `opencode run` with the prompt "Read AGENTS.md, then complete the next unchecked task in TASKS.md." Check `opencode run --help` for the right flags first. Don't invent flags.
   - Run the tests. Commit if they pass. If they fail, run `git reset --hard` back to the last good commit and log the failure.
   - Wrap the whole loop in `caffeinate -dims`.
   - Send an optional ntfy ping at the end with a summary.

9. **.gitignore** (state/, logs/, build/, .env, .venv) and **.env.example**.

10. **opencode.json** for this project: per-agent permissions that allow edits and bash inside the repo, but ask before network installs and deny `git push`. Read OpenCode's current config docs and use the real schema. If you aren't sure about a key, leave a comment in AGENTS.md instead of guessing.

## When you're done
- Run the placeholder test to confirm the skeleton works.
- `git init` and make one commit: "scaffold NewNews".
- Print a short summary: the files you created, the exact command to start the agent loop, and anything I must do by hand (e.g., create the ntfy topic).
- Do NOT start implementing tasks from TASKS.md in this session.