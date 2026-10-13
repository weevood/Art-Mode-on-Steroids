"""Preview or delete Samsung artworks uploaded since 2026-08-01.

WARNING: Samsung image_date does not identify which app/user uploaded an image.
Default mode is read-only. Deletion requires --delete and an explicit confirmation.
Each network operation has a hard process deadline.
"""
from __future__ import annotations
import argparse
from datetime import datetime, date
import multiprocessing as mp
from queue import Empty
from samsungtvws import SamsungTVWS
from config import TV_IP

CUTOFF = date(2026, 6, 1) # Keep only pictures before June 2026
TIMEOUT = 20


def operation(queue, command, content_id=None):
    tv = None
    try:
        tv = SamsungTVWS(host=TV_IP, name="ArtModeCleanup")
        art = tv.art()
        if command == "list":
            result = art.available()
        else:
            result = art.delete(content_id)
        queue.put(("ok", result))
    except BaseException as exc:
        queue.put(("error", repr(exc)))
    finally:
        if tv:
            try:
                tv.close()
            except Exception:
                pass


def call(command, content_id=None):
    queue = mp.Queue()
    proc = mp.Process(target=operation, args=(queue, command, content_id))
    proc.start()
    try:
        status, value = queue.get(timeout=TIMEOUT)
        if status != "ok":
            raise RuntimeError(value)
        return value
    except Empty:
        raise TimeoutError(f"Samsung {command} exceeded {TIMEOUT}s")
    finally:
        if proc.is_alive():
            proc.terminate()
        proc.join(timeout=2)
        if proc.is_alive():
            proc.kill()
            proc.join()
        queue.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--delete", action="store_true", help="Delete qualifying images after typing confirmation")
    args = parser.parse_args()
    all_images = call("list")
    by_id = {}
    for image in all_images:
        if not isinstance(image, dict):
            continue
        cid = image.get("content_id")
        raw = image.get("image_date")
        if not cid or not raw:
            continue
        try:
            uploaded = datetime.strptime(raw.strip(), "%Y:%m:%d %H:%M:%S").date()
        except (ValueError, TypeError):
            continue
        if uploaded >= CUTOFF:
            # Samsung may report the same artwork multiple times.
            # Each content_id must appear (and be deleted) only once.
            key = str(cid)
            candidate = (uploaded, key, raw)
            if key not in by_id or candidate[0] > by_id[key][0]:
                by_id[key] = candidate
    candidates = sorted(by_id.values(), reverse=True)
    all_ids = {str(image["content_id"]) for image in all_images if isinstance(image, dict) and image.get("content_id")}
    print(f"Total Samsung artworks: {len(all_ids)} unique ({len(all_images)} entries returned)")
    print(f"Artworks dated since {CUTOFF.isoformat()}: {len(candidates)}")
    for _, cid, raw in candidates:
        print(f"  {cid:20s} {raw}")
    if not args.delete:
        print("\nPREVIEW ONLY: nothing deleted. Use --delete after reviewing the list.")
        return
    if not candidates:
        print("Nothing to delete.")
        return
    print("\nWARNING: This includes EVERY qualifying Samsung artwork, even personal uploads.")
    confirmation = input(f"Type DELETE {len(candidates)} to permanently delete them: ")
    if confirmation != f"DELETE {len(candidates)}":
        print("Cancelled. Nothing deleted.")
        return
    failures = []
    for index, (_, cid, _) in enumerate(candidates, 1):
        print(f"[{index}/{len(candidates)}] Deleting {cid}...", flush=True)
        try:
            call("delete", cid)
        except Exception as exc:
            # Timeouts can occur after TV processed the deletion.
            print(f"  Unconfirmed: {exc}", flush=True)
            failures.append(cid)
    print(f"Completed. Unconfirmed operations: {len(failures)}")
    print("Run without --delete again to verify the remaining images.")
    if failures:
        print("Unconfirmed IDs:", ", ".join(failures))


if __name__ == "__main__":
    main()
