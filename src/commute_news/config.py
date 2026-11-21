"""Load and validate the YAML configuration.

Scaffold only: stubs with docstrings, no logic yet (see TASKS.md task 2).
"""
# HINT: keep every default in ONE place (the dataclasses below) so the rule
# "every config value has a default" is checkable by reading this file.
# HINT: prefer frozen dataclasses; pure functions are easier to test.

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Source:
    """One podcast source: id, display name, lean tag, priority and feed URL."""


@dataclass(frozen=True)
class Slot:
    """A time-of-day slot (am/pm): label, start/end times and allowed source ids."""


@dataclass(frozen=True)
class Config:
    """Whole-app settings plus the lists of sources and slots."""


class ConfigError(ValueError):
    """Raised when the configuration file is missing, malformed or invalid."""


def load_config(path: Path) -> Config:
    """Read the YAML file at ``path`` and return a validated :class:`Config`.

    Missing keys fall back to defaults. Raises :class:`ConfigError` on problems.
    """
    raise NotImplementedError


def validate_config(raw: dict) -> Config:
    """Validate a parsed YAML mapping and build a :class:`Config`.

    Must reject: unknown lean tags, duplicate source ids, ``TODO_VERIFY`` feed
    URLs, min/target/max minutes out of order, and slots naming unknown sources.
    """
    raise NotImplementedError


def slot_for_time(config: Config, now) -> Slot | None:
    """Return the slot that contains local time ``now``, or ``None`` if outside all slots."""
    raise NotImplementedError
