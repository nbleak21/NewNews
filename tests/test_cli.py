"""Tests for the CLI argument parser (TASKS.md task 8a).

Only the parser is under test: ``main`` / ``run_build`` are deliberately not
called end to end yet (that is tasks 8b and 8c). Nothing here touches the
network.
"""

from __future__ import annotations

import argparse

import pytest

from commute_news.cli import build_parser


def parse(argv: list[str]) -> argparse.Namespace:
    """Parse one command line, exactly as a user would type it."""
    return build_parser().parse_args(argv)


def test_defaults_are_the_documented_ones() -> None:
    args = parse(["build"])
    assert args.command == "build"
    assert args.config == "config/sources.yaml"
    assert args.dry_run is False


def test_dry_run_flag_is_a_store_true() -> None:
    args = parse(["build", "--dry-run"])
    assert args.dry_run is True
    assert args.config == "config/sources.yaml"


def test_config_option_overrides_the_default() -> None:
    args = parse(["build", "--config", "other/sources.yaml"])
    assert args.config == "other/sources.yaml"
    assert args.dry_run is False


def test_config_and_dry_run_combine() -> None:
    args = parse(["build", "--config", "x.yaml", "--dry-run"])
    assert (args.config, args.dry_run) == ("x.yaml", True)


def test_build_subcommand_is_required() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args([])


def test_unknown_flag_is_rejected() -> None:
    with pytest.raises(SystemExit):
        parse(["build", "--no-such-flag"])
