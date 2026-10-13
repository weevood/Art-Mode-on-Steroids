#!/usr/bin/env python3
"""Ban the artwork currently displayed on Samsung, then advance immediately.

Run from iOS Shortcuts over SSH:
cd /home/pi/Art-Mode-on-Steroids && ./venv/bin/python ban_current.py
"""
from __future__ import annotations

import json
import logging
import subprocess
import sys
import time

from art_engine import BLOCKLIST, NEXT_REQUEST, atomic_write, history, request_next, run_cycle, tv_call

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def main() -> int:
    try:
        current = tv_call("current", timeout=18)
        cid = current.get("content_id") if isinstance(current, dict) else None
        if not cid:
            print("ERROR: Cannot determine the artwork currently displayed; nothing changed.")
            return 1

        # Select the most recent history entry for that exact Samsung content_id.
        matching = [entry for entry in history() if entry.get("content_id") == cid
                    and entry.get("managed_by") == "art-mode-on-steroids-v2"
                    and entry.get("filename")]
        if not matching:
            print(f"ERROR: Current Samsung artwork {cid} was not uploaded by Art Mode. "
                  "Refusing to ban a different photo.")
            return 2
        filename = matching[-1]["filename"]
        if BLOCKLIST.exists():
            entries = json.loads(BLOCKLIST.read_text(encoding="utf-8"))
            if not isinstance(entries, list):
                raise ValueError("Invalid exclusion file; no changes made")
        else:
            entries = []
        if filename not in entries:
            entries.append(filename)
            atomic_write(BLOCKLIST, (json.dumps(sorted(set(entries)), indent=2) + "\n").encode())
        print(f"BANNED: {filename} (Samsung {cid})", flush=True)

        # The running loop handles the request after its current cycle. Never run
        # two competing Samsung uploads concurrently.
        active = subprocess.run(["systemctl", "is-active", "--quiet", "art-mode.service"]).returncode == 0
        if active:
            previous_count = len(history())
            request_next()
            print("NEXT: immediate rotation requested; waiting for the active service.", flush=True)
            for _ in range(100):
                latest = history()
                if len(latest) > previous_count and latest[-1].get("content_id") != cid:
                    print("OK: next image displayed; banned image cannot be picked again.")
                    return 0
                time.sleep(2)
            print("ERROR: rotation was requested but not confirmed. Check journalctl -u art-mode.service.")
            return 3

        # Deliberately keep art-mode.service stopped (fixed-image mode).
        print("NEXT: running exactly one new cycle, leaving the service stopped.", flush=True)
        if run_cycle():
            print("OK: next image displayed; banned image cannot be picked again.")
            return 0
        print("ERROR: the image is banned, but advancing failed. Check TV and Pi logs.")
        return 4
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 5


if __name__ == "__main__":
    sys.exit(main())
