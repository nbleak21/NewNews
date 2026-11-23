# Copyright (c) 2026 Nick L
# SPDX-License-Identifier: MIT
"""Tests for ntfy alerts (task 12).

Tests use httpx.MockTransport to avoid network access.
"""

from __future__ import annotations

import httpx


class TestNotifyFailure:
    """Test notify_failure with mocked HTTP."""

    def test_no_topic_does_nothing(self) -> None:
        """When topic is empty, no request is made and no error is raised."""
        from commute_news.cli import notify_failure

        # Should not raise, should not call HTTP
        notify_failure(topic=None, message="test")
        notify_failure(topic="", message="test")

    def test_post_happens_with_topic(self, httpx_mock) -> None:
        """When topic is set, a POST is sent to ntfy.sh."""
        from commute_news.cli import notify_failure

        topic = "newnews-alerts"
        message = "Build failed: test error"
        expected_url = f"https://ntfy.sh/{topic}"

        httpx_mock.add_response(
            method="POST",
            url=expected_url,
            status_code=200,
            content=b"OK",
        )

        notify_failure(topic=topic, message=message)

        # Verify the request was made
        assert len(httpx_mock.get_requests()) == 1
        request = httpx_mock.get_requests()[0]
        assert request.method == "POST"
        assert request.url == expected_url
        assert request.content.decode() == message

    def test_ntfy_outage_does_not_fail_run(self, httpx_mock) -> None:
        """When ntfy.sh is down, the function returns without raising."""
        from commute_news.cli import notify_failure

        topic = "newnews-alerts"
        message = "Test"

        # Simulate a connection error
        httpx_mock.add_exception(httpx.ConnectError("Connection refused"))

        # Should not raise
        notify_failure(topic=topic, message=message)

    def test_ntfy_returns_500_does_not_fail_run(self, httpx_mock) -> None:
        """When ntfy.sh returns 500, the function returns without raising."""
        from commute_news.cli import notify_failure

        topic = "newnews-alerts"
        message = "Test"

        httpx_mock.add_response(
            method="POST",
            url=f"https://ntfy.sh/{topic}",
            status_code=500,
            content=b"Internal Server Error",
        )

        # Should not raise
        notify_failure(topic=topic, message=message)

    def test_ntfy_returns_404_does_not_fail_run(self, httpx_mock) -> None:
        """When ntfy.sh returns 404 (unknown topic), the function returns without raising."""
        from commute_news.cli import notify_failure

        topic = "nonexistent-topic"
        message = "Test"

        httpx_mock.add_response(
            method="POST",
            url=f"https://ntfy.sh/{topic}",
            status_code=404,
            content=b"Not Found",
        )

        # Should not raise
        notify_failure(topic=topic, message=message)
