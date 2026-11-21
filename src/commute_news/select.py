"""Choose the lineup.

Scaffold only: stubs with docstrings, no logic yet (see TASKS.md task 5).

Newest unplayed episode per source, inside the freshness window, added in
priority order until the total is near the target (allowed range min..max),
while keeping a mix of lean tags.
"""
# HINT: keep this module pure (no I/O, no clock). Pass `now` and the set of
# already-used guids in as arguments so every case is a plain unit test.
# HINT: write the tie-break rules down in the docstring before coding them.

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Lineup:
    """The ordered episodes chosen for one run plus the total runtime in seconds."""


def eligible_episodes(episodes, used_guids, now, freshness_hours: float, max_per_source: int):
    """Keep unplayed episodes inside the freshness window, newest ``max_per_source`` each."""
    raise NotImplementedError


def order_candidates(episodes, sources):
    """Order candidates by source priority while interleaving lean tags for a balanced mix."""
    raise NotImplementedError


def fill_to_target(
    candidates, target_minutes: float, min_minutes: float, max_minutes: float
) -> Lineup:
    """Add candidates in order until the total is close to target without exceeding max."""
    raise NotImplementedError


def select_lineup(episodes, sources, used_guids, now, config) -> Lineup:
    """Run the full selection pipeline and return the :class:`Lineup`."""
    raise NotImplementedError
