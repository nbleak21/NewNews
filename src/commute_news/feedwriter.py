"""Render the private feed and write it out.

Pure functions plus one small atomic writer. The XML is built with feedgen
(already a project dependency) so escaping, RFC-2822 dates and the
``atom:link`` self reference are not hand-rolled; everything else here is plain
string / datetime work so it stays trivially testable.

The feed is *link only*: the enclosure URL, MIME type and byte length of an
episode are copied through exactly as they came from the source feed. Nothing is
downloaded, re-encoded or re-hosted.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from feedgen.entry import FeedEntry
from feedgen.feed import FeedGenerator

log = logging.getLogger(__name__)

#: How many hours of items the feed keeps. `retain_hours` is the single
#: retention control in the product; this is its default when a caller does
#: not say otherwise. It is deliberately the same window the state database
#: prunes with, so a dropped row is always too old to be re-selected.
DEFAULT_RETAIN_HOURS = 3

#: Seconds between the pubDates of two consecutive items, so a player that
#: sorts by date still shows the lineup in the order it was built.
DEFAULT_STEP_SECONDS = 5

#: Channel description. The RSS spec makes <description> mandatory; the product
#: has nothing more to say than what this feed is.
CHANNEL_DESCRIPTION = "Private commute podcast feed. Links only, no audio hosted here."

#: Weekday abbreviations for the title prefix, indexed by ``date.weekday()``
#: (Monday first). Hardcoded so the label never depends on the C locale.
_WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


@dataclass(frozen=True)
class FeedItem:
    """One entry of the generated feed.

    Everything except ``title`` and ``pub_date`` is copied verbatim from the
    source feed: the point of this product is to link, never to re-host.
    """

    title: str
    """Fully formatted title, see :func:`format_title`."""

    guid: str
    """Stable unique id, reused from the source feed when it has one, so a
    re-render never duplicates the item in a podcast player."""

    pub_date: datetime
    """Publication time. Successive items are a few seconds apart."""

    enclosure_url: str
    """Original enclosure URL. Never downloaded, never rewritten."""

    enclosure_type: str = "audio/mpeg"
    """MIME type of the enclosure, copied from the source feed."""

    enclosure_length: int = 0
    """Size in bytes as advertised by the source, or 0 if unknown."""


def format_title(
    slot_label: str,
    when: datetime,
    position: int,
    total: int,
    source_name: str,
    original_title: str,
) -> str:
    """Build the display title a person reads in the car.

    The shape is fixed by the product: a short slot and date for the human,
    the position so the run of shows reads as a queue, the source so the
    outlet is obvious, and finally the title the publisher wrote.

    >>> from datetime import datetime
    >>> format_title("AM", datetime(2025, 11, 21, 6, 15), 2, 5,
    ...              "Fox News Rundown", "The Newsroom")
    'AM Fri 11/21 · 2/5 · Fox News Rundown — The Newsroom'
    """
    weekday = _WEEKDAYS[when.weekday()]
    date_part = f"{when.month:02d}/{when.day:02d}"
    return (
        f"{slot_label} {weekday} {date_part} · "
        f"{position}/{total} · {source_name} — {original_title}"
    )


def ordered_pubdates(
    base: datetime,
    count: int,
    step_seconds: int = DEFAULT_STEP_SECONDS,
) -> list[datetime]:
    """Return ``count`` pubDates, a few seconds apart, newest first.

    Index 0 is ``base`` (the moment the feed was built) and each following
    entry steps backwards, so the first item of the lineup is also the newest
    and the XML order matches the order the shows should play in.

    Raises ``ValueError`` on a negative count or a non-positive step: both are
    caller bugs, and a silent fallback would hide one.
    """
    if count < 0:
        raise ValueError(f"count must be >= 0, got {count}")
    if step_seconds <= 0:
        raise ValueError(f"step_seconds must be > 0, got {step_seconds}")
    if count == 0:
        return []
    step = timedelta(seconds=step_seconds)
    return [base - (step * i) for i in range(count)]


def render_feed(
    items: Sequence[FeedItem],
    feed_title: str,
    feed_url: str,
    now: datetime | None = None,
    retain_hours: float | None = None,
) -> bytes:
    """Render ``items`` as an RSS 2.0 document and return the XML bytes.

    ``feed_url`` is the tokenised public address of the feed itself; it is
    written to the channel unchanged, because that is the address a podcast
    client must be pointed at.

    ``now`` defaults to the newest item, which is the value that makes the
    retention window deterministic. ``retain_hours`` defaults to
    ``DEFAULT_RETAIN_HOURS``; items published before ``now - retain_hours``
    are dropped, so the feed only ever carries the most recent window of
    shows. The cutoff is inclusive, matching ``state.prune``.
    """
    if retain_hours is None:
        retain_hours = DEFAULT_RETAIN_HOURS
    if retain_hours < 0:
        raise ValueError(f"retain_hours must be >= 0, got {retain_hours}")

    if now is None and items:
        now = max(item.pub_date for item in items)

    if now is None:
        kept: list[FeedItem] = list(items)
    else:
        cutoff = now - timedelta(hours=retain_hours)
        kept = [item for item in items if item.pub_date >= cutoff]
        dropped = len(items) - len(kept)
        if dropped:
            log.info("dropped %d item(s) older than %s", dropped, cutoff.isoformat())

    feed = FeedGenerator()
    feed.title(feed_title)
    feed.description(CHANNEL_DESCRIPTION)
    # One link is all RSS needs; feedgen reuses it for <link> and, because
    # rel is "self", also emits the matching atom:link.
    feed.link(href=feed_url, rel="self")

    for item in kept:
        # order="append" keeps the lineup order; the default is "prepend".
        entry: FeedEntry = feed.add_entry(order="append")
        entry.title(item.title)
        entry.guid(item.guid, permalink=False)
        entry.pubDate(item.pub_date)
        entry.enclosure(
            item.enclosure_url,
            length=str(item.enclosure_length),
            type=item.enclosure_type,
        )

    # Bytes, because that is what lands on disk and what a player downloads.
    return feed.rss_str(pretty=False)


def write_feed(data: bytes | str, out_path: str | os.PathLike) -> Path:
    """Write ``data`` to ``out_path`` atomically and return the final path.

    The bytes go to a temporary file in the same directory and are then moved
    into place, so a reader (Overcast, or a test) never sees a half-written
    feed. The temporary file is always cleaned up, on success and on failure.
    """
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = data.encode("utf-8") if isinstance(data, str) else bytes(data)

    tmp_path = path.with_name(f"{path.name}.tmp")
    try:
        tmp_path.write_bytes(payload)
        os.replace(tmp_path, path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
    return path
