# Art Mode on Steroids

Affiche les photos d'un album **Apple Photos « The Frame »** sur une **Samsung The Frame**, avec rotation automatique depuis un Raspberry Pi. Le Mac synchronise l'album en arrière-plan ; le Raspberry conserve les photos localement et continue à fonctionner même lorsque le Mac est éteint.

Testé sur **Raspberry Pi 4 (Debian 13, Python 3.13)** et **Samsung The Frame QE32LS03C (2023, 1920 × 1080)**. D'autres modèles Samsung peuvent se comporter différemment.

## Architecture

```text
Apple Photos : album « The Frame » (Mac)
    │  toutes les 2 heures lorsque le Mac est actif
    ▼
~/Pictures/TheFrameExport/           ← copies JPEG retouchées, une par photo
    │  SSH + rsync (ajouts, modifications, suppressions contrôlées)
    ▼
/home/pi/Pictures/ArtModeAlbum/      ← seul dossier source sur le Raspberry
    │  service art-mode.service
    ▼
Samsung The Frame                    ← rotation automatique en Art Mode
    └── current_wallpaper.jpg        ← même image sur le bureau du Pi (optionnel)
```

**Source de vérité :** l'album Apple Photos « The Frame ». L'export et le miroir sont des copies ; **ne pas y enregistrer de photos manuellement**. Une photo retirée de l'album sera retirée du miroir après une synchronisation complète validée, mais pas nécessairement immédiatement de la bibliothèque interne de la télévision.

## 1. Prérequis

- Un Mac avec **Apple Photos**, l'album nommé exactement `The Frame` et [OSXPhotos](https://github.com/RhetTbull/osxphotos) installé (sur l'installation testée : `/opt/homebrew/bin/osxphotos`). Donner à OSXPhotos les permissions d'accès à la photothèque.
- Un Raspberry Pi avec Python 3, accès à la télévision sur le LAN, SSH actif et un utilisateur `pi` (adapter les chemins/scripts si l'utilisateur change).
- Une **Samsung The Frame compatible avec l'API Art Mode** de `samsungtvws`.
- Une authentification SSH **sans mot de passe** depuis le Mac vers `pi@piscreen.local`, vérifiable avec :

```bash
ssh -o BatchMode=yes pi@piscreen.local 'echo SSH_OK'
```

Le Mac doit être allumé, avec une session utilisateur ouverte, et connecté au réseau du Pi pour la synchronisation. Le Pi et la TV peuvent continuer à fonctionner indépendamment du Mac entre deux synchronisations.

## 2. Installer le moteur sur le Raspberry

Depuis le Raspberry (première installation) :

```bash
cd /home/pi
git clone https://github.com/weevood/Art-Mode-on-Steroids.git
cd Art-Mode-on-Steroids
python3 -m venv venv
./venv/bin/python -m pip install -r requirements.txt
cp config_local.example.py config_local.py
nano config_local.py
```

Configurer **au minimum** le dossier de photos et l'adresse IP de la TV. Exemple :

```python
from pathlib import Path

IMAGES_DIR = Path("/home/pi/Pictures/ArtModeAlbum")
TV_IP = "192.168.1.20"          # adresse de VOTRE TV
TV_MAC = "28:07:08:97:28:44"    # adresse de VOTRE TV, facultative pour Wake-on-LAN
INTERVAL = 1200                 # secondes entre les rotations
MATTE = "shadowbox_antique"
```

`config_local.py` est propre à la machine, **ignoré par Git** et prioritaire sur les paramètres de `config.py`. Ne pas placer de secrets ni de personnalisations dans les fichiers versionnés. Le moteur a besoin de JPEG dans `IMAGES_DIR` avant de démarrer ; installer la synchro Mac (étape suivante) avant le premier cycle.

### Service automatique au démarrage du Pi

Créer `/etc/systemd/system/art-mode.service` avec le contenu suivant (adapter l'utilisateur et les chemins) :

```ini
[Unit]
Description=Art Mode on Steroids
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/Art-Mode-on-Steroids
ExecStart=/home/pi/Art-Mode-on-Steroids/venv/bin/python /home/pi/Art-Mode-on-Steroids/art_cron.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Puis, **après avoir synchronisé les photos** :

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now art-mode.service
sudo systemctl status art-mode.service --no-pager
```

Pour garder une photo fixe temporairement, exécuter `sudo systemctl stop art-mode.service`. Si le service est toujours `enabled`, il reprend au **prochain redémarrage du Pi**. Un redémarrage ou démarrage manuel du service change potentiellement l'image affichée.

## 3. Installer la synchronisation de l'album sur le Mac

Depuis **le dossier où ce dépôt a été cloné sur le Mac** (ne pas supposer `~/Art-Mode-on-Steroids`) :

```zsh
git pull --ff-only
./mac/sync-the-frame.zsh
/bin/zsh ./mac/install-launchagent.zsh
```

- `sync-the-frame.zsh` exporte les images en JPEG **`.jpg`**, y compris les HEIC, en privilégiant les versions modifiées (recadrages et filtres Apple Photos). Les fichiers sont nommés avec l'UUID de la photo pour éviter les collisions. L'export s'effectue dans **un seul dossier** : `~/Pictures/TheFrameExport`.
- `rsync` met à jour **le seul miroir du Pi** : `/home/pi/Pictures/ArtModeAlbum`. L'export et l'envoi sont incrémentaux. OSXPhotos affiche sa barre native ; l'envoi affiche une barre globale de fichiers grâce à `mac/rsync_progress.py`.
- `install-launchagent.zsh` installe un **LaunchAgent utilisateur toutes les 2 heures** (`StartInterval=7200`, également exécuté au chargement de la session). Il copie les scripts nécessaires vers `~/Library/Application Support/ArtModeSync/bin/` pour éviter les restrictions d'accès à un dépôt situé dans `Documents`.
- Les fichiers exécutés par launchd sont des **copies** : après une modification du script Mac suivie d'un `git pull`, **relancer** `/bin/zsh ./mac/install-launchagent.zsh` pour mettre les copies à jour. Ne pas éditer la copie installée à la main.

### Vérifications

Sur le Mac :

```zsh
launchctl list | grep ch.artmode.theframe-sync
tail -n 30 "$HOME/Library/Logs/ArtModeSync/launchd.log"
tail -n 30 "$HOME/Library/Logs/ArtModeSync/launchd-error.log"
```

Un LaunchAgent **en cours d'exécution** montre un PID ; `-` avec code de sortie `0` indique une exécution terminée avec succès. Un code non nul nécessite de consulter les journaux. La commande `tail -f` permet de suivre un journal en direct ; `Ctrl+C` arrête uniquement son affichage.

Pour compter les images sur le Pi depuis le Mac :

```bash
ssh pi@piscreen.local 'find /home/pi/Pictures/ArtModeAlbum -type f -iname "*.jpg" | wc -l'
```

## 4. Suppressions et sécurité

Le miroir doit refléter l'album, y compris lorsqu'une photo en est retirée. Le script utilise `osxphotos --update --cleanup` pour retirer les copies obsolètes **du dossier d'export dédié** et `rsync --delete --delete-excluded` pour retirer les anciennes images **du dossier ArtModeAlbum uniquement**.

Les suppressions distantes ne sont permises que si :
- OSXPhotos termine avec **`missing=0` et `errors=0`** ;
- le nombre de JPEG locaux est **égal au nombre de photos traitées**, et non nul ;
- après le premier miroir initialisé, le nombre de photos n'a pas chuté de plus de **20 %** par rapport au miroir précédent.

En cas d'export partiel, les JPEG valides peuvent être envoyés, **mais le script n'efface aucun fichier du Pi**. Une suppression massive volontaire de plus de 20 % demandera une intervention, et ne doit pas être contournée sans vérifier l'album. Le nettoyage automatique ne touche **ni aux originaux dans Apple Photos**, ni aux autres répertoires du Raspberry.

Le moteur conserve `uploaded_images.json` (historique des œuvres envoyées à la TV) et ne supprime automatiquement dans la bibliothèque Samsung que les œuvres qu'il reconnaît comme lui appartenant, après confirmation du nouveau cycle. **Ne pas supprimer cet historique.** Le changement du miroir ne supprime pas instantanément l'image déjà affichée sur la TV.

## 5. Exploitation courante

| Besoin | Commande |
| --- | --- |
| Synchroniser immédiatement l'album | Mac, depuis le dépôt : `./mac/sync-the-frame.zsh` |
| Vérifier le LaunchAgent | Mac : `launchctl list \| grep ch.artmode.theframe-sync` |
| Suivre la synchronisation Mac | Mac : `tail -f "$HOME/Library/Logs/ArtModeSync/launchd.log"` |
| Arrêter temporairement la rotation | Pi : `sudo systemctl stop art-mode.service` |
| Reprendre la rotation maintenant | Pi : `sudo systemctl start art-mode.service` |
| Vérifier la rotation | Pi : `systemctl status art-mode.service --no-pager` |
| Suivre les événements Samsung | Pi : `journalctl -u art-mode.service -f` |
| Tester un seul cycle (service arrêté) | Pi, depuis le dépôt : `./venv/bin/python -u art.py` |

Pour mettre à jour le moteur sur le Pi :

```bash
cd /home/pi/Art-Mode-on-Steroids
git pull --ff-only
sudo systemctl restart art-mode.service
```

**Attention :** redémarrer le service relance immédiatement la rotation. Si l'objectif est de conserver une image fixe, repousser ce redémarrage au moment voulu. Une récupération Git automatique ne recharge pas à elle seule un processus Python déjà démarré.

### Fond d'écran du Raspberry (facultatif)

`wallpaper.py` suit `current_wallpaper.jpg` dans une session graphique Wayland à l'aide de `swaybg`. Cet observateur est facultatif pour la télévision. Il nécessite `sudo apt install swaybg` et son lancement dans la session graphique (par exemple avec un autostart Wayland) ; ne pas lancer cet observateur dans le service Samsung.

### Nettoyage manuel des œuvres Samsung (avancé)

`cleanup_tv.py` liste par défaut les œuvres selon leur **date Samsung** ; `--delete` active une suppression interactive. Ce critère n'identifie **pas** les photos appartenant au projet : vérifier soigneusement les œuvres ciblées et la valeur `CUTOFF` du script avant toute confirmation.

```bash
cd /home/pi/Art-Mode-on-Steroids
./venv/bin/python -u cleanup_tv.py
# Mode destructeur uniquement si le contenu de la liste a été vérifié :
./venv/bin/python -u cleanup_tv.py --delete
```

## 6. Dépannage

| Symptôme | Diagnostic |
| --- | --- |
| `launchctl` affiche `127` / `can't open input file` | Réinstaller `/bin/zsh ./mac/install-launchagent.zsh` depuis le dépôt ; le script exécuté doit résider dans `~/Library/Application Support/ArtModeSync/bin/`. |
| Le LaunchAgent est chargé, mais ne synchronise pas | Vérifier `launchd-error.log`, SSH sans interaction, accès du processus à Photos et le verrou `~/Library/Caches/ArtModeSync.lock`. |
| Une photo HEIC/Live Photo échoue | Consulter le bilan OSXPhotos ; un export partiel n'autorise aucune suppression distante. Les autres JPG sont quand même transférés. |
| `Source is unexpectedly smaller` | La protection anti-suppression massive s'est déclenchée ; comparer album Photos, export et miroir avant intervention. |
| Une photo retirée de l'album reste sur le Pi | Vérifier `missing=0 errors=0` et la réussite d'un cycle `--cleanup` / `rsync`. |
| `Upload call not acknowledged` | Sur le modèle testé, Samsung peut enregistrer la photo avant de répondre. Le moteur compare les identifiants TV avant toute nouvelle tentative. |
| Aucune rotation | Vérifier `IMAGES_DIR`, `systemctl status art-mode.service` et `journalctl -u art-mode.service -n 100 --no-pager`. |
| Le code Git mis à jour ne s'applique pas | Sur Pi, redémarrer le service au moment approprié ; sur Mac, réinstaller le LaunchAgent pour actualiser les copies. |

## Structure du dépôt

```text
art_engine.py                 Moteur de rotation, transfert et nettoyage Samsung
art.py                        Un seul cycle de rotation
art_cron.py                   Boucle de rotation utilisée par systemd
config.py                     Paramètres par défaut
config_local.example.py       Modèle de configuration locale
wallpaper.py                  Fond d'écran Wayland facultatif
cleanup_tv.py                 Nettoyage manuel Samsung (outil avancé)
mac/sync-the-frame.zsh        Export Apple Photos et miroir rsync
mac/rsync_progress.py         Barre de progression de transfert
mac/install-launchagent.zsh   Installation du LaunchAgent toutes les 2 heures
pi/migrate-to-album.sh        Utilitaire de migration depuis l'ancienne source iCloud
requirements.txt              Dépendances Python Raspberry
```

`config_local.py`, `uploaded_images.json`, `current_wallpaper.jpg`, l'export Apple Photos, les photos du Pi et les journaux sont des **données locales**, pas des fichiers à versionner. Les anciens fichiers `_art_upload.py` et `_art_set.py` sont des implémentations héritées ; **ne pas les utiliser** pour lancer la rotation courante.

---

**Installation existante validée :** export et miroir à 544 JPEG, LaunchAgent macOS toutes les deux heures opérationnel, source Pi configurée sur `ArtModeAlbum`, ancienne synchronisation iCloud Favorites retirée. Le statut `art-mode.service` dépend de l'utilisation : il peut rester arrêté volontairement pour conserver une image fixe jusqu'au redémarrage du Pi.
