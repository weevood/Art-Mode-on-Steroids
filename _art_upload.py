import json
import logging
import random
import threading
import time
import cv2
import numpy as np

from datetime import datetime
from pathlib import Path
from samsungtvws import SamsungTVWS
from samsungtvws.exceptions import ConnectionFailure, ResponseError
from PIL import Image, ImageEnhance, ImageFilter
from io import BytesIO

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


TV_IP = "192.168.1.20"
IMAGES_DIR = Path(__file__).parent / "images"
LAST_IMAGE_FILE = Path(__file__).parent / "uploaded_images.json"

# Extensions d'images supportées
SUPPORTED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp'}

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("art-mode")

def load_upload_history():
    if LAST_IMAGE_FILE.exists():
        try:
            with open(LAST_IMAGE_FILE, "r") as f:
                return json.load(f).get("uploaded_images", [])
        except Exception as e:
            log.warning("Erreur lecture historique: %s", e)
    return []


def save_uploaded_image(filename):
    history = load_upload_history()

    # éviter doublons
    if any(h["filename"] == filename for h in history):
        log.info("Image déjà présente dans l'historique")
        return

    history.append({
        "filename": filename,
        "content_id": "PENDING",
        "image_date": "PENDING",
        "activated_at": datetime.utcnow().isoformat()
    })

    with open(LAST_IMAGE_FILE, "w") as f:
        json.dump({"uploaded_images": history}, f, indent=2)

    log.info("Historique mis à jour")

def get_image_files():
    """Récupère tous les fichiers images du dossier local."""
    if not IMAGES_DIR.exists():
        log.error("Le dossier 'images' n'existe pas: %s", IMAGES_DIR)
        return []
    
    image_files = [
        f for f in IMAGES_DIR.iterdir() 
        if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
    ]
    
    return sorted(image_files)

def upload_image(art, image_data, file_extension):
    # MATTE TYPES (not all matte types work for all images)
        # 'none' 'modernthin' 'modern' 'modernwide' 'flexible' 'shadowbox' 'panoramic' 'triptych' 'mix' 'squares'
    # MATTE COLORS
        # 'black' 'neutral' 'antique' 'warm' 'polar' 'sand' 'seafoam' 'sage' 'burgandy' 'navy' 'apricot' 'byzantine' 'lavender' 'redorange' 'skyblue' 'turquoise'
    art.upload(image_data, file_type=file_extension, matte="shadowbox_antique")

    log.info("Activation du Art Mode...")
    art.set_artmode(False)
    time.sleep(1)
    art.set_artmode(True)
    time.sleep(2)

def select_next_image(image_files):
    history = load_upload_history()
    uploaded_filenames = {h["filename"] for h in history}

    candidates = [
        img for img in image_files
        if img.name not in uploaded_filenames
    ]

    if not candidates:
        log.info("Toutes les images ont déjà été uploadées")
        return None

    return random.choice(candidates)

def make_artistic(image_bytes):
    # Charger image
    pil_img = Image.open(BytesIO(image_bytes)).convert("RGB")

    # --- Effet peinture léger ---
    # cv_img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
    # cv_img = cv2.stylization(
    #     cv_img,
    #     sigma_s=60,   # taille des coups de pinceau
    #     sigma_r=0.45  # intensité
    # )
    # pil_img = Image.fromarray(cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB))

    # --- Réduction de la netteté numérique ---
    pil_img = pil_img.filter(ImageFilter.SMOOTH_MORE)

    # --- Ajustements artistiques ---
    pil_img = ImageEnhance.Contrast(pil_img).enhance(1.08)
    pil_img = ImageEnhance.Color(pil_img).enhance(0.95)
    pil_img = ImageEnhance.Sharpness(pil_img).enhance(0.8)

    # --- Export ---
    output = BytesIO()
    pil_img.save(output, format="JPEG", quality=92)
    return output.getvalue()

def main() -> None:
    # Vérifier que le dossier images existe
    if not IMAGES_DIR.exists():
        log.error("Le dossier 'images' n'existe pas. Créez-le et ajoutez des images.")
        return
    
    # Récupérer les images locales
    image_files = get_image_files()
    if not image_files:
        log.error("Aucune image trouvée dans le dossier 'images'")
        log.info("Extensions supportées: %s", ', '.join(SUPPORTED_EXTENSIONS))
        return
    
    log.info("Nombre d'images trouvées: %d", len(image_files))
    
    # Sélectionner la prochaine image
    image_path = select_next_image(image_files)
    
    if not image_path:
        log.error("Impossible de sélectionner une image")
        return
    
    log.info("Image sélectionnée: %s", image_path.name)
    
    # Vérifier la taille de l'image
    file_size_mb = image_path.stat().st_size / (1024 * 1024)
    log.info("Taille de l'image: %.2f MB", file_size_mb)
    
    # Charger l'image en mémoire
    log.info("Chargement de l'image...")
    with open(image_path, 'rb') as f:
        raw_image_data = f.read()
        log.info("Application de l'effet artistique...")
        image_data = make_artistic(raw_image_data)
    
    file_extension = image_path.suffix[1:].lower()
    if file_extension == 'jpg':
        file_extension = 'jpeg'
    
    # Connexion pour l'upload - sans token_file pour éviter les problèmes
    log.info("Connexion à la TV pour upload...")
    
    # Essayer d'abord sans token persistant - connexion fraîche à chaque fois
    tv = None
    try:
        tv = SamsungTVWS(host=TV_IP, name="ArtModeUpload")
        
        log.info("Obtention de l'interface Art...")
        art = tv.art()
        
        log.info("Vérification du support du mode Art...")
        if not art.supported():
            log.error("Le mode Art n'est pas supporté sur cette TV")
            return
        
        # Upload avec gestion d'erreur détaillée
        try:
            log.info("Upload de l'image (timeout 30s), veuillez patienter sans interrompre le processus...")

            upload_thread = threading.Thread(
                target=upload_image,
                args=(art, image_data, file_extension),
                daemon=True  # Le thread n'empêche pas la fin du programme
            )
            upload_thread.start()
            upload_thread.join(timeout=30)

            if upload_thread.is_alive():
                log.warning("L'upload ne s'est pas terminé après 30 secondes, mais a (certainement) été accepté.")
            else:
                log.info("✓ Upload terminé avant le timeout")

            # On continue le script dans tous les cas
            log.info("✓ Script poursuivi après upload")
            
            # Sauvegarder l'image affichée
            save_uploaded_image(
                filename=image_path.name
            )

            log.info("Upload terminé, arrêt du process pour reset Art Mode")
            tv.close()
            sys.exit(0)
            
        except Exception as upload_err:
            log.error("Erreur lors de l'upload: %s", upload_err)
            log.error("Type d'erreur: %s", type(upload_err).__name__)
            
            # Informations de debug
            log.info("--- Informations de debug ---")
            log.info("Taille image: %.2f MB", file_size_mb)
            log.info("Format: %s", file_extension)
            log.info("Nom fichier: %s", image_path.name)
            
            raise

    except ConnectionFailure as e:
        log.error("Échec de connexion: %s", e)
        
    except ResponseError as e:
        log.error("Erreur API: %s", e)
        
    except Exception as e:
        log.exception("Erreur inattendue: %s", e)
        
    finally:
        if tv:
            try:
                tv.close()
                log.info("Connexion fermée")
            except Exception:
                pass


if __name__ == "__main__":
    main()