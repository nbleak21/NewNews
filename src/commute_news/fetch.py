# Copyright (c) 2026 Nick L
# SPDX-License-Identifier: MIT
"""Fetch source feeds politely: one conditional GET per feed per run.

Hard rules (AGENTS.md): descriptive ``User-Agent``, conditional GET with
``If-None-Match`` / ``If-Modified-Since``, each feed fetched at most once per
run, and network / HTTP failures are *returned* (as a :class:`FetchResult`
with an ``error``) rather than raised, so one bad feed cannot stop the run.
"""
# HINT: the httpx client is injected, so tests pass httpx.MockTransport and
# never touch the network.
# HINT: a 304 is a success, not an error: `not_modified` is True, `body` is
# None and the caller reuses the feed XML it already has.

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any

import httpx

from .config import DEFAULT_USER_AGENT

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS: float = 15.0

ValidatorPair = tuple[str | None, str | None]
ValidatorMap = Mapping[str, ValidatorPair]
ValidatorLookup = Callable[[str], ValidatorPair]


@dataclass(frozen=True)
class FetchResult:
    """Outcome of one fetch: status, body (if any), new ETag and Last-Modified.

    ``status`` is 0 when the request failed before a response arrived (DNS,
    timeout, ...). ``error`` is set for every failure and is never raised.
    """

    url: str
    status: int = 0
    body: bytes | None = None
    etag: str | None = None
    last_modified: str | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        """True when the fetch succeeded (200 with a body, or 304 revalidated)."""
        return self.error is None

    @property
    def not_modified(self) -> bool:
        """True when the server answered 304: reuse the previously stored feed."""
        return self.error is None and self.status == 304


def build_client(
    transport: httpx.BaseTransport | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> httpx.Client:
    """Return an HTTP client with a bounded timeout and redirect following.

    ``transport`` is injectable so tests can pass ``httpx.MockTransport``.
    """
    return httpx.Client(transport=transport, timeout=timeout, follow_redirects=True)


def build_headers(
    user_agent: str,
    etag: str | None = None,
    last_modified: str | None = None,
) -> dict[str, str]:
    """Return request headers: always the User-Agent, plus any conditional GET
    validators (``If-None-Match`` / ``If-Modified-Since``)."""
    headers = {"User-Agent": user_agent}
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified
    return headers


def fetch_feed(
    client: httpx.Client,
    url: str,
    user_agent: str,
    etag: str | None = None,
    last_modified: str | None = None,
) -> FetchResult:
    """GET one feed with conditional headers and return a :class:`FetchResult`.

    Never raises for HTTP or network errors; failures are reported in the
    result so one bad feed cannot stop the run.
    """
    headers = build_headers(user_agent, etag, last_modified)
    try:
        response = client.get(url, headers=headers)
    except httpx.HTTPError as exc:
        logger.warning("fetch failed for %s: %s", url, exc)
        return FetchResult(url=url, error=f"{type(exc).__name__}: {exc}")
    return _summarize(url, response, etag, last_modified)


def fetch_all(
    client: httpx.Client,
    sources: Iterable[Any],
    validators: ValidatorMap | Callable[[str], ValidatorPair] | None = None,
    user_agent: str = DEFAULT_USER_AGENT,
) -> dict[str, FetchResult]:
    """Fetch every source at most once, returning results keyed by source id.

    ``sources`` are the config ``Source`` objects (``.id`` / ``.feed_url``).
    ``validators`` maps a source id to its stored ``(etag, last_modified)``,
    or is a callable taking the source id; ``None`` skips validation.
    Sources that share a URL produce exactly one request.
    """
    results: dict[str, FetchResult] = {}
    by_url: dict[str, FetchResult] = {}
    for source in sources:
        url = source.feed_url
        result = by_url.get(url)
        if result is None:
            etag, last_modified = _validators_for(validators, source.id)
            result = fetch_feed(client, url, user_agent, etag, last_modified)
            by_url[url] = result
            logger.debug("fetch %s -> %s", url, result.status or result.error)
        results[source.id] = result
    return results


# --- helpers (private) -----------------------------------------------------


def _summarize(
    url: str,
    response: httpx.Response,
    previous_etag: str | None,
    previous_last_modified: str | None,
) -> FetchResult:
    """Turn an HTTP response into a :class:`FetchResult`.

    304 keeps the stored validators (the server may not echo them), 200 takes
    whatever the server just sent, and everything else is an error.
    """
    status = response.status_code
    if status == 304:  # NOT_MODIFIED
        return FetchResult(
            url=url,
            status=status,
            etag=response.headers.get("ETag") or previous_etag,
            last_modified=response.headers.get("Last-Modified") or previous_last_modified,
        )
    if status == 200:  # OK
        return FetchResult(
            url=url,
            status=status,
            body=response.content,
            etag=response.headers.get("ETag"),
            last_modified=response.headers.get("Last-Modified"),
        )
    logger.warning("unexpected status %s from %s", status, url)
    return FetchResult(url=url, status=status, error=f"HTTP {status} for {url}")


def _validators_for(
    validators: ValidatorMap | Callable[[str], ValidatorPair] | None,
    source_id: str,
) -> ValidatorPair:
    """Return ``(etag, last_modified)`` for a source, or ``(None, None)``."""
    if validators is None:
        return (None, None)
    if callable(validators):
        found = validators(source_id)
    else:
        found = validators.get(source_id)
    if not found:
        return (None, None)
    etag, last_modified = found
    return (etag, last_modified)
