"""Optional graphical-session wallpaper observer. Never required for the TV runner."""
import logging
import os
import shutil
import subprocess
import time
from pathlib import Path

FILE = Path(__file__).resolve().parent / "current_wallpaper.jpg"
LOG = logging.getLogger("wallpaper")


def main():
    logging.basicConfig(level=logging.INFO)
    if not os.environ.get("WAYLAND_DISPLAY"):
        LOG.info("No Wayland graphical session; exiting harmlessly")
        return
    if not shutil.which("swaybg"):
        LOG.error("swaybg missing; install with sudo apt install swaybg")
        return
    process = None
    last = None
    try:
        while True:
            if FILE.is_file():
                stat = FILE.stat()
                signature = (stat.st_mtime_ns, stat.st_size)
                if signature != last or (process and process.poll() is not None):
                    if process and process.poll() is None:
                        process.terminate()
                        try:
                            process.wait(timeout=4)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait()
                    process = subprocess.Popen(["swaybg", "-i", str(FILE), "-m", "fill"])
                    last = signature
                    LOG.info("Desktop wallpaper refreshed")
            time.sleep(3)
    except KeyboardInterrupt:
        pass
    finally:
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=4)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    main()
