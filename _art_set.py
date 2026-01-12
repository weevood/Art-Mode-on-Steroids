import logging
import json
import time
from pathlib import Path
from datetime import datetime

from samsungtvws import SamsungTVWS
from samsungtvws.exceptions import ConnectionFailure, ResponseError

# =========================
# CONFIG
# =========================
TV_IP = "192.168.1.20"
LAST_IMAGE_FILE = Path(__file__).parent / "uploaded_images.json"

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("art-set")


# =========================
# HISTORIQUE
# =========================
def load_upload_history():
    if LAST_IMAGE_FILE.exists():
        try:
            with open(LAST_IMAGE_FILE, "r") as f:
                return json.load(f).get("uploaded_images", [])
        except Exception as e:
            log.warning("Erreur lecture historique: %s", e)
    return []


def save_uploaded_image(content_id, image_date):
    history = load_upload_history()

    updated = False

    for entry in history:
        # On cherche une image locale uploadée mais pas encore liée à la TV
        if entry.get("content_id") in (None, "", "PENDING"):
            entry["content_id"] = content_id
            entry["image_date"] = image_date
            entry["activated_at"] = datetime.utcnow().isoformat()
            updated = True

            log.info(
                "Historique mis à jour pour le fichier local: %s",
                entry.get("filename", "UNKNOWN")
            )
            break

    if not updated:
        log.warning(
            "Aucune entrée d'historique sans content_id trouvée — rien à mettre à jour"
        )
        return

    with open(LAST_IMAGE_FILE, "w") as f:
        json.dump({"uploaded_images": history}, f, indent=2)

    log.info("Historique sauvegardé avec succès")

def parse_image_date(date_str):
    log.info(date_str)
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%Y:%m:%d %H:%M:%S")
    except ValueError as e:
        log.error(e)
        return None


def get_latest_uploaded_artwork(art):
    log.info("Récupération des œuvres Art Mode...")
    artworks = art.available()
    
    valid = []

    for a in artworks:
        dt = parse_image_date(a.get("image_date", ""))
        if not dt:
            continue

        valid.append((dt, a))

    if not valid:
        log.error("Aucune œuvre valide trouvée")
        return None

    # tri par date décroissante
    valid.sort(key=lambda x: x[0], reverse=True)
    return valid[0][1]


def activate_latest_artwork(art):
    artwork = get_latest_uploaded_artwork(art)
    if not artwork:
        return None

    content_id = artwork["content_id"]
    image_date = artwork["image_date"]

    log.info(
        "Activation de l'œuvre %s (date %s)",
        content_id, image_date
    )

    art.select_image(content_id)
    return content_id, image_date


# =========================
# MAIN
# =========================
def main():
    tv = None
    try:
        tv = SamsungTVWS(host=TV_IP, name="ArtModeSet")

        art = tv.art()

        if not art.supported():
            log.error("Art Mode non supporté")
            return

        # Activer la dernière image uploadée
        result = activate_latest_artwork(art)
        if not result:
            return

        content_id, image_date = result

        # On ne connaît pas le nom de fichier ici → placeholder
        save_uploaded_image(
            content_id=content_id,
            image_date=image_date
        )

        log.info("✓ Image Art Mode affichée avec succès")

    except ConnectionFailure as e:
        log.error("Erreur de connexion TV: %s", e)

    except ResponseError as e:
        log.error("Erreur API Samsung: %s", e)

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
