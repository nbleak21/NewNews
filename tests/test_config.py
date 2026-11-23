# Copyright (c) 2026 Nick L
# SPDX-License-Identifier: MIT
"""Tests for the config loader and schema validation (TASKS.md task 2).

Every test reads a fixture from ``tests/fixtures/``; nothing here touches the
network.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
import yaml

from commute_news.config import (
    Config,
    ConfigError,
    load_config,
    slot_for_time,
    validate_config,
)

FIXTURES = Path(__file__).parent / "fixtures"
FULL = FIXTURES / "config_full.yaml"
EMPTY = FIXTURES / "config_empty.yaml"

SOURCE_IDS = [
    "fox_news_rundown",
    "npr_news_now",
    "wsj_whats_news",
    "bbc_global_news",
    "morning_wire",
    "up_first",
    "the_daily",
]


def full_raw() -> dict:
    """The valid config mapping, parsed from the full fixture."""
    loaded = yaml.safe_load(FULL.read_text())
    assert isinstance(loaded, dict)
    return loaded


def test_full_fixture_loads() -> None:
    cfg = load_config(FULL)
    assert (cfg.min_minutes, cfg.target_minutes, cfg.max_minutes) == (20, 25, 30)
    assert cfg.freshness_hours == 2
    assert cfg.retain_hours == 3
    assert cfg.assumed_bitrate_kbps == 128
    assert cfg.max_per_source == 1
    assert cfg.timezone == "UTC"
    assert cfg.feed_title == "NewNews Commute"
    assert cfg.public_base_url == "https://machine.example.ts.net"
    assert cfg.schedule.days == "all"
    assert (cfg.schedule.first_run, cfg.schedule.last_run) == ("04:15", "18:15")
    assert cfg.schedule.minute == 15
    assert [s.id for s in cfg.sources] == SOURCE_IDS
    # the fixture mirrors the example: no `left` source in it (yet)
    assert {s.lean for s in cfg.sources} == {
        "center-left",
        "center",
        "right",
        "international",
    }
    assert [s.label for s in cfg.slots] == ["AM", "PM"]
    assert cfg.slots[0].name == "am"
    assert cfg.slots[0].start == "04:15"
    assert cfg.slots[0].end == "11:59"
    assert cfg.slots[0].sources == "all"
    fox = cfg.sources[0]
    assert (fox.lean, fox.priority) == ("right", 1)
    assert fox.feed_url.startswith("https://example.com/")


def test_empty_file_gives_defaults() -> None:
    cfg = load_config(EMPTY)
    assert cfg == Config()
    assert (cfg.min_minutes, cfg.target_minutes, cfg.max_minutes) == (20, 25, 30)
    assert cfg.freshness_hours == 2
    assert cfg.retain_hours == 3
    assert cfg.assumed_bitrate_kbps == 128
    assert cfg.ntfy_topic == ""
    assert cfg.sources == ()
    assert cfg.slots == ()


def test_missing_file_is_a_config_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        load_config(tmp_path / "nope.yaml")


def test_rejects_unknown_lean_tag() -> None:
    raw = full_raw()
    raw["sources"][0]["lean"] = "libertarian"
    with pytest.raises(ConfigError, match="lean"):
        validate_config(raw)


def test_rejects_duplicate_source_ids() -> None:
    raw = full_raw()
    raw["sources"][1]["id"] = raw["sources"][0]["id"]
    with pytest.raises(ConfigError, match="duplicate"):
        validate_config(raw)


def test_rejects_todo_verify_feed_url() -> None:
    raw = full_raw()
    raw["sources"][0]["feed_url"] = "TODO_VERIFY"
    with pytest.raises(ConfigError, match="TODO_VERIFY"):
        validate_config(raw)


def test_rejects_min_above_target() -> None:
    raw = full_raw()
    raw["min_minutes"] = 40  # > target_minutes 25
    with pytest.raises(ConfigError, match="min_minutes"):
        validate_config(raw)


def test_rejects_target_above_max() -> None:
    raw = full_raw()
    raw["max_minutes"] = 10  # < target_minutes 25
    with pytest.raises(ConfigError, match="max_minutes"):
        validate_config(raw)


def test_rejects_retain_hours_below_freshness_hours() -> None:
    raw = full_raw()
    raw["freshness_hours"] = 4  # > retain_hours 3
    with pytest.raises(ConfigError, match="freshness_hour"):
        validate_config(raw)


def test_retain_hours_value_is_honored() -> None:
    # Regression: the loader used to read the singular key "retain_hour", so a
    # config that set the documented plural "retain_hours" was silently ignored
    # and retention stayed at the default 3. The configured value must be used.
    raw = full_raw()
    raw["retain_hours"] = 6
    assert validate_config(raw).retain_hours == 6


def test_rejects_unknown_or_misspelled_key() -> None:
    # The singular "retain_hour" is the exact typo that used to pass silently;
    # unknown top-level keys are now rejected so it (and future typos) cannot.
    raw = full_raw()
    raw["retain_hour"] = 9
    with pytest.raises(ConfigError, match="unknown config key"):
        validate_config(raw)
    raw2 = full_raw()
    raw2["totally_bogus"] = 1
    with pytest.raises(ConfigError, match="unknown config key"):
        validate_config(raw2)


@pytest.mark.parametrize("bad", [0, -1, -128])
def test_rejects_non_positive_assumed_bitrate(bad: int) -> None:
    raw = full_raw()
    raw["assumed_bitrate_kbps"] = bad
    with pytest.raises(ConfigError, match="assumed_bitrate_kbps"):
        validate_config(raw)


def test_rejects_slot_naming_unknown_source() -> None:
    raw = full_raw()
    raw["slots"]["am"]["sources"] = ["not_a_known_source"]
    with pytest.raises(ConfigError, match="not_a_known_source"):
        validate_config(raw)


def test_slot_for_time_picks_the_containing_slot() -> None:
    cfg = load_config(FULL)
    assert slot_for_time(cfg, datetime(2026, 11, 21, 4, 15)).label == "AM"
    assert slot_for_time(cfg, datetime(2026, 11, 21, 11, 59)).label == "AM"
    assert slot_for_time(cfg, datetime(2026, 11, 21, 13, 0)).label == "PM"
    assert slot_for_time(cfg, datetime(2026, 11, 21, 3, 0)) is None
    assert slot_for_time(cfg, datetime(2026, 11, 21, 19, 0)) is None


def test_slot_boundaries_and_handoff() -> None:
    cfg = load_config(FULL)
    # PM slot (12:00-18:15) is inclusive on both ends.
    assert slot_for_time(cfg, datetime(2026, 11, 21, 12, 0)).label == "PM"
    assert slot_for_time(cfg, datetime(2026, 11, 21, 18, 15)).label == "PM"
    # One minute past the PM end: no slot.
    assert slot_for_time(cfg, datetime(2026, 11, 21, 18, 16)) is None
    # AM->PM handoff is seamless: 11:59 is AM, 12:00 is PM.
    assert slot_for_time(cfg, datetime(2026, 11, 21, 11, 59)).label == "AM"
