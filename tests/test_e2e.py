"""End-to-end tests: the whole pipeline run twice from fixture feeds.

These exercise the REAL pipeline behaviour — no ``used_guids`` is injected, so
``run_build`` loads it from state. A second run must not repeat the first run's
episodes, and the written feed must carry the whole retained window, not just
the latest run's lineup. Nothing here touches the network (fixtures are served
through ``httpx.MockTransport``).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import feedparser
import httpx
import pytest

from commute_news.cli import run_build
from commute_news.state import connect, used_guids

FIXTURES = Path(__file__).parent / "fixtures"
FEEDS = FIXTURES / "feeds"
CONFIG = str(FIXTURES / "config_full.yaml")

#: Fixed clock: inside the fixture config's "am" slot and within the 2h
#: freshness window of the fixtures (the instant test_cli.py also uses).
NOW = datetime(2026, 11, 19, 7, 30, tzinfo=UTC)

#: Which fixture file each example.com URL of config_full.yaml is served.
SERVED: dict[str, str] = {
    "fox-news-rundown.xml": "skip_items.xml",
    "npr-news-now.xml": "sample_feed.xml",
    "wsj-whats-news.xml": "estimate_duration.xml",
    "bbc-global-news.xml": "skip_items.xml",
    "morning-wire.xml": "sample_feed.xml",
    "up-first.xml": "estimate_duration.xml",
    "the-daily.xml": "durations.xml",
}


def fixture_client() -> httpx.Client:
    """A client whose transport serves the fixture feeds, never the network."""

    def handler(request: httpx.Request) -> httpx.Response:
        name = str(request.url).rsplit("/", 1)[-1]
        return httpx.Response(200, content=(FEEDS / SERVED[name]).read_bytes())

    return httpx.Client(transport=httpx.MockTransport(handler))


def _feed_guids(feed_path: Path) -> set[str]:
    parsed = feedparser.parse(feed_path.read_bytes())
    return {entry.id for entry in parsed.entries}


def _setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, token: str) -> None:
    monkeypatch.setenv("NEWNEWS_FEED_TOKEN", token)
    monkeypatch.chdir(tmp_path)  # build/ and state/ land under tmp_path


def test_first_run_writes_feed_and_records_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """First run writes feed.xml, records state, and the feed holds the lineup."""
    token = "e2e-first"
    _setup(tmp_path, monkeypatch, token)

    lineup = run_build(config_path=CONFIG, dry_run=False, client=fixture_client(), now=NOW)
    assert lineup.episodes, "first run should produce a lineup"

    feed_path = tmp_path / "build" / token / "feed.xml"
    assert feed_path.exists()
    content = feed_path.read_bytes()
    assert b"NewNews Commute" in content
    assert b"<item>" in content

    db = tmp_path / "state" / "commute.db"
    assert db.exists()
    recorded = used_guids(connect(db))
    assert recorded == {e.guid for e in lineup.episodes}
    # The written feed carries exactly the recorded (guid-unique) episodes.
    assert _feed_guids(feed_path) == recorded


def test_second_run_does_not_repeat_and_feed_retains_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A second run excludes the first run's episodes, yet the feed keeps them."""
    token = "e2e-second"
    _setup(tmp_path, monkeypatch, token)

    lineup1 = run_build(config_path=CONFIG, dry_run=False, client=fixture_client(), now=NOW)
    run1_guids = {e.guid for e in lineup1.episodes}
    assert run1_guids, "first run should produce a lineup"

    # No injected used_guids: run_build must load them from state and exclude them.
    lineup2 = run_build(config_path=CONFIG, dry_run=False, client=fixture_client(), now=NOW)
    run2_guids = {e.guid for e in lineup2.episodes}

    # (a) No episode is repeated across runs.
    assert run1_guids.isdisjoint(run2_guids), (
        f"second run repeated episodes: {run1_guids & run2_guids}"
    )

    # (b) The written feed still carries the first run's episodes (retained
    #     within retain_hours), not only the latest run's lineup.
    feed_path = tmp_path / "build" / token / "feed.xml"
    feed_guids = _feed_guids(feed_path)
    assert run1_guids <= feed_guids, "retained feed dropped the first run's items"
    assert run2_guids <= feed_guids


def test_feed_items_are_prefixed_and_enclosures_preserved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every feed item has the prefixed title and keeps its original enclosure."""
    token = "e2e-structure"
    _setup(tmp_path, monkeypatch, token)

    run_build(config_path=CONFIG, dry_run=False, client=fixture_client(), now=NOW)

    feed_path = tmp_path / "build" / token / "feed.xml"
    content = feed_path.read_bytes()
    parsed = feedparser.parse(content)
    assert parsed.entries, "feed should have items"
    for entry in parsed.entries:
        # Prefixed title, e.g. "AM Wed 11/19 · 1/3 · NPR News Now — ...".
        assert " · " in entry.title
    # Link-only: one <enclosure> per item, pointing at the original audio.
    assert content.count(b"<enclosure") == len(parsed.entries)
