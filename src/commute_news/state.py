"""SQLite state: which episodes were already used, plus HTTP validators.

One file (``state/commute.db`` by convention) holds two tables:

``sources``
    One row per configured source: the stored ``ETag`` and ``Last-Modified``
    validators for conditional GET.
``episodes``
    One row per episode that was placed into the feed. It is both the
    "already used" set and the items the retained feed is rebuilt from;
    ``retain_hours`` (the only retention setting) decides how long rows stay.

Timestamps are stored as UTC epoch seconds (REAL) so comparisons in SQL are
plain numbers; the public helpers accept and return aware ``datetime`` objects.
"""
# HINT: tests should use ":memory:" or pytest's tmp_path, never the real state/ file.
# HINT: stdlib sqlite3 is enough; no ORM needed.

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .parse import Episode

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    source_id   TEXT PRIMARY KEY,
    etag        TEXT,
    last_modified TEXT
);

CREATE TABLE IF NOT EXISTS episodes (
    guid              TEXT PRIMARY KEY,
    source_id         TEXT NOT NULL,
    title             TEXT NOT NULL,
    published         REAL NOT NULL,
    enclosure_url     TEXT NOT NULL,
    enclosure_type    TEXT,
    enclosure_length  INTEGER NOT NULL DEFAULT 0,
    duration          INTEGER NOT NULL,
    duration_estimated INTEGER NOT NULL DEFAULT 0,
    slot_label        TEXT NOT NULL,
    added_at          REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_episodes_added_at ON episodes (added_at);
"""

_ITEM_COLUMNS = (
    "guid, source_id, title, published, enclosure_url, enclosure_type, "
    "enclosure_length, duration, duration_estimated, slot_label, added_at"
)


def connect(path: Path) -> sqlite3.Connection:
    """Open (creating if needed) the SQLite database and ensure the schema exists.

    Missing parent directories are created. The caller owns the connection.
    """
    file_path = Path(path)
    if str(file_path) != ":memory:":
        file_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(file_path))
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


# --- HTTP validators (per source) ------------------------------------------


def get_validators(conn: sqlite3.Connection, source_id: str) -> tuple[str | None, str | None]:
    """Return the stored ``(etag, last_modified)`` for a source.

    Unknown sources give ``(None, None)``.
    """
    row = conn.execute(
        "SELECT etag, last_modified FROM sources WHERE source_id = ?", (source_id,)
    ).fetchone()
    if row is None:
        return (None, None)
    return (row["etag"], row["last_modified"])


def save_validators(
    conn: sqlite3.Connection,
    source_id: str,
    etag: str | None = None,
    last_modified: str | None = None,
) -> None:
    """Store the latest ETag and Last-Modified for a source, replacing any old pair."""
    conn.execute(
        """
        INSERT INTO sources (source_id, etag, last_modified)
        VALUES (?, ?, ?)
        ON CONFLICT (source_id) DO UPDATE SET
            etag = excluded.etag,
            last_modified = excluded.last_modified
        """,
        (source_id, etag, last_modified),
    )
    conn.commit()
    logger.debug(
        "saved validators for %s: etag=%r last_modified=%r", source_id, etag, last_modified
    )


# --- used episodes / retained items ----------------------------------------


def used_guids(conn: sqlite3.Connection) -> set[str]:
    """Return the guids of every episode already placed in the feed."""
    rows = conn.execute("SELECT guid FROM episodes").fetchall()
    return {row["guid"] for row in rows}


def mark_used(
    conn: sqlite3.Connection,
    episodes: Iterable[Episode],
    slot_label: str,
    built_at: datetime,
) -> None:
    """Record that these episodes went into the feed in this run.

    Re-marking a guid updates its row (the newest run wins).
    """
    added_at = _to_epoch(built_at)
    rows = [
        (
            episode.guid,
            episode.source_id,
            episode.title,
            _to_epoch(episode.published),
            episode.enclosure_url,
            episode.enclosure_type,
            int(episode.enclosure_length or 0),
            int(episode.duration),
            1 if episode.duration_estimated else 0,
            slot_label,
            added_at,
        )
        for episode in episodes
    ]
    if not rows:
        return
    placeholders = ", ".join("?" for _ in range(len(rows[0])))
    conn.executemany(
        f"""
        INSERT INTO episodes ({_ITEM_COLUMNS})
        VALUES ({placeholders})
        ON CONFLICT (guid) DO UPDATE SET
            source_id = excluded.source_id,
            title = excluded.title,
            published = excluded.published,
            enclosure_url = excluded.enclosure_url,
            enclosure_type = excluded.enclosure_type,
            enclosure_length = excluded.enclosure_length,
            duration = excluded.duration,
            duration_estimated = excluded.duration_estimated,
            slot_label = excluded.slot_label,
            added_at = excluded.added_at
        """,
        rows,
    )
    conn.commit()
    logger.debug("marked %d episode(s) used for slot %r", len(rows), slot_label)


def recent_items(conn: sqlite3.Connection, since: datetime) -> list[dict[str, Any]]:
    """Feed items added at or after ``since``, newest first.

    These are the rows the retained feed is rebuilt from; the caller applies
    ``retain_hours`` by passing ``since = now - retain_hours``.
    """
    rows = conn.execute(
        f"""
        SELECT {_ITEM_COLUMNS} FROM episodes
        WHERE added_at >= ?
        ORDER BY added_at DESC, guid
        """,
        (_to_epoch(since),),
    ).fetchall()
    return [_row_to_item(row) for row in rows]


def prune(conn: sqlite3.Connection, older_than: datetime) -> int:
    """Delete state rows older than ``older_than`` and return how many were removed.

    ``older_than`` is ``now - retain_hours``; ``retain_hours`` is the only
    retention setting. Rows exactly at the cutoff are kept ("older than" is
    strict), so a row is only dropped once it is provably past retention.
    """
    cursor = conn.execute("DELETE FROM episodes WHERE added_at < ?", (_to_epoch(older_than),))
    removed = cursor.rowcount
    conn.commit()
    logger.debug("pruned %d row(s) older than %s", removed, older_than.isoformat())
    return int(removed)


# --- helpers (private) -----------------------------------------------------


def _to_epoch(value: datetime) -> float:
    """UTC epoch seconds for ``value``; naive datetimes are read as UTC."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.timestamp()


def _from_epoch(value: float) -> datetime:
    return datetime.fromtimestamp(float(value), tz=UTC)


def _row_to_item(row: sqlite3.Row | Sequence[Any]) -> dict[str, Any]:
    return {
        "guid": row["guid"],
        "source_id": row["source_id"],
        "title": row["title"],
        "published": _from_epoch(row["published"]),
        "enclosure_url": row["enclosure_url"],
        "enclosure_type": row["enclosure_type"],
        "enclosure_length": row["enclosure_length"],
        "duration": row["duration"],
        "duration_estimated": bool(row["duration_estimated"]),
        "slot_label": row["slot_label"],
        "added_at": _from_epoch(row["added_at"]),
    }
