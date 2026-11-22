# NewNews

A private news podcast feed for the commute. A script on a Mac reads a list of
public news podcast RSS feeds, picks the newest unplayed episodes that fit in
about 25 minutes with a mix of outlets, and writes one RSS feed (`feed.xml`)
that you subscribe to once in Overcast and play through CarPlay.

It only links to each publisher's original audio. Nothing is downloaded,
re-hosted or edited.

**Status:** scaffold only. The modules are stubs; the work is listed in
[TASKS.md](TASKS.md) and logged in [PROGRESS.md](PROGRESS.md).

<!-- HINT (template): keep README for humans (what, quick start, how to use).
Agent instructions belong in AGENTS.md so the two do not drift. -->

## Quick start

Requires macOS, [uv](https://docs.astral.sh/uv/) and git.

```sh
uv sync                                        # creates .venv with Python 3.12
uv run pytest                                  # should pass
cp .env.example .env                           # then set NEWNEWS_FEED_TOKEN
cp config/sources.example.yaml config/sources.yaml   # then replace every TODO
uv run commute-news build --dry-run            # prints the lineup (after task 8)
uv run commute-news build                      # writes the feed (after task 8)
```

Feed URLs in the example config are `TODO_VERIFY` placeholders. Verify each one
before use (TASKS.md task 9).

## Building it out with an agent

```sh
scripts/agent-loop.sh
```

Runs OpenCode on one TASKS.md item at a time, runs the tests, commits on pass
and resets on fail. Stops when the list is done or after 15 iterations
(`scripts/agent-loop.sh 5` for a different cap). Read the header of the script
before the first run. Agents follow [AGENTS.md](AGENTS.md).

## Serving the feed

Overcast and Pocket Casts fetch feeds from their own servers, so the feed has
to be reachable from the public internet. A Tailscale-only address will not
work. The plan is to serve the `build/` folder with a long random token in the
path so the URL cannot be guessed:

```
https://<machine>.<tailnet>.ts.net/<token>/feed.xml
```

Setup steps are documented in [docs/serving.md](docs/serving.md). Treat the URL
like a password.

## Subscribing in Overcast

1. In Overcast, tap **+** (Add Podcast), then **Add URL**.
2. Paste the full feed URL, including the token, and add it.
3. Recommended: create a **Smart Playlist** so CarPlay plays the lineup in
   order: New Playlist, Smart Playlist; include **only this podcast**; show
   **unplayed** episodes; sort **oldest to newest**.
4. Pick that playlist in CarPlay.

<!-- HINT: Overcast menu names change between versions; if a label above does
not match the app, fix it here rather than working around it. -->

## Configuration

See the comments in [config/sources.example.yaml](config/sources.example.yaml).
Secrets (feed token, ntfy topic) go in `.env`, which is never committed.

## Alerts (optional)

Set `NTFY_TOPIC` in `.env` (or `ntfy_topic` in the config) to get a push from
[ntfy.sh](https://ntfy.sh) when a run fails. Subscribe to the same topic in the
ntfy app. With no topic set, nothing is sent and the script runs normally.
