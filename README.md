# Art Mode on Steroids

Affiche automatiquement des photos personnelles sur une **Samsung The Frame**, avec synchronisation facultative du fond d'écran du Raspberry Pi.

**Installation validée le 13 octobre 2026** : Raspberry Pi 4, Debian 13 (Trixie), Samsung The Frame **QE32LS03C** (2023, Full HD 1920 × 1080), bibliothèque d'images iCloud synchronisée localement. Le cycle complet — upload, sélection, wallpaper et nettoyage de la précédente image gérée — a été testé avec succès.

## Fonctionnement

À chaque rotation :

1. Le moteur choisit une photo dans `IMAGES_DIR`. Il privilégie les souvenirs dont la date est proche du jour courant (arborescence `AAAA/MM/JJ`) et évite les photos déjà utilisées tant que possible.
2. Il prépare un JPEG **1920 × 1080**, corrigé et recadré pour la télévision.
3. Il envoie un paquet Wake-on-LAN si `TV_MAC` est renseignée. L'envoi ne garantit pas le réveil effectif de la TV.
4. Il inventorie les œuvres Samsung **par identifiant unique** (`content_id`), envoie la photo une seule fois, puis compare l'inventaire avant/après pour identifier la nouvelle œuvre.
5. Il sélectionne directement cette œuvre sur la télévision, sans basculement Art Mode OFF/ON.
6. Après confirmation de la sélection, il écrit le **même JPEG** dans `current_wallpaper.jpg` et enregistre son identifiant dans `uploaded_images.json`.
7. Il supprime les anciennes œuvres dont l'historique atteste qu'elles ont été ajoutées par ce moteur v2. Les œuvres personnelles ou d'origine inconnue sont conservées.

### Pourquoi le moteur isole les appels Samsung

Sur la **QE32LS03C**, `samsungtvws` peut rester bloqué dans `art.upload()` **alors que la photo a bien été enregistrée** sur le téléviseur. Le moteur exécute donc ses opérations dans des processus distincts avec des délais bornés. Un timeout d'upload **ne déclenche pas un second upload** : la réussite est vérifiée dans la bibliothèque TV. Dans notre test, l'upload `MY_F0895` a été détecté après expiration de l'appel, puis sélectionné et affiché correctement.

Les identifiants retournés par `art.available()` peuvent apparaître plusieurs fois : les inventaires et nettoyages utilisent toujours des `content_id` uniques. Une sélection en erreur ou un nouvel identifiant ambigu fait échouer le cycle plutôt que de sélectionner une autre œuvre au hasard.

## Album Apple Photos « The Frame » — synchronisation et migration (octobre 2026)

**Architecture :** Apple Photos sur le Mac → export JPEG unique `~/Pictures/TheFrameExport` → `rsync` vers `/home/pi/Pictures/ArtModeAlbum` → moteur Art Mode sur la TV Samsung. Les retouches et recadrages Apple Photos sont exportés ; les fichiers HEIC sont convertis en JPEG. Les noms d'export sont basés sur l'UUID de la photo afin d'éviter les collisions comme `GPTempDownload.jpg`. Le Mac doit être allumé, avec une session utilisateur active, une photothèque accessible et un accès SSH sans mot de passe. Aucun transfert n'est effectué lorsque le Mac dort ou est éteint.

### Installer la synchronisation toutes les deux heures (Mac)

Depuis **le vrai dossier du dépôt** sur le Mac (celui où `git status` fonctionne) :

```zsh
git pull --ff-only
./mac/sync-the-frame.zsh
/bin/zsh ./mac/install-launchagent.zsh
```

Le programme d'installation `mac/install-launchagent.zsh` crée `~/Library/LaunchAgents/ch.artmode.theframe-sync.plist` en découvrant automatiquement le chemin réel du dépôt. Il configure `StartInterval = 7200` (2 heures) et `RunAtLoad = true`. Les journaux sont dans `~/Library/Logs/ArtModeSync/`. Vérification :

```zsh
launchctl list | grep ch.artmode.theframe-sync
tail -n 30 ~/Library/Logs/ArtModeSync/launchd.log
```

Le LaunchAgent d'exemple du dépôt est purement indicatif ; **utiliser l'installateur**, sans chemins `/Users/thibaud/Art-Mode-on-Steroids` supposés. Pour le désactiver : `launchctl bootout "gui/$(id -u)/ch.artmode.theframe-sync"`. Le service effectue des synchronisations incrémentales avec la barre native d'OSXPhotos puis une barre globale de transfert `[3/3]` pilotée par `mac/rsync_progress.py` ; le pourcentage de transfert compte les fichiers terminés. Le script vérifie les erreurs et affiche le nombre de JPEG présents.

**Validation du miroir (13 octobre 2026) :** export Apple Photos de 544 JPEG, synchronisation terminée sans erreur, 544 fichiers JPEG vérifiés sur le Raspberry. L'ancien contenu de `ArtModeAlbum` a été réconcilié. La migration de la source utilisée par le moteur et la suppression de `iCloud/Favourites` restent des opérations distinctes, à effectuer avec `pi/migrate-to-album.sh` ; l'installation de l'agent toutes les deux heures se fait avec `mac/install-launchagent.zsh`. Aucun redémarrage d'Art Mode n'est réalisé par ces commandes.

### Propagation sécurisée des suppressions

OSXPhotos exporte avec `--update --update-errors --retry 2 --cleanup` vers **le seul dossier** `~/Pictures/TheFrameExport`. `--cleanup` enlève les copies exportées des photos retirées de l'album. Ensuite, `rsync --delete --delete-excluded` remet `/home/pi/Pictures/ArtModeAlbum` à l'identique **uniquement si** :

- le rapport OSXPhotos indique `missing=0` et `errors=0` ;
- le nombre de fichiers JPEG exportés est exactement égal au nombre de photos traitées, et strictement positif ;
- le nouveau total n'est pas inférieur de plus de 20 % au nombre de JPEG présents sur le Pi (protection contre les suppressions massives accidentelles).

Si une vérification échoue, le script transfère seulement les JPEG valides **sans supprimer de fichiers distants**. Il ne touche jamais à la photothèque Apple Photos ni à l'ancien répertoire iCloud du Pi. Les anciens fichiers présents dans `ArtModeAlbum` peuvent être supprimés au premier cycle complet réussi. Les suppressions du miroir local n'effacent pas immédiatement l'œuvre déjà sélectionnée sur la télévision.

### Bascule de la source et nettoyage de l'ancien iCloud (Raspberry)

**Après une synchronisation Mac complète**, depuis le terminal du Mac, exécuter :

```zsh
ssh pi@piscreen.local 'cd /home/pi/Art-Mode-on-Steroids && git pull --ff-only && bash pi/migrate-to-album.sh'
```

Le script vérifie qu'il existe au moins **400 JPEG et aucun autre format** dans `ArtModeAlbum`, **arrête** `art-mode.service` sans le redémarrer, conserve `config_local.py` et les réglages de la TV, puis bascule `IMAGES_DIR` vers `/home/pi/Pictures/ArtModeAlbum`. Il sauvegarde `config_local.py.before-album-migration` et la crontab dans `/home/pi/old-crontab.before-album-migration`, retire **uniquement** l'appel à `/home/pi/icloud-sync/sync-icloud-favourites.sh` de la crontab, puis supprime l'ancien répertoire local **`/home/pi/Pictures/iCloud/Favourites`**. Le dépôt, le script `icloud-sync` lui-même, d'éventuels autres dossiers sous `Pictures/iCloud` et l'historique `uploaded_images.json` sont préservés.

**Important :** aucune commande ne redémarre le service après cette bascule. La photo sélectionnée sur Samsung reste fixe. Si `art-mode.service` est activé au démarrage, la rotation reprend automatiquement **au prochain reboot** du Pi. Vérifier `systemctl is-enabled art-mode.service` et `systemctl is-active art-mode.service` sans démarrer le service.

### Tests finaux

```zsh
ssh pi@piscreen.local 'find /home/pi/Pictures/ArtModeAlbum -type f -iname "*.jpg" | wc -l'
ssh pi@piscreen.local 'test ! -e /home/pi/Pictures/iCloud/Favourites && echo "Ancien miroir supprimé"'
ssh pi@piscreen.local 'cd /home/pi/Art-Mode-on-Steroids && ./venv/bin/python -c "import config; print(config.IMAGES_DIR)"'
ssh pi@piscreen.local 'systemctl is-active art-mode.service || true; systemctl is-enabled art-mode.service'
```


## Prérequis

- Raspberry Pi avec Python 3 et accès réseau à la Samsung The Frame.
- TV accessible sur le réseau local, compatible avec l'API Art Mode de `samsungtvws`.
- Photos disponibles sur le disque du Raspberry. La synchronisation iCloud est **externe à ce dépôt**.
- Pour le fond d'écran : session graphique **Wayland/labwc** et utilitaire `swaybg` (facultatif).
- Wake-on-LAN facultatif, sous réserve de prise en charge par le téléviseur et le réseau.

Les scripts ont été validés avec Python **3.13**, `samsungtvws==3.0.2` et Pillow. `requirements.txt` contient également des dépendances historiques non utilisées par le moteur actuel.

## Installation

```bash
cd /home/pi
git clone https://github.com/weevood/Art-Mode-on-Steroids.git
cd Art-Mode-on-Steroids

python3 -m venv venv
./venv/bin/python -m pip install -r requirements.txt

cp config_local.example.py config_local.py
nano config_local.py
```

Renseigner le chemin réel des images et, si nécessaire, l'IP/MAC de la TV. Les exemples sont propres à l'installation existante : **les adapter sur une autre machine**.

### Configuration : deux fichiers, aucun conflit Git

| Fichier | Suivi par Git | Usage |
| --- | --- | --- |
| `config.py` | Oui | Valeurs par défaut du projet |
| `config_local.example.py` | Oui | Modèle à copier |
| `config_local.py` | **Non** | Paramètres de la machine, prioritaires sur les valeurs par défaut |

Exemple de `config_local.py` :

```python
from pathlib import Path

IMAGES_DIR = Path("/home/pi/Pictures/iCloud/Favourites")
TV_IP = "192.168.1.20"
TV_MAC = "28:07:08:97:28:44"
INTERVAL = 1200  # 20 minutes entre les débuts de cycles réussis
MATTE = "shadowbox_antique"
```

`config_local.py` est ignoré par Git : ne personnalisez pas directement `config.py`. Les paramètres disponibles sont notamment `IMAGES_DIR`, `LAST_IMAGE_FILE`, `TV_IP`, `TV_MAC`, `INTERVAL` et `MATTE`.

**Important :** la valeur par défaut actuellement versionnée est `INTERVAL = 60` secondes. Pour une utilisation quotidienne, un intervalle plus long (par exemple **1200 secondes**) évite de multiplier les uploads. Si un cycle échoue, le moteur attend au minimum **20 minutes** avant une nouvelle tentative.

## Utilisation

### Un cycle manuel

Pour éviter deux processus concurrents, arrêter le service avant le test :

```bash
cd ~/Art-Mode-on-Steroids
sudo systemctl stop art-mode
./venv/bin/python -u art.py
```

Messages de réussite attendus :

```text
INFO art-mode: New artwork IDs after upload: ['MY_F....']
INFO art-mode: Selected and confirmed Samsung artwork MY_F....
INFO art-mode: Cycle finished; wallpaper updated at .../current_wallpaper.jpg
```

Le message `Upload call not acknowledged` est **attendu sur le téléviseur testé** : il n'est pas une erreur si un nouvel identifiant est ensuite détecté et sélectionné.

### Service systemd

Sur le Raspberry configuré, le service `art-mode.service` lance `art_cron.py` en permanence tant que le Raspberry est allumé :

```bash
sudo systemctl start art-mode
sudo systemctl stop art-mode
sudo systemctl status art-mode --no-pager
journalctl -u art-mode -f
```

Pour créer le même service sur une nouvelle machine :

```ini
[Unit]
Description=Art Mode on Steroids
After=network-online.target
Wants=network-online.target

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

Enregistrer dans `/etc/systemd/system/art-mode.service` (adapter l'utilisateur et les chemins), puis :

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now art-mode
```

Le script ne pilote **pas** l'alimentation du Raspberry ; il tourne aussi longtemps que le Pi est alimenté.

### Fond d'écran du Raspberry (facultatif)

`wallpaper.py` surveille `current_wallpaper.jpg` et actualise le fond d'écran via `swaybg` dans une session **Wayland**. Il n'ouvre pas de mode kiosque et quitte normalement si aucune session Wayland n'est présente.

```bash
sudo apt install swaybg
```

Créer `~/.config/autostart/art-mode-wallpaper.desktop` dans la session de l'utilisateur graphique :

```ini
[Desktop Entry]
Type=Application
Name=Art Mode Wallpaper
Exec=/home/pi/Art-Mode-on-Steroids/venv/bin/python /home/pi/Art-Mode-on-Steroids/wallpaper.py
Terminal=false
X-GNOME-Autostart-enabled=true
```

L'autostart ci-dessus est installé séparément du service systemd, dans la session graphique. Il permet d'avoir le même fond d'écran via VNC sans dépendre de la présence physique d'un moniteur.

## Stockage et nettoyage des œuvres

- `uploaded_images.json` : historique persistant des photos utilisées et des identifiants Samsung. **Ne pas le supprimer** lors d'un ménage : le moteur s'en sert pour reconnaître ses anciennes œuvres.
- `current_wallpaper.jpg` : image générée, réutilisée par le fond d'écran. Ignorée par Git.
- Le moteur nettoie **seulement** les anciennes œuvres marquées `managed_by: "art-mode-on-steroids-v2"`. Il ne supprime pas les œuvres Samsung d'origine ni les photos plus anciennes non identifiées.
- Si une suppression échoue ou n'est pas confirmée, le moteur pourra réessayer après un cycle réussi. Un upload non confirmé par le moteur peut toutefois laisser une œuvre orpheline à nettoyer manuellement.

### Nettoyage manuel

`cleanup_tv.py` est un outil indépendant, avec aperçu par défaut et option de suppression :

```bash
sudo systemctl stop art-mode
./venv/bin/python -u cleanup_tv.py
./venv/bin/python -u cleanup_tv.py --delete
```

**Attention :** le critère est uniquement la **date Samsung** (`image_date`), pas la provenance de la photo. Il peut donc inclure des œuvres ajoutées manuellement. Le seuil actuellement défini dans le script est `CUTOFF = date(2026, 6, 1)` : le consulter avant de supprimer. En mode `--delete`, le script demande de saisir `DELETE N`, où `N` est le nombre d'identifiants uniques retenus. Les entrées dupliquées sont dédoublonnées : chaque identifiant est supprimé au plus une fois lors de l'exécution.

## Mise à jour depuis GitHub

Sur cette installation, un cron exécute `git pull --ff-only` toutes les deux minutes. Cela **récupère les fichiers**, mais ne redémarre pas un processus Python déjà en cours. Pour déployer un changement de code sur le service :

```bash
cd ~/Art-Mode-on-Steroids
git status -sb
git pull --ff-only
sudo systemctl restart art-mode
```

Ne pas employer `git reset --hard` pour résoudre un conflit de configuration. Les personnalisations doivent être placées dans `config_local.py`. Pour tester manuellement, arrêter le service avant d'exécuter `art.py`.

## Dépannage

| Symptôme | Vérification / action |
| --- | --- |
| `Upload call not acknowledged` | Comportement connu ; vérifier ensuite `New artwork IDs` et `Selected and confirmed`. |
| Plusieurs entrées API pour une image | Normal sur ce modèle : compter les `content_id` uniques. |
| `select_image` refuse un identifiant | Vérifier que l'œuvre existe encore. Une sélection directe a été validée pour les IDs `MY_` et `SAM-` présents. |
| Aucun nouvel identifiant | Vérifier le réseau, la TV et les logs ; ne pas relancer des uploads simultanés. |
| Fond d'écran inchangé | Vérifier l'horodatage de `current_wallpaper.jpg`, la session Wayland et le processus `wallpaper.py`. |
| Pas d'images disponibles | Vérifier `IMAGES_DIR` et la synchronisation externe iCloud. |
| Un changement de code ne prend pas effet | Redémarrer le service après `git pull`. |
| Service en échec | Consulter `journalctl -u art-mode -n 100 --no-pager`. |

## Structure du dépôt

```text
art.py                     # un cycle manuel
art_cron.py                # boucle automatique
art_engine.py              # sélection, conversion, API Samsung et nettoyage
wallpaper.py               # synchronisation graphique Wayland
cleanup_tv.py              # nettoyage manuel par date
config.py                  # valeurs par défaut versionnées
config_local.example.py    # exemple de configuration locale
config_local.py            # configuration locale ignorée par Git
uploaded_images.json       # historique généré, ignoré par Git
current_wallpaper.jpg      # JPEG généré, ignoré par Git
_art_upload.py             # ancienne implémentation, conservée comme référence
_art_set.py                # ancienne implémentation, conservée comme référence
requirements.txt           # dépendances Python
```

## Limites connues

Les commandes Art Mode de Samsung peuvent avoir des délais ou des erreurs propres au firmware. La méthode par inventaire + processus isolés a été **validée sur QE32LS03C**, mais son comportement n'est pas garanti sur tous les modèles The Frame. Les uploads depuis d'autres appareils pendant un cycle peuvent produire plusieurs nouveaux identifiants et faire échouer volontairement la sélection. Le projet ne gère ni la synchronisation iCloud ni l'alimentation électrique du Raspberry.


### Synchronisation incrémentale malgré les erreurs Photos (13 octobre 2026)

Après le constat d'un export de 545 photos, 534 exportées, 10 manquantes et 1 erreur de conversion HEIC/Live Photo, le script Mac utilise désormais systématiquement `--update --update-errors --retry 2`, avec la barre native OSXPhotos. Un export partiel n'empêche plus l'envoi des JPEG valides vers le Raspberry. L'export local ne lance plus `--cleanup` et le transfert rsync **ne supprime jamais de fichiers à distance dans cette version**, même si le rapport est parfait : cela évite une perte de photos pendant le diagnostic et la réconciliation des copies obsolètes. **Les suppressions d'images retirées de l'album ne sont temporairement plus propagées** ; cette fonctionnalité sera réactivée uniquement après une méthode sûre de nettoyage et une validation complète. L'écart avec les 545 photos doit être résolu avant suppression de l'ancien dossier iCloud du Raspberry.

### Correction du parsing OSXPhotos via pseudo-terminal

Sous macOS, `/usr/bin/script` conserve les retours chariot et séquences de contrôle ANSI de la barre native OSXPhotos. Le contrôle précédent fondé sur `sed` échouait à extraire `Processed`, `missing` et `error`, même pour un bilan valide tel que `Processed: 545 photos, exported: 10, updated: 0, skipped: 534, updated EXIF data: 0, missing: 0, error: 1`. Désormais, le rapport est normalisé et le **dernier bilan** est analysé en une fois via Perl ; en cas d'absence de bilan, les dernières lignes du rapport sont affichées pour diagnostic. Les JPEG sont envoyés au Pi même si une photo Live Photo/HEIC a échoué ; aucun fichier distant n'est supprimé pendant cette phase.

### Barre de progression pour le transfert Raspberry

Le script calcule d'abord combien de JPEG doivent réellement être envoyés avec un `rsync --dry-run`, puis effectue le transfert avec une **barre unique `[3/3] Upload ... (n/total files)`** actualisée à chaque fichier. Cette méthode fonctionne avec `/usr/bin/rsync` fourni par macOS, sans installer une nouvelle version, et évite les centaines de lignes `--progress` par fichier. La progression représente **le nombre de fichiers transférés**, pas le volume en octets ; les très gros JPEG peuvent prendre davantage de temps. Si aucun transfert n'est nécessaire, un message `Raspberry already up to date` est affiché. Le rapport final de transfert reste visible, les erreurs provoquent l'échec du script grâce à `pipefail`, et aucune suppression distante n'est activée durant la migration.

### Barre d'upload réactive (correction octobre 2026)

Le comptage global côté Raspberry passe maintenant par `mac/rsync_progress.py`, lancé depuis `mac/sync-the-frame.zsh`. Le script affiche immédiatement `[3/3] Upload ... 0/N`, puis actualise l'état au moins toutes les deux secondes, **même lorsque rsync n'a terminé aucun gros fichier** ou tamponne ses messages. Il lit les sorties dans un pseudo-terminal macOS, compte les noms de JPEG transférés et propage le code d'erreur du transfert. La progression correspond au nombre de fichiers terminés, et non au volume d'octets déjà transmis. Le chemin du helper est résolu relativement au script Mac, pas à un répertoire personnel supposé.

### LaunchAgent : erreur 127 depuis Documents

Si `launchctl list` affiche `127` et que `launchd-error.log` indique `can't open input file` pour un chemin situé sous `~/Documents`, réinstaller avec `/bin/zsh ./mac/install-launchagent.zsh` depuis le dépôt. L'installateur copie désormais `sync-the-frame.zsh` **et** `rsync_progress.py` dans `~/Library/Application Support/ArtModeSync/bin/` et configure le LaunchAgent pour utiliser cette copie. Le dépôt reste dans Documents ; il n'est pas nécessaire d'accorder l'accès complet au disque à `/bin/zsh`. Vérifier le nouveau chemin avec `plutil -p ~/Library/LaunchAgents/ch.artmode.theframe-sync.plist`, puis le statut avec `launchctl list | grep ch.artmode.theframe-sync`. Après une future mise à jour Git, relancer l'installateur pour actualiser les copies exécutées. Si le code 127 persiste, lire `~/Library/Logs/ArtModeSync/launchd-error.log` pour distinguer un problème d'accès de fichier d'une autre erreur.
