#!/bin/zsh
# Install one user LaunchAgent, every two hours. Run from any checkout path.
set -euo pipefail
ROOT="${0:A:h:h}"
SCRIPT="$ROOT/mac/sync-the-frame.zsh"
PLIST="$HOME/Library/LaunchAgents/ch.artmode.theframe-sync.plist"
LOG="$HOME/Library/Logs/ArtModeSync"
mkdir -p "$HOME/Library/LaunchAgents" "$LOG"
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>ch.artmode.theframe-sync</string>
<key>ProgramArguments</key><array><string>/bin/zsh</string><string>$SCRIPT</string></array>
<key>RunAtLoad</key><true/>
<key>StartInterval</key><integer>7200</integer>
<key>StandardOutPath</key><string>$LOG/launchd.log</string>
<key>StandardErrorPath</key><string>$LOG/launchd-error.log</string>
</dict></plist>
EOF
/usr/bin/plutil -lint "$PLIST"
USER_UID=$(/usr/bin/id -u)
/bin/launchctl bootout "gui/$USER_UID/ch.artmode.theframe-sync" 2>/dev/null || true
/bin/launchctl bootstrap "gui/$USER_UID" "$PLIST"
/bin/launchctl enable "gui/$USER_UID/ch.artmode.theframe-sync"
echo "Installed 2-hourly user sync: $PLIST"
echo "Logs: $LOG/launchd.log"
