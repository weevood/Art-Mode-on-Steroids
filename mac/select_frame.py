#!/usr/bin/env python3
"""Select Apple Photos smart-album UUIDs without exporting originals."""
import argparse
import csv
import os
from pathlib import Path
import re
import subprocess
import tempfile

UUID = re.compile(r"\b[0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}\b")

def album_ids(name):
    escaped = name.replace("\\", "\\\\").replace('"', '\\"')
    script = 'tell application "Photos" to get id of every media item of album "' + escaped + '"'
    result = subprocess.run(["/usr/bin/osascript", "-e", script],
                            text=True, capture_output=True, check=True)
    return list(dict.fromkeys(x.upper() for x in UUID.findall(result.stdout)))

def atomic_text(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False, encoding="utf-8") as handle:
        handle.write(content)
        temp = handle.name
    os.replace(temp, path)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--album", default="The Frame")
    parser.add_argument("--library", type=Path, default=Path.home() / "Pictures/Photos Library.photoslibrary")
    parser.add_argument("--output", type=Path, default=Path.home() / "Library/Application Support/ArtModeSync/selected-uuids.txt")
    parser.add_argument("--min-score", type=float, default=0.75)
    parser.add_argument("--min-ratio", type=float, default=1.3)
    parser.add_argument("--min-width", type=int, default=1600)
    parser.add_argument("--min-height", type=int, default=900)
    args = parser.parse_args()

    import osxphotos
    ids = album_ids(args.album)
    if not ids:
        raise RuntimeError("Smart album returned no UUIDs: existing selection preserved")
    db = osxphotos.PhotosDB(str(args.library))
    selected, excluded = [], {}
    for uid in ids:
        photo = db.get_photo(uid)
        reason = None
        if photo is None:
            reason = "uuid_not_found"
        elif not photo.isphoto or photo.ismovie or photo.screenshot or photo.hidden or photo.intrash:
            reason = "media_type"
        else:
            w, h = photo.width or 0, photo.height or 0
            if w < args.min_width or h < args.min_height or not h or w/h < args.min_ratio:
                reason = "dimensions"
            else:
                overall = getattr(getattr(photo, "score", None), "overall", None)
                if overall is None or float(overall) < args.min_score:
                    reason = "score"
                else:
                    selected.append((float(overall), uid, w, h))
        if reason:
            excluded[reason] = excluded.get(reason, 0) + 1
    if not selected:
        raise RuntimeError("No eligible photos: existing selection preserved")
    selected.sort(reverse=True)
    atomic_text(args.output, "".join(uid + "\n" for _, uid, _, _ in selected))
    report = args.output.with_suffix(".csv")
    with tempfile.NamedTemporaryFile(mode="w", dir=report.parent, delete=False, newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(("apple_overall_score", "uuid", "width", "height"))
        writer.writerows(selected)
        tmp = f.name
    os.replace(tmp, report)
    print(f"Smart album: {len(ids)} | selected: {len(selected)} | excluded: {excluded}", flush=True)
    print(f"Scores selected: {selected[-1][0]:.3f} ... {selected[0][0]:.3f}")
    print(f"UUID manifest: {args.output}")

if __name__ == "__main__":
    main()
