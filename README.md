# NewNews

A private news podcast feed for the commute. A script on a Mac reads a list of
public news podcast RSS feeds, picks the newest unplayed episodes that fit in
about 25 minutes with a mix of outlets, and writes one RSS feed (`feed.xml`)
that you subscribe to once in Overcast and play through CarPlay.

It only links to each publisher's original audio. Nothing is downloaded,
re-hosted or edited.

**Status:** built out. All modules are implemented and the full test suite
passes; the task history is in [TASKS.md](TASKS.md) and [PROGRESS.md](PROGRESS.md).

<!-- HINT (template): keep README for humans (what, quick start, how to use).
Agent instructions belong in AGENTS.md so the two do not drift. -->

## Quick start

Requires macOS, [uv](https://docs.astral.sh/uv/) and git.

```sh
uv sync                                        # creates .venv with Python 3.12
uv run pytest                                  # should pass
cp .env.example .env                           # then set NEWNEWS_FEED_TOKEN
cp config/sources.example.yaml config/sources.yaml   # then replace every TODO
uv run commute-news build --dry-run            # prints the lineup, writes nothing
uv run commute-news build                      # writes build/<token>/feed.xml
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

## Adding a new source

Follow these steps to add a new podcast to your lineup.

### 1. Find the feed URL

Find the podcast on Apple Podcasts, then look up its feed URL using the
iTunes Lookup API. For example, if the Apple Podcasts ID is `123456789`:

```bash
curl "https://itunes.apple.com/lookup?id=123456789&entity=podcast"
```

The response will include `"feedUrl"` — that's the URL you need.

**Important:** Never guess a feed URL. Always verify it via the Apple lookup
API. The loader will reject placeholder URLs (like `TODO_VERIFY`).

### 2. Add the YAML block

Open `config/sources.yaml` and add a new source block under `sources:`. Copy
one of the existing blocks and update the fields:

```yaml
  - id: your_podcast_id
    name: "Your Podcast Name"
    lean: center          # one of: left, center-left, center, right, international
    priority: 2           # 1 = picked first, higher = picked later
    feed_url: "https://feeds.example.com/your-podcast.xml"  # from step 1
```

**Notes:**
- `id` must be unique and use underscores (no spaces or special characters).
- `lean` tags help keep a mix of outlets in your lineup.
- `priority` controls selection order: 1 is picked first, 4 is picked last.
- Keep the `feed_url` as the last thing you fill in — it's what you verified.

### 3. Run a dry-run test

Test your configuration before fetching feeds:

```sh
uv run commute-news build --dry-run
```

This prints your lineup to stdout without writing any files. Check that:
- Your new source appears in the lineup (if it has fresh episodes).
- The total minutes are in the 20–30 minute range.
- No errors appear in the output.

If your source doesn't appear, it may have no fresh episodes (within 2 hours)
or its `priority` is too low to make the cutoff.

### 4. Add a fixture for testing

To ensure your new source works in the test suite, add a fixture:

1. Fetch a real episode from your feed (the first item is usually best).
2. Save it as `tests/fixtures/feeds/your-podcast-id.xml`.
3. Trim the XML to just one episode — keep the RSS header and channel tags.
4. Make sure the `pubDate` is recent (within the last 2–3 hours) so it reads
   as "fresh" during tests.

The fixture lets the end-to-end tests run offline without touching the
network. Your new source will then be covered by `uv run pytest`.

### 5. Commit your changes

Once everything works:

```sh
git add config/sources.yaml tests/fixtures/feeds/your-podcast-id.xml
git commit -m "Add Your Podcast Name source"
```

The feed will be regenerated automatically on the next scheduled run (hourly
from 04:15 to 18:15 Central time). Your new source will appear in the feed
within 2 hours if it has fresh episodes.
