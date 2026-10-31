# Smart album aesthetic selection (candidate implementation)

The macOS sync now reads Photos' smart album named `The Frame` through AppleScript and OSXPhotos Python metadata. It selects still images that meet all of these conditions:
- Landscape: width/height >= 1.30
- Width >= 1600 and height >= 900
- Not hidden, trashed, screenshot, or video
- Apple Photos `score.overall >= 0.75`
- No arbitrary number limit; images without an Apple score are excluded

The selection script writes an atomic UUID manifest to `~/Library/Application Support/ArtModeSync/selected-uuids.txt`. OSXPhotos exports edited JPEGs using `--uuid-from-file`, preserving date folders. The existing rsync protections remain in place.

## Prerequisite

`$HOME/.venvs/frame-curation/bin/python` must exist and have `osxphotos` installed. This matches the Python virtual environment used during the initial tests. Set up with:
```bash
$HOME/.venvs/frame-curation/bin/python -m pip install osxphotos
```

## Before activation

This branch is a proposed migration, not enabled automatically. Do **not** reinstall the LaunchAgent until you are ready.

From the Mac checkout of this branch:
```bash
git switch feature/smart-frame-aesthetic-075
$HOME/.venvs/frame-curation/bin/python mac/select_frame.py
wc -l "$HOME/Library/Application Support/ArtModeSync/selected-uuids.txt"
```
Review the count and the nearby CSV. The old LaunchAgent continues to use its previously installed script.

## Safe migration to production

1. Back up the existing `~/Pictures/TheFrameExport` and inspect the proposed selection count; avoid leaving any backup within that export directory.
2. Check `--uuid-from-file` is supported by the installed OSXPhotos with `osxphotos export --help`.
3. Run `./mac/sync-the-frame.zsh` manually and inspect the logs.
4. A drop greater than 20% from the old Raspberry collection is intentionally refused. Do not disable that guard blindly; inspect both libraries and explicitly plan a one-time approved migration. If the migration blocks, the current Raspberry collection remains intact.
5. Only after a successful verified end-to-end test, reinstall the LaunchAgent using `/bin/zsh ./mac/install-launchagent.zsh`.

Notes: Apple aesthetic scoring is an imperfect subjective ranking and a threshold of 0.75 may produce few candidates. No photos are deleted from Apple Photos. Current code has not been validated on the user's Mac or TV.
