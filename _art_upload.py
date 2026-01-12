import json
import logging
import random
import threading
import time
import sys

from datetime import datetime
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
# Functions
# =========================
def load_upload_history():
    """
    Load upload history from the local JSON file.
    """
    if LAST_IMAGE_FILE.exists():
        try:
            with open(LAST_IMAGE_FILE, "r") as f:
                return json.load(f).get("uploaded_images", [])
        except Exception as exc:
            log.warning("Failed to read upload history: %s", exc)
    return []


def save_uploaded_image(filename, file_size_mb):
    """
    Save a newly uploaded image into the local history file.
    """
    history = load_upload_history()

    # Avoid duplicates
    if any(entry["filename"] == filename for entry in history):
        log.info("Image already present in upload history")
        return

    history.append(
        {
            "filename": filename,
            "size": file_size_mb,
            "content_id": "PENDING",
            "image_date": "PENDING",
            "activated_at": datetime.utcnow().isoformat(),
        }
    )

    with open(LAST_IMAGE_FILE, "w") as f:
        json.dump({"uploaded_images": history}, f, indent=2)

    log.info("Upload history updated")


def get_image_files():
    """
    Retrieve all supported image files from the images directory.
    """
    if not IMAGES_DIR.exists():
        log.error("Images directory does not exist: %s", IMAGES_DIR)
        return []

    return sorted(
        [
            f
            for f in IMAGES_DIR.iterdir()
            if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
        ]
    )


def select_next_image(image_files):
    """
    Select a random image that has not yet been uploaded.
    """
    history = load_upload_history()
    uploaded = {entry["filename"] for entry in history}

    candidates = [img for img in image_files if img.name not in uploaded]

    if not candidates:
        log.info("All images have already been uploaded")
        return None

    return random.choice(candidates)


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

    image_path = select_next_image(image_files)
    if not image_path:
        return

    log.info("Selected image: %s", image_path.name)

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

        save_uploaded_image(image_path.name, f"{file_size_mb:.2f} MB")

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
