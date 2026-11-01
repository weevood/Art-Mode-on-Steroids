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
FRAME_PYTHON="$HOME/.venvs/frame-curation/bin/python"
UUID_FILE="$STATE_DIR/selected-uuids.txt"

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

# Generate an atomic UUID manifest from the Photos smart album before exporting.
# Never remove exported content when selection fails.
if [[ ! -x "$FRAME_PYTHON" ]]; then
  echo "Missing selection Python: $FRAME_PYTHON" >&2
  exit 1
fi
if ! "$FRAME_PYTHON" "${0:A:h}/select_frame.py" --album "$ALBUM" --library "$LIBRARY" --output "$UUID_FILE"; then
  echo "Selection failed: no export or Raspberry changes." >&2
  exit 1
fi
selected_count=$(/usr/bin/wc -l < "$UUID_FILE" | /usr/bin/tr -d " ")
if (( selected_count < 1 )); then
  echo "Empty selection: aborting safely." >&2
  exit 1
fi
# Export new or edited selected JPEGs. Existing JPEGs outside the selection stay untouched.
TMP_REPORT=$(mktemp)
export_mode=(--update --update-errors --retry 2)
echo "[1/3] Incremental JPEG export of $selected_count selected photos from smart album $ALBUM"
echo "OSXPhotos native progress bar (detailed terminal output suppressed)."
# macOS script allocates a pseudo-terminal: Rich displays its native progress bar,
# and records its final summary for verification without a fragile awk pipeline.
if ! /usr/bin/script -q "$TMP_REPORT" "$OSXPHOTOS" export "$EXPORT_DIR" \
  --uuid-from-file "$UUID_FILE" --export-by-date --skip-original-if-edited \
  --skip-live --skip-raw --convert-to-jpeg --jpeg-quality 0.92 \
  --jpeg-ext jpg --filename "{uuid}" --edited-suffix "" \
  "${export_mode[@]}" --download-missing; then
  echo "Unable to run OSXPhotos; remote mirror untouched." >&2
  exit 1
fi
echo "[1/3] Export finished; verifying counts."

# OSXPhotos may report missing iCloud images; valid JPEGs can still sync.
# No deletion is performed in either case.
# macOS script captures terminal progress with CR/ANSI control codes.
# Read the full transcript, normalize control characters, and parse the LAST summary.
summary=$(/usr/bin/perl -0777 -ne '
  s/\e\[[0-9;?]*[ -\/]*[@-~]//g;
  s/\r/\n/g;
  while (/Processed:\s*(\d+)\s+photos[^\n]*?missing:\s*(\d+)\s*,\s*error:\s*(\d+)/g) {
    $found = "$1 $2 $3";
  }
  END { print "$found\n" if defined $found; }
' "$TMP_REPORT")
if [[ ! "$summary" =~ '^[0-9]+ [0-9]+ [0-9]+$' ]]; then
  echo "Could not parse OSXPhotos summary; last report lines:" >&2
  /usr/bin/tr '\r' '\n' < "$TMP_REPORT" | /usr/bin/tail -n 15 >&2
  exit 1
fi
read -r processed missing errors <<< "$summary"
echo "[1/3] OSXPhotos processed=$processed missing=$missing errors=$errors"
echo "[1/3] Removing macOS Finder metadata from export."
/usr/bin/find "$EXPORT_DIR" -type f -name ".DS_Store" -delete

# Count JPEG exports after the completed, checked OSXPhotos export.
count=$(/usr/bin/find "$EXPORT_DIR" -type f \( -iname '*.jpg' -o -iname '*.jpeg' \) | /usr/bin/wc -l | /usr/bin/tr -d ' ')
if (( processed < 1 || count < 1 )); then
  echo "No usable JPEG exports; Raspberry untouched." >&2
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

# Additive sync only: never delete local exports or Raspberry images.
echo "[3/3] Preparing additive JPEG sync (no deletions)."
remote_count=$(/usr/bin/ssh -o BatchMode=yes -o ConnectTimeout=12 "$REMOTE" \
  "find '$REMOTE_DIR' -type f \\( -iname '*.jpg' -o -iname '*.jpeg' \\) | wc -l" | /usr/bin/tr -d '[:space:]')
echo "[3/3] Checking changes..."
rsync_filters=(
  --include='*/'
  --include='*.[jJ][pP][gG]'
  --exclude='*'
)
ssh_command='/usr/bin/ssh -o BatchMode=yes -o ConnectTimeout=12'
pending=$(/usr/bin/rsync -an --out-format='%n' "${rsync_filters[@]}" \
  -e "$ssh_command" "$EXPORT_DIR/" "$REMOTE:$REMOTE_DIR/" \
  | /usr/bin/awk 'tolower($0) ~ /\\.jpg$/ {n++} END {print n+0}')
echo "[3/3] $pending JPEG to transfer, $count local JPEG, $remote_count Pi JPEG."
if (( pending > 0 )); then
  script_dir="${0:A:h}"
  /usr/bin/python3 "$script_dir/rsync_progress.py" "$pending" \
    /usr/bin/rsync -a --out-format='%n' "${rsync_filters[@]}" \
    -e "$ssh_command" "$EXPORT_DIR/" "$REMOTE:$REMOTE_DIR/"
else
  /usr/bin/rsync -a "${mirror_args[@]}" "${rsync_filters[@]}" \
    -e "$ssh_command" "$EXPORT_DIR/" "$REMOTE:$REMOTE_DIR/"
  echo "[3/3] Existing files reconciled; Raspberry up to date."
fi

touch "$JPEG_READY"
echo "Sync completed: $count local JPEG files; missing=$missing errors=$errors."
