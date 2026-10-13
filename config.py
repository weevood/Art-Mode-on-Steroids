"""
Global configuration for ART scripts.
All tunable constants should be defined here.
"""

from pathlib import Path

# Script names
UPLOAD_SCRIPT = "_art_upload.py"
SET_SCRIPT = "_art_set.py"

# Images files path
IMAGES_DIR = Path(__file__).parent / "images"
LAST_IMAGE_FILE = Path(__file__).parent / "uploaded_images.json"

# TV static IP address   
TV_IP = "192.168.X.X"
TV_MAC = "AA:BB:CC:DD:EE:FF"

# Execution interval (in seconds) must be >= 35, best with >= 90
INTERVAL = 1200

# Matte type and color
# MATTE TYPES (not all matte types work for all images)
    # 'none' 'modernthin' 'modern' 'modernwide' 'flexible' 'shadowbox' 'panoramic' 'triptych' 'mix' 'squares'
# MATTE COLORS
    # 'black' 'neutral' 'antique' 'warm' 'polar' 'sand' 'seafoam' 'sage' 'burgandy' 'navy' 'apricot' 'byzantine' 'lavender' 'redorange' 'skyblue' 'turquoise'
MATTE = "shadowbox_antique"

# Optional machine-specific overrides. This file is deliberately not tracked by Git.
try:
    from config_local import IMAGES_DIR as _LOCAL_IMAGES_DIR
except ImportError as exc:
    if exc.name != "config_local":
        raise
else:
    IMAGES_DIR = Path(_LOCAL_IMAGES_DIR)

try:
    import config_local as _local
except ModuleNotFoundError as exc:
    if exc.name != "config_local":
        raise
else:
    for _key in ("TV_IP", "TV_MAC", "INTERVAL", "MATTE", "LAST_IMAGE_FILE"):
        if hasattr(_local, _key):
            globals()[_key] = getattr(_local, _key)
    LAST_IMAGE_FILE = Path(LAST_IMAGE_FILE)
