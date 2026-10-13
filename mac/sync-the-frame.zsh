#!/bin/zsh
# macOS user-session sync: Photos album "The Frame" -> dedicated Raspberry directory.
set -euo pipefail
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

ALBUM="The Frame"
LIBRARY="$HOME/Pictures/Photos Library.photoslibrary"
EXPORT_DIR="$HOME/Pictures/TheFrameExport"
STATE_DIR="$HOME/Library/Application Support/ArtModeSync"
JPEG_READY="$STATE_DIR/jpg-uuid-layout"
REMOTE="pi@piscreen.local"
REMOTE_DIR="/home/pi/Pictures/ArtModeAlbum"
LOG_DIR="$HOME/Library/Logs/ArtModeSync"
LOCK_DIR="$HOME/Library/Caches/ArtModeSync.lock"
OSXPHOTOS="/opt/homebrew/bin/osxphotos"

mkdir -p "$LOG_DIR" "$HOME/Library/Caches" "$STATE_DIR" "$EXPORT_DIR"
# A lock directory alone can survive a crash. Store the owning PID and
# reclaim stale locks. Only this process removes its own lock.
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  lock_pid=""
  [[ -f "$LOCK_DIR/pid" ]] && read -r lock_pid < "$LOCK_DIR/pid"
  if [[ "$lock_pid" == <-> ]] && kill -0 "$lock_pid" 2>/dev/null; then
    echo "Sync already running (PID $lock_pid); skipping."
    exit 0
  fi
  # Give a newly created lock a moment to write its PID before reclaiming.
  if [[ -z "$lock_pid" ]]; then
    sleep 2
    [[ -f "$LOCK_DIR/pid" ]] && read -r lock_pid < "$LOCK_DIR/pid"
    if [[ "$lock_pid" == <-> ]] && kill -0 "$lock_pid" 2>/dev/null; then
      echo "Sync already running (PID $lock_pid); skipping."
      exit 0
    fi
  fi
  echo "Recovering abandoned sync lock."
  /bin/rm -f "$LOCK_DIR/pid"
  rmdir "$LOCK_DIR" || { echo "Cannot reclaim sync lock" >&2; exit 1; }
  mkdir "$LOCK_DIR" || { echo "Another sync acquired the lock; skipping."; exit 0; }
fi
print -r -- "$$" > "$LOCK_DIR/pid"
TMP_REPORT=""
cleanup() {
  [[ -n "$TMP_REPORT" ]] && /bin/rm -f "$TMP_REPORT"
  local pid=""
  [[ -f "$LOCK_DIR/pid" ]] && read -r pid < "$LOCK_DIR/pid"
  if [[ "$pid" == "$$" ]]; then
    /bin/rm -f "$LOCK_DIR/pid"
    rmdir "$LOCK_DIR" 2>/dev/null || true
  fi
}
trap cleanup EXIT

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
if [[ -f "$JPEG_READY" ]]; then
  export_mode=(--update)
  echo "[1/3] Updating JPEG export of album: $ALBUM"
else
  export_mode=(--overwrite)
  echo "[1/3] One-time JPEG conversion of existing export: $ALBUM"
fi
echo "OSXPhotos native progress bar (detailed terminal output suppressed)."
# macOS script allocates a pseudo-terminal: Rich displays its native progress bar,
# and records its final summary for verification without a fragile awk pipeline.
if ! /usr/bin/script -q "$TMP_REPORT" "$OSXPHOTOS" export "$EXPORT_DIR" \
  --album "$ALBUM" --export-by-date --skip-original-if-edited \
  --skip-live --skip-raw --convert-to-jpeg --jpeg-quality 0.92 \
  --jpeg-ext jpg --filename "{uuid}" --edited-suffix "" \
  "${export_mode[@]}" --download-missing --cleanup; then
  echo "Unable to run OSXPhotos; remote mirror untouched." >&2
  exit 1
fi
echo "[1/3] Export finished; verifying counts."

# An apparently successful command may still have skipped all iCloud originals.
# Accept only a fully completed, explicitly clean export report.
if ! /usr/bin/grep -Eq 'Processed:[[:space:]]*[0-9]+ photos.*missing:[[:space:]]*0.*error:[[:space:]]*0' "$TMP_REPORT"; then
  echo "Export not proven complete (missing/error counts). Remote mirror untouched." >&2
  exit 1
fi

echo "[1/3] Removing macOS Finder metadata from export."
/usr/bin/find "$EXPORT_DIR" -type f -name ".DS_Store" -delete

# Count JPEG exports after the completed, checked OSXPhotos export.
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

touch "$JPEG_READY"
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
