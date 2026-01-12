import logging
import subprocess
import time

from samsungtvws import SamsungTVWS
from config import UPLOAD_SCRIPT, SET_SCRIPT, TV_IP

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

    # Short delay between scripts to avoid race conditions
    time.sleep(2)

    subprocess.run(["python3", SET_SCRIPT], check=False)

    log.info("Art-Mode-on-Steroids execution finished")
