# Copyright (c) 2026 Nick L
# SPDX-License-Identifier: MIT
"""Skeleton tests: the project imports, the entry point is wired, and the
public module names exist.

These are the invariants of Task 1 (project skeleton and uv setup). They must
keep passing as the project grows: they only assert that the names are present
and importable, never that a function is unimplemented.
"""

from __future__ import annotations

import commute_news
from commute_news import cli, config


def test_package_exposes_nonempty_version() -> None:
    assert isinstance(commute_news.__version__, str)
    assert commute_news.__version__


def test_cli_entry_point_is_importable() -> None:
    assert callable(cli.main)


def test_config_api_names_exist() -> None:
    for name in ("load_config", "validate_config", "slot_for_time", "ConfigError"):
        assert hasattr(config, name), f"config.{name} missing from the skeleton"
