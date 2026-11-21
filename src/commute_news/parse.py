"""Turn raw feed XML into Episode records.

Scaffold only: stubs with docstrings, no logic yet (see TASKS.md task 4).

Duration rules (decided, see "Decisions" in AGENTS.md):

1. Prefer ``<itunes:duration>``.
2. If it is missing, ESTIMATE from the enclosure ``length`` (bytes)::

       seconds ~= length_bytes * 8 / (assumed_bitrate_kbps * 1000)

   ``assumed_bitrate_kbps`` is a config value (default 128). This is an
   approximation: real bitrates vary and some feeds report a wrong length.
3. If ``length`` is also missing or zero, skip the episode.

Never download audio to measure it.
"""
# HINT: itunes:duration appears as "1234", "20:34" or "1:02:03". Test all three.
# HINT: enclosure `length` is BYTES, not seconds. At 128 kbps, 1 MB is roughly
# 62.5 seconds, so a 5 MB file estimates to a little over 5 minutes.
# HINT: keep "duration was estimated" visible (e.g. a flag on Episode) so the
# dry run can show which lineup minutes are approximate.

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Episode:
    """One episode: source id, guid, title, published time, enclosure URL/type/length, duration."""


def parse_duration(value: str | None) -> int | None:
    """Parse an ``itunes:duration`` string into whole seconds, or ``None`` if unusable."""
    raise NotImplementedError


DEFAULT_ASSUMED_BITRATE_KBPS = 128


def estimate_duration_from_length(
    length_bytes: int | None, assumed_bitrate_kbps: int = DEFAULT_ASSUMED_BITRATE_KBPS
) -> int | None:
    """Approximate seconds from the enclosure byte length.

    ``seconds ~= length_bytes * 8 / (assumed_bitrate_kbps * 1000)``. Returns
    ``None`` when ``length_bytes`` is missing or zero, so the caller skips the episode.
    """
    raise NotImplementedError


def parse_feed(
    source_id: str, xml: bytes, assumed_bitrate_kbps: int = DEFAULT_ASSUMED_BITRATE_KBPS
) -> list[Episode]:
    """Parse feed XML into episodes, newest first.

    Skips episodes with no audio enclosure, and episodes with neither an
    ``itunes:duration`` nor a non-zero enclosure ``length``.
    """
    raise NotImplementedError
