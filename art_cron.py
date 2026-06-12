import sys
import logging
import subprocess
import json
import time

from config import UPLOAD_SCRIPT, SET_SCRIPT, INTERVAL, LAST_IMAGE_FILE

# =========================
# Logging configuration
# =========================
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("art_cron.py")


# =========================
# Functions
# =========================
def reset_uploaded_images_file() -> None:
    """
    Overwrite the uploaded images JSON file with an empty uploaded_images list.
    """
    data = {
        "uploaded_images": []
    }

    with open(LAST_IMAGE_FILE, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=2)


def run_script(script_name: str) -> None:
    """
    Execute a Python script as a subprocess.

    Parameters
    ----------
    script_name : str
        Name of the script to execute
    """
    log.info("Starting script: %s", script_name)
    try:
        subprocess.run([sys.executable, script_name], check=False)
    except Exception as exc:
        log.error(
            "Error while executing %s: %s",
            script_name,
            exc,
            exc_info=True
        )


# =========================
# Main loop
# =========================
def main() -> None:
    """
    Continuous runner.

    Executes the upload and set scripts periodically,
    ensuring a fixed execution interval.
    """
    log.info("Art-Mode-on-Steroids cron runner started (interval: %s seconds)", INTERVAL)
    
    reset_uploaded_images_file()

    while True:
        cycle_start = time.time()

        run_script(UPLOAD_SCRIPT)

        # Short delay between scripts to avoid race conditions
        time.sleep(2)

        run_script(SET_SCRIPT)

        elapsed = time.time() - cycle_start
        sleep_time = max(0, INTERVAL - elapsed)

        log.info("Cycle completed — sleeping for %s seconds", round(sleep_time, 1))
        time.sleep(sleep_time)


# =========================
# Entry point
# =========================
if __name__ == "__main__":
    main()
