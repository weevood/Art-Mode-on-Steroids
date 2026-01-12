import logging
import subprocess

from config import UPLOAD_SCRIPT, SET_SCRIPT

# =========================
# Logging configuration
# =========================
logging.basicConfig(level=logging.DEBUG)
log = logging.getLogger("art.py")


# =========================
# Entry point
# =========================
if __name__ == "__main__":
    """
    One-shot execution script.

    This script sequentially executes:
    - the upload script
    - the set script

    Errors in subprocess execution do not stop the program.
    """

    log.info("Starting Art-Mode-on-Steroids one-shot execution")

    subprocess.run(["python3", UPLOAD_SCRIPT], check=False)
    subprocess.run(["python3", SET_SCRIPT], check=False)

    log.info("Art-Mode-on-Steroids execution finished")
