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
from collections.abc import Collection
from datetime import UTC, datetime

import httpx

from .config import Config, Source, load_config, slot_for_time
from .fetch import build_client, fetch_all
from .parse import Episode, parse_feed
from .select import Lineup, select_lineup

#: Where ``--config`` points when the flag is not given.
DEFAULT_CONFIG = "config/sources.yaml"

#: Log level for the one place the CLI configures logging.
LOG_LEVEL = "INFO"

#: Log format: level, logger name and message (the logger name says the file).
LOG_FORMAT = "%(levelname)s %(name)s: %(message)s"

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
) -> Lineup:
    """Fetch, parse and select the lineup for one run.

    Returns the chosen :class:`Lineup`; printing it and writing ``feed.xml``
    (task 8c) still has to happen. ``client``, ``now`` and ``used_guids``
    are injectable so tests run offline against a fixed clock.
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
    logger.info(
        "selected %d episodes totalling %.1f minutes", len(lineup.episodes), lineup.total_minutes
    )
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
    # 8b: the lineup is not printed or written yet (that is 8c), so there is
    # nothing to report; return a real exit code instead of the Lineup.
    run_build(config_path=args.config, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
