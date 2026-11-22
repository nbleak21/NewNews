"""Command line entry point: ``commute-news``.

``commute-news build`` runs one build; ``--dry-run`` prints the lineup and
total minutes and writes nothing. The build itself (fetch, parse, select,
write) is filled in by the tasks in TASKS.md.
"""
# HINT: use logging, not print (the dry-run lineup is the one deliberate stdout output).
# HINT: return an int exit code from main() so launchd and run.sh can see failures.

from __future__ import annotations

import argparse
import logging

#: Where ``--config`` points when the flag is not given.
DEFAULT_CONFIG = "config/sources.yaml"

#: Log level for the one place the CLI configures logging.
LOG_LEVEL = "INFO"

#: Log format: level, logger name and message (the logger name says the file).
LOG_FORMAT = "%(levelname)s %(name)s: %(message)s"


def build_parser() -> argparse.ArgumentParser:
    """Return the argparse parser for the ``commute-news`` command.

    The only subcommand today is ``build``; the options belong to it, so
    ``commute-news build --dry-run`` works and a bare ``commute-news`` is a
    usage error rather than a silent no-op.
    """
    parser = argparse.ArgumentParser(
        prog="commute-news",
        description="Build one private commute podcast feed (links only).",
    )
    subparsers = parser.add_subparsers(dest="command", required=True, metavar="command")
    build = subparsers.add_parser(
        "build",
        help="run one build (writes build/<token>/feed.xml)",
        description="Fetch the sources, pick a lineup and write the feed.",
    )
    build.add_argument(
        "--config",
        default=DEFAULT_CONFIG,
        metavar="PATH",
        help=f"YAML config to load (default: {DEFAULT_CONFIG})",
    )
    build.add_argument(
        "--dry-run",
        action="store_true",
        help="print the lineup and total minutes, write nothing",
    )
    return parser


def run_build(config_path: str, dry_run: bool) -> int:
    """Fetch, parse, select and (unless ``dry_run``) write the feed. Return an exit code."""
    raise NotImplementedError


def notify_failure(topic: str | None, message: str) -> None:
    """Send an ntfy.sh alert if a topic is configured; do nothing otherwise."""
    raise NotImplementedError


def main(argv: list[str] | None = None) -> int:
    """Parse arguments, configure logging and dispatch. Return the process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(level=LOG_LEVEL, format=LOG_FORMAT)
    if args.command != "build":  # pragma: no cover - argparse enforces this
        parser.error(f"unknown command {args.command!r}")
    return run_build(config_path=args.config, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
