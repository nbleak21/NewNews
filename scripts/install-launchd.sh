#!/bin/bash
# install-launchd.sh - Install or uninstall the NewNews launchd agent
#
# Usage:
#   ./install-launchd.sh         # install to ~/Library/LaunchAgents/
#   ./install-launchd.sh --uninstall  # remove from ~/Library/LaunchAgents/
#   ./install-launchd.sh --dry-run    # print the rendered plist (install mode)
#
# launchd uses the system time zone, so this script checks if the Mac is
# running on America/Chicago and warns if not. The schedule (hours 4-18 at
# minute 15) is interpreted in the system time zone.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLIST_NAME="com.example.newnews.plist"
PLIST_PATH="$HOME/Library/LaunchAgents/$PLIST_NAME"

# Print usage
usage() {
  echo "Usage: $0 [--uninstall] [--dry-run]"
  echo "  --uninstall    Remove the plist from ~/Library/LaunchAgents/"
  echo "  --dry-run      Print the rendered plist (do not write)"
  exit 1
}

# Check for America/Chicago timezone
check_timezone() {
  local current_tz
  # macOS keeps the active zone as a symlink to its zoneinfo file; the IANA name
  # is the tail of that path. (tzutil is a Windows command, not macOS.)
  current_tz=$(readlink /etc/localtime 2>/dev/null | sed 's#.*/zoneinfo/##')
  
  if [[ "$current_tz" != "America/Chicago" ]]; then
    echo "WARNING: System timezone is '${current_tz:-unknown}', not America/Chicago" >&2
    echo "launchd runs the schedule in system time, so the 04:15-18:15 run times" >&2
    echo "will not match your intent unless the Mac is on America/Chicago." >&2
    echo "" >&2
  fi
}

# Render the plist content
render_plist() {
  local python_script
  python_script=$(cat << 'PYTHON_EOF'
import plistlib
import sys
from pathlib import Path

repo_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent.parent

plist = {
    "Label": "com.example.newnews",
    "Program": str(repo_dir / "scripts" / "run.sh"),
    "RunAtLoad": False,
    "KeepAlive": False,
    # 15 entries, one per hour 04:15..18:15. Keep in sync with the `schedule:`
    # block in config/sources.yaml (and the Schedule dataclass in config.py).
    "StartCalendarInterval": [
        {"Hour": hour, "Minute": 15} for hour in range(4, 19)  # 4 AM to 6 PM (18:15)
    ],
}

print(plistlib.dumps(plist).decode("utf-8"))
PYTHON_EOF
  )
  
  python3 -c "$python_script" "$REPO_DIR"
}

# Install the plist
install() {
  check_timezone
  
  if [ -f "$PLIST_PATH" ]; then
    echo "Plist already exists at $PLIST_PATH"
    echo "Run with --uninstall first, then re-run this script to reinstall."
    exit 1
  fi
  
  # Create LaunchAgents directory if needed
  mkdir -p "$(dirname "$PLIST_PATH")"
  
  # Render and write the plist
  render_plist > "$PLIST_PATH"
  echo "Installed $PLIST_PATH"
  
  # Load the job (bootstrap replaces the deprecated 'launchctl load')
  launchctl bootstrap "gui/$(id -u)" "$PLIST_PATH"
  echo "Bootstrapped com.example.newnews with launchctl"
}

# Uninstall the plist
uninstall() {
  if [ ! -f "$PLIST_PATH" ]; then
    echo "Plist not found at $PLIST_PATH"
    echo "Nothing to uninstall."
    exit 0
  fi
  
  # Unload the job if loaded (bootout replaces the deprecated 'launchctl unload')
  if launchctl bootout "gui/$(id -u)/com.example.newnews" 2>/dev/null; then
    echo "Booted out com.example.newnews with launchctl"
  fi
  
  rm "$PLIST_PATH"
  echo "Removed $PLIST_PATH"
}

# Main
DRY_RUN=false
UNINSTALL=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    --uninstall)
      UNINSTALL=true
      shift
      ;;
    -h|--help)
      usage
      ;;
    *)
      echo "Unknown option: $1"
      usage
      ;;
  esac
done

if $DRY_RUN; then
  # Dry run: just render and print the plist
  check_timezone
  render_plist
elif $UNINSTALL; then
  uninstall
else
  install
fi
