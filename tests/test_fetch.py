"""Tests for the polite feed fetcher (TASKS.md task 3).

Every test drives ``httpx.MockTransport``, so nothing here touches the
network. The sample body is the saved fixture feed.
"""

from __future__ import annotations

from pathlib import Path

import httpx

from commute_news.config import Source
from commute_news.fetch import (
    DEFAULT_USER_AGENT,
    build_client,
    build_headers,
    fetch_all,
    fetch_feed,
)

FEED_URL = "https://feeds.example.test/sample.xml"
BODY = (Path(__file__).parent / "fixtures" / "feeds" / "sample_feed.xml").read_bytes()
UA = "NewNews-Test/1.0 (unit tests)"
ETAG = '"sample-etag-1"'
LAST_MODIFIED = "Thu, 19 Nov 2026 06:00:00 GMT"


def source(source_id: str, url: str = FEED_URL) -> Source:
    """A Source for the tests; the URL is a reserved .test host, never fetched."""
    return Source(id=source_id, name=source_id, lean="center", priority=1, feed_url=url)


def serve(handler) -> httpx.Client:
    """A client whose transport is the given handler (no network)."""
    return build_client(transport=httpx.MockTransport(handler))


# --- header contents -------------------------------------------------------


def test_build_headers_includes_user_agent_and_validators() -> None:
    headers = build_headers(UA, etag=ETAG, last_modified=LAST_MODIFIED)
    assert headers == {
        "User-Agent": UA,
        "If-None-Match": ETAG,
        "If-Modified-Since": LAST_MODIFIED,
    }


def test_build_headers_omits_missing_validators() -> None:
    assert build_headers(UA) == {"User-Agent": UA}
    assert build_headers(UA, etag=ETAG) == {
        "User-Agent": UA,
        "If-None-Match": ETAG,
    }
    assert build_headers(UA, last_modified=LAST_MODIFIED) == {
        "User-Agent": UA,
        "If-Modified-Since": LAST_MODIFIED,
    }


def test_request_sends_descriptive_user_agent() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=BODY)

    with serve(handler) as client:
        fetch_feed(client, FEED_URL, UA)
    assert len(seen) == 1
    assert seen[0].headers["User-Agent"] == UA
    assert "If-None-Match" not in seen[0].headers


def test_conditional_get_sends_stored_validators() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(304)

    with serve(handler) as client:
        fetch_feed(client, FEED_URL, UA, etag=ETAG, last_modified=LAST_MODIFIED)
    assert seen[0].headers["If-None-Match"] == ETAG
    assert seen[0].headers["If-Modified-Since"] == LAST_MODIFIED


# --- one response per case -------------------------------------------------


def test_200_returns_body_and_fresh_validators() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=BODY,
            headers={"ETag": '"new-etag"', "Last-Modified": LAST_MODIFIED},
        )

    with serve(handler) as client:
        result = fetch_feed(client, FEED_URL, UA)

    assert result.status == 200
    assert result.body == BODY
    assert result.etag == '"new-etag"'
    assert result.last_modified == LAST_MODIFIED
    assert result.error is None
    assert result.ok


def test_304_is_not_an_error_and_keeps_stored_validators() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(304)  # no validators echoed back

    with serve(handler) as client:
        result = fetch_feed(client, FEED_URL, UA, etag=ETAG, last_modified=LAST_MODIFIED)

    assert len(seen) == 1
    assert result.status == 304
    assert result.not_modified
    assert result.body is None
    assert result.error is None
    assert result.ok
    # the stored validators survive so the next run can revalidate
    assert result.etag == ETAG
    assert result.last_modified == LAST_MODIFIED


def test_404_is_returned_not_raised() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="no such feed")

    with serve(handler) as client:
        result = fetch_feed(client, FEED_URL, UA)

    assert result.status == 404
    assert result.body is None
    assert result.error is not None
    assert "404" in result.error
    assert not result.ok


def test_timeout_is_returned_not_raised() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("simulated timeout", request=request)

    with serve(handler) as client:
        result = fetch_feed(client, FEED_URL, UA)

    assert result.status == 0
    assert result.body is None
    assert result.error is not None
    assert "timeout" in result.error.lower()
    assert not result.ok


# --- one request per feed per run ------------------------------------------


def test_fetch_all_requests_each_url_exactly_once() -> None:
    counts: dict[str, int] = {}
    sources = (
        source("a", "https://feeds.example.test/a.xml"),
        source("b", "https://feeds.example.test/b.xml"),
        source("c", "https://feeds.example.test/c.xml"),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        counts[request.url.host + request.url.path] = (
            counts.get(request.url.host + request.url.path, 0) + 1
        )
        return httpx.Response(200, content=BODY)

    with serve(handler) as client:
        results = fetch_all(client, sources, None, UA)

    assert set(results) == {"a", "b", "c"}
    assert counts == {
        "feeds.example.test/a.xml": 1,
        "feeds.example.test/b.xml": 1,
        "feeds.example.test/c.xml": 1,
    }
    assert all(r.status == 200 for r in results.values())


def test_fetch_all_shares_one_request_for_a_shared_url() -> None:
    hits = {"n": 0}
    sources = (source("first"), source("second"))  # both use FEED_URL

    def handler(request: httpx.Request) -> httpx.Response:
        hits["n"] += 1
        return httpx.Response(200, content=BODY)

    with serve(handler) as client:
        results = fetch_all(client, sources, None, UA)

    assert hits["n"] == 1
    assert set(results) == {"first", "second"}
    assert results["second"].body == BODY


def test_fetch_all_passes_stored_validators_to_the_request() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(304)

    sources = (source("a"),)
    validators = {"a": (ETAG, LAST_MODIFIED)}

    with serve(handler) as client:
        results = fetch_all(client, sources, validators, UA)

    assert len(seen) == 1
    assert seen[0].headers["If-None-Match"] == ETAG
    assert seen[0].headers["If-Modified-Since"] == LAST_MODIFIED
    assert results["a"].not_modified
    assert results["a"].etag == ETAG
    assert results["a"].last_modified == LAST_MODIFIED


def test_default_user_agent_is_descriptive() -> None:
    assert "NewNews" in DEFAULT_USER_AGENT
    headers = build_headers(DEFAULT_USER_AGENT)
    assert headers["User-Agent"] == DEFAULT_USER_AGENT
