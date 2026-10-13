#!/usr/bin/env python3
"""Read-only health check. Exit 0=OK, 1=warning, 2=error.

SSH/iOS shortcut:
cd /home/pi/Art-Mode-on-Steroids && ./venv/bin/python diagnostics.py
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import shutil
import socket
import subprocess
from pathlib import Path

from config import IMAGES_DIR, TV_IP
from art_engine import BLOCKLIST, EXTENSIONS, history

MIN_FREE_GIB = 0.5


def check(*, network: bool = True) -> int:
    problems = []
    warnings = []
    print("Art Mode — diagnostic (read-only)")
    files = ([p for p in IMAGES_DIR.rglob("*") if p.is_file() and p.suffix.lower() in EXTENSIONS]
             if IMAGES_DIR.is_dir() else [])
    print(f"Photos: {len(files)} | Dossier: {IMAGES_DIR}")
    if not files:
        problems.append("Dossier photos inexistant ou vide")

    try:
        excluded = json.loads(BLOCKLIST.read_text(encoding="utf-8")) if BLOCKLIST.exists() else []
        if not isinstance(excluded, list):
            raise ValueError("format attendu : liste JSON")
        valid_names = {p.relative_to(IMAGES_DIR).as_posix() for p in files}
        usable = len(valid_names - set(excluded))
        print(f"Photos exclues: {len(excluded)} | Disponibles: {usable}")
        if not usable:
            problems.append("Toutes les photos sont exclues")
    except (ValueError, OSError, TypeError) as exc:
        problems.append(f"Liste des exclusions invalide : {exc}")

    try:
        records = history()
        print(f"Historique: {len(records)} œuvres")
    except Exception as exc:
        warnings.append(f"Historique inaccessible : {exc}")

    status = subprocess.run(["systemctl", "is-active", "art-mode.service"],
                            capture_output=True, text=True, timeout=8)
    state = status.stdout.strip() or "unknown"
    print(f"Service: {state}")
    if state != "active":
        warnings.append("Rotation actuellement arrêtée (éventuellement volontaire)")

    free_gib = shutil.disk_usage(IMAGES_DIR if IMAGES_DIR.is_dir() else Path.home()).free / 1024**3
    print(f"Espace libre: {free_gib:.1f} Gio")
    if free_gib < MIN_FREE_GIB:
        warnings.append("Espace disque faible (< 0,5 Gio)")

    if network:
        try:
            with socket.create_connection((TV_IP, 8002), timeout=4):
                print(f"Télévision {TV_IP}: TCP 8002 accessible")
        except OSError as exc:
            warnings.append(f"Télévision {TV_IP}: port TCP 8002 inaccessible ({exc})")
    else:
        print("Télévision: vérification réseau ignorée (--offline)")
    for issue in problems:
        print(f"ERREUR: {issue}")
    for issue in warnings:
        print(f"ATTENTION: {issue}")
    result = 2 if problems else 1 if warnings else 0
    print("BILAN:", "ERREUR" if result == 2 else "ATTENTION" if result == 1 else "OK")
    return result


def notification(network: bool = True) -> str:
    """Compact iOS notification. Internal verbose diagnostic stays unchanged."""
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        result = check(network=network)
    lines = stream.getvalue().splitlines()
    def find(prefix: str) -> str:
        return next((line for line in lines if line.startswith(prefix)), "")
    photos = find("Photos: ")
    counts = find("Photos exclues: ")
    service = find("Service: ").removeprefix("Service: ")
    free = find("Espace libre: ").removeprefix("Espace libre: ")
    tv = find("Télévision ")
    title = ("✅ Tout fonctionne" if result == 0 else
             "⚠️ Vérification nécessaire" if result == 1 else
             "❌ Problème détecté")
    count = photos.split("|")[0].replace("Photos: ", "").strip()
    excluded = counts.split("|")[0].replace("Photos exclues: ", "").strip()
    usable = counts.split("Disponibles: ")[-1].strip() if "Disponibles: " in counts else "?"
    tv_icon = ("✅" if "TCP 8002 accessible" in tv else
               "➖" if not network else "⚠️")
    tv_label = ("accessible" if tv_icon == "✅" else
                "non vérifiée" if not network else "inaccessible")
    service_icon = "✅" if service == "active" else "⏸️" if service == "inactive" else "⚠️"
    result_lines = [
        "🖼 The Frame — Diagnostic",
        title,
        f"{tv_icon} TV : {tv_label}",
        f"📷 Photos : {usable}/{count} disponibles",
        f"🚫 Exclues : {excluded}",
        f"{service_icon} Rotation : {'active' if service == 'active' else 'arrêtée' if service == 'inactive' else service}",
        f"💾 Disque : {free} libres",
    ]
    issues = [line for line in lines if line.startswith(("ERREUR:", "ATTENTION:"))
              and not line.startswith("ATTENTION: Rotation actuellement arrêtée")]
    if issues:
        result_lines.append("• " + issues[0].split(": ", 1)[-1][:85])
    return "\n".join(result_lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true", help="Do not contact the TV")
    parser.add_argument("--notification", action="store_true", help="Compact iOS notification output")
    args = parser.parse_args()
    if args.notification:
        print(notification(network=not args.offline))
    else:
        raise SystemExit(check(network=not args.offline))
