"""Write the private podcast RSS feed (``feed.xml``).

Scaffold only: stubs with docstrings, no logic yet (see TASKS.md task 7).

Each item's enclosure is the ORIGINAL audio URL, untouched. Titles are prefixed
(e.g. ``AM Fri 11/21 · 2/5 · Fox News Rundown — <original title>``) and
pubDates are spaced a few seconds apart so players keep the intended order.
"""
# HINT: write to a temp file and os.replace() it so a player never fetches a
# half-written feed.
# HINT: feedgen is allowed, but hand-rolled XML is fine if it is simpler; pick
# one in task 7 and record the choice in PROGRESS.md.

from __future__ import annotations

from pathlib import Path


def format_title(
    slot_label: str, when, position: int, total: int, source_name: str, original_title: str
) -> str:
    """Return the prefixed item title, e.g. ``AM Fri 11/21 · 2/5 · Source — Title``."""
    raise NotImplementedError


def ordered_pubdates(base, count: int, step_seconds: int = 5) -> list:
    """Return ``count`` timestamps a few seconds apart that keep the lineup order in players."""
    raise NotImplementedError


def render_feed(items, feed_title: str, feed_url: str) -> bytes:
    """Render the RSS document for ``items`` and return it as UTF-8 bytes."""
    raise NotImplementedError


def write_feed(xml: bytes, out_path: Path) -> None:
    """Atomically write the feed bytes to ``out_path``."""
    raise NotImplementedError
