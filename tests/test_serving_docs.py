# Copyright (c) 2026 Nick L
# SPDX-License-Identifier: MIT
"""Tests for docs/serving.md - serving documentation."""

import pathlib

import pytest

DOCS_DIR = pathlib.Path(__file__).parent.parent / "docs"
SERVING_DOC = DOCS_DIR / "serving.md"


@pytest.fixture
def serving_doc_content() -> str:
    """Read the serving documentation."""
    return SERVING_DOC.read_text()


class TestServingDocExists:
    """Verify the serving documentation file exists."""

    def test_serving_doc_exists(self) -> None:
        """docs/serving.md must exist."""
        assert SERVING_DOC.exists(), f"serving.md not found at {SERVING_DOC}"

    def test_serving_doc_not_empty(self, serving_doc_content: str) -> None:
        """docs/serving.md must have content."""
        assert len(serving_doc_content) > 200, "serving.md appears to be empty or too short"


class TestServingDocContent:
    """Verify the serving documentation has the required sections."""

    def test_has_tailscale_funnel_section(self, serving_doc_content: str) -> None:
        """Must document Tailscale Funnel setup."""
        assert "Tailscale Funnel" in serving_doc_content
        assert "tailscale funnel" in serving_doc_content.lower()

    def test_has_token_in_path_section(self, serving_doc_content: str) -> None:
        """Must explain the token-in-path layout."""
        assert "token" in serving_doc_content.lower()
        assert "feed.xml" in serving_doc_content.lower()

    def test_has_rotate_token_section(self, serving_doc_content: str) -> None:
        """Must document how to rotate the token."""
        content_lower = serving_doc_content.lower()
        assert "rotate" in content_lower or "rotation" in content_lower
        assert "token" in content_lower

    def test_has_cloudflare_comparison(self, serving_doc_content: str) -> None:
        """Must compare with Cloudflare options."""
        assert "Cloudflare" in serving_doc_content
        assert "Tunnel" in serving_doc_content or "R2" in serving_doc_content

    def test_has_comparison_table(self, serving_doc_content: str) -> None:
        """Must have a real feature comparison table (header + option rows)."""
        # Count actual table rows, not just stray pipe characters.
        table_rows = [line for line in serving_doc_content.splitlines() if line.count("|") >= 3]
        assert len(table_rows) >= 4, "expected a header, separator, and option rows"
        joined = "\n".join(table_rows)
        assert "Tailscale Funnel" in joined
        assert "Cloudflare" in joined

    def test_tailscale_commands_are_current(self, serving_doc_content: str) -> None:
        """Regression guard: the corrected Funnel commands, not the stale ones."""
        c = serving_doc_content
        # Correct current CLI.
        assert "tailscale funnel --bg" in c
        assert "tailscale funnel status" in c
        # Stale / wrong forms must stay gone.
        assert "funnel 8080 on" not in c
        assert ".zip.ts.net" not in c
        assert "http://<" not in c  # Funnel is HTTPS; no public http:// host

    def test_explains_why_token_needed(self, serving_doc_content: str) -> None:
        """Must explain why the token is needed (unguessable URL)."""
        content_lower = serving_doc_content.lower()
        assert "unguessable" in content_lower or "guess" in content_lower
        assert "password" in content_lower or "secret" in content_lower

    def test_has_cloudflare_r2_pages(self, serving_doc_content: str) -> None:
        """Must mention Cloudflare R2 and Pages as an option."""
        assert "R2" in serving_doc_content
        assert "Pages" in serving_doc_content


class TestServingDocInstructions:
    """Verify the documentation has actionable setup steps."""

    def test_has_setup_steps(self, serving_doc_content: str) -> None:
        """Must have numbered or step-by-step instructions."""
        # Look for numbered lists or clear step indicators
        steps = ["step", "setup", "configure", "install", "enable"]
        content_lower = serving_doc_content.lower()
        assert any(step in content_lower for step in steps)

    def test_has_troubleshooting_section(self, serving_doc_content: str) -> None:
        """Must have troubleshooting advice."""
        assert "troubleshoot" in serving_doc_content.lower()


class TestREADMELinksToServing:
    """Verify README.md links to the serving documentation."""

    def test_readme_links_to_serving(self) -> None:
        """README must link to docs/serving.md."""
        readme = pathlib.Path(__file__).parent.parent / "README.md"
        content = readme.read_text()
        assert "docs/serving.md" in content
        assert "serving" in content.lower()
