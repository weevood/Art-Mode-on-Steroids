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

## Synchronisation automatique depuis un album Apple Photos (MacBook)

Le Mac peut exporter l'album **The Frame** depuis sa photothèque Apple Photos et transférer les copies retouchées sur le Raspberry via `ssh pi@piscreen.local`. Cette fonctionnalité est indépendante de la synchronisation iCloud Favorites historique. Fichiers ajoutés au dépôt : `mac/sync-the-frame.zsh` et `mac/ch.artmode.theframe-sync.plist.example`.

### Installer sur le Mac

Prérequis : macOS 27, OSXPhotos 0.77.2 installé via Homebrew, accès à la photothèque `~/Pictures/Photos Library.photoslibrary`, accès SSH non interactif au Raspberry (`ssh -o BatchMode=yes pi@piscreen.local true`). Vérifier que Photos et OSXPhotos disposent des autorisations requises.

```zsh
cd ~
git clone https://github.com/weevood/Art-Mode-on-Steroids.git
chmod +x ~/Art-Mode-on-Steroids/mac/sync-the-frame.zsh
ssh pi@piscreen.local 'mkdir -p /home/pi/Pictures/ArtModeAlbum'
~/Art-Mode-on-Steroids/mac/sync-the-frame.zsh
```

Si le dépôt existe déjà sur le Mac : faire `git pull --ff-only` au lieu de le cloner.

Le script exporte vers `~/Pictures/TheFrameExport` avec `--album "The Frame" --skip-original-if-edited --update --download-missing --cleanup`. Les modifications Apple Photos sont respectées. **Attention : `--cleanup` supprime du dossier d'export les fichiers qui ne font plus partie de l'album** ; ne placer aucun fichier personnel dans ce dossier. Si le rapport n'indique pas exactement `missing: 0, error: 0`, le script refuse le transfert distant pour éviter de supprimer des images lorsque iCloud n'a pas terminé les téléchargements. Seuls les JPEG sont synchronisés ; les HEIC et autres formats photo sont convertis avant transfert. Contrôler le nombre d'images disponibles.

### Couverture de l'album : vérifier les HEIC avant bascule

Un premier miroir s'est terminé avec `545` photos traitées par OSXPhotos, `187` fichiers compatibles transférés et `0` nouveau fichier à transférer par rsync. **Ce dernier zéro confirme seulement que les 187 fichiers filtrés sont à jour**, pas que les 545 photos de l'album sont représentées sur le Raspberry. Les originaux `.heic` sont actuellement exclus. Vérifier les formats dans `~/Pictures/TheFrameExport`, puis tester la conversion OSXPhotos `--convert-to-jpeg --jpeg-quality 0.92` **dans un dossier de test distinct**, afin de valider le rendu des versions retouchées sans affecter le miroir en service. Voir la [documentation officielle OSXPhotos](https://rhettbull.github.io/osxphotos/cli) pour ces options.

**Ne supprimer ni l'ancien miroir iCloud ni basculer `IMAGES_DIR` tant que la couverture de l'album n'est pas validée.**

### Export JPEG obligatoire (HEIC inclus)

Depuis le **13 octobre 2026**, le script Mac exporte l'album Photos **The Frame** dans un **nouveau dossier dédié** `~/Pictures/TheFrameExport`, pour éviter que la base de l'ancien export HEIC/JPEG ne masque les conversions. OSXPhotos 0.77.2 utilise `--convert-to-jpeg --jpeg-quality 0.92 --jpeg-ext jpg` avec `--skip-original-if-edited` pour garder le rendu retouché (crop, filtres) tout en convertissant HEIC/PNG/etc. en JPEG. Les JPEG déjà présents restent JPEG. Les fichiers transférés au Raspberry sont exclusivement `.jpg` ou `.jpeg`.

Le script exige un export sans `missing` ni `error`, refuse les formats image non-JPEG résiduels et vérifie une couverture minimale **80 % du nombre de photos traitées** avant d'autoriser `rsync --delete`. Ce seuil est une protection contre une exportation manifestement incomplète, **pas une garantie** qu'une image existe pour chaque photo : vérifier les statistiques avant la migration définitive. Si l'album contient des vidéos, elles ne sont pas destinées à Art Mode.

L'ancien `~/Pictures/TheFrameExport` n'est plus utilisé après migration : il peut être supprimé **sur le Mac seulement après vérification du nouveau dossier**. Le dossier ancien du Raspberry `iCloud/Favourites` reste intact jusqu'à validation du nouveau miroir et de plusieurs rotations.

### Barre de progression et absence de collisions de noms

**Correctif macOS (13/10/2026)** : la barre utilise les expressions régulières POSIX compatibles avec `/usr/bin/awk` (`\(` et `\)` dans le code awk, sans double échappement). Un motif incorrect provoquait `illegal primary in regular expression` et interrompait l'export avant la synchronisation. Corrigé et vérifié sur un exemple de sortie `(307/545)`.

Le script Mac affiche désormais une **barre de progression compacte** basée sur les compteurs `(n/total)` d'OSXPhotos, au lieu de dérouler une ligne par opération. Un rapport complet reste temporairement disponible pour vérifier les erreurs avant le transfert. À la première exécution après cette migration, `--filename "{uuid}" --edited-suffix "" --jpeg-ext jpg` garantit un nom de fichier `.jpg` stable et distinct pour chaque photo, même si plusieurs images portent le nom d'origine `GPTempDownload.jpg`. OSXPhotos utilise `--cleanup` pour écarter les anciennes sorties aux noms différents. **Contrôler le résultat (compteur JPEG et absence de HEIC) avant suppression de l'ancien miroir du Raspberry.**

### Progression fiable sur macOS

Le parseur `awk` utilisé pour fabriquer une barre de progression a été abandonné : il masquait la sortie d'OSXPhotos et pouvait arrêter l'export. Depuis le correctif du 13 octobre 2026, `/usr/bin/script -q` lance OSXPhotos dans un pseudo-terminal pour **réutiliser sa propre barre de progression native** et enregistrer sa sortie en parallèle dans un rapport temporaire ; aucune ligne par photo n'est demandée (`--verbose` retiré). Le transfert distant reste conditionné à un bilan d'export indiquant aucune photo manquante ou erreur, puis au contrôle des fichiers JPEG.

### Diagnostic export JPEG (13 octobre 2026)

Un export OSXPhotos peut finir avec `512` fichiers `.jpg` pour `545` entrées d'album (les causes de l'écart restent à vérifier). Les fichiers `.DS_Store` sont des métadonnées Finder sans rapport avec les images. Avec `--verbose --timestamp`, la ligne `Processed: ... missing: 0, error: 0` comporte aussi d'autres champs entre `Processed` et `missing`. Le contrôle de succès accepte cette ligne complète et le script efface les `.DS_Store` dans **le dossier dédié d'export uniquement** avant de synchroniser. Le contrôle de couverture minimal reste activé ; un échec ne modifie pas le Raspberry.

### Progression visible et chemin du dépôt Mac

Depuis le correctif du 13 octobre 2026, OSXPhotos est exécuté avec `--verbose --no-progress --timestamp`, et sa sortie est affichée **en direct** via `tee` tout en conservant un rapport pour vérifier `missing: 0, error: 0`. Lors d’une conversion initiale longue, on voit ainsi quelles photos sont traitées, puis les étapes `[2/3]` connexion et `[3/3]` `rsync --progress`. En cas d’échec, la sortie d’erreur apparaît immédiatement et aucune suppression distante n’est lancée.

**Ne pas supposer que le dépôt Mac se trouve dans `~/Art-Mode-on-Steroids`** : sa localisation réelle est donnée par `pwd -P` depuis le répertoire où `./mac/sync-the-frame.zsh` fonctionne. Pour mettre le code à jour, exécuter `git pull --ff-only` **depuis ce répertoire**. Le chemin `Exec` du LaunchAgent fourni comme exemple doit être adapté à cette localisation avant activation.

### Récupération après interruption du Mac

Le script utilise un verrou local `~/Library/Caches/ArtModeSync.lock` avec un fichier `pid` pour éviter deux synchronisations concurrentes. Depuis le correctif d'octobre 2026, il reconnaît un processus encore actif et récupère automatiquement un verrou abandonné après un arrêt brutal. Il supprime son propre verrou à la fin, y compris en cas d'échec normal. Il n'est plus nécessaire de supprimer le verrou manuellement, sauf si le dossier a été altéré ou si les droits sont incorrects.

Pour diagnostiquer : `ps aux | grep -E '[s]ync-the-frame|[o]sxphotos|[r]sync'` et `ls -la ~/Library/Caches/ArtModeSync.lock`. En cas de plantage de l'export, vérifier l'erreur d'OSXPhotos **avant** de relancer ; la protection contre les exports incomplets empêche un miroir destructeur.

### Premier transfert et suivi de progression

Le premier miroir peut transférer plusieurs gigaoctets. Depuis le correctif du 13 octobre 2026, `mac/sync-the-frame.zsh` affiche des étapes `[1/3]` à `[3/3]`, la progression `rsync --progress` et un bilan `--stats`. Le dossier Raspberry peut être partiellement rempli si le transfert est interrompu ; **relancer le script reprend en ne retransférant que les fichiers manquants ou modifiés**.

Le récapitulatif `rsync -avhn --delete ...` présente les **éléments restant à transférer**, y compris les répertoires, et non le nombre total de photos. La taille totale reportée correspond à la sélection de fichiers et ne mesure pas le volume restant à envoyer. Les originaux HEIC ne sont pas inclus ; les JPEG édités `_edited.jpeg` sont inclus.

Ne modifier `IMAGES_DIR` sur le Raspberry **qu'après** la première synchronisation réussie.

### Migration finale et nettoyage du Raspberry (sans doublons)

**Règle : une seule bibliothèque active sur le Pi.** Ancien dossier : `/home/pi/Pictures/iCloud/Favourites` alimenté par le script historique `/home/pi/icloud-sync/sync-icloud-favourites.sh`. Nouveau dossier : `/home/pi/Pictures/ArtModeAlbum` alimenté exclusivement par le Mac. **Ne jamais supprimer l'ancien dossier pendant que le transfert initial est incomplet.** Au 13 octobre 2026, 187 fichiers seulement ont été transférés : la migration est encore en cours.

1. **Sur le Mac**, terminer `./mac/sync-the-frame.zsh` et vérifier que le script annonce `Sync completed`. Réexécuter une fois sans changement pour confirmer une synchronisation stable. Comparer les **fichiers pris en charge** (JPEG/JPG/PNG/BMP) du dossier d'export et du Pi ; il ne faut pas comparer seulement le nombre total de photos Photos, car les fichiers HEIC et annexes sont exclus.
2. **Sur le Raspberry**, arrêter `art-mode` avant la bascule, puis éditer **seulement** `~/Art-Mode-on-Steroids/config_local.py` pour y écrire `IMAGES_DIR = Path("/home/pi/Pictures/ArtModeAlbum")`. Valider avec `./venv/bin/python -c 'import config; print(config.IMAGES_DIR)'`. Tester un cycle manuel `./venv/bin/python -u art.py`, puis redémarrer `art-mode`.
3. **Désactiver l'ancien export cron**, pas les autres lignes cron. Lister avec `crontab -l`, puis `crontab -e` et retirer uniquement la ligne appelant `/home/pi/icloud-sync/sync-icloud-favourites.sh` ; **conserver** la ligne `git pull --ff-only`. Vérifier avec `crontab -l` que l'ancien export ne se relancera plus.
4. **Contrôler toutes les références** à l'ancienne source avant sa suppression : `grep -R "iCloud/Favourites\|icloud-sync" ~/Art-Mode-on-Steroids ~/.config/autostart 2>/dev/null` et revoir les éventuels scripts externes. `uploaded_images.json` est un historique utile au moteur : le conserver.
5. Après validation de plusieurs rotations sur le nouveau dossier, **vérifier visuellement** que le dossier à supprimer est bien l'ancien miroir. Supprimer uniquement `/home/pi/Pictures/iCloud/Favourites` — jamais `/home/pi/Pictures` ni `/home/pi/Pictures/ArtModeAlbum`. Par exemple, depuis le Pi : `du -sh /home/pi/Pictures/iCloud/Favourites /home/pi/Pictures/ArtModeAlbum`, puis `rm -r -- /home/pi/Pictures/iCloud/Favourites` **uniquement après contrôle de la cible**. Ne supprimer le reste de `~/icloud-sync` qu'après inventaire de son contenu et confirmation qu'aucune autre tâche ne l'utilise.

Ne pas supprimer les fichiers iCloud dans Photos : ces opérations concernent uniquement les **copies locales** du Raspberry. Le miroir Mac est la source de vérité : retirer une photo de l'album *The Frame* supprime sa copie sur le Pi au prochain transfert complet.


### Activer en arrière-plan avec launchd

```zsh
mkdir -p ~/Library/LaunchAgents ~/Library/Logs/ArtModeSync
cp ~/Art-Mode-on-Steroids/mac/ch.artmode.theframe-sync.plist.example \
  ~/Library/LaunchAgents/ch.artmode.theframe-sync.plist
plutil -lint ~/Library/LaunchAgents/ch.artmode.theframe-sync.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/ch.artmode.theframe-sync.plist
```

Le LaunchAgent démarre à l'ouverture de session et environ toutes les **15 minutes** pendant que le Mac est actif ; en cas de veille, il reprend aux prochaines opportunités macOS. Il évite les exécutions concurrentes avec un verrou local. Journaux : `~/Library/Logs/ArtModeSync/launchd.log` et `launchd-error.log`. Sur une autre machine, **adapter le chemin absolu** `/Users/thibaud/Art-Mode-on-Steroids` du fichier plist. Pour désactiver : `launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/ch.artmode.theframe-sync.plist`.

### Basculer le Raspberry vers l'album

**Seulement après un transfert réussi**, éditer le fichier local, ignoré par Git :

```python
# /home/pi/Art-Mode-on-Steroids/config_local.py
from pathlib import Path
IMAGES_DIR = Path("/home/pi/Pictures/ArtModeAlbum")
```

Puis redémarrer le service : `sudo systemctl restart art-mode`. L'ancien dossier `/home/pi/Pictures/iCloud/Favourites` reste intact. Pour vérifier le nouveau chemin : `./venv/bin/python -c 'import config; print(config.IMAGES_DIR)'`.

Le miroir `rsync --delete` est limité à `/home/pi/Pictures/ArtModeAlbum`. Retirer une photo de l'album Photo entraîne sa suppression **dans ce miroir**, pas dans la photothèque Apple ni dans l'ancien dossier de favoris. Une copie déjà envoyée dans la mémoire de la TV n'est supprimée qu'après remplacement réussi par une autre image et selon l'historique propre au moteur.

**Limites connues :** `launchd` n'exécute pas la synchronisation lorsque le Mac est éteint ; Photos peut ne pas avoir fini de télécharger les originaux ; le script refuse alors la synchronisation. L'accès SSH par clé doit être configuré avant d'activer le lancement silencieux. Le fichier plist fourni correspond à l'installation Mac sous `/Users/thibaud`.

---

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
