"""Fetch source feeds politely.

Scaffold only: stubs with docstrings, no logic yet (see TASKS.md task 3).

Rules: descriptive User-Agent, conditional GET (ETag / Last-Modified), and at
most one request per feed per run.
"""
# HINT: inject the httpx client (or use httpx.MockTransport) so tests never
# touch the network.
# HINT: a 304 is a success, not an error; return "not modified" and reuse nothing.

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FetchResult:
    """Outcome of one fetch: status, body (if any), new ETag and Last-Modified."""


def build_headers(user_agent: str, etag: str | None, last_modified: str | None) -> dict[str, str]:
    """Return request headers including User-Agent and any conditional GET validators."""
    raise NotImplementedError


def fetch_feed(
    client, url: str, user_agent: str, etag: str | None, last_modified: str | None
) -> FetchResult:
    """GET one feed with conditional headers and return a :class:`FetchResult`.

    Never raises for HTTP or network errors; failures are reported in the result
    so one bad feed cannot stop the run.
    """
    raise NotImplementedError


def fetch_all(client, sources, validators, user_agent: str) -> dict[str, FetchResult]:
    """Fetch every source exactly once and return results keyed by source id."""
    raise NotImplementedError
