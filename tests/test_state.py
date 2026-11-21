"""Tests for state.py: SQLite storage of validators, used episodes, pruning.

Every test uses a database file inside pytest's ``tmp_path``. No network, and
never the real ``state/`` file.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from commute_news import state
from commute_news.parse import Episode

NOW = datetime(2026, 11, 21, 12, 0, 0, tzinfo=UTC)


def make_episode(guid: str = "g1", source_id: str = "nyt-daily") -> Episode:
    return Episode(
        source_id=source_id,
        guid=guid,
        title=f"Title {guid}",
        published=datetime(2026, 11, 21, 6, 0, 0, tzinfo=UTC),
        enclosure_url=f"https://example.com/audio/{guid}.mp3",
        enclosure_type="audio/mpeg",
        enclosure_length=1_000_000,
        duration=600,
        duration_estimated=False,
    )


def test_connect_creates_missing_parent_directories_and_schema(tmp_path):
    db = tmp_path / "state" / "nested" / "state.db"
    conn = state.connect(db)
    try:
        assert db.exists()
        assert state.used_guids(conn) == set()
    finally:
        conn.close()


def test_connect_reopens_an_existing_file(tmp_path):
    db = tmp_path / "state.db"
    first = state.connect(db)
    state.save_validators(first, "nyt", etag='"v1"', last_modified="Mon")
    first.close()

    second = state.connect(db)  # same file, new connection
    try:
        assert state.get_validators(second, "nyt") == ('"v1"', "Mon")
    finally:
        second.close()


def test_validators_default_to_none_and_round_trip_per_source(tmp_path):
    conn = state.connect(tmp_path / "state.db")
    try:
        assert state.get_validators(conn, "nyt") == (None, None)

        state.save_validators(conn, "nyt", etag='"abc"', last_modified="Mon, 01 Jan 2026")
        assert state.get_validators(conn, "nyt") == ('"abc"', "Mon, 01 Jan 2026")

        # A second source is independent.
        state.save_validators(conn, "bbc", etag=None, last_modified="Tue, 02 Feb 2026")
        assert state.get_validators(conn, "bbc") == (None, "Tue, 02 Feb 2026")
        assert state.get_validators(conn, "nyt") == ('"abc"', "Mon, 01 Jan 2026")

        # Saving the same source again overwrites, it does not append.
        state.save_validators(conn, "nyt", etag='"xyz"', last_modified=None)
        assert state.get_validators(conn, "nyt") == ('"xyz"', None)
    finally:
        conn.close()


def test_mark_used_round_trips_and_used_guids_grows(tmp_path):
    conn = state.connect(tmp_path / "state.db")
    try:
        assert state.used_guids(conn) == set()

        state.mark_used(conn, [make_episode("g1"), make_episode("g2")], "AM", NOW)
        assert state.used_guids(conn) == {"g1", "g2"}

        state.mark_used(conn, [make_episode("g3", source_id="bbc")], "PM", NOW)
        assert state.used_guids(conn) == {"g1", "g2", "g3"}

        # Re-marking the same episodes is idempotent: still three rows.
        state.mark_used(conn, [make_episode("g1")], "AM", NOW)
        assert state.used_guids(conn) == {"g1", "g2", "g3"}
    finally:
        conn.close()


def test_recent_items_returns_newest_first_from_since(tmp_path):
    conn = state.connect(tmp_path / "state.db")
    try:
        state.mark_used(conn, [make_episode("old")], "AM", NOW - timedelta(hours=5))
        state.mark_used(conn, [make_episode("kept")], "AM", NOW - timedelta(hours=1))
        state.mark_used(conn, [make_episode("newer")], "PM", NOW)

        items = state.recent_items(conn, since=NOW - timedelta(hours=2))
        assert [item["guid"] for item in items] == ["newer", "kept"]

        kept = items[1]
        assert kept["source_id"] == "nyt-daily"
        assert kept["title"] == "Title kept"
        assert kept["enclosure_url"] == "https://example.com/audio/kept.mp3"
        assert kept["enclosure_type"] == "audio/mpeg"
        assert kept["duration"] == 600
        assert kept["published"] == datetime(2026, 11, 21, 6, 0, 0, tzinfo=UTC)
        assert kept["slot_label"] == "AM"
        assert kept["added_at"] == NOW - timedelta(hours=1)

        # "at or after": a row exactly at `since` is included.
        at_cutoff = state.recent_items(conn, since=NOW - timedelta(hours=1))
        assert {item["guid"] for item in at_cutoff} == {"kept", "newer"}
    finally:
        conn.close()


def test_prune_removes_only_rows_older_than_retain_hours(tmp_path):
    retain_hours = 3
    older_than = NOW - timedelta(hours=retain_hours)
    conn = state.connect(tmp_path / "state.db")
    try:
        state.mark_used(conn, [make_episode("too_old")], "AM", NOW - timedelta(hours=4, minutes=1))
        state.mark_used(conn, [make_episode("boundary")], "AM", older_than)
        state.mark_used(conn, [make_episode("kept_1")], "AM", NOW - timedelta(minutes=30))
        state.mark_used(conn, [make_episode("kept_2")], "PM", NOW)

        removed = state.prune(conn, older_than=older_than)

        assert removed == 1
        # "boundary" sits exactly on the cutoff: not older, so it stays.
        assert state.used_guids(conn) == {"boundary", "kept_1", "kept_2"}
        # A second pass has nothing left to delete.
        assert state.prune(conn, older_than=older_than) == 0
    finally:
        conn.close()


def test_data_survives_closing_and_reopening_the_file(tmp_path):
    db = tmp_path / "state.db"

    first = state.connect(db)
    state.save_validators(first, "nyt", etag='"v1"', last_modified="Mon")
    state.mark_used(first, [make_episode("g1")], "PM", NOW)
    first.close()

    second = state.connect(db)
    try:
        assert state.get_validators(second, "nyt") == ('"v1"', "Mon")
        assert state.used_guids(second) == {"g1"}
        items = state.recent_items(second, since=NOW - timedelta(hours=1))
        assert [item["guid"] for item in items] == ["g1"]
        assert items[0]["slot_label"] == "PM"
    finally:
        second.close()
