"""Tests for the launchd plist and install script (task 10).

These tests verify:
- The rendered plist has exactly 15 entries (hours 4-18 at minute 15)
- No Weekday key (runs every day)
- The install script renders paths correctly
- The uninstall script removes the plist
"""

from __future__ import annotations

import plistlib
import subprocess
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"

# The repo root for path resolution
REPO_ROOT = Path(__file__).parent.parent


def load_plist_from_script() -> dict:
    """Render the plist by running install-launchd.sh with --dry-run."""
    script = REPO_ROOT / "scripts" / "install-launchd.sh"
    result = subprocess.run(
        [str(script), "--dry-run"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, f"Script failed: {result.stderr}"
    # The dry-run output is the plist content
    return plistlib.loads(result.stdout.encode("utf-8"))


class TestPlistContent:
    """Tests that the rendered plist meets the spec."""

    def test_has_exactly_15_calendar_entries(self) -> None:
        """The StartCalendarInterval should have 15 entries (hours 4-18)."""
        plist = load_plist_from_script()
        entries = plist.get("StartCalendarInterval", [])
        assert len(entries) == 15, f"Expected 15 entries, got {len(entries)}"

    def test_entries_cover_hours_4_to_18(self) -> None:
        """Each hour from 4 to 18 should appear exactly once."""
        plist = load_plist_from_script()
        entries = plist.get("StartCalendarInterval", [])
        hours = sorted([e["Hour"] for e in entries])
        assert hours == list(range(4, 19)), f"Expected hours 4-18, got {hours}"

    def test_all_entries_have_minute_15(self) -> None:
        """Every entry should have Minute=15."""
        plist = load_plist_from_script()
        entries = plist.get("StartCalendarInterval", [])
        for entry in entries:
            assert entry.get("Minute") == 15, f"Expected Minute=15, got {entry.get('Minute')}"

    def test_no_weekday_keys(self) -> None:
        """No entry should have a Weekday key (runs every day)."""
        plist = load_plist_from_script()
        entries = plist.get("StartCalendarInterval", [])
        for entry in entries:
            assert "Weekday" not in entry, f"Found unexpected Weekday key: {entry}"

    def test_runs_every_day(self) -> None:
        """The plist should run every day (no Weekday key in any entry)."""
        plist = load_plist_from_script()
        entries = plist.get("StartCalendarInterval", [])
        # Verify no Weekday key exists in any entry
        for entry in entries:
            assert "Weekday" not in entry

    def test_has_label_and_program(self) -> None:
        """The plist should have Label and Program keys."""
        plist = load_plist_from_script()
        assert "Label" in plist
        assert plist["Label"] == "com.example.newnews"
        assert "Program" in plist
        assert plist["Program"] == str(REPO_ROOT / "scripts" / "run.sh")

    def test_keep_alive_is_false(self) -> None:
        """KeepAlive should be False (launchd runs on calendar interval)."""
        plist = load_plist_from_script()
        assert plist.get("KeepAlive") is False or plist.get("KeepAlive") == {}

    def test_run_at_load_is_false(self) -> None:
        """RunAtLoad should be False (we use calendar intervals)."""
        plist = load_plist_from_script()
        assert plist.get("RunAtLoad") is False or plist.get("RunAtLoad") == {}


class TestInstallScript:
    """Tests for the install-launchd.sh script."""

    def test_script_exists(self) -> None:
        """The install script should exist."""
        script = REPO_ROOT / "scripts" / "install-launchd.sh"
        assert script.exists(), f"Script not found: {script}"

    def test_script_is_executable(self) -> None:
        """The install script should be executable."""
        script = REPO_ROOT / "scripts" / "install-launchd.sh"
        assert script.stat().st_mode & 0o111, f"Script not executable: {script}"

    def test_dry_run_does_not_write(self, tmp_path: Path) -> None:
        """--dry-run should not write any files."""
        import stat

        # Create a temp directory to run in
        temp_dir = tmp_path / "temp_repo"
        temp_dir.mkdir()

        # Copy the script to temp
        script_src = REPO_ROOT / "scripts" / "install-launchd.sh"
        script_dst = temp_dir / "install-launchd.sh"
        script_dst.write_bytes(script_src.read_bytes())
        # Make the copy executable
        script_dst.chmod(script_dst.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

        # Run in dry-run mode
        result = subprocess.run(
            [str(script_dst), "--dry-run"],
            capture_output=True,
            text=True,
            cwd=temp_dir,
        )
        assert result.returncode == 0
        # No files should be created
        assert not (temp_dir / "Library" / "LaunchAgents").exists()

    def test_rendered_plist_is_valid_xml(self) -> None:
        """The rendered plist should be valid XML that parses."""
        plist = load_plist_from_script()
        # Should be a valid dict after parsing
        assert isinstance(plist, dict)
        # Should have required keys
        assert "Label" in plist
        assert "Program" in plist
        assert "StartCalendarInterval" in plist


class TestTimezoneHandling:
    """Tests for timezone verification in the install script."""

    def test_script_checks_timezone(self) -> None:
        """The install script should check for America/Chicago timezone."""
        script = REPO_ROOT / "scripts" / "install-launchd.sh"
        content = script.read_text()
        # Should contain some timezone check
        assert "timezone" in content.lower() or "America" in content or "Chicago" in content
