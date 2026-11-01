# Sélection automatique The Frame (mode ajout uniquement)

Le Mac lit l'album intelligent Apple Photos `The Frame` avec AppleScript, récupère les métadonnées via OSXPhotos et retient les photos horizontales (ratio >= 1,3), au moins 1600 × 900 pixels, avec un score esthétique Apple `overall >= 0,75`. Pas de plafond d'images. Les vidéos, captures d'écran, images masquées et supprimées sont exclues.

Toutes les deux heures **quand le Mac est allumé et qu'une session utilisateur est ouverte**, le LaunchAgent lance :
1. La sélection des UUID (sans export d'images rejetées)
2. L'export incrémental JPEG vers `~/Pictures/TheFrameExport` (sans `--cleanup`)
3. `rsync` des JPEG vers `pi@piscreen.local:/home/pi/Pictures/ArtModeAlbum/` (**sans `--delete`**)

**Les photos historiques sont préservées sur le Mac et le Pi**, même si elles ne sont plus dans l'album intelligent ou passent sous le seuil esthétique. Les fichiers existants de même chemin peuvent être actualisés. Aucune donnée de Photos n'est supprimée.

## Installation sur le Mac

Depuis le dépôt local :
```zsh
git switch feature/smart-frame-aesthetic-075
git pull --ff-only
"$HOME/.venvs/frame-curation/bin/python" -m pip install osxphotos
"$HOME/.venvs/frame-curation/bin/python" mac/select_frame.py
./mac/sync-the-frame.zsh
/bin/zsh ./mac/install-launchagent.zsh
```

Vérifier les journaux :
```zsh
tail -n 50 "$HOME/Library/Logs/ArtModeSync/launchd.log"
tail -n 50 "$HOME/Library/Logs/ArtModeSync/launchd-error.log"
```

Le script utilise `~/.venvs/frame-curation/bin/python` et `/opt/homebrew/bin/osxphotos`, conformes à la machine de référence. Le service ne peut pas agir lorsque le Mac est éteint ; le Raspberry continue alors sa rotation locale.

**Important** : le LaunchAgent exécute des copies dans `~/Library/Application Support/ArtModeSync/bin/`. Après un `git pull`, réexécuter `/bin/zsh ./mac/install-launchagent.zsh` pour déployer les modifications.

Cette fonctionnalité a été vérifiée au niveau du code et des UUID sur le Mac de référence, mais le nouveau flux complet n'a pas encore été testé sur son installation après modification.
