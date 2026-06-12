import json
import logging
import random
import threading
import time
import sys

from datetime import date, datetime, timezone
from pathlib import Path
from io import BytesIO

import urllib3
from PIL import Image, ImageEnhance, ImageFilter
from samsungtvws import SamsungTVWS
from samsungtvws.exceptions import ConnectionFailure, ResponseError

from config import (
    UPLOAD_SCRIPT,
    TV_IP,
    IMAGES_DIR,
    LAST_IMAGE_FILE,
    MATTE,
)

# Disable SSL warnings (Samsung TVs often use self-signed certificates)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# =========================
# Logging configuration
# =========================
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(UPLOAD_SCRIPT)

# Supported image extensions
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp"}

# Target Art Mode resolution (4K UHD)
TARGET_WIDTH = 3840
TARGET_HEIGHT = 2160
TARGET_RATIO = TARGET_WIDTH / TARGET_HEIGHT


# =========================
# History helpers
# =========================
def load_upload_history():
    """
    Load upload history from the local JSON file.
    """
    if LAST_IMAGE_FILE.exists():
        try:
            with open(LAST_IMAGE_FILE, "r", encoding="utf-8") as f:
                return json.load(f).get("uploaded_images", [])
        except Exception as exc:
            log.warning("Failed to read upload history: %s", exc)

    return []


def get_image_id(image_path: Path) -> str:
    """
    Return a stable image identifier relative to IMAGES_DIR.

    Example:
    IMAGES_DIR/2023/06/04/IMG_5758.JPG
    -> 2023/06/04/IMG_5758.JPG
    """
    return image_path.relative_to(IMAGES_DIR).as_posix()


def save_uploaded_image(image_path: Path, file_size_mb, selection_info=None):
    """
    Save a newly uploaded image into the local history file.
    """
    history = load_upload_history()
    image_id = get_image_id(image_path)

    # Avoid duplicates
    if any(entry.get("filename") == image_id for entry in history):
        log.info("Image already present in upload history")
        return

    selection_info = selection_info or {}

    history.append(
        {
            "filename": image_id,
            "original_filename": image_path.name,
            "size": file_size_mb,
            "content_id": "PENDING",
            "image_date": selection_info.get("image_date", "PENDING"),
            "memory_year": selection_info.get("memory_year", "PENDING"),
            "match_type": selection_info.get("match_type", "PENDING"),
            "delta_days": selection_info.get("delta_days", "PENDING"),
            "activated_at": datetime.now(timezone.utc).isoformat(),
        }
    )

    with open(LAST_IMAGE_FILE, "w", encoding="utf-8") as f:
        json.dump({"uploaded_images": history}, f, indent=2)

    log.info("Upload history updated")


# =========================
# Image discovery and selection
# =========================
def get_image_files():
    """
    Retrieve all supported image files recursively from the images directory.
    """
    if not IMAGES_DIR.exists():
        log.error("Images directory does not exist: %s", IMAGES_DIR)
        return []

    return sorted(
        [
            f
            for f in IMAGES_DIR.rglob("*")
            if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
        ]
    )


def extract_date_from_path(image_path: Path):
    """
    Extract image date from a path like:
    IMAGES_DIR/YYYY/MM/DD/image.jpg

    Example:
    IMAGES_DIR/2023/06/04/IMG_5758.JPG
    -> date(2023, 6, 4)
    """
    try:
        relative_parts = image_path.relative_to(IMAGES_DIR).parts

        if len(relative_parts) < 4:
            return None

        year = int(relative_parts[0])
        month = int(relative_parts[1])
        day = int(relative_parts[2])

        return date(year, month, day)

    except Exception:
        return None


def days_from_today_anniversary(image_date: date, today: date):
    """
    Compare a past image date to today's month/day in the same year as the image.

    Example:
    today = 2026-06-12
    image_date = 2023-06-14
    delta = +2
    """
    try:
        anniversary = date(image_date.year, today.month, today.day)
    except ValueError:
        return None

    return (image_date - anniversary).days


def build_selection_info(image_path: Path, image_date, match_type: str, delta_days=None):
    """
    Build metadata describing why this image was selected.
    """
    return {
        "image_date": image_date.isoformat() if image_date else "PENDING",
        "memory_year": image_date.year if image_date else "PENDING",
        "match_type": match_type,
        "delta_days": delta_days if delta_days is not None else "PENDING",
    }


def select_next_image(image_files):
    """
    Select one image intelligently based on today's date.

    Priority:
    1. Same month/day in a previous year
    2. ±1 day
    3. ±2 days
    4. ±3 days
    5. ±7 days
    6. Same month
    7. Fallback to any image not already uploaded
    """
    today = date.today()

    history = load_upload_history()
    uploaded = {entry.get("filename") for entry in history}

    # Avoid images already uploaded.
    # Backward compatible: checks both relative path and raw filename.
    available_images = [
        img
        for img in image_files
        if get_image_id(img) not in uploaded and img.name not in uploaded
    ]

    if not available_images:
        log.info("All images have already been uploaded")
        return None, None

    dated_images = []
    fallback_images = []

    for img in available_images:
        image_date = extract_date_from_path(img)

        if image_date and image_date < today:
            dated_images.append((img, image_date))
        else:
            fallback_images.append(img)

    # Priority 1: exact same month/day in previous years
    exact_matches = [
        (img, image_date, 0)
        for img, image_date in dated_images
        if image_date.month == today.month and image_date.day == today.day
    ]

    if exact_matches:
        img, image_date, delta_days = random.choice(exact_matches)
        log.info(
            "Selected memory image: %s | date=%s | match=exact_day",
            get_image_id(img),
            image_date,
        )
        return img, build_selection_info(img, image_date, "exact_day", delta_days)

    # Priority 2–5: progressively wider windows around the same day
    for window in [1, 2, 3, 7]:
        candidates = []

        for img, image_date in dated_images:
            delta_days = days_from_today_anniversary(image_date, today)

            if delta_days is None:
                continue

            if abs(delta_days) <= window:
                candidates.append((img, image_date, delta_days))

        if candidates:
            img, image_date, delta_days = random.choice(candidates)
            log.info(
                "Selected memory image: %s | date=%s | match=within_%s_days | delta=%s",
                get_image_id(img),
                image_date,
                window,
                delta_days,
            )
            return img, build_selection_info(
                img,
                image_date,
                f"within_{window}_days",
                delta_days,
            )

    # Priority 6: same month in previous years
    same_month = [
        (img, image_date)
        for img, image_date in dated_images
        if image_date.month == today.month
    ]

    if same_month:
        img, image_date = random.choice(same_month)
        delta_days = days_from_today_anniversary(image_date, today)

        log.info(
            "Selected memory image: %s | date=%s | match=same_month | delta=%s",
            get_image_id(img),
            image_date,
            delta_days,
        )

        return img, build_selection_info(
            img,
            image_date,
            "same_month",
            delta_days,
        )

    # Priority 7: fallback to any image not already uploaded
    fallback_candidates = fallback_images if fallback_images else available_images
    img = random.choice(fallback_candidates)

    log.info(
        "Selected fallback image: %s | no usable YYYY/MM/DD date found",
        get_image_id(img),
    )

    return img, build_selection_info(img, None, "fallback")


# =========================
# Image processing
# =========================
def crop_to_4k(image: Image.Image) -> Image.Image:
    """
    Center-crop and resize an image to 3840x2160 (16:9),
    without stretching or distorting the image.
    """
    width, height = image.size
    current_ratio = width / height

    if current_ratio > TARGET_RATIO:
        # Image is wider than 16:9 → crop horizontally
        new_width = int(height * TARGET_RATIO)
        offset = (width - new_width) // 2
        image = image.crop((offset, 0, offset + new_width, height))
    else:
        # Image is taller than 16:9 → crop vertically
        new_height = int(width / TARGET_RATIO)
        offset = (height - new_height) // 2
        image = image.crop((0, offset, width, offset + new_height))

    return image.resize((TARGET_WIDTH, TARGET_HEIGHT), Image.LANCZOS)


def make_artistic(image_bytes: bytes) -> bytes:
    """
    Apply artistic post-processing and resize image for Art Mode.
    """
    image = Image.open(BytesIO(image_bytes)).convert("RGB")

    # Ensure correct resolution and aspect ratio
    image = crop_to_4k(image)

    # Slight smoothing to reduce digital sharpness
    image = image.filter(ImageFilter.SMOOTH_MORE)

    # Artistic adjustments
    image = ImageEnhance.Contrast(image).enhance(1.08)
    image = ImageEnhance.Color(image).enhance(0.95)
    image = ImageEnhance.Sharpness(image).enhance(0.8)

    output = BytesIO()
    image.save(output, format="JPEG", quality=92)
    return output.getvalue()


# =========================
# Samsung Art Mode upload
# =========================
def upload_image(art, image_data: bytes, file_extension: str) -> None:
    """
    Upload image data to Samsung Art Mode.
    """
    art.upload(image_data, file_type=file_extension, matte=MATTE)

    # Restart Art Mode to ensure the image is registered
    log.info("Restarting Art Mode...")
    art.set_artmode(False)
    time.sleep(1)
    art.set_artmode(True)
    time.sleep(2)


# =========================
# Main execution
# =========================
def main() -> None:
    if not IMAGES_DIR.exists():
        log.error("Images directory does not exist. Please create it and add images.")
        return

    image_files = get_image_files()
    if not image_files:
        log.error("No images found in directory")
        return

    image_path, selection_info = select_next_image(image_files)
    if not image_path:
        return

    log.info("Selected image: %s", get_image_id(image_path))

    file_size_mb = image_path.stat().st_size / (1024 * 1024)
    log.info("Image size: %.2f MB", file_size_mb)

    with open(image_path, "rb") as f:
        raw_data = f.read()

    log.info("Applying artistic processing...")
    image_data = make_artistic(raw_data)

    file_extension = image_path.suffix[1:].lower()
    if file_extension == "jpg":
        file_extension = "jpeg"

    tv = None

    try:
        log.info("Connecting to TV...")
        tv = SamsungTVWS(host=TV_IP, name=f"ArtModeUpload-{time.time()}")

        art = tv.art()
        if not art.supported():
            log.error("Art Mode is not supported on this TV")
            return

        log.info("Uploading image (timeout: 30s)...")

        upload_thread = threading.Thread(
            target=upload_image,
            args=(art, image_data, file_extension),
            daemon=True,
        )

        upload_thread.start()
        upload_thread.join(timeout=30)

        if upload_thread.is_alive():
            log.warning("Upload still running after 30s (likely accepted)")
        else:
            log.info("✓ Upload completed")

        save_uploaded_image(
            image_path,
            f"{file_size_mb:.2f} MB",
            selection_info,
        )

        log.info("Upload finished successfully")

    except ConnectionFailure as exc:
        log.error("TV connection failure: %s", exc)

    except ResponseError as exc:
        log.error("Samsung API error: %s", exc)

    except Exception as exc:
        log.exception("Unexpected error: %s", exc)

    finally:
        if tv:
            try:
                tv.close()
                log.info("TV connection closed")
            except Exception:
                pass


if __name__ == "__main__":
    main()