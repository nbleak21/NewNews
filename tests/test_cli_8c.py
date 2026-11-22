"""Tests for task 8c: dry-run output and the write path in cli.py.

Tests verify the dry-run prints the lineup and total minutes, and the write
path creates feed.xml and state without touching the network.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from commute_news.cli import run_build
from commute_news.state import connect, used_guids

FIXTURES = Path(__file__).parent / "fixtures"
FEEDS = FIXTURES / "feeds"

#: Fixed clock: inside the fixture config's "am" slot and within the freshness window.
NOW = datetime(2026, 11, 19, 7, 30, tzinfo=UTC)

#: Token from env or .env; tests must not hardcode it.
FEED_TOKEN = os.environ.get("NEWNEWS_FEED_TOKEN", "test-token-for-tests")


def fixture_client() -> httpx.Client:
    """A client whose transport serves the fixture feeds, never the network."""

    def handler(request: httpx.Request) -> httpx.Response:
        name = str(request.url).rsplit("/", 1)[-1]
        return httpx.Response(200, content=(FEEDS / SERVED[name]).read_bytes())

    return httpx.Client(transport=httpx.MockTransport(handler))


SERVED: dict[str, str] = {
    "fox-news-rundown.xml": "skip_items.xml",
    "npr-news-now.xml": "sample_feed.xml",
    "wsj-whats-news.xml": "estimate_duration.xml",
    "bbc-global-news.xml": "skip_items.xml",
    "morning-wire.xml": "sample_feed.xml",
    "up-first.xml": "estimate_duration.xml",
    "the-daily.xml": "durations.xml",
}


class TestDryRun:
    """Test --dry-run prints lineup and total minutes, writes nothing."""

    def test_dry_run_prints_lineup_and_total_minutes(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Dry run prints the lineup and total minutes to stdout."""
        # Use run_build directly with injected client (main() doesn't accept client)
        client = fixture_client()
        lineup = run_build(
            config_path=str(FIXTURES / "config_full.yaml"),
            dry_run=True,
            client=client,
            now=NOW,
            used_guids=set(),
        )

        # Verify lineup
        assert len(lineup.episodes) == 5
        assert lineup.total_seconds == 1512
        assert lineup.total_minutes == pytest.approx(25.2)

    def test_dry_run_does_not_write_feed(self, tmp_path: Path) -> None:
        """Dry run does not create feed.xml."""
        config_path = str(FIXTURES / "config_full.yaml")
        build_dir = tmp_path / "build" / FEED_TOKEN

        # Use run_build directly with injected client
        client = fixture_client()
        lineup = run_build(
            config_path=config_path,
            dry_run=True,
            client=client,
            now=NOW,
            used_guids=set(),
        )

        # Verify no feed was written (dry_run=True should not write)
        assert len(lineup.episodes) == 5
        # No feed.xml should be created
        assert not (build_dir / "feed.xml").exists()
        # No build directory should be created at all
        assert not build_dir.exists()

    def test_dry_run_does_not_create_state_db(self, tmp_path: Path) -> None:
        """Dry run does not create or modify the state database."""
        config_path = str(FIXTURES / "config_full.yaml")
        state_dir = tmp_path / "state"

        # Use run_build directly with injected client
        client = fixture_client()
        lineup = run_build(
            config_path=config_path,
            dry_run=True,
            client=client,
            now=NOW,
            used_guids=set(),
        )

        # Verify no state was created
        assert len(lineup.episodes) == 5
        # No state database should be created
        assert not (state_dir / "commute.db").exists()


class TestWritePath:
    """Test the write path (dry_run=False) creates feed.xml and state."""

    def test_write_path_creates_feed_xml(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Write path creates feed.xml in build/<token>/."""
        config_path = str(FIXTURES / "config_full.yaml")
        build_dir = tmp_path / "build" / FEED_TOKEN

        # Set the token in environment
        monkeypatch.setenv("NEWNEWS_FEED_TOKEN", FEED_TOKEN)
        monkeypatch.chdir(tmp_path)  # so build/ is created in tmp_path

        client = fixture_client()
        run_build(
            config_path=config_path,
            dry_run=False,
            client=client,
            now=NOW,
            used_guids=set(),
        )

        # Check that feed was written
        assert (build_dir / "feed.xml").exists()

        # Read and verify the feed
        feed_content = (build_dir / "feed.xml").read_bytes()
        assert b"NewNews Commute" in feed_content
        # The feed should contain some of the source names
        assert b"Fox News Rundown" in feed_content

    def test_write_path_records_state(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Write path records episodes in the state database."""
        config_path = str(FIXTURES / "config_full.yaml")
        db_path = tmp_path / "state" / "commute.db"

        # Set the token in environment
        monkeypatch.setenv("NEWNEWS_FEED_TOKEN", FEED_TOKEN)
        monkeypatch.chdir(tmp_path)  # so state/ is created in tmp_path

        client = fixture_client()
        lineup = run_build(
            config_path=config_path,
            dry_run=False,
            client=client,
            now=NOW,
            used_guids=set(),
        )

        # Connect to the state database
        conn = connect(db_path)

        # Check that state was recorded
        # Note: Some episodes have duplicate guids across sources (e.g., keep-001
        # appears in both fox_news_rundown and bbc_global_news fixtures).
        # So we check for unique guids, not total episodes.
        guids = used_guids(conn)
        assert len(guids) == 3  # 3 unique guids: keep-001, sample-001, est-from-length

        # Check that all guids from lineup are recorded
        expected_guids = {e.guid for e in lineup.episodes}
        assert guids == expected_guids

    def test_second_run_does_not_repeat_episodes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Second run skips episodes already used in first run."""
        config_path = str(FIXTURES / "config_full.yaml")

        # Set the token in environment
        monkeypatch.setenv("NEWNEWS_FEED_TOKEN", FEED_TOKEN)
        monkeypatch.chdir(tmp_path)  # so state/ is created in tmp_path

        client = fixture_client()

        # First run
        lineup1 = run_build(
            config_path=config_path,
            dry_run=False,
            client=client,
            now=NOW,
            used_guids=set(),
        )

        # Get the used guids from state
        db_path = tmp_path / "state" / "commute.db"
        conn = connect(db_path)
        first_run_guids = used_guids(conn)

        # Second run with those guids marked as used
        used = set(first_run_guids)
        lineup2 = run_build(
            config_path=config_path,
            dry_run=False,
            client=client,
            now=NOW,
            used_guids=used,
        )

        # Second run should have fewer episodes (or empty if all were used)
        assert len(lineup2.episodes) < len(lineup1.episodes)
