"""Samsung The Frame runner using isolated, time-bounded TV operations."""
from __future__ import annotations
import json
import logging
import os
import random
import multiprocessing as mp
from queue import Empty
import sys
import time
from datetime import date, datetime, timezone
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter, ImageOps
from samsungtvws import SamsungTVWS
from config import IMAGES_DIR, LAST_IMAGE_FILE, MATTE, TV_IP, TV_MAC

LOG = logging.getLogger("art-mode")
ROOT = Path(__file__).resolve().parent
WALLPAPER = ROOT / "current_wallpaper.jpg"
BLOCKLIST = ROOT / "excluded_photos.json"
NEXT_REQUEST = ROOT / ".next_photo_requested"
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
    """Calendar distance, independent of year (including year boundary)."""
    if when is None or when > today:
        return 6, 366
    if (when.month, when.day) == (2, 29) and not _is_leap(today.year):
        anniversary = date(today.year, 2, 28)
    else:
        anniversary = date(today.year, when.month, when.day)
    # Compare dates in adjacent years to handle Dec 31 / Jan 1 properly.
    distances = []
    for year in (today.year - 1, today.year, today.year + 1):
        try:
            point = anniversary.replace(year=year)
            distances.append(abs((point - today).days))
        except ValueError:
            continue
    distance = min(distances)
    if distance == 0:
        return 0, 0
    if distance <= 1:
        return 1, distance
    if distance <= 3:
        return 2, distance
    if distance <= 7:
        return 3, distance
    if distance <= 14:
        return 4, distance
    return 5, distance


def _is_leap(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)



def excluded_photos() -> set[str]:
    try:
        entries = json.loads(BLOCKLIST.read_text(encoding="utf-8"))
        if not isinstance(entries, list):
            raise ValueError("Invalid exclusion list")
        return set(str(x) for x in entries)
    except FileNotFoundError:
        return set()


def request_next() -> None:
    atomic_write(NEXT_REQUEST, b"next")


def choose_photo() -> tuple[Path, list[dict]] | None:
    files = sorted(p for p in IMAGES_DIR.rglob("*") if p.is_file() and p.suffix.lower() in EXTENSIONS) if IMAGES_DIR.is_dir() else []
    excluded = excluded_photos()
    files = [p for p in files if p.relative_to(IMAGES_DIR).as_posix() not in excluded]
    if not files:
        LOG.error("No images found under %s", IMAGES_DIR)
        return None
    items = history()
    seen = {e.get("filename") for e in items if isinstance(e, dict)}
    remaining = [p for p in files if p.relative_to(IMAGES_DIR).as_posix() not in seen and p.name not in seen]
    if not remaining:
        LOG.info("All %d photos used; starting a fresh rotation", len(files))
        remaining = files
        # Keep ownership records so previously uploaded TV artworks can be cleaned up.
    today = date.today()
    # Favour anniversary photos but mix in general memories and avoid repeating
    # one day/album burst. Recent history is scoped to today's available candidates.
    recent = [str(e.get("filename", "")) for e in items[-12:] if isinstance(e, dict)]
    recent_days = []
    for name in recent[-6:]:
        parts = name.split("/")
        if len(parts) >= 3:
            recent_days.append("/".join(parts[:3]))
    choices = []
    for path in remaining:
        category, distance = priority(photo_date(path), today)
        day_key = "/".join(path.relative_to(IMAGES_DIR).parts[:3])
        weight = (12, 9, 6, 4, 2, 1)[category]
        if day_key in recent_days:
            weight *= 0.15
        choices.append(weight)
    selected = random.choices(remaining, weights=choices, k=1)[0]
    LOG.info("Selected %s (anniversary priority %d, distance %d days)",
             selected.relative_to(IMAGES_DIR), *priority(photo_date(selected), today))
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
    mac = TV_MAC.strip()
    if not mac:
        LOG.warning("TV_MAC missing in config.py: cannot wake the TV")
        return
    try:
        from wakeonlan import send_magic_packet
        send_magic_packet(mac)
        LOG.info("Sent Wake-on-LAN to %s", mac)
    except Exception:
        LOG.exception("Wake-on-LAN failed")


def artwork_ids(art) -> set[str]:
    return {str(x["content_id"]) for x in art.available() if isinstance(x, dict) and x.get("content_id")}


def _tv_worker(queue, command: str, payload=None):
    """One fresh connection per operation; the parent can terminate a hung API."""
    tv = None
    try:
        tv = SamsungTVWS(host=TV_IP, name="ArtModeWorker")
        art = tv.art()
        if command == "current":
            result = art.get_current()
        elif command == "inventory":
            result = artwork_ids(art)
        elif command == "upload":
            result = art.upload(payload, file_type="jpeg", matte=MATTE)
        elif command == "select":
            result = art.select_image(payload)
        elif command == "delete":
            result = art.delete(payload)
        else:
            raise ValueError(command)
        queue.put(("ok", result))
    except BaseException as exc:
        queue.put(("error", repr(exc)))
    finally:
        if tv:
            try:
                tv.close()
            except Exception:
                pass


def tv_call(command: str, payload=None, timeout: int = 15):
    """Hard deadline regardless of a hung Samsung WebSocket recv()."""
    queue = mp.Queue()
    proc = mp.Process(target=_tv_worker, args=(queue, command, payload))
    proc.start()
    try:
        try:
            status, result = queue.get(timeout=timeout)
        except Empty as exc:
            raise TimeoutError(f"Samsung {command} did not respond within {timeout}s") from exc
        if status != "ok":
            raise RuntimeError(f"Samsung {command} error: {result}")
        return result
    finally:
        if proc.is_alive():
            proc.terminate()
        proc.join(timeout=2)
        if proc.is_alive():
            proc.kill()
            proc.join()
        queue.close()


def inventory() -> set[str]:
    return tv_call("inventory", timeout=18)


def upload_and_select(data: bytes) -> str:
    """Upload exactly once, identify by inventory delta, then select directly."""
    wake_tv()
    before = inventory()
    LOG.info("TV inventory before upload: %d unique artworks", len(before))
    try:
        tv_call("upload", data, timeout=15)
        LOG.info("Samsung upload returned normally")
    except (TimeoutError, RuntimeError) as exc:
        LOG.warning("Upload call not acknowledged (%s); checking actual TV inventory", exc)

    # Never repeat upload on an absent acknowledgment: it might already exist.
    deadline = time.monotonic() + 50
    new_id = None
    while time.monotonic() < deadline:
        time.sleep(3)
        try:
            additions = inventory() - before
        except Exception as exc:
            LOG.warning("Inventory check failed: %s", exc)
            continue
        LOG.info("New artwork IDs after upload: %s", sorted(additions))
        if len(additions) > 1:
            raise RuntimeError("Ambiguous multiple TV additions; refusing to select")
        if len(additions) == 1:
            new_id = next(iter(additions))
            break
    if not new_id:
        raise RuntimeError("Unconfirmed upload: refusing to resend blindly")

    # No set_artmode OFF/ON: confirmed harmful for this Frame 2023 firmware.
    result = tv_call("select", new_id, timeout=18)
    if not isinstance(result, dict) or str(result.get("content_id")) != new_id or result.get("is_shown") != "Yes":
        raise RuntimeError(f"Samsung did not confirm selection of {new_id}: {result!r}")
    LOG.info("Selected and confirmed Samsung artwork %s", new_id)
    return new_id


def remove_previous_managed_artworks(current_id: str) -> None:
    """Remove only historical artworks positively tagged as owned by v2."""
    records = history()
    obsolete = [item for item in records if item.get("managed_by") == "art-mode-on-steroids-v2"
                and item.get("content_id") and item["content_id"] != current_id
                and item.get("deleted") is not True]
    if not obsolete:
        return
    try:
        present = inventory()
    except Exception as exc:
        LOG.warning("Cleanup inventory unavailable: %s", exc)
        return
    for item in obsolete:
        cid = str(item["content_id"])
        if cid not in present:
            item["deleted"] = True
        else:
            try:
                tv_call("delete", cid, timeout=15)
            except Exception as exc:
                LOG.warning("Delete %s not acknowledged: %s", cid, exc)
            # A write might complete even when it times out: trust the inventory.
            try:
                item["deleted"] = cid not in inventory()
            except Exception as exc:
                LOG.warning("Could not verify deletion of %s: %s", cid, exc)
                item["deleted"] = False
        save_history(records)
        if item["deleted"]:
            LOG.info("Confirmed removal of prior managed artwork %s", cid)


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
            "managed_by": "art-mode-on-steroids-v2",
            "deleted": False,
            "image_date": when.isoformat() if when else None,
            "activated_at": datetime.now(timezone.utc).isoformat(),
        })
        save_history(items)
        remove_previous_managed_artworks(content_id)
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
        success = run_cycle()
        # Back off after any failed cycle to avoid flooding TV with orphaned uploads.
        delay = INTERVAL if success else max(INTERVAL, 1200)
        remaining = max(1, delay - (time.monotonic() - started))
        while remaining > 0:
            if NEXT_REQUEST.exists():
                NEXT_REQUEST.unlink(missing_ok=True)
                LOG.info("Immediate rotation requested")
                break
            pause = min(2, remaining)
            time.sleep(pause)
            remaining -= pause


if __name__ == "__main__":
    main("--loop" in sys.argv)
