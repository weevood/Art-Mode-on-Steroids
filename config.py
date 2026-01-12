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
TV_IP = "192.168.1.20"

# Execution interval (in seconds) must be >= 35
INTERVAL = 60

# Matte type and color
# MATTE TYPES (not all matte types work for all images)
    # 'none' 'modernthin' 'modern' 'modernwide' 'flexible' 'shadowbox' 'panoramic' 'triptych' 'mix' 'squares'
# MATTE COLORS
    # 'black' 'neutral' 'antique' 'warm' 'polar' 'sand' 'seafoam' 'sage' 'burgandy' 'navy' 'apricot' 'byzantine' 'lavender' 'redorange' 'skyblue' 'turquoise'
MATTE = "shadowbox_antique"
