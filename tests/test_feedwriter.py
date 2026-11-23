# Copyright (c) 2026 Nick L
# SPDX-License-Identifier: MIT
"""Tests for the private feed writer (TASKS.md task 7).

Everything runs offline: the feed is rendered in memory, parsed back with
feedparser (what a podcast player reads) and with ElementTree (strict XML),
and files are only ever written under pytest's ``tmp_path``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

import feedparser
import pytest

from commute_news.feedwriter import (
    DEFAULT_RETAIN_HOURS,
    DEFAULT_STEP_SECONDS,
    FeedItem,
    format_title,
    ordered_pubdates,
    render_feed,
    write_feed,
)

# 2025-11-21 is a Friday, the date in the title example from AGENTS.md.
BASE = datetime(2025, 11, 21, 10, 15, tzinfo=UTC)
FEED_URL = "https://commute.example.test/secret-token/feed.xml"
FEED_TITLE = "NewNews Commute"


def lineup(count: int, *, base: datetime = BASE) -> list[FeedItem]:
    """The items one run adds: prefixed titles, pubDates a few seconds apart."""
    stamps = ordered_pubdates(base, count)
    items: list[FeedItem] = []
    for position in range(1, count + 1):
        items.append(
            FeedItem(
                title=format_title(
                    "AM", base, position, count, f"Source {position}", f"Episode {position}"
                ),
                guid=f"guid-{position}",
                pub_date=stamps[position - 1],
                enclosure_url=f"https://media.example.test/episode-{position}.mp3",
                enclosure_type="audio/mpeg",
                enclosure_length=1_000_000 + position,
            )
        )
    return items


def one(guid: str, published: datetime) -> FeedItem:
    """A single item, for the retention cases."""
    return FeedItem(
        title=f"Title {guid}",
        guid=guid,
        pub_date=published,
        enclosure_url=f"https://media.example.test/{guid}.mp3",
        enclosure_type="audio/mpeg",
        enclosure_length=4242,
    )


def titles_of(xml: bytes) -> list[str]:
    return [entry.title for entry in feedparser.parse(xml).entries]


def enclosure_url_of(entry) -> str:
    enclosure = entry["enclosures"][0]
    return str(enclosure.get("url") or enclosure.get("href") or "")


# --- format_title ----------------------------------------------------------


def test_title_matches_the_documented_example() -> None:
    when = datetime(2025, 11, 21, 6, 15, tzinfo=UTC)
    assert (
        format_title("AM", when, 2, 5, "Fox News Rundown", "The Newsroom")
        == "AM Fri 11/21 · 2/5 · Fox News Rundown — The Newsroom"
    )


# --- ordered_pubdates ------------------------------------------------------


def test_pubdates_are_a_few_seconds_apart_and_newest_first() -> None:
    stamps = ordered_pubdates(BASE, 4)
    assert len(stamps) == 4
    assert stamps[0] == BASE
    # `stamps[1:]` is one shorter on purpose: pairs overlap by one element.
    gaps = {
        int((earlier - later).total_seconds())
        for earlier, later in zip(stamps, stamps[1:], strict=False)
    }
    assert gaps == {5}
    # The first item of the lineup is also the newest, so a player that
    # lists newest-first shows the lineup in the intended order.
    assert max(stamps) == stamps[0]


def test_pubdates_honour_a_custom_step() -> None:
    stamps = ordered_pubdates(BASE, 3, step_seconds=10)
    gaps = {
        int((earlier - later).total_seconds())
        for earlier, later in zip(stamps, stamps[1:], strict=False)
    }
    assert gaps == {10}


def test_no_items_gives_no_pubdates() -> None:
    assert ordered_pubdates(BASE, 0) == []


def test_a_negative_count_is_rejected() -> None:
    with pytest.raises(ValueError):
        ordered_pubdates(BASE, -1)


# --- render: what a player reads back --------------------------------------


def test_round_trip_titles_order_and_enclosures() -> None:
    items = lineup(3)
    xml = render_feed(items, FEED_TITLE, FEED_URL, now=BASE)

    entries = feedparser.parse(xml).entries
    assert [entry.title for entry in entries] == [item.title for item in items]
    assert [enclosure_url_of(entry) for entry in entries] == [item.enclosure_url for item in items]
    assert [parsedate_to_datetime(entry.published) for entry in entries] == [
        item.pub_date for item in items
    ]


def test_enclosures_pass_through_type_and_length_untouched() -> None:
    items = lineup(2)
    xml = render_feed(items, FEED_TITLE, FEED_URL, now=BASE)

    channel = ElementTree.fromstring(xml).find("channel")
    assert channel is not None
    rendered = channel.findall("item")
    assert len(rendered) == len(items)
    for element, item in zip(rendered, items, strict=True):
        enclosure = element.find("enclosure")
        assert enclosure is not None
        assert enclosure.get("url") == item.enclosure_url
        assert enclosure.get("type") == item.enclosure_type
        assert enclosure.get("length") == str(item.enclosure_length)


def test_special_characters_survive_the_round_trip() -> None:
    tricky = FeedItem(
        title=format_title("AM", BASE, 1, 1, "A & B", 'Quoted "news" <daily>'),
        guid="guid-&1",
        pub_date=BASE,
        enclosure_url="https://media.example.test/a.mp3?x=1&y=2&z=3",
        enclosure_type="audio/mpeg",
        enclosure_length=7,
    )
    xml = render_feed([tricky], FEED_TITLE, FEED_URL, now=BASE)

    entries = feedparser.parse(xml).entries
    assert [entry.title for entry in entries] == [tricky.title]
    assert enclosure_url_of(entries[0]) == tricky.enclosure_url


def test_channel_title_and_feed_url_come_back() -> None:
    xml = render_feed(lineup(1), "My Commute", FEED_URL, now=BASE)
    parsed = feedparser.parse(xml)
    assert str(parsed.feed.get("title")) == "My Commute"
    # The token URL is the channel's own address; it must never be rewritten.
    assert str(parsed.feed.get("link")) == FEED_URL
    assert FEED_URL in xml.decode("utf-8")


def test_no_items_still_renders_well_formed_xml() -> None:
    xml = render_feed([], FEED_TITLE, FEED_URL, now=BASE)
    assert ElementTree.fromstring(xml) is not None
    assert feedparser.parse(xml).entries == []


# --- retention (retain_hours, default 3) -----------------------------------


def test_default_retention_is_three_hours() -> None:
    assert DEFAULT_RETAIN_HOURS == 3


def test_default_pubdate_step_is_five_seconds() -> None:
    # cli.py relies on this default spacing (it no longer hardcodes 5).
    assert DEFAULT_STEP_SECONDS == 5


def test_items_older_than_retain_hours_are_dropped() -> None:
    fresh = one("fresh", BASE - timedelta(hours=2, minutes=59))
    stale = one("stale", BASE - timedelta(hours=3, minutes=1))
    xml = render_feed([stale, fresh], FEED_TITLE, FEED_URL, now=BASE)
    assert titles_of(xml) == [fresh.title]


def test_item_exactly_at_the_cutoff_is_kept() -> None:
    on_the_fence = one("edge", BASE - timedelta(hours=DEFAULT_RETAIN_HOURS))
    xml = render_feed([on_the_fence], FEED_TITLE, FEED_URL, now=BASE)
    assert titles_of(xml) == [on_the_fence.title]


def test_now_defaults_to_the_newest_item() -> None:
    fresh = one("fresh", BASE)
    stale = one("stale", BASE - timedelta(days=1))
    xml = render_feed([stale, fresh], FEED_TITLE, FEED_URL)
    assert titles_of(xml) == [fresh.title]


def test_a_negative_retain_hours_is_rejected() -> None:
    with pytest.raises(ValueError):
        render_feed([], FEED_TITLE, FEED_URL, retain_hours=-1)


# --- write_feed (atomic) ---------------------------------------------------


def test_write_feed_creates_the_directory_and_writes(tmp_path) -> None:
    target = tmp_path / "build" / "secret-token" / "feed.xml"
    write_feed(b"<rss/>", target)
    assert target.read_bytes() == b"<rss/>"


def test_write_feed_replaces_the_file_and_leaves_no_temp(tmp_path) -> None:
    target = tmp_path / "feed.xml"
    write_feed(b"first", target)
    write_feed(b"second", target)

    assert target.read_bytes() == b"second"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["feed.xml"]


def test_write_feed_writes_exactly_the_rendered_bytes(tmp_path) -> None:
    items = lineup(2)
    xml = render_feed(items, FEED_TITLE, FEED_URL, now=BASE)
    target = tmp_path / "feed.xml"
    write_feed(xml, target)

    assert target.read_bytes() == xml
    assert [entry.title for entry in feedparser.parse(target.read_bytes()).entries] == [
        item.title for item in items
    ]
