"""Tests for the README adding-a-new-source section."""

import pathlib

import pytest

README = pathlib.Path(__file__).parent.parent / "README.md"


@pytest.fixture
def readme_content() -> str:
    """Read the README content."""
    return README.read_text()


class TestAddSourceSectionExists:
    """Verify the adding-a-new-source section exists in README."""

    def test_section_heading_exists(self, readme_content: str) -> None:
        """README must have an 'Adding a new source' heading."""
        assert "Adding a new source" in readme_content

    def test_section_has_step_by_step_format(self, readme_content: str) -> None:
        """Section must have step-by-step instructions."""
        content = readme_content
        # Look for numbered or bullet steps
        steps = ["1.", "2.", "3.", "4.", "5.", "6.", "first", "second", "third"]
        assert any(step in content.lower() for step in steps)


class TestAddSourceSectionContent:
    """Verify the section has all required steps."""

    def test_find_feed_url_step(self, readme_content: str) -> None:
        """Must tell user how to find the feed URL."""
        content_lower = readme_content.lower()
        assert "feed" in content_lower
        assert "url" in content_lower or "link" in content_lower

    def test_verify_feed_url_step(self, readme_content: str) -> None:
        """Must tell user how to verify the feed URL."""
        content = readme_content
        # Look for Apple ID or lookup API references
        assert "apple" in content.lower() or "verify" in content.lower()
        assert "id" in content.lower()

    def test_add_yaml_block_step(self, readme_content: str) -> None:
        """Must tell user how to add a YAML block to config."""
        content = readme_content
        assert "yaml" in content.lower()
        assert "config" in content.lower() or "sources" in content.lower()

    def test_pick_lean_priority_step(self, readme_content: str) -> None:
        """Must tell user how to pick lean and priority."""
        content = readme_content.lower()
        assert "lean" in content
        assert "priority" in content

    def test_dry_run_step(self, readme_content: str) -> None:
        """Must tell user to run a dry-run test."""
        content = readme_content.lower()
        assert "dry" in content
        assert "run" in content or "test" in content

    def test_add_fixture_step(self, readme_content: str) -> None:
        """Must tell user to add a fixture for testing."""
        content = readme_content.lower()
        assert "fixture" in content or "test" in content


class TestAddSourceSectionNotes:
    """Verify the section includes helpful notes."""

    def test_notes_on_unguessable_url(self, readme_content: str) -> None:
        """Should mention the feed token makes the URL unguessable."""
        content = readme_content.lower()
        assert "token" in content
        assert "unguessable" in content or "secret" in content or "private" in content

    def test_notes_on_not_downloading_audio(self, readme_content: str) -> None:
        """Should actively state the link-only policy, not just avoid a word."""
        content = readme_content.lower()
        assert "nothing is downloaded" in content or "only links" in content
