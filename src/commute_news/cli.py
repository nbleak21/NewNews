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
from datetime import UTC, datetime, timedelta, tzinfo
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from .config import Config, Source, load_config, slot_for_time
from .feedwriter import FeedItem, format_title, ordered_pubdates, render_feed, write_feed
from .fetch import build_client, fetch_all
from .parse import Episode, parse_feed
from .select import Lineup, select_lineup
from .state import (
    connect,
    get_validators,
    mark_used,
    prune,
    recent_items,
    save_validators,
)
from .state import (
    used_guids as read_used_guids,
)

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
    used_guids: Collection[str] | None = None,
    state_conn: sqlite3.Connection | None = None,
) -> Lineup:
    """Fetch, parse and select the lineup for one run.

    When ``dry_run`` is True: print the lineup and total minutes to stdout
    and return the Lineup (no files are written, no state is created).

    When ``dry_run`` is False: record this run, prune, and write the whole
    retained (~``retain_hours``) feed to ``build/<token>/feed.xml``.

    State is READ as well as written: already-used episode guids are loaded so
    an episode is never repeated across runs, and each source's stored ETag /
    Last-Modified drive a conditional GET. ``client``, ``now``, ``used_guids``
    and ``state_conn`` are injectable so tests run offline against a fixed
    clock; an explicit ``used_guids`` (even empty) disables the auto-load.
    """
    config = load_config(config_path)
    if client is None:
        client = build_client()
    if now is None:
        now = datetime.now(UTC)

    # A state connection for reading (and, on a real build, writing). A dry run
    # must never CREATE the database, so it only opens one that already exists.
    conn = state_conn
    own_conn = False
    if conn is None:
        state_path = Path(DEFAULT_STATE_PATH)
        if not dry_run or state_path.exists():
            conn = connect(state_path)
            own_conn = True

    # Already-used episodes: an explicit argument wins (tests); otherwise load
    # them from state so a later run never repeats an episode.
    if used_guids is None:
        used_guids = read_used_guids(conn) if conn is not None else set()

    # Slots and title dates are in the configured local timezone, not UTC.
    zone = _zone(config)
    local_now = now.astimezone(zone)
    allowed = _slot_sources(config, local_now)
    allowed_ids = {source.id for source in allowed}
    slot = slot_for_time(config, local_now)
    slot_label = slot.label if slot else ""

    # Conditional GET: send each allowed source's stored ETag / Last-Modified.
    # Only the slot's sources are fetched, so a slot-excluded source is not hit
    # on its publisher this run (its earlier items stay in the retained feed).
    validators = (
        {source.id: get_validators(conn, source.id) for source in allowed}
        if conn is not None
        else None
    )
    results = fetch_all(client, allowed, validators=validators, user_agent=config.user_agent)

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

    # Check for failure conditions and alert if topic is configured
    # (but only in non-dry-run mode since alerts are for real failures)
    if not dry_run:
        topic = _get_ntfy_topic(config)
        if not allowed:
            notify_failure(topic, "Build skipped: no slot covers the current time")
        elif not episodes:
            notify_failure(topic, "Build failed: no episodes fetched from any source")
        elif not lineup.episodes:
            notify_failure(topic, "Build failed: lineup is empty after selection")
        elif lineup.total_minutes < config.min_minutes:
            notify_failure(
                topic,
                f"Build warning: lineup is short ({lineup.total_minutes:.1f} min, "
                f"target {config.min_minutes} min)",
            )

    if dry_run:
        # Print the lineup to stdout (the one deliberate use of print)
        _print_lineup(lineup, config, slot_label, zone)
    else:
        # Record state and write the retained (~retain_hours) feed.
        _write_feed_and_state(
            lineup, config, now, slot_label, zone, state_conn=conn, fetch_results=results
        )

    if own_conn and conn is not None:
        conn.close()

    return lineup


def _zone(config: Config) -> tzinfo:
    """The configured timezone, or UTC if it is unknown / tzdata is missing."""
    try:
        return ZoneInfo(config.timezone)
    except Exception:  # noqa: BLE001 - unknown zone name or missing tz database
        logger.warning("unknown timezone %r; falling back to UTC", config.timezone)
        return UTC


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


def _print_lineup(lineup: Lineup, config: Config, slot_label: str, zone: tzinfo) -> None:
    """Print the lineup to stdout (the one deliberate use of print).

    One line per episode with the formatted title and minutes, then
    total minutes.
    """
    for i, episode in enumerate(lineup.episodes, start=1):
        # Get the source name for this episode
        source = next((s for s in config.sources if s.id == episode.source_id), None)
        source_name = source.name if source else episode.source_id

        # Format the title (slot label + date in the configured local timezone)
        formatted = format_title(
            slot_label=slot_label,
            when=episode.published.astimezone(zone),
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
    slot_label: str,
    zone: tzinfo,
    state_conn: sqlite3.Connection | None = None,
    fetch_results: dict[str, Any] | None = None,
) -> None:
    """Record this run's state, then write the whole retained feed.

    The feed is the entire retained window (``retain_hours``), not just this
    run's lineup: this run's episodes are recorded, old rows pruned, and the
    feed rebuilt from ``recent_items`` so items persist across runs and drop
    off once they age past ``retain_hours``. Validators are saved for the next
    run's conditional GET.
    """
    feed_token = _get_feed_token()

    own = False
    if state_conn is None:
        state_conn = connect(Path(DEFAULT_STATE_PATH))
        own = True

    # 1. Record this run, save validators, prune — so the window read back below
    #    is current.
    mark_used(state_conn, lineup.episodes, slot_label, now)
    if fetch_results:
        for source in config.sources:
            result = fetch_results.get(source.id)
            if result is not None and result.error is None:
                save_validators(
                    state_conn,
                    source.id,
                    etag=result.etag,
                    last_modified=result.last_modified,
                )
    cutoff = now - timedelta(hours=config.retain_hours)
    removed = prune(state_conn, cutoff)
    if removed:
        logger.info("pruned %d old episode(s)", removed)

    # 2. Build the feed, guid-unique, from the whole retained window: this run's
    #    lineup first (keeping its curated order), then older retained items
    #    (recent_items is newest-first).
    retained = recent_items(state_conn, cutoff)
    source_names = {source.id: source.name for source in config.sources}
    seen: set[str] = set()
    items: list[dict[str, Any]] = []
    for episode in lineup.episodes:
        if episode.guid in seen:
            continue
        seen.add(episode.guid)
        items.append(
            {
                "guid": episode.guid,
                "source_id": episode.source_id,
                "title": episode.title,
                "published": episode.published,
                "enclosure_url": episode.enclosure_url,
                "enclosure_type": episode.enclosure_type,
                "enclosure_length": episode.enclosure_length,
                "slot_label": slot_label,
            }
        )
    for row in retained:
        if row["guid"] in seen:
            continue
        seen.add(row["guid"])
        items.append(row)

    pub_dates = ordered_pubdates(base=now, count=len(items))  # default DEFAULT_STEP_SECONDS
    feed_items = [
        FeedItem(
            title=format_title(
                slot_label=item["slot_label"],
                when=item["published"].astimezone(zone),
                position=i + 1,
                total=len(items),
                source_name=source_names.get(item["source_id"], item["source_id"]),
                original_title=item["title"],
            ),
            guid=item["guid"],
            pub_date=pub_dates[i],
            enclosure_url=item["enclosure_url"],
            enclosure_type=item["enclosure_type"] or "audio/mpeg",
            enclosure_length=int(item["enclosure_length"] or 0),
        )
        for i, item in enumerate(items)
    ]

    # 3. Render and write. retain_hours is already enforced above by
    #    prune/recent_items; render_feed drops nothing (every pub_date is ~now).
    feed_url = f"{config.public_base_url}/{feed_token}/feed.xml"
    feed_xml = render_feed(
        feed_items,
        feed_title=config.feed_title,
        feed_url=feed_url,
        now=now,
        retain_hours=config.retain_hours,
    )
    feed_path = Path("build") / feed_token / "feed.xml"
    write_feed(feed_xml, feed_path)
    logger.info("wrote feed to %s", feed_path)

    if own:
        state_conn.close()


def _get_ntfy_topic(config: Config | None = None) -> str | None:
    """Return the ntfy topic from environment variable or config.

    The NTFY_TOPIC environment variable takes precedence over config.ntfy_topic.
    Returns None if no topic is configured (empty string or not set).
    """
    # Environment variable overrides config
    env_topic = os.environ.get("NTFY_TOPIC")
    if env_topic:
        return env_topic
    if config and config.ntfy_topic:
        return config.ntfy_topic
    return None


def notify_failure(topic: str | None, message: str) -> None:
    """Send an ntfy.sh alert if a topic is configured; do nothing otherwise.

    Errors (network, 5xx, 404) are caught and logged at DEBUG level so the
    failure alert itself does not fail the run.
    """
    if not topic:
        return

    import logging

    logger = logging.getLogger(__name__)

    url = f"https://ntfy.sh/{topic}"
    try:
        with httpx.Client() as client:
            response = client.post(url, content=message)
            response.raise_for_status()
            logger.debug("ntfy alert sent to %s", topic)
    except Exception as exc:
        # Log at DEBUG so failures don't cascade; the run continues
        logger.debug("ntfy alert failed for %s: %s", topic, exc)


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
        # Try to get the config to check for ntfy topic
        try:
            config = load_config(args.config)
            topic = _get_ntfy_topic(config)
            notify_failure(topic, f"Build failed: {exc}")
        except Exception:
            # If we can't load config or notify, just log the original error
            logger.debug("could not send ntfy alert due to config error", exc_info=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
