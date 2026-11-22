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
  current_tz=$(tzutil get 2>/dev/null || date +%Z)
  
  if [[ "$current_tz" != "America/Chicago" && "$current_tz" != "CDT" && "$current_tz" != "CST" ]]; then
    echo "WARNING: System timezone is $current_tz, not America/Chicago" >&2
    echo "The launchd schedule will run in system time." >&2
    echo "Consider switching to America/Chicago for the scheduled times to match your intent." >&2
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
    echo "Run with --uninstall first, or use 'launchctl load' to reload."
    exit 1
  fi
  
  # Create LaunchAgents directory if needed
  mkdir -p "$(dirname "$PLIST_PATH")"
  
  # Render and write the plist
  render_plist > "$PLIST_PATH"
  echo "Installed $PLIST_PATH"
  
  # Load the job
  launchctl load "$PLIST_PATH"
  echo "Loaded com.example.newnews with launchctl"
}

# Uninstall the plist
uninstall() {
  if [ ! -f "$PLIST_PATH" ]; then
    echo "Plist not found at $PLIST_PATH"
    echo "Nothing to uninstall."
    exit 0
  fi
  
  # Unload the job if loaded
  if launchctl list | grep -q "com.example.newnews"; then
    launchctl unload "$PLIST_PATH"
    echo "Unloaded com.example.newnews with launchctl"
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
