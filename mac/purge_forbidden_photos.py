#!/usr/bin/env python3
"""One-off, narrowly scoped purge of four forbidden Apple Photos originals.

Dry-run by default. --apply removes their UUID-named JPEG exports on the Mac
and Raspberry (not Apple Photos originals). It also blocks surviving Raspberry
paths from the rotation before deleting them. No broad rsync deletions.
"""
import argparse
import json
from pathlib import Path
import shlex
import subprocess

import osxphotos

from select_frame import NEVER_SYNC_STEMS, NEVER_SYNC_UUIDS, forbidden

MAC_EXPORT = Path.home() / "Pictures/TheFrameExport"
STATE = Path.home() / "Library/Application Support/ArtModeSync"
LIBRARY = Path.home() / "Pictures/Photos Library.photoslibrary"
REMOTE = "pi@piscreen.local"
REMOTE_DIR = "/home/pi/Pictures/ArtModeAlbum"

REMOTE_CODE = r"""
import json
import sys
from pathlib import Path

payload = json.loads(sys.argv[1])
root = Path(payload["root"])
if str(root) != "/home/pi/Pictures/ArtModeAlbum" or not root.is_dir():
    raise SystemExit("Unexpected/missing Raspberry photo directory; aborting")
ids = set(payload["ids"])
paths = sorted(p for p in root.rglob("*") if p.is_file()
               and p.suffix.casefold() in (".jpg", ".jpeg")
               and p.stem.upper() in ids)
print("RASPBERRY files matched:", len(paths), flush=True)
for p in paths:
    print(" ", p.relative_to(root), flush=True)
if payload["apply"]:
    # Guard against rotation races: the Pi engine reads this list every cycle.
    exclusions = root.parent.parent / "Art-Mode-on-Steroids" / "excluded_photos.json"
    if not exclusions.parent.is_dir():
        raise SystemExit("Raspberry engine directory missing; aborting purge")
    existing = json.loads(exclusions.read_text()) if exclusions.exists() else []
    if not isinstance(existing, list):
        raise SystemExit("Invalid existing exclusion list; aborting purge")
    combined = sorted(set(existing) | {p.relative_to(root).as_posix() for p in paths})
    tmp = exclusions.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(combined, indent=2) + "\n")
    tmp.replace(exclusions)
    for p in paths:
        p.unlink()
    remaining = [p for p in root.rglob("*") if p.is_file() and p.suffix.casefold() in (".jpg", ".jpeg") and p.stem.upper() in ids]
    if remaining:
        raise SystemExit("ERROR: some forbidden Raspberry exports remain")
    print("Raspberry blocked + purged successfully", flush=True)
"""


def remote_call(ids, apply):
    data = json.dumps({"ids": sorted(ids), "root": REMOTE_DIR, "apply": apply})
    command = "python3 -c " + shlex.quote(REMOTE_CODE) + " " + shlex.quote(data)
    subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=12",
                    REMOTE, command], check=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--apply", action="store_true", help="Purge UUID exports on Mac and Pi")
    args = p.parse_args()

    db = osxphotos.PhotosDB(str(LIBRARY))
    matched = {}
    for photo in db.photos():
        if forbidden(photo):
            matched[str(photo.uuid).upper()] = photo

    ids = set(matched) | NEVER_SYNC_UUIDS
    print("Blocked UUIDs:", len(ids))
    for uid in sorted(ids):
        photo = matched.get(uid)
        print(" ", uid, "|", getattr(photo, "original_filename", None) if photo else "UUID explicitly blocked")
    found_stems = {
        Path(str(name)).stem.casefold()
        for photo in matched.values()
        for name in (getattr(photo, "original_filename", None), getattr(photo, "filename", None))
        if name
    } & NEVER_SYNC_STEMS
    missing = NEVER_SYNC_STEMS - found_stems
    if missing:
        print("WARNING: filename stems not resolved by OSXPhotos:", ", ".join(sorted(missing)))
        print("Check these in Apple Photos. The two explicit UUIDs are still blocked.")

    local = sorted(f for f in MAC_EXPORT.rglob("*") if f.is_file()
                   and f.suffix.casefold() in (".jpg", ".jpeg")
                   and f.stem.upper() in ids) if MAC_EXPORT.is_dir() else []
    print("MAC exports matched:", len(local))
    for f in local:
        print(" ", f.relative_to(MAC_EXPORT))

    # Check connectivity before making any changes.
    remote_call(ids, False)
    if not args.apply:
        print("DRY RUN ONLY. To purge: add --apply.")
        return

    # Block stale UUID manifest entries before any later manual export.
    manifest = STATE / "selected-uuids.txt"
    if manifest.exists():
        old = manifest.read_text().splitlines()
        new = [uid for uid in old if uid.upper() not in ids]
        if len(new) != len(old):
            manifest.write_text("".join(uid + "\n" for uid in new))
            print("Removed blocked UUIDs from selection manifest:", len(old)-len(new))

    # Remove Pi candidates and add blocklist first, then remove Mac exports.
    remote_call(ids, True)
    for path in local:
        path.unlink()
    print("MAC UUID exports purged:", len(local))
    print("Apple Photos originals were not touched.")
    if missing:
        print("WARNING: unresolved original names require checking; do not assume all four are found.")


if __name__ == "__main__":
    main()
