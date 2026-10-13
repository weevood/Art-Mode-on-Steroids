"""Reliable Samsung The Frame runner; keeps the legacy Art Mode refresh workaround."""
from __future__ import annotations
import json
import logging
import os
import random
import threading
import sys
import time
from datetime import date, datetime, timezone
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter, ImageOps
from samsungtvws import SamsungTVWS
from config import IMAGES_DIR, LAST_IMAGE_FILE, MATTE, TV_IP

LOG = logging.getLogger("art-mode")
ROOT = Path(__file__).resolve().parent
WALLPAPER = ROOT / "current_wallpaper.jpg"
EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp"}
SIZE = (1920, 1080)  # QE32LS03C native Full HD
CONNECT_ATTEMPTS = 3
PAUSE_BETWEEN_ATTEMPTS = 12


def history() -> list[dict]:
    try:
        value = json.loads(Path(LAST_IMAGE_FILE).read_text(encoding="utf-8"))
        return value.get("uploaded_images", []) if isinstance(value.get("uploaded_images"), list) else []
    except (FileNotFoundError, OSError, ValueError, TypeError) as exc:
        LOG.warning("History unavailable (%s); using empty history", exc)
        return []


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    try:
        temp.write_bytes(data)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def save_history(items: list[dict]) -> None:
    atomic_write(Path(LAST_IMAGE_FILE), json.dumps({"uploaded_images": items}, indent=2, ensure_ascii=False).encode())


def photo_date(path: Path) -> date | None:
    try:
        y, m, d = path.relative_to(IMAGES_DIR).parts[:3]
        return date(int(y), int(m), int(d))
    except (ValueError, IndexError):
        return None


def priority(when: date | None, today: date) -> tuple[int, int]:
    if when is None or when >= today:
        return 6, 0
    if (when.month, when.day) == (today.month, today.day):
        return 0, 0
    try:
        anniversary = date(when.year, today.month, today.day)
    except ValueError:
        return 6, 0
    delta = abs((when - anniversary).days)
    for index, limit in enumerate((1, 2, 3, 7), start=1):
        if delta <= limit:
            return index, delta
    return (5, delta) if when.month == today.month else (6, delta)


def choose_photo() -> tuple[Path, list[dict]] | None:
    files = sorted(p for p in IMAGES_DIR.rglob("*") if p.is_file() and p.suffix.lower() in EXTENSIONS) if IMAGES_DIR.is_dir() else []
    if not files:
        LOG.error("No images found under %s", IMAGES_DIR)
        return None
    items = history()
    seen = {e.get("filename") for e in items if isinstance(e, dict)}
    remaining = [p for p in files if p.relative_to(IMAGES_DIR).as_posix() not in seen and p.name not in seen]
    if not remaining:
        LOG.info("All %d photos used; starting a fresh rotation", len(files))
        remaining, items = files, []
    today = date.today()
    best = min(priority(photo_date(p), today)[0] for p in remaining)
    candidates = [p for p in remaining if priority(photo_date(p), today)[0] == best]
    selected = random.choice(candidates)
    LOG.info("Selected %s (priority %d)", selected.relative_to(IMAGES_DIR), best)
    return selected, items


def make_image(path: Path) -> bytes:
    with Image.open(path) as original:
        image = ImageOps.exif_transpose(original).convert("RGB")
        image = ImageOps.fit(image, SIZE, method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
        image = image.filter(ImageFilter.SMOOTH_MORE)
        image = ImageEnhance.Contrast(image).enhance(1.08)
        image = ImageEnhance.Color(image).enhance(0.95)
        image = ImageEnhance.Sharpness(image).enhance(0.8)
        stream = BytesIO()
        image.save(stream, "JPEG", quality=92)
        return stream.getvalue()


def wake_tv() -> None:
    mac = os.environ.get("ART_TV_MAC", "").strip()
    if not mac:
        LOG.warning("ART_TV_MAC missing: cannot wake an off TV via Wake-on-LAN")
        return
    try:
        from wakeonlan import send_magic_packet
        send_magic_packet(mac)
        LOG.info("Sent Wake-on-LAN to %s", mac)
    except Exception:
        LOG.exception("Wake-on-LAN failed")


def artwork_ids(art) -> set[str]:
    return {str(x["content_id"]) for x in art.available() if isinstance(x, dict) and x.get("content_id")}


def upload_and_select(data: bytes) -> str:
    """Upload once; verify TV inventory even if Samsung's upload call hangs.

    A timed-out upload is never repeated automatically: it may have succeeded.
    """
    wake_tv()
    before = None
    last_error = None
    for attempt in range(1, CONNECT_ATTEMPTS + 1):
        tv = None
        try:
            tv = SamsungTVWS(host=TV_IP, name="ArtModeInventory")
            art = tv.art()
            if not art.supported():
                raise RuntimeError("Samsung Art Mode unavailable")
            before = artwork_ids(art)
            break
        except Exception as exc:
            last_error = exc
            LOG.warning("Inventory attempt %d failed: %s", attempt, exc)
            time.sleep(PAUSE_BETWEEN_ATTEMPTS)
        finally:
            if tv:
                try:
                    tv.close()
                except Exception:
                    pass
    if before is None:
        raise RuntimeError("Cannot inventory Samsung artworks before upload") from last_error

    completed = threading.Event()
    upload_errors = []
    def do_upload():
        tv = None
        try:
            tv = SamsungTVWS(host=TV_IP, name="ArtModeUpload")
            tv.art().upload(data, file_type="jpeg", matte=MATTE)
        except Exception as exc:
            upload_errors.append(exc)
        finally:
            if tv:
                try:
                    tv.close()
                except Exception:
                    pass
            completed.set()

    threading.Thread(target=do_upload, daemon=True).start()
    # Poll a separate connection. The legacy upload socket may hang even after
    # the TV has accepted the artwork. Do not issue a second upload.
    deadline = time.monotonic() + 75
    new_id = None
    while time.monotonic() < deadline:
        time.sleep(3)
        probe = None
        try:
            probe = SamsungTVWS(host=TV_IP, name="ArtModeVerify")
            new = artwork_ids(probe.art()) - before
            if len(new) == 1:
                new_id = new.pop()
                break
            if len(new) > 1:
                raise RuntimeError("Multiple new artworks found: refusing ambiguous selection")
        except RuntimeError:
            raise
        except Exception as exc:
            LOG.warning("Inventory probe failed: %s", exc)
        finally:
            if probe:
                try:
                    probe.close()
                except Exception:
                    pass
        if completed.is_set() and upload_errors:
            LOG.warning("Upload returned an error; checking TV inventory until deadline")
    if not new_id:
        raise RuntimeError("Upload remains unverified; not retrying to prevent duplicates")

    tv = None
    try:
        tv = SamsungTVWS(host=TV_IP, name="ArtModeSelect")
        art = tv.art()
        # Preserve Samsung Art Mode refresh workaround after a verified upload.
        art.set_artmode(False)
        time.sleep(1)
        art.set_artmode(True)
        time.sleep(2)
        art.select_image(new_id)
        LOG.info("Selected confirmed artwork %s", new_id)
        return new_id
    finally:
        if tv:
            try:
                tv.close()
            except Exception:
                pass


def run_cycle() -> bool:
    choice = choose_photo()
    if not choice:
        return False
    path, items = choice
    try:
        data = make_image(path)
        content_id = upload_and_select(data)
        # Store exactly the same processed JPEG as the one sent to the TV.
        # No screen / no graphic session is required for this atomic disk write.
        atomic_write(WALLPAPER, data)
        when = photo_date(path)
        items.append({
            "filename": path.relative_to(IMAGES_DIR).as_posix(),
            "content_id": content_id,
            "image_date": when.isoformat() if when else None,
            "activated_at": datetime.now(timezone.utc).isoformat(),
        })
        save_history(items)
        LOG.info("Cycle finished; wallpaper updated at %s", WALLPAPER)
        return True
    except Exception:
        LOG.exception("Cycle failed; will retry on next cycle")
        return False


def main(continuous: bool = False) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if not continuous:
        run_cycle()
        return
    from config import INTERVAL
    LOG.info("Continuous Art Mode started with interval=%ds", INTERVAL)
    while True:
        started = time.monotonic()
        run_cycle()
        time.sleep(max(1, INTERVAL - (time.monotonic() - started)))


if __name__ == "__main__":
    main("--loop" in sys.argv)
