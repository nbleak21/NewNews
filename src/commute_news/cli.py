"""Command line entry point: ``commute-news``.

Scaffold only: stubs with docstrings, no logic yet (see TASKS.md task 8).

Planned commands:
    commute-news build            run once and write feed.xml
    commute-news build --dry-run  print the chosen lineup and total minutes, write nothing
"""
# HINT: use logging, not print (the dry-run lineup is the one deliberate stdout output).
# HINT: return an int exit code from main() so launchd and run.sh can see failures.

from __future__ import annotations


def build_parser():
    """Return the argparse parser for the ``commute-news`` command."""
    raise NotImplementedError


def run_build(config_path, dry_run: bool) -> int:
    """Fetch, parse, select and (unless ``dry_run``) write the feed. Return an exit code."""
    raise NotImplementedError


def notify_failure(topic: str | None, message: str) -> None:
    """Send an ntfy.sh alert if a topic is configured; do nothing otherwise."""
    raise NotImplementedError


def main(argv: list[str] | None = None) -> int:
    """Parse arguments, configure logging and dispatch. Return the process exit code."""
    raise NotImplementedError


if __name__ == "__main__":
    raise SystemExit(main())
