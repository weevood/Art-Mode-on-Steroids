#!/usr/bin/env python3
"""Build a local original-vs-center-16:9 contact sheet from the crop audit.

Only exports 11 reviewed candidates into a separate local directory.
Never changes Apple Photos, TheFrameExport, or the Raspberry.
Requires Pillow and the existing OSXPhotos CLI.
"""
import argparse
import csv
from pathlib import Path
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont, ImageOps

WIDTH, HEIGHT = 550, 310
GAP = 16
LABEL_HEIGHT = 38


def load_candidates(csv_path):
    with csv_path.open(newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r["status"] == "crop_candidate"]
    return sorted(rows, key=lambda r: (-float(r["apple_score"]), r["uuid"]))


def find_jpeg(directory, uuid):
    matches = sorted(p for p in directory.rglob("*")
                     if p.is_file() and p.suffix.lower() in (".jpg", ".jpeg")
                     and uuid.lower() in p.stem.lower())
    return matches[0] if matches else None


def render_original(im):
    return ImageOps.contain(im, (WIDTH, HEIGHT), method=Image.Resampling.LANCZOS)


def centered_crop(im):
    w, h = im.size
    target = 16 / 9
    if w / h > target:
        crop_w = min(w, int(h * target))
        x0 = (w - crop_w) // 2
        return im.crop((x0, 0, x0 + crop_w, h))
    crop_h = min(h, int(w / target))
    y0 = (h - crop_h) // 2
    return im.crop((0, y0, w, y0 + crop_h))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--audit", type=Path, default=Path.home() /
                   "Library/Application Support/ArtModeSync/crop-candidates.csv")
    p.add_argument("--output", type=Path, default=Path.home() / "Pictures/TheFrameCropReview")
    p.add_argument("--osxphotos", default="/opt/homebrew/bin/osxphotos")
    args = p.parse_args()
    if not args.audit.is_file():
        p.error(f"Missing audit CSV: {args.audit}. Run audit_crop_candidates.py first.")
    rows = load_candidates(args.audit)
    if not rows:
        p.error("Audit contains no crop_candidate photos.")
    if len(rows) > 500:
        p.error("Refusing to export more than 500 photos in one contact sheet.")

    args.output.mkdir(parents=True, exist_ok=True)
    originals = args.output / "originals"
    originals.mkdir(exist_ok=True)
    manifest = args.output / "crop-review-uuids.txt"
    manifest.write_text("".join(r["uuid"] + "\n" for r in rows), encoding="utf-8")

    # Same OSXPhotos JPEG semantics as the established sync, but separate output.
    cmd = [args.osxphotos, "export", str(originals),
           "--uuid-from-file", str(manifest),
           "--skip-original-if-edited", "--skip-live", "--skip-raw",
           "--convert-to-jpeg", "--jpeg-quality", "0.92",
           "--jpeg-ext", "jpg", "--filename", "{uuid}",
           "--edited-suffix", "", "--update", "--download-missing"]
    print(f"Exporting up to {len(rows)} candidates to a separate review folder...", flush=True)
    subprocess.run(cmd, check=True)

    sheet_w = 2 * WIDTH + 3 * GAP
    row_h = HEIGHT + LABEL_HEIGHT + GAP
    sheet = Image.new("RGB", (sheet_w, GAP + len(rows) * row_h), "#f2f2f2")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    missing = []
    successful = 0

    for i, row in enumerate(rows, start=1):
        uid = row["uuid"]
        path = find_jpeg(originals, uid)
        if path is None:
            missing.append(uid)
            continue
        with Image.open(path) as file:
            im = ImageOps.exif_transpose(file).convert("RGB")
        crop = centered_crop(im)
        # Each candidate is also saved as a *preview*, never to the sync folder.
        crop.save(args.output / f"{i:02d}-{uid}-preview.jpg", quality=90)
        y = GAP + (i - 1) * row_h
        for col, image, label in (
            (0, render_original(im), "ORIGINAL"),
            (1, ImageOps.fit(crop, (WIDTH, HEIGHT), method=Image.Resampling.LANCZOS), "CENTER 16:9"),
        ):
            x = GAP + col * (WIDTH + GAP)
            if col == 0:
                x_offset = (WIDTH - image.width) // 2
                y_offset = (HEIGHT - image.height) // 2
                sheet.paste(image, (x + x_offset, y + y_offset))
            else:
                sheet.paste(image, (x, y))
            detail = f"{i:02d}  {label} | score {row['apple_score']} | {row['capture_date'][:10]}"
            draw.text((x, y + HEIGHT + 8), detail, fill="#222222", font=font)
        successful += 1
    output_file = args.output / "contact-sheet.jpg"
    sheet.save(output_file, quality=92)
    print(f"Review sheet: {output_file}")
    print(f"Previews created: {successful}/{len(rows)}")
    if missing:
        print(f"Missing JPEG exports ({len(missing)}): {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)
    print("No Photos originals or Raspberry files changed. Center crops are proposals only.")


if __name__ == "__main__":
    main()
