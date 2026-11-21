"""Choose the lineup.

Pure functions: no I/O, no clock. Pass ``now`` and the already-used guids in
as arguments so every case is a plain unit test.

Preference order (best first), used by :func:`order_candidates`:

1. ``Source.priority`` ascending: 1 is picked before 2 (see
   ``config/sources.example.yaml``).
2. Then the newer ``published`` wins.
3. Then ``source_id`` ascending, so the order is always deterministic.

Lean mix: after ranking, the candidates are grouped by their source's lean tag
and the groups are round-robined (one candidate from each non-empty group per
pass, groups visited in the order above). The first pick is still the
best-ranked candidate, but the next pick comes from a different lean whenever
one is available, so one outlet's lean cannot fill the whole lineup.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable
from dataclasses import dataclass
from datetime import datetime

from .config import Config, Source
from .parse import Episode

# An episode whose source is not in the config is ranked last, never first.
_UNKNOWN_PRIORITY = 2**31


@dataclass(frozen=True)
class Lineup:
    """The ordered episodes chosen for one run plus the total runtime in seconds."""

    episodes: tuple[Episode, ...] = ()
    total_seconds: int = 0

    @property
    def total_minutes(self) -> float:
        """``total_seconds`` in minutes, unrounded (25.0, 14.0, ...)."""
        return self.total_seconds / 60


def eligible_episodes(
    episodes: Iterable[Episode],
    used_guids: Collection[str],
    now: datetime,
    freshness_hours: float,
    max_per_source: int,
) -> list[Episode]:
    """Unplayed episodes from the freshness window, newest per source.

    Keeps an episode when its guid is not in ``used_guids`` and its age
    (``now - published``) is at most ``freshness_hours``. Of the survivors at
    most ``max_per_source`` per source are kept: the newest ones. The input
    order of the kept episodes is preserved; a source with no fresh episode
    simply contributes nothing.
    """
    if freshness_hours < 0:
        raise ValueError(f"freshness_hours must be >= 0, got {freshness_hours}")
    if max_per_source < 1:
        raise ValueError(f"max_per_source must be >= 1, got {max_per_source}")

    fresh = [
        episode
        for episode in episodes
        if episode.guid not in used_guids and _age_seconds(episode, now) <= freshness_hours * 3600
    ]

    by_source: dict[str, list[Episode]] = {}
    for episode in fresh:
        by_source.setdefault(episode.source_id, []).append(episode)

    keep: set[Episode] = set()
    for group in by_source.values():
        newest_first = sorted(group, key=lambda episode: episode.published, reverse=True)
        keep.update(newest_first[:max_per_source])

    return [episode for episode in fresh if episode in keep]


def order_candidates(episodes: Iterable[Episode], sources: Iterable[Source]) -> list[Episode]:
    """Rank the candidates, then interleave lean tags for a balanced mix.

    See the module docstring for the tie-break rules. An episode whose source
    is not in ``sources`` is ranked last and grouped under the empty lean.
    """
    lookup = {source.id: source for source in sources}
    ranked = sorted(episodes, key=lambda episode: _rank(episode, lookup))

    groups: dict[str, list[Episode]] = {}
    for episode in ranked:
        groups.setdefault(_lean_of(episode, lookup), []).append(episode)

    # Round-robin: one candidate per group per pass, groups in rank order.
    group_list = list(groups.values())
    positions = [0] * len(group_list)
    ordered: list[Episode] = []
    took_any = True
    while took_any:
        took_any = False
        for index, group in enumerate(group_list):
            position = positions[index]
            if position < len(group):
                ordered.append(group[position])
                positions[index] = position + 1
                took_any = True
    return ordered


def fill_to_target(
    candidates: Iterable[Episode], target_minutes: float, min_minutes: float, max_minutes: float
) -> Lineup:
    """Add candidates in order until the total reaches ``target_minutes``.

    Never exceeds ``max_minutes``: the first candidate that does not fit under
    the ceiling ends the fill, so the result is always a prefix of
    ``candidates``. A short result (candidates exhausted, or the next one would
    break the ceiling) is returned as-is; the caller decides whether it is
    shorter than ``min_minutes``.

    Raises ``ValueError`` unless ``0 <= min_minutes <= target_minutes <=
    max_minutes``.
    """
    if not (0 <= min_minutes <= target_minutes <= max_minutes):
        raise ValueError(
            "require 0 <= min_minutes <= target_minutes <= max_minutes, got "
            f"min_minutes={min_minutes} target_minutes={target_minutes} "
            f"max_minutes={max_minutes}"
        )
    target_seconds = int(target_minutes * 60)
    max_seconds = int(max_minutes * 60)

    chosen: list[Episode] = []
    total = 0
    for episode in candidates:
        if total >= target_seconds:
            break
        if total + episode.duration > max_seconds:
            break
        chosen.append(episode)
        total += episode.duration
    return Lineup(episodes=tuple(chosen), total_seconds=total)


def select_lineup(
    episodes: Iterable[Episode],
    sources: Iterable[Source],
    used_guids: Collection[str],
    now: datetime,
    config: Config,
) -> Lineup:
    """Freshness + unplayed + newest-per-source, then rank, then fill.

    Slot limits (``config.slot_for_time``) are the caller's business: filter
    ``episodes`` or ``sources`` before calling if a slot restricts them.
    """
    fresh = eligible_episodes(
        episodes,
        used_guids,
        now,
        freshness_hours=config.freshness_hours,
        max_per_source=config.max_per_source,
    )
    ordered = order_candidates(fresh, sources)
    return fill_to_target(
        ordered,
        target_minutes=config.target_minutes,
        min_minutes=config.min_minutes,
        max_minutes=config.max_minutes,
    )


# --- helpers (private) -----------------------------------------------------


def _age_seconds(episode: Episode, now: datetime) -> float:
    """Seconds since publication; negative for a feed that lies about dates."""
    return (now - episode.published).total_seconds()


def _priority_of(episode: Episode, lookup: dict[str, Source]) -> int:
    source = lookup.get(episode.source_id)
    return source.priority if source is not None else _UNKNOWN_PRIORITY


def _lean_of(episode: Episode, lookup: dict[str, Source]) -> str:
    source = lookup.get(episode.source_id)
    return source.lean if source is not None else ""


def _rank(episode: Episode, lookup: dict[str, Source]) -> tuple[int, float, str]:
    """Sort key, best first: priority, then newest, then source id."""
    return (
        _priority_of(episode, lookup),
        -episode.published.timestamp(),
        episode.source_id,
    )
