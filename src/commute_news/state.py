"""SQLite state: which episodes were already used, plus HTTP validators.

Scaffold only: stubs with docstrings, no logic yet (see TASKS.md task 6).
The database file lives under ``state/`` (gitignored).
"""
# HINT: tests should use ":memory:" or pytest's tmp_path, never the real state/ file.
# HINT: stdlib sqlite3 is enough; no ORM needed.

from __future__ import annotations

from pathlib import Path


def connect(path: Path):
    """Open (creating if needed) the SQLite database and ensure the schema exists."""
    raise NotImplementedError


def get_validators(conn, source_id: str) -> tuple[str | None, str | None]:
    """Return the stored ``(etag, last_modified)`` for a source."""
    raise NotImplementedError


def save_validators(conn, source_id: str, etag: str | None, last_modified: str | None) -> None:
    """Store the latest ETag and Last-Modified for a source."""
    raise NotImplementedError


def used_guids(conn) -> set[str]:
    """Return the guids of every episode already placed in the feed."""
    raise NotImplementedError


def mark_used(conn, episodes, slot_label: str, built_at) -> None:
    """Record that these episodes went into the feed in this run."""
    raise NotImplementedError


def recent_items(conn, since):
    """Return feed items added at or after ``since``, for rebuilding the retained feed."""
    raise NotImplementedError


def prune(conn, older_than) -> int:
    """Delete state rows older than ``older_than`` and return how many were removed.

    ``older_than`` is ``now - retain_hours``; ``retain_hours`` is the only retention setting.
    """
    raise NotImplementedError
