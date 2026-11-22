"""Tests for the CLI: the argument parser (task 8a) and the build wiring
(task 8b).

Nothing here touches the network: the wiring test serves the fixture feeds
from ``tests/fixtures/`` through ``httpx.MockTransport``.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from commute_news.cli import build_parser, run_build


def parse(argv: list[str]) -> argparse.Namespace:
    """Parse one command line, exactly as a user would type it."""
    return build_parser().parse_args(argv)


def test_defaults_are_the_documented_ones() -> None:
    args = parse(["build"])
    assert args.command == "build"
    assert args.config == "config/sources.yaml"
    assert args.dry_run is False


def test_dry_run_flag_is_a_store_true() -> None:
    args = parse(["build", "--dry-run"])
    assert args.dry_run is True
    assert args.config == "config/sources.yaml"


def test_config_option_overrides_the_default() -> None:
    args = parse(["build", "--config", "other/sources.yaml"])
    assert args.config == "other/sources.yaml"
    assert args.dry_run is False


def test_config_and_dry_run_combine() -> None:
    args = parse(["build", "--config", "x.yaml", "--dry-run"])
    assert (args.config, args.dry_run) == ("x.yaml", True)


def test_build_subcommand_is_required() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args([])


def test_unknown_flag_is_rejected() -> None:
    with pytest.raises(SystemExit):
        parse(["build", "--no-such-flag"])


# --- task 8b: fetch -> parse -> select, everything injected ---------------

FIXTURES = Path(__file__).parent / "fixtures"
FEEDS = FIXTURES / "feeds"

#: Which fixture file each example.com URL of config_full.yaml is served.
#: Every fixture under tests/fixtures/feeds/ is used by at least one URL.
SERVED: dict[str, str] = {
    "fox-news-rundown.xml": "skip_items.xml",
    "npr-news-now.xml": "sample_feed.xml",
    "wsj-whats-news.xml": "estimate_duration.xml",
    "bbc-global-news.xml": "skip_items.xml",
    "morning-wire.xml": "sample_feed.xml",
    "up-first.xml": "estimate_duration.xml",
    "the-daily.xml": "durations.xml",
}

#: Fixed clock: inside the fixture config's "am" slot (04:15-11:59) and
#: within the 2 hour freshness window of the fixtures' pubDates.
NOW = datetime(2026, 11, 19, 7, 30, tzinfo=UTC)


def fixture_client() -> httpx.Client:
    """A client whose transport serves the fixture feeds, never the network."""

    def handler(request: httpx.Request) -> httpx.Response:
        name = str(request.url).rsplit("/", 1)[-1]
        return httpx.Response(200, content=(FEEDS / SERVED[name]).read_bytes())

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_wiring_selects_the_expected_lineup() -> None:
    lineup = run_build(
        config_path=str(FIXTURES / "config_full.yaml"),
        dry_run=True,
        client=fixture_client(),
        now=NOW,
        used_guids=set(),
    )
    assert [(e.source_id, e.guid) for e in lineup.episodes] == [
        ("fox_news_rundown", "keep-001"),
        ("npr_news_now", "sample-001"),
        ("bbc_global_news", "keep-001"),
        ("wsj_whats_news", "est-from-length"),
        ("morning_wire", "sample-001"),
    ]
    assert len(lineup.episodes) == 5
    assert lineup.total_seconds == 1512
    assert lineup.total_minutes == pytest.approx(25.2)


# --- timezone: slots are LOCAL wall-clock, not UTC -------------------------


def _one_episode_feed(published: str, guid: str) -> bytes:
    return (
        "<?xml version='1.0'?><rss version='2.0' "
        "xmlns:itunes='http://www.itunes.com/dtds/podcast-1.0.dtd'><channel>"
        "<title>T</title>"
        f"<item><guid>{guid}</guid><title>Ep</title>"
        f"<pubDate>{published}</pubDate>"
        "<itunes:duration>600</itunes:duration>"
        "<enclosure url='https://example.com/a.mp3' type='audio/mpeg' length='1000'/>"
        "</item></channel></rss>"
    ).encode()


def test_slot_selection_uses_config_timezone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """run_build must convert ``now`` to the config timezone before slot matching.

    NOW is 15:00 UTC = 09:00 in America/Chicago (CST), inside the single
    04:00-11:59 slot. As a raw UTC wall-clock, 15:00 is OUTSIDE it — so the old
    code produced an empty lineup. The fix converts to local first and selects
    the episode.
    """
    monkeypatch.chdir(tmp_path)
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text(
        "timezone: 'America/Chicago'\n"
        "freshness_hours: 6\n"
        "retain_hours: 6\n"
        "slots:\n"
        "  am:\n"
        "    label: AM\n"
        "    start: '04:00'\n"
        "    end: '11:59'\n"
        "    sources: all\n"
        "sources:\n"
        "  - id: s1\n"
        "    name: Source One\n"
        "    lean: center\n"
        "    priority: 1\n"
        "    feed_url: 'https://example.com/s1.xml'\n"
    )
    body = _one_episode_feed("Thu, 19 Nov 2026 14:00:00 GMT", "ep-1")
    client = httpx.Client(
        transport=httpx.MockTransport(lambda _req: httpx.Response(200, content=body))
    )
    now = datetime(2026, 11, 19, 15, 0, tzinfo=UTC)  # 09:00 America/Chicago

    lineup = run_build(config_path=str(cfg), dry_run=True, client=client, now=now, used_guids=set())
    # Empty on the old UTC-based code (15:00 > 11:59); selected after the fix.
    assert [e.guid for e in lineup.episodes] == ["ep-1"]
