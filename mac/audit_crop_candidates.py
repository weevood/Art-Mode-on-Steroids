#!/usr/bin/env python3
"""Audit aesthetically strong Photos images excluded by the Frame geometry filter.

Read-only: no photo export, crop, or deletion. Uses the same smart album and
geometry rules as select_frame.py. Scores >= 0.80 are required for candidates.
"""
import argparse
from collections import Counter
import csv
from datetime import datetime
from pathlib import Path
import subprocess
import tempfile
import os

from select_frame import album_ids

TARGET_RATIO = 16 / 9


def category(w, h):
    ratio = w / h
    if ratio < 0.85:
        return "portrait"
    if ratio < 1.15:
        return "square"
    if ratio < 1.45:
        return "landscape_4_3"
    if ratio < 1.7:
        return "landscape_3_2"
    return "wide_landscape"


def crop_geometry(w, h):
    """Largest centered 16:9 crop, with exact integer pixel dimensions."""
    if w / h >= TARGET_RATIO:
        crop_h = min(h, int(w / TARGET_RATIO))
        crop_w = int(crop_h * TARGET_RATIO)
    else:
        crop_w = min(w, int(h * TARGET_RATIO))
        crop_h = int(crop_w / TARGET_RATIO)
    return crop_w, crop_h, (crop_w * crop_h) / (w * h)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--album", default="The Frame")
    p.add_argument("--library", type=Path, default=Path.home() / "Pictures/Photos Library.photoslibrary")
    p.add_argument("--output", type=Path, default=Path.home() / "Library/Application Support/ArtModeSync/crop-candidates.csv")
    p.add_argument("--min-score", type=float, default=0.80)
    p.add_argument("--min-ratio", type=float, default=1.3)
    p.add_argument("--min-width", type=int, default=1600)
    p.add_argument("--min-height", type=int, default=900)
    p.add_argument("--min-retained", type=float, default=0.60)
    args = p.parse_args()
    if not (0 < args.min_retained <= 1):
        p.error("--min-retained must be within (0, 1]")

    import osxphotos
    ids = album_ids(args.album)
    if not ids:
        raise RuntimeError("Smart album returned no UUIDs; audit not overwritten")
    db = osxphotos.PhotosDB(str(args.library))
    rows = []
    counts = Counter()
    month_counts = Counter()
    for uid in ids:
        photo = db.get_photo(uid)
        if photo is None:
            counts["missing_uuid"] += 1
            continue
        if not photo.isphoto or photo.ismovie or photo.screenshot or photo.hidden or photo.intrash:
            counts["invalid_media"] += 1
            continue
        w, h = int(photo.width or 0), int(photo.height or 0)
        if not w or not h:
            counts["unknown_dimensions"] += 1
            continue
        # The audit targets only images the current selector rejects for geometry.
        fails_geometry = w < args.min_width or h < args.min_height or w / h < args.min_ratio
        if not fails_geometry:
            counts["passes_existing_geometry"] += 1
            continue
        counts["geometry_excluded"] += 1
        score = getattr(getattr(photo, "score", None), "overall", None)
        if score is None or float(score) < args.min_score:
            counts["below_interest_threshold"] += 1
            continue
        counts["high_interest_geometry_excluded"] += 1
        cw, ch, retained = crop_geometry(w, h)
        enough_pixels = cw >= args.min_width and ch >= args.min_height
        usable = enough_pixels and retained >= args.min_retained
        status = "crop_candidate" if usable else ("resolution_too_low" if not enough_pixels else "crop_too_destructive")
        counts[status] += 1
        taken = getattr(photo, "date", None)
        date_text = taken.isoformat() if isinstance(taken, datetime) else str(taken or "")
        month = getattr(taken, "month", None)
        if usable:
            month_counts[month or 0] += 1
        rows.append((uid, round(float(score), 4), date_text, w, h,
                     round(w / h, 3), category(w, h), cw, ch,
                     round(retained, 3), status))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", dir=args.output.parent, delete=False,
                                     encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(("uuid", "apple_score", "capture_date", "width", "height",
                         "aspect_ratio", "original_format", "crop_width", "crop_height",
                         "retained_area_fraction", "status"))
        writer.writerows(sorted(rows, key=lambda row: (-row[1], row[0])))
        temp = f.name
    os.replace(temp, args.output)
    print(f"Smart album examined: {len(ids)}")
    print(f"Interest threshold: >= {args.min_score:.2f}; output ratio: 16:9")
    for key in ("geometry_excluded", "high_interest_geometry_excluded",
                "crop_candidate", "crop_too_destructive", "resolution_too_low"):
        print(f"{key}: {counts[key]}")
    print("Candidate formats:", dict(sorted(Counter(row[6] for row in rows if row[-1] == "crop_candidate").items())))
    print("Candidate months:", dict(sorted(month_counts.items())))
    print(f"Audit CSV: {args.output}")
    print("IMPORTANT: geometric feasibility only; visual composition still requires human review.")


if __name__ == "__main__":
    main()
