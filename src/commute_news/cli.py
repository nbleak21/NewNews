"""Command line entry point: ``commute-news``.

``commute-news build`` runs one build; ``--dry-run`` prints the lineup and
total minutes and writes nothing. The build itself (fetch, parse, select,
write) is filled in by the tasks in TASKS.md.
"""
# HINT: use logging, not print (the dry-run lineup is the one deliberate stdout output).
# HINT: return an int exit code from main() so launchd and run.sh can see failures.

from __future__ import annotations

import argparse
import logging
import os
import sqlite3
from collections.abc import Collection
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from .config import Config, Source, load_config, slot_for_time
from .feedwriter import FeedItem, format_title, ordered_pubdates, render_feed, write_feed
from .fetch import build_client, fetch_all
from .parse import Episode, parse_feed
from .select import Lineup, select_lineup
from .state import connect, mark_used, prune, save_validators

#: Where ``--config`` points when the flag is not given.
DEFAULT_CONFIG = "config/sources.yaml"

#: Log level for the one place the CLI configures logging.
LOG_LEVEL = "INFO"

#: Log format: level, logger name and message (the logger name says the file).
LOG_FORMAT = "%(levelname)s %(name)s: %(message)s"

#: Environment variable name for the feed token.
FEED_TOKEN_ENV = "NEWNEWS_FEED_TOKEN"

#: Default state database path relative to project root.
DEFAULT_STATE_PATH = "state/commute.db"

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    """Return the argparse parser for the ``commute-news`` command.

    The only subcommand today is ``build``; the options belong to it, so
    ``commute-news build --dry-run`` works and a bare ``commute-news`` is a
    usage error rather than a silent no-op.
    """
    parser = argparse.ArgumentParser(
        prog="commute-news",
        description="Build one private commute podcast feed (links only).",
    )
    subparsers = parser.add_subparsers(dest="command", required=True, metavar="command")
    build = subparsers.add_parser(
        "build",
        help="run one build (writes build/<token>/feed.xml)",
        description="Fetch the sources, pick a lineup and write the feed.",
    )
    build.add_argument(
        "--config",
        default=DEFAULT_CONFIG,
        metavar="PATH",
        help=f"YAML config to load (default: {DEFAULT_CONFIG})",
    )
    build.add_argument(
        "--dry-run",
        action="store_true",
        help="print the lineup and total minutes, write nothing",
    )
    return parser


def run_build(
    config_path: str,
    dry_run: bool,
    *,
    client: httpx.Client | None = None,
    now: datetime | None = None,
    used_guids: Collection[str] = frozenset(),
    state_conn: sqlite3.Connection | None = None,
) -> Lineup:
    """Fetch, parse and select the lineup for one run.

    When ``dry_run`` is True: print the lineup and total minutes to stdout
    and return the Lineup (no files are written, no state is updated).

    When ``dry_run`` is False: write ``feed.xml`` to ``build/<token>/`` and
    record state to ``state/commute.db``.

    ``client``, ``now``, ``used_guids`` and ``state_conn`` are injectable so
    tests run offline against a fixed clock.
    """
    config = load_config(config_path)
    if client is None:
        client = build_client()
    if now is None:
        now = datetime.now(UTC)

    allowed = _slot_sources(config, now)
    allowed_ids = {source.id for source in allowed}
    results = fetch_all(client, config.sources, user_agent=config.user_agent)

    episodes: list[Episode] = []
    for source in config.sources:
        if source.id not in allowed_ids:
            continue
        result = results[source.id]
        if result.error is not None:
            logger.warning("skipping %s: %s", source.id, result.error)
            continue
        if result.body is None:
            logger.debug("no body for %s (status %s)", source.id, result.status)
            continue
        episodes.extend(parse_feed(source.id, result.body, config.assumed_bitrate_kbps))

    lineup = select_lineup(episodes, allowed, used_guids, now, config)

    if dry_run:
        # Print the lineup to stdout (the one deliberate use of print)
        _print_lineup(lineup, config)
    else:
        # Write the feed and record state
        _write_feed_and_state(lineup, config, now, state_conn, results)

    return lineup


def _slot_sources(config: Config, now: datetime) -> list[Source]:
    """The sources the current slot allows, in config order.

    No slots configured means every source; a slot that matches but names
    sources keeps only those; no slot covering ``now`` allows none.
    """
    if not config.slots:
        return list(config.sources)
    slot = slot_for_time(config, now)
    if slot is None:
        logger.warning("no slot covers %s; selecting from no source", now.isoformat())
        return []
    if slot.sources == "all":
        return list(config.sources)
    allowed = set(slot.sources)
    return [source for source in config.sources if source.id in allowed]


def _get_feed_token() -> str:
    """Return the feed token from environment variable.

    Raises RuntimeError if the token is not set.
    """
    token = os.environ.get(FEED_TOKEN_ENV)
    if not token:
        raise RuntimeError(f"Feed token not set. Set {FEED_TOKEN_ENV} in environment or .env")
    return token


def _print_lineup(lineup: Lineup, config: Config) -> None:
    """Print the lineup to stdout (the one deliberate use of print).

    One line per episode with the formatted title and minutes, then
    total minutes.
    """
    for i, episode in enumerate(lineup.episodes, start=1):
        # Get the source name for this episode
        source = next((s for s in config.sources if s.id == episode.source_id), None)
        source_name = source.name if source else episode.source_id

        # Format the title
        formatted = format_title(
            slot_label=config.slots[0].label if config.slots else "",
            when=episode.published,
            position=i,
            total=len(lineup.episodes),
            source_name=source_name,
            original_title=episode.title,
        )
        minutes = episode.duration / 60
        print(f"{formatted} — {minutes:.1f} min")

    print(f"\nTotal: {lineup.total_minutes:.1f} minutes")


def _write_feed_and_state(
    lineup: Lineup,
    config: Config,
    now: datetime,
    state_conn: sqlite3.Connection | None = None,
    fetch_results: dict[str, Any] | None = None,
) -> None:
    """Write the feed.xml and record state.

    Creates ``build/<token>/feed.xml`` and updates ``state/commute.db``.

    ``fetch_results`` is optional; if provided, ETags and Last-Modified
    headers are saved for each source.
    """
    # Get the feed token
    _get_feed_token()

    # Build the FeedItems from the lineup
    feed_items = []
    for i, episode in enumerate(lineup.episodes):
        # Get the source name for this episode
        source = next((s for s in config.sources if s.id == episode.source_id), None)
        source_name = source.name if source else episode.source_id

        # Format the title
        formatted = format_title(
            slot_label=config.slots[0].label if config.slots else "",
            when=episode.published,
            position=i + 1,
            total=len(lineup.episodes),
            source_name=source_name,
            original_title=episode.title,
        )

        # Calculate pubDate (newest first, a few seconds apart)
        pub_dates = ordered_pubdates(
            base=now,
            count=len(lineup.episodes),
            step_seconds=5,  # 5 seconds apart
        )
        pub_date = pub_dates[i]

        feed_items.append(
            FeedItem(
                title=formatted,
                guid=episode.guid,
                pub_date=pub_date,
                enclosure_url=episode.enclosure_url,
                enclosure_type=episode.enclosure_type or "audio/mpeg",
                enclosure_length=int(episode.enclosure_length or 0),
            )
        )

    # Render the feed
    feed_token = _get_feed_token()
    feed_url = f"{config.public_base_url}/{feed_token}/feed.xml"
    feed_xml = render_feed(
        feed_items,
        feed_title=config.feed_title,
        feed_url=feed_url,
        now=now,
        retain_hours=config.retain_hour,
    )

    # Write to build/<token>/feed.xml
    build_dir = Path("build") / feed_token
    feed_path = build_dir / "feed.xml"
    write_feed(feed_xml, feed_path)
    logger.info("wrote feed to %s", feed_path)

    # Record state
    if state_conn is None:
        state_conn = connect(Path(DEFAULT_STATE_PATH))

    # Mark used episodes
    slot_label = config.slots[0].label if config.slots else ""
    mark_used(state_conn, lineup.episodes, slot_label, now)

    # Save validators from the fetch results
    if fetch_results:
        for source in config.sources:
            result = fetch_results.get(source.id)
            if result:
                save_validators(
                    state_conn,
                    source.id,
                    etag=result.etag,
                    last_modified=result.last_modified,
                )

    # Prune old rows
    cutoff = now - timedelta(hours=config.retain_hour)
    removed = prune(state_conn, cutoff)
    if removed:
        logger.info("pruned %d old episode(s)", removed)


def notify_failure(topic: str | None, message: str) -> None:
    """Send an ntfy.sh alert if a topic is configured; do nothing otherwise."""
    raise NotImplementedError


def main(argv: list[str] | None = None) -> int:
    """Parse arguments, configure logging and dispatch. Return the process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(level=LOG_LEVEL, format=LOG_FORMAT)
    if args.command != "build":  # pragma: no cover - argparse enforces this
        parser.error(f"unknown command {args.command!r}")

    try:
        run_build(config_path=args.config, dry_run=args.dry_run)
        return 0
    except Exception as exc:
        logger.error("build failed: %s", exc)
        # TODO: send ntfy alert (task 12)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
