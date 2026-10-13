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

*Ce guide documente le système observé sans supposer que les composants externes (iCloud, configuration locale, firmware Samsung) sont inclus dans GitHub.*