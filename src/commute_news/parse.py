"""Turn raw feed XML into Episode records.

Duration rules (decided, see "Decisions" in AGENTS.md):

1. Prefer ``<itunes:duration>``.
2. If it is missing, ESTIMATE from the enclosure ``length`` (bytes)::

       seconds ~= length_bytes * 8 / (assumed_bitrate_kbps * 1000)

   ``assumed_bitrate_kbps`` is a config value (default 128). This is an
   approximation: real bitrates vary and some feeds report a wrong length.
3. If ``length`` is also missing or zero, skip the episode.

Never download audio to measure it.
"""
# HINT: itunes:duration appears as "1234", "05:00" or "1:02:03". Test all three.
# HINT: enclosure `length` is BYTES, not seconds. At 128 kbps one second of
# audio is 16 000 bytes, so a 5 000 000 byte file estimates to 312 seconds.
# Check the formula in the tests, not this comment.
# HINT: keep "duration was estimated" visible (``duration_estimated``) so the
# dry run can show which lineup minutes are approximate.

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

import feedparser

logger = logging.getLogger(__name__)

DEFAULT_ASSUMED_BITRATE_KBPS = 128

# feedparser exposes <itunes:duration> under one of these keys, depending on
# how the source feed spells the namespace prefix.
_DURATION_KEYS = ("duration", "itunes_duration", "itunes:duration")


@dataclass(frozen=True)
class Episode:
    """One episode, as far as this app cares: who made it, when, and the link.

    ``duration`` is seconds. ``duration_estimated`` is True when it came from
    the byte-length approximation rather than ``<itunes:duration>``.
    """

    source_id: str
    guid: str
    title: str
    published: datetime
    enclosure_url: str
    enclosure_type: str | None
    enclosure_length: int
    duration: int
    duration_estimated: bool = False


def parse_duration(value: str | None) -> int | None:
    """Parse an ``itunes:duration`` string into whole seconds.

    Accepts plain seconds (``"1234"``), ``MM:SS`` (``"05:00"``) and
    ``HH:MM:SS`` (``"1:02:03"``). Returns ``None`` for anything unusable.
    """
    if value is None:
        return None
    parts = str(value).strip().split(":")
    try:
        numbers = [int(part) for part in parts]
    except ValueError:
        return None
    if not numbers or any(number < 0 for number in numbers):
        return None
    if len(numbers) == 1:
        return numbers[0]  # already seconds
    if len(numbers) == 2:
        minutes, seconds = numbers
        if seconds > 59:
            return None
        return minutes * 60 + seconds
    if len(numbers) > 3:
        return None
    hours, minutes, seconds = numbers
    if minutes > 59 or seconds > 59:
        return None
    return hours * 3600 + minutes * 60 + seconds


def estimate_duration_from_length(
    length_bytes: int | None, assumed_bitrate_kbps: int = DEFAULT_ASSUMED_BITRATE_KBPS
) -> int | None:
    """Approximate seconds from the enclosure byte length.

    ``seconds ~= length_bytes * 8 / (assumed_bitrate_kbps * 1000)``. Returns
    ``None`` when ``length_bytes`` is missing or zero, so the caller skips the episode.
    """
    if not length_bytes or length_bytes <= 0:
        return None
    if assumed_bitrate_kbps <= 0:
        raise ValueError(f"assumed_bitrate_kbps must be > 0, got {assumed_bitrate_kbps}")
    # Approximation: assumes a constant bitrate, so the whole file is
    # `length_bytes * 8` bits delivered at `assumed_bitrate_kbps` kbit/s.
    return int(length_bytes * 8 / (assumed_bitrate_kbps * 1000))


def parse_feed(
    source_id: str, xml: bytes, assumed_bitrate_kbps: int = DEFAULT_ASSUMED_BITRATE_KBPS
) -> list[Episode]:
    """Parse feed XML into episodes, newest first.

    Skips episodes with no audio enclosure, no parseable publication date, or
    neither an ``itunes:duration`` nor a non-zero enclosure ``length``.
    """
    parsed = feedparser.parse(xml)
    episodes: list[Episode] = []
    for entry in getattr(parsed, "entries", []) or []:
        episode = _build_episode(source_id, entry, assumed_bitrate_kbps)
        if episode is not None:
            episodes.append(episode)
    episodes.sort(key=lambda episode: episode.published, reverse=True)
    return episodes


def _build_episode(source_id: str, entry, assumed_bitrate_kbps: int) -> Episode | None:
    """One entry to an :class:`Episode`, or ``None`` when it must be skipped."""
    enclosure = _audio_enclosure(entry)
    if enclosure is None:
        logger.debug("skipping %r: no audio enclosure", _entry_title(entry))
        return None

    published = _published(entry)
    if published is None:
        logger.debug("skipping %r: missing or malformed date", _entry_title(entry))
        return None

    enclosure_url = _enclosure_url(enclosure)
    raw_duration = _raw_duration(entry)
    duration = parse_duration(raw_duration)
    estimated = duration is None
    if duration is None:
        duration = estimate_duration_from_length(_enclosure_length(enclosure), assumed_bitrate_kbps)
    if duration is None:
        logger.debug("skipping %r: no duration and no usable length", _entry_title(entry))
        return None

    return Episode(
        source_id=source_id,
        guid=str(entry.get("id") or enclosure_url),
        title=str(entry.get("title") or ""),
        published=published,
        enclosure_url=enclosure_url,
        enclosure_type=enclosure.get("type") or None,
        enclosure_length=_enclosure_length(enclosure) or 0,
        duration=duration,
        duration_estimated=estimated,
    )


def _entry_title(entry) -> str:
    return str(entry.get("title") or entry.get("id") or "<untitled>")


def _audio_enclosure(entry) -> dict | None:
    """First enclosure that points at audio, or ``None``.

    An enclosure that declares a type is kept only when it is ``audio/*`` (so an
    image or video enclosure is not mistaken for the episode). An enclosure with
    no declared type is accepted as a fallback, since some feeds omit it.
    """
    fallback = None
    for enclosure in entry.get("enclosures") or []:
        if not _enclosure_url(enclosure):
            continue
        etype = str(enclosure.get("type") or "")
        if etype.lower().startswith("audio/"):
            return enclosure
        if not etype and fallback is None:
            fallback = enclosure
    return fallback


def _enclosure_url(enclosure) -> str:
    return str(enclosure.get("href") or enclosure.get("url") or "") or ""


def _enclosure_length(enclosure) -> int:
    raw = enclosure.get("length")
    try:
        return int(str(raw))
    except (TypeError, ValueError):
        return 0


def _raw_duration(entry) -> str | None:
    for key in _DURATION_KEYS:
        value = entry.get(key)
        if value:
            return str(value)
    return None


def _published(entry) -> datetime | None:
    # Read a key only when it is really there: feedparser builds deprecated
    # temporary mappings (and warns) when a key has to be looked up by name.
    for key in ("published_parsed", "updated_parsed"):
        if key not in entry or not entry[key]:
            continue
        parsed_time = entry[key]
        return datetime(
            parsed_time.tm_year,
            parsed_time.tm_mon,
            parsed_time.tm_mday,
            parsed_time.tm_hour,
            parsed_time.tm_min,
            parsed_time.tm_sec,
            tzinfo=UTC,
        )
    return None
