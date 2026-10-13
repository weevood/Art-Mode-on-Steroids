#!/bin/bash
# One-time Raspberry migration. Run ON PI after a completed full Mac mirror.
# Do not start/restart Art Mode: the fixed TV artwork must stay unchanged.
set -euo pipefail
PI_HOME=/home/pi
ROOT="$PI_HOME/Art-Mode-on-Steroids"
ALBUM="$PI_HOME/Pictures/ArtModeAlbum"
OLD="$PI_HOME/Pictures/iCloud/Favourites"
CONFIG="$ROOT/config_local.py"
echo "[1/5] Stopping photo rotation; keeping currently selected TV art"
sudo systemctl stop art-mode.service
echo "[2/5] Checking new JPEG-only source"
[ -d "$ALBUM" ] || { echo "New mirror missing: $ALBUM"; exit 1; }
count=$(find "$ALBUM" -type f -iname '*.jpg' | wc -l)
[ "$count" -ge 400 ] || { echo "Only $count JPEG found; refusing cleanup (<400)"; exit 1; }
other=$(find "$ALBUM" -type f ! -iname '*.jpg' | wc -l)
[ "$other" -eq 0 ] || { echo "$other unexpected non-JPG files. Run Mac mirror cleanup first."; exit 1; }
echo "Verified $count JPEG"
echo "[3/5] Switching local image source without changing TV/network settings"
[ -f "$CONFIG" ] || { echo "Missing $CONFIG; refusing to replace machine settings"; exit 1; }
cp -p "$CONFIG" "$CONFIG.before-album-migration"
python3 - "$CONFIG" "$ALBUM" <<'PY'
from pathlib import Path
import sys
path = Path(sys.argv[1])
text = path.read_text()
tag = "# ArtModeAlbum source (managed by pi/migrate-to-album.sh)"
text = text.split("\n" + tag)[0]
path.write_text(text.rstrip() + "\n\n" + tag + "\nfrom pathlib import Path\nIMAGES_DIR = Path(" + repr(sys.argv[2]) + ")\n")
PY
cd "$ROOT"
./venv/bin/python -c 'from config import IMAGES_DIR; from pathlib import Path; assert IMAGES_DIR == Path("/home/pi/Pictures/ArtModeAlbum"), IMAGES_DIR; print("Source:", IMAGES_DIR)'
echo "[4/5] Disabling only the old iCloud Favourites sync cron"
tmp=$(mktemp)
crontab -l > "$tmp" 2>/dev/null || : 
cp "$tmp" "$PI_HOME/old-crontab.before-album-migration"
sed '/\/home\/pi\/icloud-sync\/sync-icloud-favourites\.sh/d' "$tmp" | crontab -
rm -f "$tmp"
echo "[5/5] Removing obsolete iCloud Favourites local copies"
if [ -d "$OLD" ]; then
  du -sh "$OLD"
  # Only the known obsolete directory; never remove Pictures/iCloud or other paths.
  rm -r -- "$OLD"
  echo "Removed $OLD"
else
  echo "Old Favourites mirror already absent"
fi
echo "Migration complete. Art Mode remains STOPPED until the next reboot."
systemctl is-active art-mode.service || true
