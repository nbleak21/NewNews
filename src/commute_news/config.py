"""Load and validate the YAML configuration."""
# HINT: keep every default in ONE place (the dataclasses below) so the rule
# "every config value has a default" is checkable by reading this file.
# HINT: prefer frozen dataclasses; pure functions are easier to test.

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import yaml

ALLOWED_LEANS: frozenset[str] = frozenset(
    {"left", "center-left", "center", "right", "international"}
)
DEFAULT_USER_AGENT = "NewNews/0.1 (personal podcast aggregator)"


@dataclass(frozen=True)
class Source:
    """One podcast source: id, display name, lean tag, priority and feed URL."""

    id: str
    name: str
    lean: str
    priority: int
    feed_url: str


@dataclass(frozen=True)
class Slot:
    """A time-of-day slot (am/pm): label, start/end times and allowed sources.

    ``sources`` is the string ``"all"`` (every configured source) or an
    explicit tuple of source ids.
    """

    name: str
    label: str
    start: str  # "HH:MM", inclusive
    end: str  # "HH:MM", inclusive
    sources: tuple[str, ...] | str = "all"


@dataclass(frozen=True)
class Schedule:
    """When launchd fires a run: hourly, all days, within this window."""

    days: str = "all"
    first_run: str = "04:15"
    last_run: str = "18:15"
    minute: int = 15


@dataclass(frozen=True)
class Config:
    """Whole-app settings plus the lists of sources and slots."""

    target_minutes: int = 25
    min_minutes: int = 20
    max_minutes: int = 30
    freshness_hours: int = 2
    max_per_source: int = 1
    assumed_bitrate_kbps: int = 128
    feed_title: str = "NewNews Commute"
    public_base_url: str = ""
    retain_hours: int = 3
    ntfy_topic: str = ""
    user_agent: str = DEFAULT_USER_AGENT
    timezone: str = "America/Chicago"
    schedule: Schedule = field(default_factory=Schedule)
    slots: tuple[Slot, ...] = ()
    sources: tuple[Source, ...] = ()


class ConfigError(ValueError):
    """Raised when the configuration file is missing, malformed or invalid."""


def load_config(path: Path) -> Config:
    """Read the YAML file at ``path`` and return a validated :class:`Config`.

    Missing keys fall back to defaults. Raises :class:`ConfigError` on problems.
    """
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:  # missing file, permission, ...
        raise ConfigError(f"cannot read {path}: {exc}") from exc
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path} is not valid YAML: {exc}") from exc
    if raw is None:  # an empty file is an empty (all defaults) config
        raw = {}
    if not isinstance(raw, dict):
        raise ConfigError(f"{path} must contain a YAML mapping")
    return validate_config(raw)


#: Every recognised top-level config key. Anything else is treated as a typo and
#: rejected -- this is what catches e.g. ``retain_hour`` for ``retain_hours``.
_KNOWN_KEYS = frozenset(
    {
        "target_minutes",
        "min_minutes",
        "max_minutes",
        "freshness_hours",
        "max_per_source",
        "assumed_bitrate_kbps",
        "feed_title",
        "public_base_url",
        "retain_hours",
        "ntfy_topic",
        "user_agent",
        "timezone",
        "schedule",
        "slots",
        "sources",
    }
)


def validate_config(raw: dict) -> Config:
    """Validate a parsed YAML mapping and build a :class:`Config`.

    Must reject: unknown lean tags, duplicate source ids, ``TODO_VERIFY`` feed
    URLs, min/target/max minutes out of order, ``retain_hours`` below
    ``freshness_hours``, a non-positive ``assumed_bitrate_kbps``, slots that
    name unknown sources, and any unrecognised top-level key.
    """
    if not isinstance(raw, dict):
        raise ConfigError("config must be a mapping")

    unknown = set(raw) - _KNOWN_KEYS
    if unknown:
        raise ConfigError(
            f"unknown config key(s): {', '.join(sorted(unknown))}. "
            "Check spelling (e.g. retain_hours, not retain_hour)."
        )

    min_minutes = _as_int(raw, "min_minutes", 20)
    target_minutes = _as_int(raw, "target_minutes", 25)
    max_minutes = _as_int(raw, "max_minutes", 30)
    if not min_minutes <= target_minutes <= max_minutes:
        raise ConfigError(
            "minutes out of order: require min_minutes <= target_minutes <= "
            f"max_minutes, got min_minutes={min_minutes} "
            f"target_minutes={target_minutes} max_minutes={max_minutes}"
        )

    freshness_hours = _as_int(raw, "freshness_hours", 2)
    retain_hours = _as_int(raw, "retain_hours", 3)
    if retain_hours < freshness_hours:
        raise ConfigError(
            f"retain_hours ({retain_hours}) must be >= freshness_hours ({freshness_hours})"
        )

    bitrate = _as_int(raw, "assumed_bitrate_kbps", 128)
    if bitrate <= 0:
        raise ConfigError(f"assumed_bitrate_kbps must be > 0, got {bitrate}")

    sources = _parse_sources(raw.get("sources"))
    source_ids = {source.id for source in sources}
    slots = _parse_slots(raw.get("slots"), source_ids)

    return Config(
        target_minutes=target_minutes,
        min_minutes=min_minutes,
        max_minutes=max_minutes,
        freshness_hours=freshness_hours,
        max_per_source=_as_int(raw, "max_per_source", 1),
        assumed_bitrate_kbps=bitrate,
        feed_title=_as_str(raw, "feed_title", "NewNews Commute"),
        public_base_url=_as_str(raw, "public_base_url", ""),
        retain_hours=retain_hours,
        ntfy_topic=_as_str(raw, "ntfy_topic", ""),
        user_agent=_as_str(raw, "user_agent", DEFAULT_USER_AGENT),
        timezone=_as_str(raw, "timezone", "America/Chicago"),
        schedule=_parse_schedule(raw.get("schedule")),
        slots=slots,
        sources=sources,
    )


def slot_for_time(config: Config, now: datetime) -> Slot | None:
    """Return the slot whose window contains the local time ``now``.

    Returns ``None`` when no slot covers that time of day.
    """
    minute_of_day = now.hour * 60 + now.minute
    for slot in config.slots:
        if _minutes_of_day(slot.start) <= minute_of_day <= _minutes_of_day(slot.end):
            return slot
    return None


# --- helpers (private) -----------------------------------------------------


def _as_int(raw: dict, key: str, default: int) -> int:
    value = raw.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{key} must be an integer, got {value!r}")
    return value


def _as_str(raw: dict, key: str, default: str) -> str:
    value = raw.get(key, default)
    if not isinstance(value, str):
        raise ConfigError(f"{key} must be a string, got {value!r}")
    return value


def _minutes_of_day(hhmm: str) -> int:
    """``"HH:MM"`` to minutes after midnight. Pure; raises on bad input."""
    hour_text, _, minute_text = str(hhmm).partition(":")
    try:
        hour = int(hour_text)
        minute = int(minute_text)
    except ValueError as exc:
        raise ConfigError(f"bad time {hhmm!r}, expected HH:MM") from exc
    if not (0 <= hour < 24 and 0 <= minute < 60):
        raise ConfigError(f"bad time {hhmm!r}, expected HH:MM")
    return hour * 60 + minute


def _parse_hhmm(value: object, where: str) -> str:
    """Validate an ``HH:MM`` string and return it unchanged."""
    if not isinstance(value, str):
        raise ConfigError(f"{where} must be a string, got {value!r}")
    _minutes_of_day(value)  # raises ConfigError when malformed
    return value


def _parse_sources(value: object) -> tuple[Source, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ConfigError("sources must be a list")
    seen: set[str] = set()
    sources: list[Source] = []
    for item in value:
        if not isinstance(item, dict):
            raise ConfigError(f"each source must be a mapping, got {item!r}")
        source_id = item.get("id")
        if not isinstance(source_id, str) or not source_id:
            raise ConfigError(f"source is missing a string id: {item!r}")
        if source_id in seen:
            raise ConfigError(f"duplicate source id {source_id!r}")
        seen.add(source_id)

        lean = item.get("lean")
        if not isinstance(lean, str) or lean not in ALLOWED_LEANS:
            raise ConfigError(
                f"source {source_id!r} has unknown lean {lean!r}; allowed: {sorted(ALLOWED_LEANS)}"
            )

        feed_url = item.get("feed_url")
        if not isinstance(feed_url, str) or not feed_url:
            raise ConfigError(f"source {source_id!r} is missing a feed_url")
        if "TODO_VERIFY" in feed_url:
            raise ConfigError(f"source {source_id!r} still has TODO_VERIFY as feed_url")

        priority = item.get("priority", 1)
        if isinstance(priority, bool) or not isinstance(priority, int):
            raise ConfigError(f"source {source_id!r} priority must be an integer, got {priority!r}")
        sources.append(
            Source(
                id=source_id,
                name=str(item.get("name", source_id)),
                lean=lean,
                priority=priority,
                feed_url=feed_url,
            )
        )
    return tuple(sources)


def _parse_slots(value: object, source_ids: set[str]) -> tuple[Slot, ...]:
    if value is None:
        return ()
    if not isinstance(value, dict):
        raise ConfigError("slots must be a mapping of name -> slot")
    slots: list[Slot] = []
    for name, spec in value.items():
        if not isinstance(spec, dict):
            raise ConfigError(f"slot {name!r} must be a mapping")
        where = f"slot {name!r}"
        allowed = spec.get("sources", "all")
        if not (allowed == "all" or isinstance(allowed, list)):
            raise ConfigError(f"{where} sources must be 'all' or a list of source ids")
        if isinstance(allowed, list):
            unknown = [s for s in allowed if not isinstance(s, str) or s not in source_ids]
            if unknown:
                names = ", ".join(repr(s) for s in unknown)
                raise ConfigError(f"{where} names unknown source(s): {names}")
            allowed = tuple(allowed)
        label = spec.get("label")
        if label is None:
            label = str(name).upper()
        slots.append(
            Slot(
                name=str(name),
                label=str(label),
                start=_parse_hhmm(spec.get("start", "00:00"), f"{where} start"),
                end=_parse_hhmm(spec.get("end", "23:59"), f"{where} end"),
                sources=allowed,
            )
        )
    return tuple(slots)


def _parse_schedule(value: object) -> Schedule:
    if value is None:
        return Schedule()
    if not isinstance(value, dict):
        raise ConfigError("schedule must be a mapping")
    minute = value.get("minute", 15)
    if isinstance(minute, bool) or not isinstance(minute, int):
        raise ConfigError(f"schedule.minute must be an integer, got {minute!r}")
    return Schedule(
        days=str(value.get("days", "all")),
        first_run=_parse_hhmm(value.get("first_run", "04:15"), "schedule.first_run"),
        last_run=_parse_hhmm(value.get("last_run", "18:15"), "schedule.last_run"),
        minute=minute,
    )
