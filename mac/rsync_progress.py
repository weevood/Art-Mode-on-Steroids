#!/usr/bin/env python3
"""Show a responsive global file progress indicator for macOS rsync."""
import os
import pty
import re
import select
import subprocess
import sys
import time

def main():
    if len(sys.argv) < 3:
        print("usage: rsync_progress.py COUNT RSYNC_ARGS...", file=sys.stderr)
        return 2
    total = int(sys.argv[1])
    args = sys.argv[2:]
    master, slave = pty.openpty()
    proc = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=slave,
                            stderr=slave, start_new_session=True)
    os.close(slave)
    done = 0
    pending = b""
    last_display = 0.0
    errors = []
    started = time.monotonic()

    def show(force=False):
        nonlocal last_display
        now = time.monotonic()
        if not force and now - last_display < 2:
            return
        elapsed = int(now - started)
        pct = min(100, int(100 * done / total)) if total else 100
        bars = int(pct / 2)
        sys.stdout.write(
            "\r[3/3] Upload [" + "#" * bars + "-" * (50 - bars)
            + f"] {pct:3d}% ({done}/{total} fichiers) · {elapsed}s"
            + (" " * 8)
        )
        sys.stdout.flush()
        last_display = now

    show(True)
    try:
        while True:
            ready, _, _ = select.select([master], [], [], 2)
            if ready:
                try:
                    chunk = os.read(master, 65536)
                except OSError:
                    chunk = b""
                if not chunk:
                    break
                pending += chunk
                while b"\n" in pending:
                    raw, pending = pending.split(b"\n", 1)
                    line = raw.decode("utf-8", "replace").strip("\r")
                    # --out-format='%n' prints each successfully transferred file.
                    if re.search(r"\.(?:jpg|jpeg)$", line, re.IGNORECASE):
                        done += 1
                        show(True)
                    elif line and not re.match(r"^(sending incremental file list|\./)$", line):
                        if any(word in line.lower() for word in ("error", "failed", "rsync:")):
                            errors.append(line)
            show()
            if proc.poll() is not None and not ready:
                break
    except KeyboardInterrupt:
        proc.terminate()
        proc.wait()
        raise
    finally:
        os.close(master)
    result = proc.wait()
    sys.stdout.write("\n")
    if result:
        for line in errors[-10:]:
            print(line, file=sys.stderr)
        print(f"rsync failed (exit {result})", file=sys.stderr)
    else:
        print(f"[3/3] Transfer complete: {done} JPEG files, {int(time.monotonic()-started)}s.")
    return result

if __name__ == "__main__":
    sys.exit(main())
