"""Tests for the episode parser and duration handling (TASKS.md task 4).

Every test reads a hand-written fixture from ``tests/fixtures/feeds/`` with
``.example.test`` / reserved URLs, so nothing here touches the network.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from commute_news.parse import (
    DEFAULT_ASSUMED_BITRATE_KBPS,
    estimate_duration_from_length,
    parse_duration,
    parse_feed,
)

FEEDS = Path(__file__).parent / "fixtures" / "feeds"


def feed(name: str) -> bytes:
    """The bytes of one saved fixture feed (never fetched)."""
    return (FEEDS / name).read_bytes()


# --- parse_duration: three accepted shapes ----------------------------------


def test_duration_plain_seconds() -> None:
    assert parse_duration("1234") == 1234


def test_duration_mm_ss() -> None:
    assert parse_duration("05:00") == 300


def test_duration_hh_mm_ss() -> None:
    assert parse_duration("1:02:03") == 3723


def test_duration_unusable_values_are_none() -> None:
    for value in (None, "", "   ", "not a duration", "12:99", "1:2:3:4", "abc"):
        assert parse_duration(value) is None, repr(value)


# --- estimate_duration_from_length: the documented approximation -------------


def test_estimate_matches_the_documented_formula() -> None:
    assert DEFAULT_ASSUMED_BITRATE_KBPS == 128
    assert estimate_duration_from_length(5_000_000) == 5_000_000 * 8 // (128 * 1000)


def test_estimate_honours_the_given_bitrate() -> None:
    assert estimate_duration_from_length(5_000_000, 64) == 5_000_000 * 8 // (64 * 1000)


def test_estimate_needs_a_usable_length() -> None:
    assert estimate_duration_from_length(None) is None
    assert estimate_duration_from_length(0) is None


# --- parse_feed: durations, ordering, skipping ------------------------------


def test_three_duration_formats_newest_first() -> None:
    episodes = parse_feed("src", feed("durations.xml"))

    # Sorted by pubDate descending, not by document order (the fixture lists
    # the items out of order on purpose).
    assert [e.title for e in episodes] == [
        "Hours minutes seconds",
        "Minutes and seconds",
        "Plain seconds, huge length must not win",
    ]
    assert [e.duration for e in episodes] == [3723, 300, 1234]
    assert [e.duration_estimated for e in episodes] == [False, False, False]
    assert {e.source_id for e in episodes} == {"src"}
    assert episodes[0].published == datetime(2026, 11, 19, 8, 0, tzinfo=UTC)


def test_missing_duration_is_estimated_from_length() -> None:
    episodes = parse_feed("npr", feed("estimate_duration.xml"))

    assert len(episodes) == 1  # the missing-length and zero-length items are skipped
    only = episodes[0]
    assert only.title == "Estimated from length"
    assert only.duration == 5_000_000 * 8 // (DEFAULT_ASSUMED_BITRATE_KBPS * 1000)
    assert only.duration_estimated is True


def test_estimate_uses_the_configured_bitrate() -> None:
    episodes = parse_feed("npr", feed("estimate_duration.xml"), assumed_bitrate_kbps=64)
    assert [e.duration for e in episodes] == [5_000_000 * 8 // (64 * 1000)]


def test_missing_enclosure_and_unusable_dates_are_skipped() -> None:
    episodes = parse_feed("npr", feed("skip_items.xml"))
    assert [e.title for e in episodes] == ["Kept: enclosure and a real date"]


def test_episode_passes_the_enclosure_through() -> None:
    (episode,) = parse_feed("npr", feed("skip_items.xml"))
    assert episode.enclosure_url == "https://media.example.test/audio/keep.mp3"
    assert episode.enclosure_type == "audio/mpeg"
    assert episode.enclosure_length == 1000
    assert episode.guid == "keep-001"
