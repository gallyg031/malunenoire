# -*- coding: utf-8 -*-
"""
build_fonds.py — fonds illustrés par signe (spec 04 §4).

Source : design/uploads/LLN_<Signe>.png (941 × 1672, privés, hors dépôt).
Sortie (static/fonds/, privé, hors dépôt) :
  <signe>.jpg      1080 × 1920, JPEG q85   (rendu PNG des cartes)
  <signe>.webp     1080 × 1920, WebP q80   (cartes dans le site)
  <signe>-390.webp  390 × 693,  WebP q80   (fond qui affleure au scroll)

Recadrage « cover » ancré en haut. Table de noms explicite (accents des fichiers source).
Usage : python scripts/build_fonds.py
"""

import os
import sys

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "design", "uploads")
OUT = os.path.join(ROOT, "static", "fonds")

SOURCES = {
    "belier": "LLN_Bélier.png", "taureau": "LLN_Taureau.png", "gemeaux": "LLN_Gemeaux.png",
    "cancer": "LLN_Cancer.png", "lion": "LLN_Lion.png", "vierge": "LLN_Vierge.png",
    "balance": "LLN_Balance.png", "scorpion": "LLN_Scorpion.png",
    "sagittaire": "LLN_Sagittaire.png", "capricorne": "LLN_Capricorne.png",
    "verseau": "LLN_Verseau.png", "poissons": "LLN_Poissons.png",
}
TAILLES = [((1080, 1920), "{}.jpg", "JPEG", {"quality": 85, "optimize": True, "progressive": True}),
           ((1080, 1920), "{}.webp", "WEBP", {"quality": 80, "method": 6}),
           ((390, 693), "{}-390.webp", "WEBP", {"quality": 80, "method": 6})]


def cover_haut(img, w, h):
    """Redimensionne pour couvrir w × h puis recadre, ancré en haut, centré horizontalement."""
    s = max(w / img.width, h / img.height)
    r = img.resize((round(img.width * s), round(img.height * s)), Image.LANCZOS)
    x = (r.width - w) // 2
    return r.crop((x, 0, x + w, h))


def build():
    os.makedirs(OUT, exist_ok=True)
    manquants = []
    for signe, nom in SOURCES.items():
        src = os.path.join(SRC, nom)
        if not os.path.exists(src):
            manquants.append(nom)
            continue
        img = Image.open(src).convert("RGB")
        for (w, h), motif, fmt, opts in TAILLES:
            cover_haut(img, w, h).save(os.path.join(OUT, motif.format(signe)), fmt, **opts)
        poids = {m.format(signe): os.path.getsize(os.path.join(OUT, m.format(signe))) // 1024
                 for _, m, _, _ in TAILLES}
        print(signe, " · ".join(f"{k} {v} Ko" for k, v in poids.items()))
    if manquants:
        print("sources manquantes :", ", ".join(manquants))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(build())
