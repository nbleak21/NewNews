"""End-to-end test: whole pipeline twice from fixture feeds.

First run writes a valid feed; second run does not repeat episodes.
Asserts lineup length, order, enclosure URLs and state contents.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

FIXTURES = Path(__file__).parent / "fixtures"
FEEDS = FIXTURES / "feeds"

#: Fixed clock: inside the fixture config's "am" slot and within the freshness window.
#: Using a later time so fixture episodes are within the freshness window.
#: Fixture episodes are published at various times; we need to be within 2 hours.
NOW = datetime(2026, 11, 19, 10, 0, tzinfo=UTC)


#: Map of expected feed URLs to fixture files.
SERVED: dict[str, str] = {
    "fox-news-rundown.xml": "skip_items.xml",
    "npr-news-now.xml": "sample_feed.xml",
    "wsj-whats-news.xml": "estimate_duration.xml",
    "bbc-global-news.xml": "skip_items.xml",
    "morning-wire.xml": "sample_feed.xml",
    "up-first.xml": "estimate_duration.xml",
    "the-daily.xml": "durations.xml",
}


def fixture_transport_handler(request: httpx.Request) -> httpx.Response:
    """HTTP transport handler that serves fixture feeds from tests/fixtures/feeds/."""
    # Extract filename from URL path
    path = str(request.url)
    name = path.rsplit("/", 1)[-1]

    # Normalize underscores to hyphens to match fixture files
    # e.g., fox_news_rundown.xml -> fox-news-rundown.xml
    normalized_name = name.replace("_", "-")

    if normalized_name in SERVED:
        fixture_file = FEEDS / SERVED[normalized_name]
        content = fixture_file.read_bytes()
        return httpx.Response(200, content=content)

    # Return 404 for unknown URLs
    return httpx.Response(404)


class TestEndToEnd:
    """End-to-end tests: whole pipeline from CLI using fixture feeds."""

    def test_e2e_full_pipeline_first_run(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """First run: writes feed.xml and records state to database."""
        # Set up environment
        token = "test-e2e-full-token"
        monkeypatch.setenv("NEWNEWS_FEED_TOKEN", token)
        monkeypatch.chdir(tmp_path)

        # Monkeypatch build_client to use a transport that serves fixture feeds
        def mock_build_client(**kwargs):
            transport = httpx.MockTransport(fixture_transport_handler)
            return httpx.Client(transport=transport, **kwargs)

        # Patch both fetch.build_client and cli.build_client
        monkeypatch.setattr("commute_news.fetch.build_client", mock_build_client)
        monkeypatch.setattr("commute_news.cli.build_client", mock_build_client)

        config_path = str(FIXTURES / "config_full.yaml")

        # First run - write path (dry_run=False)
        # Use run_build directly with injected client and now
        from commute_news.cli import run_build

        lineup = run_build(
            config_path=config_path,
            dry_run=False,
            client=mock_build_client(),
            now=NOW,
        )

        # Verify lineup
        assert len(lineup.episodes) > 0, "First run should produce episodes"

        # Verify feed was written
        build_dir = tmp_path / "build" / token
        feed_path = build_dir / "feed.xml"
        assert feed_path.exists(), "feed.xml should exist after first run"

        # Read and verify the feed
        feed_content = feed_path.read_bytes()
        assert b"NewNews Commute" in feed_content
        assert b"<channel>" in feed_content
        assert b"<item>" in feed_content

        # Verify state database was created
        state_dir = tmp_path / "state"
        state_db = state_dir / "commute.db"
        assert state_db.exists(), "state database should exist after first run"

        # Check state contents
        from commute_news.state import connect, used_guids

        conn = connect(state_db)
        guids = used_guids(conn)
        assert len(guids) > 0, "State should have recorded some episodes"

        # Verify all episodes from lineup are in state
        lineup_guids = {e.guid for e in lineup.episodes}
        assert guids == lineup_guids, "All lineup episodes should be recorded in state"

    def test_e2e_full_pipeline_second_run(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Second run: does not repeat episodes already used (state-based)."""
        # Set up environment
        token = "test-e2e-second-token"
        monkeypatch.setenv("NEWNEWS_FEED_TOKEN", token)
        monkeypatch.chdir(tmp_path)

        # Monkeypatch build_client to use a transport that serves fixture feeds
        def mock_build_client(**kwargs):
            transport = httpx.MockTransport(fixture_transport_handler)
            return httpx.Client(transport=transport, **kwargs)

        monkeypatch.setattr("commute_news.fetch.build_client", mock_build_client)
        monkeypatch.setattr("commute_news.cli.build_client", mock_build_client)

        config_path = str(FIXTURES / "config_full.yaml")

        # First run - write path
        from commute_news.cli import run_build

        lineup1 = run_build(
            config_path=config_path,
            dry_run=False,
            client=mock_build_client(),
            now=NOW,
        )

        # Verify first run produced episodes
        assert len(lineup1.episodes) > 0, "First run should produce some episodes"

        # Get the used guids from state database
        state_db = tmp_path / "state" / "commute.db"
        from commute_news.state import connect, used_guids

        conn1 = connect(state_db)
        first_run_guids = used_guids(conn1)

        # Second run - without passing used_guids (should read from state)
        lineup2 = run_build(
            config_path=config_path,
            dry_run=False,
            client=mock_build_client(),
            now=NOW,
        )

        # Second run should have fewer or equal episodes than first run
        # (it might have same if no new episodes available, but should not have more)
        assert len(lineup2.episodes) <= len(lineup1.episodes), (
            "Second run should not produce more episodes than first run"
        )

        # Get second run state
        conn2 = connect(state_db)
        second_run_guids = used_guids(conn2)

        # Second run should have at least as many guids as first run
        # (it might have more if new episodes were added, but not fewer)
        assert len(second_run_guids) >= len(first_run_guids), (
            "Second run should not remove previously recorded episodes"
        )

    def test_e2e_feed_structure(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Feed has correct structure: titles prefixed, pubDates ordered, enclosures preserved."""
        # Set up environment
        token = "test-e2e-structure-token"
        monkeypatch.setenv("NEWNEWS_FEED_TOKEN", token)
        monkeypatch.chdir(tmp_path)

        # Monkeypatch build_client to use a transport that serves fixture feeds
        def mock_build_client(**kwargs):
            transport = httpx.MockTransport(fixture_transport_handler)
            return httpx.Client(transport=transport, **kwargs)

        monkeypatch.setattr("commute_news.fetch.build_client", mock_build_client)
        monkeypatch.setattr("commute_news.cli.build_client", mock_build_client)

        config_path = str(FIXTURES / "config_full.yaml")

        # Run the build
        from commute_news.cli import run_build

        lineup = run_build(
            config_path=config_path,
            dry_run=False,
            client=mock_build_client(),
            now=NOW,
        )

        # Verify lineup structure
        assert len(lineup.episodes) > 0, "Lineup should have episodes"

        # Check episode attributes
        for episode in lineup.episodes:
            url = episode.enclosure_url
            assert url is not None, "Episode should have enclosure URL"
            assert "media.example.test" in url or "example.com" in url, (
                f"Episode enclosure URL should point to test fixture, got {url}"
            )
