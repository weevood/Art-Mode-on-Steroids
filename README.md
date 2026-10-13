# Art-Mode-on-Steroids

> **Version 2 — 13 octobre 2026.** Nouveau moteur central `art_engine.py`, fonds d'écran facultatif et suppression automatique désactivée. **Attention : un Raspberry déjà installé récupère le code via Git, mais doit redémarrer `art-mode.service` pour l'exécuter et installer séparément le composant graphique.**

## Configuration simplifiée de l'adresse MAC (13 octobre 2026)

Le réveil Wake-on-LAN lit désormais directement `TV_MAC` dans `config.py`, à côté de `TV_IP` :

```python
TV_IP = "192.168.1.20"
TV_MAC = "28:07:08:97:28:44"
```

Il n'est **plus nécessaire** de définir `ART_TV_MAC` dans systemd ou dans le terminal. L'ancien override systemd peut subsister, mais la variable d'environnement n'est plus utilisée. L'envoi de la trame de réveil ne garantit pas que la TV se réveille (dépend du firmware et de la connectivité réseau).

**Migration Raspberry existant :** `config.py` avait été modifié localement (Git `M config.py`). Comme ce fichier est également mis à jour sur GitHub, le pull automatique peut être bloqué. **Sauvegarder le fichier local et comparer son contenu avant toute restauration** : `cp config.py config.py.backup`, `git diff -- config.py`, puis intégrer les différences locales dans la version Git. Ne pas lancer `git reset --hard`.

**Sécurité :** le service automatique de rotation doit rester arrêté tant que la gestion des blocages Samsung et la suppression contrôlée des œuvres n'ont pas été vérifiées sur le téléviseur réel.

---

## Gestion automatique de la mémoire TV — 13 octobre 2026

**Règle de conservation : une seule œuvre gérée par la version 2 doit rester sur la TV après une rotation réussie.**

1. Une nouvelle photo est uploadée et identifiée de manière non ambiguë.
2. Elle devient l'image affichée sur la Samsung, puis le JPEG identique est écrit sur le Raspberry.
3. L'historique JSON sauvegarde son `content_id` avec `managed_by: "art-mode-on-steroids-v2"`.
4. **Après cette sauvegarde uniquement**, le moteur tente de supprimer les **anciennes** œuvres munies de ce marqueur. Il ne supprime jamais l'identifiant en cours d'affichage.
5. Si la TV ou la suppression ne répond pas, la photo ancienne reste en place et l'opération sera retentée lors d'un cycle réussi ultérieur. Le processus ne considère pas une suppression échouée comme réussie.
6. Les œuvres héritées de l'ancien moteur, les œuvres personnelles Samsung et les identifiants d'origine inconnue **ne sont jamais supprimés automatiquement**.

**Important :** les 194 œuvres déjà présentes avant ce changement restent intactes ; un ménage historique nécessite un inventaire et une décision explicite. Les images uploadées lors d'un appel Samsung bloqué mais jamais identifiées dans notre historique peuvent encore se cumuler : la gestion de ces uploads non confirmés reste un chantier prioritaire. **Ne pas lancer la boucle en continu tant que ce comportement n'est pas validé**, notamment en raison des appels Samsung susceptibles de bloquer.

Après publication sur GitHub, le changement ne s'applique que lors d'un redémarrage du service `art-mode.service`. Un test manuel nécessite d'arrêter le service auparavant, pour éviter les uploads concurrents.

---

## Correction vérifiée par diagnostic — 13 octobre 2026

La Samsung QE32LS03C répond à `art.supported() == True` et `art.available()`, avec **185 œuvres** recensées. Malgré un timeout de l'appel `art.upload()` après 45 secondes, une œuvre datée de **11:47:05** est apparue pendant le test démarré à **11:47:01**. L'API d'upload peut donc rester bloquée **après un envoi réussi**. D'autres œuvres ont été enregistrées autour de ce test ; leur origine individuelle n'est pas établie.

**Nouveau mécanisme (`art_engine.py`) :** inventaire initial des identifiants Samsung, lancement d'un seul upload dans un thread séparé, puis vérification toutes les 3 secondes via une **nouvelle connexion** à l'API (`art.available()`) pendant au plus 75 secondes. Si **un seul nouvel identifiant** est identifié, le code exécute le contournement historique Art Mode OFF/ON puis sélectionne cet identifiant. Si aucun ou plusieurs identifiants sont détectés, il refuse de choisir au hasard. Il **ne réessaie pas automatiquement l'upload** incertain pour éviter les doublons. Le wallpaper n'est enregistré que si l'activation s'achève sans erreur.

**À tester impérativement avant reprise automatique :** arrêter `art-mode.service`, relever le nombre d'œuvres, exécuter `./venv/bin/python art.py` une fois, inspecter le journal, puis vérifier le contenu de la TV et `current_wallpaper.jpg`. Le comportement du nouveau mécanisme n'est **pas encore validé** sur la TV. Un upload en thread qui ne se termine jamais reste une limitation potentielle de la bibliothèque Samsung.

---

## Diagnostic en cours — 13 octobre 2026 : upload Samsung bloqué

**Observation réelle (QE32LS03C) :** lancement manuel de `./venv/bin/python art.py` à 11:47. Sélection de `2025/08/02/IMG_8580.JPG` puis `art.upload()` ne rend pas la main sous 45 s. Le moteur échoue volontairement avec `Samsung upload unconfirmed after 45s`. Aucun `current_wallpaper.jpg` n'est produit par ce cycle ; il est **impossible d'affirmer si la TV a reçu l'image**.

**Procédure de diagnostic :** conserver `art-mode.service` arrêté pendant les essais ; interroger `tv.art().supported()` et `tv.art().available()` **en lecture seule** pour vérifier l'accès à l'API et le contenu de la TV. Attention : une commande de lecture peut également bloquer sur certains firmwares. Ne pas reprendre la boucle automatique tant que la cause n'est pas établie. Les anciens scripts `_art_upload.py` et `_art_set.py` contiennent un contournement du délai qui **supposait** l'upload réussi, sans confirmation : ce comportement ne doit pas être rétabli sans validation. Éviter les tentatives répétées qui pourraient accumuler des images.

---

## Configuration confirmée : Samsung QE32LS03C (2023)

- **Téléviseur :** Samsung The Frame QE32LS03C, 32 pouces, **1920 × 1080 (Full HD)** selon Samsung. Le moteur actif prépare désormais les JPEG en Full HD au lieu de 4K. Les sections historiques mentionnant « 4K » documentent l'ancienne version.
- **Raspberry :** Pi 4, Debian 13, service système `art-mode.service` déjà activé avec `WorkingDirectory=/home/pi/Art-Mode-on-Steroids`, `Restart=always`, `ExecStart=.../venv/bin/python .../art_cron.py`. L'unité reste inchangée.
- **Bureau :** le choix est **fond d'écran du bureau**. `XDG_SESSION_TYPE=tty` dans le terminal SSH ne permet pas de conclure que la session locale n'est pas Wayland. Vérifier `loginctl list-sessions` et `pgrep -af 'labwc|wayfire|Xorg'`. `swaybg` est installé.
- **TV en veille :** activer si disponible « Power On with Mobile » dans les paramètres réseau avancés Samsung ; obtenir la MAC réelle et configurer `ART_TV_MAC`. La capacité de réveil doit être testée sur cet appareil. Ne pas utiliser `POWER_TOGGLE` à l'aveugle.
- **Important :** plusieurs modèles Samsung 2023 utilisent des comportements API spécifiques. Garder le basculement Art Mode OFF/ON tant que la compatibilité n'a pas été vérifiée sur cette TV.
- **Validation avant activation :** `./venv/bin/python -m compileall -q art_engine.py art_cron.py art.py wallpaper.py` ; vérifier ensuite modules, logs, photos et une rotation réelle.
- **Prudence :** la nouvelle gestion des œuvres Samsung et la gestion des uploads bloqués n'ont pas encore été validées sur le téléviseur réel. Une erreur du processus en arrière-plan ne doit pas être considérée comme une validation.

## Mise en route de la nouvelle version (IMPORTANT)

### Ce qui change
- `art.py` lance un cycle unique avec le nouveau moteur, `art_cron.py` lance la boucle continue ;
- `art_engine.py` sélectionne les souvenirs, produit un JPEG 4K, l'envoie à la TV, vérifie une nouvelle œuvre identifiable et l'active ;
- le JPEG envoyé à la TV est enregistré en `current_wallpaper.jpg` **après activation confirmée**. Le fichier demeure disponible même si aucun écran n'est branché ;
- `wallpaper.py` affiche ce même fichier avec `swaybg` **uniquement dans une session graphique Wayland**. L'absence d'écran, de session graphique ou de `swaybg` ne bloque **jamais** le moteur TV ;
- le code supprime uniquement les anciennes œuvres **explicitement identifiées comme appartenant à la version 2**, après activation réussie d'une nouvelle image ; les œuvres antérieures/personnelles sont protégées ;
- l'historique ne s'efface plus à chaque reboot : une nouvelle rotation commence seulement après utilisation de toutes les photos ;
- le contournement Samsung **Art Mode OFF → ON** après upload est conservé. Il pourra être adapté sur la base de tests réels ;
- l'ancien `_art_upload.py` et `_art_set.py` sont conservés dans Git **pour référence historique**, mais ne sont plus appelés par les deux runners.

### Installation sur le Raspberry existant

1. Vérifier la synchronisation Git et la configuration personnelle :
```bash
cd /home/pi/Art-Mode-on-Steroids
git status -sb
git log -1 --oneline
git diff -- config.py
```
2. Vérifier les dépendances :
```bash
./venv/bin/python -c 'import samsungtvws, PIL, wakeonlan; print("Modules OK")'
```
Si `wakeonlan` manque : `./venv/bin/pip install wakeonlan`. L'absence de cette bibliothèque n'empêche pas la rotation si la TV est déjà allumée.
3. Pour que le Raspberry **réveille la TV éteinte**, obtenir son **adresse MAC Ethernet/Wi-Fi effective**, lui conserver l'alimentation réseau en veille et ajouter `ART_TV_MAC` à l'environnement du service (voir ci-dessous). **Sans MAC et Wake-on-LAN compatible, le réveil automatique n'est pas garanti.** Vérifier aussi les paramètres de veille/réveil réseau du Samsung The Frame.
4. Redémarrer le service **après lecture de son unité existante** :
```bash
systemctl cat art-mode.service
sudo systemctl restart art-mode.service
journalctl -u art-mode -n 60 --no-pager
```
5. En cas de réussite, vérifier `ls -lh current_wallpaper.jpg`. Il s'agit d'un fichier généré ; ne pas l'ajouter à Git.

### Configurer le réveil réseau de la TV

**Ne jamais utiliser aveuglément une commande “power toggle”** : elle pourrait éteindre une TV déjà allumée. Le moteur envoie seulement des trames **Wake-on-LAN** si `ART_TV_MAC` est configurée, puis tente de joindre l'API Samsung. Il réessaie jusqu'à trois fois. La compatibilité dépend du modèle, du mode réseau et du firmware.

Sur le Pi, afficher le service : `systemctl cat art-mode.service`. Créer un override (sans modifier l'unité fournie par le système) :
```bash
sudo systemctl edit art-mode.service
```
Dans l'éditeur, ajouter :
```ini
[Service]
Environment="ART_TV_MAC=AA:BB:CC:DD:EE:FF"
```
Remplacer l'adresse fictive **par la MAC de la TV**. Enregistrer, puis :
```bash
sudo systemctl daemon-reload
sudo systemctl restart art-mode.service
```
Sans cette variable, le programme écrit un avertissement clair et poursuit les tentatives de connexion, mais ne peut pas garantir l'allumage de la TV.

### Activer le même fond sur l'écran local (Wayland / labwc)

C'est un **composant facultatif**, exécuté dans la session graphique, pas dans le service système `art-mode`. Sur Debian 13 Raspberry Pi OS avec Wayland/labwc :

```bash
sudo apt install -y swaybg
mkdir -p ~/.config/autostart
cat > ~/.config/autostart/art-mode-wallpaper.desktop <<'EOF'
[Desktop Entry]
Type=Application
Name=Art Mode wallpaper
Exec=/home/pi/Art-Mode-on-Steroids/venv/bin/python /home/pi/Art-Mode-on-Steroids/wallpaper.py
Terminal=false
X-GNOME-Autostart-enabled=true
EOF
```

La session graphique doit être ouverte en tant que `pi` (adaptation nécessaire si le compte est différent). Se déconnecter/reconnecter au bureau, ou redémarrer **une fois**, pour lancer l'observateur. Celui-ci surveille `current_wallpaper.jpg` toutes les trois secondes et actualise `swaybg` lorsque l'image change. S'il n'y a **pas** de session Wayland, il quitte sans erreur. Il ne force **jamais** l'allumage d'un écran et ne modifie pas `art-mode.service`.

**Attention :** si le navigateur Chromium est toujours lancé avec `--kiosk`, il recouvre le fond d'écran. Il faut quitter/désactiver le kiosk pour **voir** l'image sur le bureau. Un bureau Raspberry utilisant un gestionnaire de fond différent peut également masquer `swaybg` ; tester visuellement avant de considérer l'intégration graphique validée. Ce processus n'est pas conçu pour X11.

### Installer sur un Pi vierge

Suivre les étapes de clonage, d'environnement Python, d'images et de service ci-dessous, puis appliquer **le réveil TV et l'observateur graphique ci-dessus**. Le service utilise toujours le nom `art-mode.service` et lance `art_cron.py`, lequel importe maintenant `art_engine.py`. Le dossier `images/` doit être alimenté séparément ; la synchronisation iCloud n'est pas incluse.

### Avant de considérer la migration terminée

Vérifier le journal et la TV sur plusieurs cycles, d'abord avec la TV allumée, puis en veille. **Le comportement Wake-on-LAN reste à valider sur ton modèle précis.** L'upload Samsung dispose désormais d'une attente bornée à 45 secondes : un dépassement n'est **jamais** enregistré comme une réussite. La bibliothèque Samsung peut ne pas renvoyer une nouvelle œuvre identifiable ; dans ce cas, le moteur privilégie un échec journalisé plutôt que de sélectionner au hasard ou supprimer une œuvre. Les anciennes méthodes restent consultables pour diagnostic.

---

# Art-Mode-on-Steroids

> **Un cadre photo intelligent pour Samsung The Frame, piloté par Raspberry Pi.** Le projet sélectionne des souvenirs en fonction de la date, transforme les images en 4K et utilise l'API Art Mode du téléviseur pour les afficher.

**Documentation de référence — 13 octobre 2026.** Ce document distingue le comportement vérifié dans le code de la configuration particulière du Raspberry `piscreen`. Les valeurs de configuration locale et le contenu du service systemd devront être confirmés sur la machine.

## Sommaire

1. [Présentation](#1-présentation)
2. [Architecture](#2-architecture)
3. [Prérequis](#3-prérequis)
4. [Installation de zéro](#4-installation-de-zéro)
5. [Configuration et photothèque](#5-configuration-et-photothèque)
6. [Premier test](#6-premier-test)
7. [Démarrage automatique](#7-démarrage-automatique)
8. [Synchronisation GitHub et déploiement](#8-synchronisation-github-et-déploiement)
9. [Comportement détaillé](#9-comportement-détaillé)
10. [Exploitation et dépannage](#10-exploitation-et-dépannage)
11. [Risques et limites du code actuel](#11-risques-et-limites-du-code-actuel)
12. [Fiche de référence : piscreen](#12-fiche-de-référence--piscreen)

---

## 1. Présentation

Art-Mode-on-Steroids transforme un téléviseur **Samsung The Frame compatible avec l'API Art Mode** en écran de souvenirs photos. Le Raspberry Pi :

1. parcourt une bibliothèque de photos locale ;
2. choisit prioritairement une photo prise le même jour lors d'une année antérieure, puis les dates proches ;
3. la recadre au format **3840 × 2160 (16:9)** et applique un traitement esthétique ;
4. l'envoie au téléviseur via la bibliothèque Python `samsungtvws` ;
5. tente d'activer l'œuvre et de supprimer une ancienne image.

Deux modes sont disponibles : **`art.py`**, pour un seul cycle, et **`art_cron.py`**, pour une exécution répétée.

> **Périmètre :** ce dépôt ne télécharge pas les photos depuis iCloud. La récupération des favoris iCloud est gérée sur `piscreen` par un autre projet, dans `/home/pi/icloud-sync`. Ce projet consomme uniquement des photos déjà présentes dans son dossier `images/`.

## 2. Architecture

```text
Art-Mode-on-Steroids/
├── README.md                    # Ce guide
├── config.py                    # Paramètres d'exécution versionnés
├── art.py                       # Exécution unique
├── art_cron.py                  # Boucle périodique
├── _art_upload.py               # Choix, transformation et upload
├── _art_set.py                  # Activation et suppression sur TV
├── requirements.txt             # Dépendances (liste historique étendue)
├── uploaded_images_empty.json   # Exemple de structure JSON
├── images/                      # Photos locales, non versionnées
├── uploaded_images.json         # Historique généré, non versionné
└── venv/                         # Environnement Python local
```

**Flux :** source de photos → `images/AAAA/MM/JJ/` → `_art_upload.py` → Samsung The Frame → `_art_set.py`. Les deux sous-scripts sont appelés séquentiellement, avec **2 secondes** entre eux. Un fichier JSON garde les traces des images sélectionnées.

**Indépendance :** le navigateur Chromium en mode kiosk Home Assistant peut coexister sur le Raspberry ; il ne fait pas partie de cette application.

## 3. Prérequis

- Raspberry Pi avec Raspberry Pi OS / Debian récent, accès au terminal et droits `sudo`. Installation connue : **Raspberry Pi 4 Model B, Debian 13 Trixie, Python 3.13.5, 4 Go de RAM**.
- TV Samsung The Frame dont l'API Art Mode est accessible via `samsungtvws`. Le support varie suivant le modèle et le firmware : **à tester sur l'appareil cible**.
- Pi et TV sur un réseau local permettant une communication directe. Réserver une adresse IP à la TV dans le routeur est conseillé.
- Images locales accessibles par l'utilisateur exécutant le programme.
- Internet pour installer les paquets et récupérer les mises à jour Git. Les échanges avec la TV sont locaux.

Les chemins ci-dessous utilisent l'utilisateur `pi`, comme sur la machine existante. Pour un Raspberry neuf, remplacer `pi` par le compte choisi lors de l'installation.

## 4. Installation de zéro

### 4.1 Préparer Raspberry Pi OS

Utiliser [Raspberry Pi Imager](https://www.raspberrypi.com/software/) pour installer un système 64 bits. Configurer l'utilisateur, le réseau et SSH dans Imager si nécessaire. Puis, sur le Raspberry :

```bash
sudo apt update
sudo apt upgrade -y
sudo apt install -y git python3 python3-venv python3-pip
```

### 4.2 Récupérer le code

```bash
cd ~
git clone https://github.com/weevood/Art-Mode-on-Steroids.git
cd Art-Mode-on-Steroids
```

Sur la machine historique, ce dossier est `/home/pi/Art-Mode-on-Steroids`.

### 4.3 Installer Python et les dépendances

```bash
python3 -m venv venv
./venv/bin/python -m pip install --upgrade pip
./venv/bin/python -m pip install -r requirements.txt
```

**Attention :** le fichier `requirements.txt` est une liste historique qui comprend de nombreuses bibliothèques non utilisées directement par les scripts (Flask, Selenium, Pandas, OpenCV, etc.). Il peut entraîner des problèmes de versions ou de compilation sous Debian 13/ARM. Si son installation échoue, essayer, pour **tester les scripts présents** :

```bash
./venv/bin/python -m pip install 'samsungtvws==3.0.2' 'Pillow>=11.0.0' 'urllib3>=2'
```

Ce jeu minimal découle des imports directs du code ; la compatibilité complète dépend aussi des dépendances transitives et du téléviseur. Les versions réellement opérationnelles doivent être validées sur la machine.

### 4.4 Préparer les photos

La bibliothèque n'est pas incluse dans le dépôt. Configurer le dossier `images/` comme décrit ci-dessous. Tester manuellement **avant** d'activer une boucle ou un service.

## 5. Configuration et photothèque

### 5.1 `config.py`

```python
TV_IP = "192.168.1.20"   # Exemple présent dans le dépôt
INTERVAL = 60            # En secondes (>= 90 recommandé par le commentaire du code)
MATTE = "shadowbox_antique"
# IMAGES_DIR = Path(__file__).parent / "images"
# LAST_IMAGE_FILE = Path(__file__).parent / "uploaded_images.json"
```

| Paramètre | Description |
| --- | --- |
| `TV_IP` | IP de la TV sur le réseau local ; mettre une réservation DHCP |
| `INTERVAL` | Intervalle cible entre les **débuts** de deux cycles, pas une pause après chaque cycle |
| `MATTE` | Type / couleur de bordure Art Mode ; compatibilité selon le téléviseur |
| `IMAGES_DIR` | Dossier de photos (`images/` sous le dépôt par défaut) |
| `LAST_IMAGE_FILE` | Historique local de rotation (`uploaded_images.json`) |

**Piège Git :** `config.py` est versionné. Toute modification locale peut empêcher un futur `git pull --ff-only` si le même fichier évolue dans GitHub. Ne jamais exécuter `git reset --hard` sans sauvegarder les paramètres locaux. Aucun mécanisme `config.local.py` n'est implémenté dans le code actuel.

### 5.2 Organisation des images

```text
images/
├── 2021/10/13/IMG_001.jpg
├── 2022/10/14/IMG_002.jpeg
└── 2024/10/15/souvenir.png
```

Les **trois premiers dossiers** après `images/` doivent représenter l'année, le mois et le jour (`AAAA/MM/JJ`) pour activer la sélection par souvenir. Les extensions acceptées sont `.jpg`, `.jpeg`, `.png` et `.bmp`, sans sensibilité à la casse. Le code **ne lit pas les dates EXIF**.

On peut utiliser un **lien symbolique** si les photos sont déjà stockées ailleurs :

```bash
cd ~/Art-Mode-on-Steroids
# Seulement si images/ n'existe pas déjà et ne contient aucune photo :
ln -s /chemin/vers/phototheque images
ls -l images
find -L images -type f | head
```

Ne pas supprimer ou remplacer `images/` sans inspecter son contenu et sa destination.

### 5.3 Source iCloud (optionnelle)

Sur `piscreen`, une tâche cron indépendante existe :

```cron
0 */1 * * * /home/pi/icloud-sync/sync-icloud-favourites.sh >> /home/pi/icloud-sync/sync-favourites.log 2>&1
```

Elle tourne toutes les heures. **Son code, son authentification et le chemin réel des photos ne sont pas disponibles dans ce dépôt.** Sur un Raspberry neuf, il faut configurer séparément une source de photos puis relier `images/` au répertoire obtenu.

## 6. Premier test

Dans le dossier du dépôt :

```bash
cd ~/Art-Mode-on-Steroids
./venv/bin/python -c "import samsungtvws, PIL, urllib3; print('Imports OK')"
ls -ld images
find -L images -type f | head
```

Vérifier également que `TV_IP` correspond à la bonne TV. Ensuite :

```bash
./venv/bin/python art.py
```

> **Attention : cette commande n'est pas un test en lecture seule.** Elle peut envoyer une photo, changer le mode Art et **supprimer une œuvre présente sur la TV**. Sauvegarder les œuvres précieuses et consulter les limites de la section 11 avant l'essai.

Lorsque l'exécution unique a été validée, tester la boucle :

```bash
./venv/bin/python art_cron.py
# Ctrl+C pour arrêter
```

Ne pas lancer cette boucle **en parallèle** de `art-mode.service`, sous peine de commandes concurrentes envoyées au téléviseur.

## 7. Démarrage automatique

### 7.1 Machine déjà configurée

Sur `piscreen`, le service **`art-mode.service` est activé** et lance `art_cron.py` via `venv/bin/python`. Avant toute modification, consulter le fichier effectif :

```bash
systemctl cat art-mode.service
systemctl status art-mode.service --no-pager
```

Le contenu exact du service historique n'a pas encore été relevé : **ne pas remplacer aveuglément sa configuration**.

### 7.2 Sur un Raspberry neuf uniquement

Créer une unité systemd (adapter le compte et les chemins si nécessaire) :

```bash
sudo tee /etc/systemd/system/art-mode.service >/dev/null <<'EOF_SERVICE'
[Unit]
Description=Samsung The Frame - Art-Mode-on-Steroids
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/Art-Mode-on-Steroids
ExecStart=/home/pi/Art-Mode-on-Steroids/venv/bin/python /home/pi/Art-Mode-on-Steroids/art_cron.py
Restart=on-failure
RestartSec=15

[Install]
WantedBy=multi-user.target
EOF_SERVICE

sudo systemctl daemon-reload
sudo systemctl enable --now art-mode.service
```

⚠️ `tee` remplace le contenu d'un fichier existant : cette procédure est destinée à une **installation neuve**, pas à modifier `piscreen` sans précaution.

### 7.3 Commandes indispensables

```bash
sudo systemctl status art-mode --no-pager
sudo systemctl stop art-mode
sudo systemctl start art-mode
sudo systemctl restart art-mode
journalctl -u art-mode -n 100 --no-pager
journalctl -u art-mode -f
```

## 8. Synchronisation GitHub et déploiement

Dépôt : https://github.com/weevood/Art-Mode-on-Steroids — branche `main`.

Sur `piscreen`, le remote `origin` est en **HTTPS**. Une tâche cron tire les changements toutes les deux minutes :

```cron
*/2 * * * * /usr/bin/git -C /home/pi/Art-Mode-on-Steroids pull --ff-only >> /home/pi/git-update.log 2>&1
```

Pour reproduire cette synchronisation sur une nouvelle machine, lancer `crontab -e` et ajouter cette ligne en adaptant le chemin.

**Ce mécanisme réalise uniquement un `git pull` :**

- il récupère les commits à condition qu'aucun conflit ne bloque la fusion rapide ;
- il ne redémarre **pas** le processus Python ;
- il ne met pas automatiquement à jour les bibliothèques de `venv` ;
- il ne garantit pas un déploiement atomique pendant l'exécution ;
- il peut échouer à cause de modifications locales, notamment `config.py`.

Contrôler les synchronisations :

```bash
cd ~/Art-Mode-on-Steroids
git status -sb
git log -1 --oneline
tail -n 30 ~/git-update.log
```

**Tester une mise à jour documentaire :** après publication d'un commit modifiant ce README, comparer le SHA affiché sur GitHub à celui retourné par `git log -1 --oneline`, et vérifier le journal après le prochain passage cron. **Aucun redémarrage du service n'est nécessaire pour une modification du README.**

Pour des changements de code, vérifier d'abord le diff et les logs, puis procéder à un redémarrage **contrôlé** avec `sudo systemctl restart art-mode` ; noter le SHA précédent (`git rev-parse HEAD`) et conserver une sauvegarde de la configuration.

## 9. Comportement détaillé

### 9.1 Sélection des souvenirs

La date d'une photo est déduite de son chemin de dossier. La sélection privilégie, dans l'ordre :

1. le même jour et mois lors d'une année précédente ;
2. un écart maximal de ±1 jour ;
3. ±2 jours ;
4. ±3 jours ;
5. ±7 jours ;
6. le même mois lors d'une année précédente ;
7. une photo restante en solution de repli.

À chaque niveau, une photo est sélectionnée **aléatoirement** parmi les candidates non présentes dans l'historique. Les dates non valides, absentes ou futures sont traitées comme candidates de repli.

### 9.2 Traitement des images

`_art_upload.py` effectue un **recadrage central en 16:9**, redimensionne à 3840 × 2160 avec Lanczos, applique `SMOOTH_MORE`, augmente légèrement le contraste (`1.08`), réduit la saturation (`0.95`) et la netteté (`0.8`), puis encode en JPEG qualité `92`. L'API Samsung est sollicitée avec la bordure `MATTE`.

### 9.3 Rotation et historique

`art.py` exécute un cycle unique. `art_cron.py` répète le cycle et compense sa durée pour viser `INTERVAL` secondes entre les **débuts** de cycles. Si un cycle dépasse l'intervalle, le prochain commence sans attente supplémentaire.

**Particularité importante :** au démarrage, `art_cron.py` exécute `reset_uploaded_images_file()` qui réinitialise `uploaded_images.json` à `{"uploaded_images": []}`. Une relance du service peut donc conduire à choisir à nouveau des photos déjà affichées. Le JSON n'est pas une archive pérenne.

## 10. Exploitation et dépannage

| Besoin / symptôme | Vérification ou action |
| --- | --- |
| Application active ? | `systemctl status art-mode --no-pager` |
| Journaux récents | `journalctl -u art-mode -n 100 --no-pager` |
| Journaux en direct | `journalctl -u art-mode -f` |
| Arrêter puis relancer | `sudo systemctl stop art-mode` puis `sudo systemctl start art-mode` |
| Photos introuvables | `ls -ld images` ; `find -L images -type f | head` |
| TV inaccessible | Vérifier `TV_IP`, le LAN, l'état de la TV et la compatibilité de l'API |
| Mise à jour Git bloquée | `git status -sb` ; `tail -n 30 ~/git-update.log` |
| Code récupéré mais ancien comportement | Vérifier `git log -1 --oneline`, puis redémarrage contrôlé du service |
| Historique réinitialisé | C'est le comportement actuel au démarrage de `art_cron.py` |
| Différence entre kiosk et Art Mode | Le kiosk Home Assistant est géré séparément par `~/.config/autostart/kiosk.desktop` |

Pour inspecter l'exécution réelle :

```bash
pgrep -af 'art.py|art_cron.py|_art_upload.py|_art_set.py'
```

Pour une réinstallation, **sauvegarder séparément** les photos, la configuration locale, la définition effective de l'unité systemd et les scripts d'import. Ne jamais mettre de mot de passe, jeton ou clé SSH privée dans ce dépôt public.

## 11. Risques et limites du code actuel

Ces points proviennent de la lecture du **code existant**, et ne sont pas des corrections déjà réalisées :

1. **Suppression risquée :** `_art_set.py` prend l'œuvre la plus récente à afficher et la **troisième plus récente** (`valid[2]`) à supprimer, sans confirmer qu'elle a été créée par ce programme. S'il existe moins de trois œuvres valides, le script peut lever une exception. **Attention aux images personnelles stockées sur la TV.**
2. **Confirmation d'upload insuffisante :** le thread d'upload attend 30 secondes ; s'il est encore actif après ce délai, le script peut quand même ajouter l'image à l'historique. Une erreur dans le thread ne remonte pas correctement au processus principal.
3. **Historique effacé au démarrage** de `art_cron.py`, et donc photos susceptibles de réapparaître après reboot.
4. **Erreurs parfois ignorées :** les runners utilisent `subprocess.run(..., check=False)`. Ils peuvent poursuivre après une étape échouée.
5. **Chemins relatifs :** les sous-scripts sont lancés par nom de fichier. Utiliser le répertoire du projet ou déclarer `WorkingDirectory` dans systemd.
6. **Cas particuliers du calendrier :** le calcul des anniversaires mérite des tests, notamment aux changements d'année et le 29 février.
7. **Configuration locale suivie par Git :** les modifications à `config.py` peuvent empêcher une synchronisation future.
8. **Pas de suite de tests, de rollback intégré ni de déploiement atomique** dans la version actuelle.

**Priorités pour la suite :** sécuriser la suppression d'œuvres, confirmer les uploads, préserver l'historique, isoler la configuration locale, puis ajouter des tests et un redémarrage de service après validation.

## 12. Fiche de référence : piscreen

**Observations du 13 octobre 2026 ; à revalider sur le Raspberry.**

| Élément | État connu |
| --- | --- |
| Hôte | `piscreen` |
| Matériel | Raspberry Pi 4 Model B Rev 1.5, RAM 4 Go |
| Système | Debian GNU/Linux 13 (Trixie), aarch64 |
| Python | 3.13.5 |
| Carte SD | 128 Go commerciaux (~117 Gio) |
| Projet | `/home/pi/Art-Mode-on-Steroids` |
| Python virtuel | `/home/pi/Art-Mode-on-Steroids/venv` |
| Processus actif | `/home/pi/Art-Mode-on-Steroids/venv/bin/python .../art_cron.py` |
| Service | `art-mode.service`, activé ; définition exacte à inspecter |
| Remote Git | `https://github.com/weevood/Art-Mode-on-Steroids.git` |
| Branche | `main` |
| Commit observé | `9956ef6` avant mise à jour du README |
| Modifications locales | `config.py` modifié ; contenu non vérifié |
| Mise à jour du dépôt | `git pull --ff-only` toutes les deux minutes par cron |
| Synchronisation iCloud | `/home/pi/icloud-sync/sync-icloud-favourites.sh` toutes les heures |
| Photothèque | Emplacement et éventuel lien symbolique **à confirmer** |
| Kiosk distinct | Chromium ouvrant Home Assistant via `~/.config/autostart/kiosk.desktop` |

### Commande de diagnostic à conserver

```bash
cd /home/pi/Art-Mode-on-Steroids
hostname
cat /etc/os-release | grep PRETTY_NAME
git status -sb
git log -1 --oneline
git diff -- config.py
systemctl cat art-mode.service
systemctl status art-mode.service --no-pager
crontab -l
ls -ld images venv uploaded_images.json 2>&1
readlink -f images
journalctl -u art-mode -n 50 --no-pager
tail -n 20 ~/git-update.log
```

**À compléter prochainement :** configuration réelle du service, chemin exact de la photothèque iCloud et paramètres locaux de la TV (sans secrets).

---

### Références

- [Dépôt GitHub](https://github.com/weevood/Art-Mode-on-Steroids)
- [Bibliothèque samsungtvws](https://github.com/xchwarze/samsung-tv-ws-api)
- [Raspberry Pi Imager](https://www.raspberrypi.com/software/)

*Ce guide documente le système observé sans supposer que les composants externes (iCloud, configuration locale, firmware Samsung) sont inclus dans GitHub.*\n\n---\n**Note de version :** les sections historiques ci-dessus décrivent le code initial et servent de référence à la migration. Pour le **comportement actif**, privilégier les instructions « Version 2 » en tête du document ; l'ancienne suppression automatique n'est plus utilisée par les runners.\n