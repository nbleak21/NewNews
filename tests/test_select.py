# Copyright (c) 2026 Nick L
# SPDX-License-Identifier: MIT
"""Tests for the selection algorithm (TASKS.md task 5).

Pure functions only: the clock (``now``), the set of already-used guids and
the config are passed in, so every case below is a plain unit test. Nothing
is fetched and nothing is written; the episodes are built in memory.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from commute_news.config import Config, Source
from commute_news.parse import Episode
from commute_news.select import (
    eligible_episodes,
    fill_to_target,
    order_candidates,
    select_lineup,
)

NOW = datetime(2026, 11, 21, 12, 0, 0, tzinfo=UTC)


def ep(source_id: str, guid: str, *, minutes_ago: float = 30.0, duration: int = 600) -> Episode:
    """An in-memory episode: published ``minutes_ago``, ``duration`` seconds long."""
    return Episode(
        source_id=source_id,
        guid=guid,
        title=guid,
        published=NOW - timedelta(minutes=minutes_ago),
        enclosure_url=f"https://audio.example.test/{guid}.mp3",
        enclosure_type="audio/mpeg",
        enclosure_length=duration * 16000,
        duration=duration,
    )


def src(source_id: str, lean: str = "center", priority: int = 1) -> Source:
    """A Source for the tests; the URL is a reserved .test host, never fetched."""
    return Source(
        id=source_id,
        name=source_id,
        lean=lean,
        priority=priority,
        feed_url="https://feeds.example.test/sample.xml",
    )


def cfg(
    sources: tuple[Source, ...],
    *,
    target: int = 20,
    low: int = 10,
    high: int = 30,
    freshness: int = 2,
    per_source: int = 1,
) -> Config:
    return Config(
        target_minutes=target,
        min_minutes=low,
        max_minutes=high,
        freshness_hours=freshness,
        max_per_source=per_source,
        sources=sources,
    )


# --- freshness filter, unplayed filter, newest per source -------------------


def test_nothing_fresh_gives_no_candidates() -> None:
    stale = ep("a", "stale", minutes_ago=121)
    assert eligible_episodes([stale], set(), NOW, 2, 1) == []


def test_freshness_window_boundary_is_inclusive() -> None:
    just = ep("a", "just", minutes_ago=120)
    assert [e.guid for e in eligible_episodes([just], set(), NOW, 2, 1)] == ["just"]


def test_unplayed_filter_drops_used_guids() -> None:
    keep = ep("a", "keep")
    drop = ep("b", "drop")
    result = eligible_episodes([keep, drop], {"drop"}, NOW, 2, 1)
    assert [e.guid for e in result] == ["keep"]


def test_newest_episode_of_each_source_only() -> None:
    older = ep("a", "older", minutes_ago=90)
    newest = ep("a", "newest", minutes_ago=10)
    other = ep("b", "other", minutes_ago=45)
    result = eligible_episodes([older, newest, other], set(), NOW, 2, 1)
    assert sorted(e.guid for e in result) == ["newest", "other"]


def test_max_per_source_allows_two_when_asked() -> None:
    first = ep("a", "first", minutes_ago=90)
    second = ep("a", "second", minutes_ago=45)
    third = ep("a", "third", minutes_ago=10)
    result = eligible_episodes([first, second, third], set(), NOW, 2, 2)
    assert sorted(e.guid for e in result) == ["second", "third"]


def test_all_used_gives_no_candidates() -> None:
    episodes = [ep("a", "g1"), ep("b", "g2")]
    assert eligible_episodes(episodes, {"g1", "g2"}, NOW, 2, 1) == []


# --- priority order, tie on priority, lean mix ------------------------------


def test_priority_one_is_ordered_first() -> None:
    sources = (src("aaa", priority=2), src("bbb", priority=1))
    episodes = [ep("aaa", "g1"), ep("bbb", "g2")]
    ordered = order_candidates(episodes, sources)
    assert [e.source_id for e in ordered] == ["bbb", "aaa"]


def test_tie_on_priority_prefers_the_newer_episode() -> None:
    sources = (src("aaa", priority=1), src("bbb", priority=1))
    older = ep("aaa", "g1", minutes_ago=90)
    newer = ep("bbb", "g2", minutes_ago=10)
    ordered = order_candidates([older, newer], sources)
    assert [e.guid for e in ordered] == ["g2", "g1"]


def test_tie_on_priority_and_time_falls_back_to_source_id() -> None:
    sources = (src("zzz", priority=1), src("aaa", priority=1))
    # same priority, same published minute: the order must still be stable
    first = ep("aaa", "g1", minutes_ago=30)
    second = ep("zzz", "g2", minutes_ago=30)
    ordered = order_candidates([second, first], sources)
    assert [e.source_id for e in ordered] == ["aaa", "zzz"]


def test_lean_mix_is_kept_in_the_order() -> None:
    sources = (
        src("c1", lean="center", priority=1),
        src("c2", lean="center", priority=2),
        src("r1", lean="right", priority=3),
    )
    episodes = [
        ep("c1", "g1"),
        ep("c2", "g2"),
        ep("r1", "g3"),
    ]
    ordered = order_candidates(episodes, sources)
    # the right-lean source is pulled to the front rather than queued last,
    # so the lineup is not three "center" episodes in a row.
    assert [e.source_id for e in ordered] == ["c1", "r1", "c2"]


def test_lean_mix_survives_the_fill() -> None:
    sources = (
        src("c1", lean="center", priority=1),
        src("c2", lean="center", priority=2),
        src("r1", lean="right", priority=3),
    )
    episodes = [
        ep("c1", "g1", duration=600),
        ep("c2", "g2", duration=600),
        ep("r1", "g3", duration=600),
    ]
    ordered = order_candidates(episodes, sources)
    lineup = fill_to_target(ordered, 20, 10, 20)
    # two 10-minute slots: the mix keeps one "center" AND one "right",
    # where a plain priority order would have chosen c1 + c2.
    assert [e.source_id for e in lineup.episodes] == ["c1", "r1"]


# --- fill to target --------------------------------------------------------


def test_exact_fit_stops_on_target() -> None:
    episodes = [
        ep("a", "a", duration=600),  # 10 min
        ep("b", "b", duration=900),  # 15 min
        ep("c", "c", duration=600),  # would be 45 min in total
    ]
    lineup = fill_to_target(episodes, 25, 20, 30)
    assert [e.guid for e in lineup.episodes] == ["a", "b"]
    assert lineup.total_seconds == 1500
    assert lineup.total_minutes == 25


def test_undershoot_returns_every_candidate_as_a_short_lineup() -> None:
    episodes = [ep("a", "a", duration=420), ep("b", "b", duration=420)]
    lineup = fill_to_target(episodes, 25, 20, 30)
    assert [e.guid for e in lineup.episodes] == ["a", "b"]
    assert lineup.total_seconds == 840
    assert lineup.total_minutes < 20  # below min_minutes: a "short" lineup


def test_overshoot_is_avoided() -> None:
    episodes = [ep(f"s{i}", f"g{i}", duration=600) for i in range(4)]
    lineup = fill_to_target(episodes, 25, 20, 30)
    assert len(lineup.episodes) == 3
    assert lineup.total_seconds == 1800  # exactly the ceiling, the 4th is dropped
    assert lineup.total_seconds <= 30 * 60


def test_candidate_larger_than_the_ceiling_is_never_added() -> None:
    oversized = ep("a", "oversized", duration=45 * 60)
    lineup = fill_to_target([oversized], 25, 20, 30)
    assert lineup.episodes == ()
    assert lineup.total_seconds == 0


def test_minutes_out_of_order_is_rejected() -> None:
    with pytest.raises(ValueError):
        fill_to_target([], 40, 35, 30)  # target > max


# --- the whole pipeline (select_lineup) ------------------------------------


def test_select_lineup_takes_fresh_unplayed_in_order() -> None:
    sources = (src("a", priority=1), src("b", priority=2))
    episodes = [
        ep("a", "a1", minutes_ago=30, duration=600),
        ep("b", "b1", minutes_ago=45, duration=600),
    ]
    lineup = select_lineup(episodes, sources, set(), NOW, cfg(sources, target=20, high=20))
    assert [e.guid for e in lineup.episodes] == ["a1", "b1"]
    assert lineup.total_seconds == 1200


def test_select_lineup_with_nothing_fresh_is_empty() -> None:
    sources = (src("a"),)
    episodes = [ep("a", "stale", minutes_ago=180)]
    lineup = select_lineup(episodes, sources, set(), NOW, cfg(sources))
    assert lineup.episodes == ()
    assert lineup.total_seconds == 0


def test_select_lineup_with_everything_used_is_empty() -> None:
    sources = (src("a"), src("b"))
    episodes = [ep("a", "g1"), ep("b", "g2")]
    used = {e.guid for e in episodes}
    lineup = select_lineup(episodes, sources, used, NOW, cfg(sources))
    assert lineup.episodes == ()
    assert lineup.total_seconds == 0


# --- robustness / edge cases ------------------------------------------------


def test_oversized_top_candidate_is_skipped_for_a_fitting_one() -> None:
    # Regression: the top-ranked candidate alone exceeds the ceiling; a shorter
    # later candidate must still be picked instead of an empty lineup.
    oversized = ep("a", "too-long", duration=45 * 60)  # 45 min > 30 min ceiling
    fits = ep("b", "fits", duration=600)  # 10 min
    lineup = fill_to_target([oversized, fits], 25, 20, 30)
    assert [e.guid for e in lineup.episodes] == ["fits"]
    assert lineup.total_seconds == 600


def test_eligible_episodes_rejects_bad_params() -> None:
    with pytest.raises(ValueError):
        eligible_episodes([], set(), NOW, freshness_hours=-1, max_per_source=1)
    with pytest.raises(ValueError):
        eligible_episodes([], set(), NOW, freshness_hours=2, max_per_source=0)


def test_order_candidates_ranks_unknown_source_last() -> None:
    # An episode whose source is not in `sources` is ranked last, never dropped.
    known = ep("known", "k1")
    orphan = ep("ghost", "o1")
    ordered = order_candidates([orphan, known], [src("known")])
    assert [e.guid for e in ordered] == ["k1", "o1"]
