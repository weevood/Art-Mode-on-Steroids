#!/bin/zsh
# macOS user-session sync: Photos album "The Frame" -> dedicated Raspberry directory.
set -euo pipefail
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

ALBUM="The Frame"
LIBRARY="$HOME/Pictures/Photos Library.photoslibrary"
EXPORT_DIR="$HOME/Pictures/TheFrameJPEGExport"
REMOTE="pi@piscreen.local"
REMOTE_DIR="/home/pi/Pictures/ArtModeAlbum"
LOG_DIR="$HOME/Library/Logs/ArtModeSync"
LOCK_DIR="$HOME/Library/Caches/ArtModeSync.lock"
OSXPHOTOS="/opt/homebrew/bin/osxphotos"

mkdir -p "$LOG_DIR" "$HOME/Library/Caches"
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  echo "Sync already running; skipping."
  exit 0
fi
trap 'rmdir "$LOCK_DIR" 2>/dev/null || true' EXIT

if [[ ! -x "$OSXPHOTOS" ]]; then
  echo "OSXPhotos not found: $OSXPHOTOS" >&2
  exit 1
fi
if [[ ! -d "$LIBRARY" ]]; then
  echo "Photos library not available: $LIBRARY" >&2
  exit 1
fi

# Re-export edited versions; remove files removed from the album.
# IMPORTANT: this is a dedicated, disposable OSXPhotos export directory.
TMP_REPORT=$(mktemp)
trap 'rm -f "$TMP_REPORT"; rmdir "$LOCK_DIR" 2>/dev/null || true' EXIT
echo "[1/3] Exporting Photos album: $ALBUM"
if ! "$OSXPHOTOS" export "$EXPORT_DIR" \
  --album "$ALBUM" --export-by-date --skip-original-if-edited \
  --skip-live --skip-raw --convert-to-jpeg --jpeg-quality 0.92 \
  --jpeg-ext jpg --update --download-missing --cleanup \
  >"$TMP_REPORT" 2>&1; then
  cat "$TMP_REPORT"
  echo "Export failed; remote mirror not touched." >&2
  exit 1
fi
cat "$TMP_REPORT"

# An apparently successful command may still have skipped all iCloud originals.
# Accept only a fully completed, explicitly clean export report.
if ! /usr/bin/grep -Eq 'missing:[[:space:]]*0,[[:space:]]*error:[[:space:]]*0' "$TMP_REPORT"; then
  echo "Export not proven complete (missing/error counts). Remote mirror untouched." >&2
  exit 1
fi

# A fresh JPEG-only export is used so existing HEICs cannot be skipped by --update.
count=$(/usr/bin/find "$EXPORT_DIR" -type f \( -iname '*.jpg' -o -iname '*.jpeg' \) | /usr/bin/wc -l | /usr/bin/tr -d ' ')
processed=$(/usr/bin/sed -nE 's/.*Processed: ([0-9]+) photos.*/\1/p' "$TMP_REPORT" | /usr/bin/tail -1)
if [[ -z "$processed" ]] || (( processed < 1 || count < 1 || count * 100 < processed * 80 )); then
  echo "Incomplete JPEG coverage: $count JPEG for ${processed:-unknown} Photos entries; refusing remote --delete." >&2
  exit 1
fi
unexpected=$(/usr/bin/find "$EXPORT_DIR" -type f \( -iname '*.heic' -o -iname '*.png' -o -iname '*.tif' -o -iname '*.tiff' -o -iname '*.raw' -o -iname '*.dng' \) | /usr/bin/wc -l | /usr/bin/tr -d ' ')
if (( unexpected > 0 )); then
  echo "$unexpected non-JPEG images remain; refusing incomplete mirror." >&2
  exit 1
fi

echo "[2/3] Checking Raspberry connection ($REMOTE)"
# Create a dedicated remote folder; do not touch the old iCloud/Favourites source.
/usr/bin/ssh -o BatchMode=yes -o ConnectTimeout=12 "$REMOTE" \
  "mkdir -p '$REMOTE_DIR'"

# Mirror only after verified export; show per-file transfer progress.
# --delete removes files that were removed from the album only inside REMOTE_DIR.
echo "[3/3] Syncing $count supported image files to $REMOTE_DIR"
/usr/bin/rsync -av --progress --stats --delete --delete-excluded \
  --include='*/' --include='*.[jJ][pP][gG]' --include='*.[jJ][pP][eE][gG]' --exclude='*' \
  -e '/usr/bin/ssh -o BatchMode=yes -o ConnectTimeout=12' \
  "$EXPORT_DIR/" "$REMOTE:$REMOTE_DIR/"

echo "Sync completed: $count supported files exported to $REMOTE:$REMOTE_DIR"
