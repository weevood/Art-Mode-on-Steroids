import logging
import json
import time

from pathlib import Path
from datetime import datetime
from samsungtvws import SamsungTVWS
from samsungtvws.exceptions import ConnectionFailure, ResponseError

from config import SET_SCRIPT, TV_IP, LAST_IMAGE_FILE

# =========================
# Logging configuration
# =========================
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(SET_SCRIPT)


# =========================
# Functions
# =========================
def load_upload_history():
    """
    Load upload history from the local JSON file.
    Returns a list of uploaded images metadata.
    """
    if LAST_IMAGE_FILE.exists():
        try:
            with open(LAST_IMAGE_FILE, "r") as f:
                return json.load(f).get("uploaded_images", [])
        except Exception as exc:
            log.warning("Failed to read upload history: %s", exc)
    return []


def save_uploaded_image(art, content_id, image_date, artwork_to_del):
    """
    Update the last uploaded image entry by attaching the TV content_id
    and activation metadata.
    """
    history = load_upload_history()
    updated = False

    for entry in history:
        # Look for a locally uploaded image not yet linked to the TV
        if entry.get("content_id") in (None, "", "PENDING"):
            entry["content_id"] = content_id
            entry["image_date"] = image_date
            entry["activated_at"] = datetime.utcnow().isoformat()
            updated = True

            log.info(
                "History updated for local file: %s",
                entry.get("filename", "UNKNOWN")
            )
        if entry.get("content_id") == artwork_to_del["content_id"]:
            delete_artwork(art, artwork_to_del)
            entry["deleted"] = "True"

    if not updated:
        log.warning("No pending history entry found — nothing to update")
        return

    with open(LAST_IMAGE_FILE, "w") as f:
        json.dump({"uploaded_images": history}, f, indent=2)

    log.info("History successfully saved")


def parse_image_date(date_str):
    """
    Parse Samsung Art image date format.
    """
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%Y:%m:%d %H:%M:%S")
    except ValueError as exc:
        log.error("Invalid image date format: %s", exc)
        return None


def get_latest_uploaded_artwork(art):
    """
    Retrieve the most recently uploaded artwork from the TV.
    """
    log.info("Fetching Art Mode artworks...")
    artworks = art.available()

    valid = []
    for artwork in artworks:
        dt = parse_image_date(artwork.get("image_date", ""))
        if dt:
            valid.append((dt, artwork))

    if not valid:
        log.error("No valid artwork found")
        return None

    # Sort by date descending
    valid.sort(key=lambda x: x[0], reverse=True)
    return [valid[0][1], valid[2][1]]


def activate_latest_artwork(art, artwork):
    """
    Activate the most recently uploaded artwork on the TV.
    """

    content_id = artwork["content_id"]
    image_date = artwork["image_date"]

    log.info(
        "Activating artwork %s (date: %s)",
        content_id, image_date
    )

    art.select_image(content_id)
    return content_id, image_date

def delete_artwork(art, artwork):
    """
    Delete an artwork on the TV.
    """

    content_id = artwork["content_id"]
    image_date = artwork["image_date"]

    log.info(
        "Deleting artwork %s (date: %s)",
        content_id, image_date
    )

    art.delete(content_id)
    return content_id, image_date


# =========================
# Main entry point
# =========================
def main():
    tv = None
    try:
        tv = SamsungTVWS(host=TV_IP, name=f"ArtModeSet-{time.time()}")
        art = tv.art()

        if not art.supported():
            log.error("Art Mode is not supported on this TV")
            return
        
        [artwork, art_to_del] = get_latest_uploaded_artwork(art)
        if not artwork:
            log.error("Nothing to activate")
            return  
        else:
            result = activate_latest_artwork(art, artwork)
            content_id, image_date = result
            save_uploaded_image(art, content_id, image_date, art_to_del)

        log.info("✓ Art Mode image successfully displayed")

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
                log.info("Connection closed")
            except Exception:
                pass


if __name__ == "__main__":
    main()
