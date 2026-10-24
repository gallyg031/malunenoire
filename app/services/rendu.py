# -*- coding: utf-8 -*-
"""Rendu PNG des cartes (spec 04 §1, §5, §8) : SVG → PNG par resvg, polices embarquées.

Les polices du site sont en WOFF2 ; resvg lit le TTF : conversion une fois par processus
(fontTools), dans un dossier temporaire. Aucune police système : rendu déterministe.
"""

import functools
import io
import os
import tempfile
import threading

import resvg_py
from fontTools.ttLib import TTFont
from PIL import Image

from app.services import cartes

FONTS = os.path.join(cartes.ROOT, "static", "fonts")
STATIC = os.path.join(cartes.ROOT, "static")
FACES = ["cormorant-garamond-latin-500-normal", "cormorant-garamond-latin-500-italic",
         "marcellus-latin-400-normal"]
# Les fichiers fontsource se nomment « Cormorant Garamond Light » (instance variable) :
# on rétablit la famille que les gabarits demandent.
FAMILLES = {"cormorant": "Cormorant Garamond"}
_verrou = threading.Lock()


@functools.lru_cache(maxsize=1)
def polices_ttf():
    dossier = os.path.join(tempfile.gettempdir(), "lln-polices-v2")
    os.makedirs(dossier, exist_ok=True)
    chemins = []
    for nom in FACES:
        ttf = os.path.join(dossier, f"{nom}.ttf")
        if not os.path.exists(ttf):
            f = TTFont(os.path.join(FONTS, f"{nom}.woff2"))
            f.flavor = None
            famille = next((v for k, v in FAMILLES.items() if nom.startswith(k)), None)
            if famille:
                for rec in f["name"].names:
                    if rec.nameID in (1, 16):
                        rec.string = famille
            f.save(ttf)
        chemins.append(ttf)
    return chemins


def _resvg(svg, largeur, hauteur):
    with _verrou:                      # on sérialise pour borner la mémoire
        data = resvg_py.svg_to_bytes(svg_string=svg, font_files=polices_ttf(), skip_system_fonts=True,
                                     resources_dir=STATIC, width=largeur, height=hauteur)
    return Image.open(io.BytesIO(bytes(data)))


def _encoder(img, quantifier):
    img = img.convert("RGB")
    if quantifier:                     # fond photo : palette 256 couleurs tramée (poids < 900 Ko)
        img = img.quantize(colors=256, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.FLOYDSTEINBERG)
    out = io.BytesIO()
    img.save(out, "PNG", compress_level=6)
    return out.getvalue()


def png(svg, largeur, hauteur, quantifier=False):
    """SVG (chaîne) → octets PNG."""
    return _encoder(_resvg(svg, largeur, hauteur), quantifier)


# Les fonds (photo, dégradé pleine page) coûtent l'essentiel du rendu et ne dépendent que du
# design et du signe : rendus une fois, gardés en mémoire ; resvg ne dessine ensuite que le
# calque (cadre, éclipse, texte) sur fond transparent.

@functools.lru_cache(maxsize=4)
def _fond_carte(design, signe):
    if design == "illustre":
        return Image.open(os.path.join(STATIC, "fonds", f"{signe}.jpg")).convert("RGBA")
    return _resvg(cartes.eclipse_fond_svg(), cartes.W, cartes.H).convert("RGBA")


@functools.lru_cache(maxsize=4)
def _fond_og(signe):
    """Fond OG du design illustré : la photo recadrée et voilée."""
    return _resvg(cartes.og_fond_svg(f"fonds/{signe}.jpg"), cartes.OG_W, cartes.OG_H).convert("RGBA")


def carte_png(env, design, signe, phrase, accent, signe_label, house_roman):
    design = cartes.design_effectif(design, signe)
    if design in ("illustre", "eclipse"):
        svg = cartes.svg(env, design, signe, phrase, accent, signe_label, house_roman, uid="png",
                         sans_fond=True)
        calque = _resvg(svg, cartes.W, cartes.H).convert("RGBA")
        img = Image.alpha_composite(_fond_carte(design, signe), calque)
        return _encoder(img, quantifier=design == "illustre")
    svg = cartes.svg(env, design, signe, phrase, accent, signe_label, house_roman, uid="png")
    return png(svg, cartes.W, cartes.H)


def og_png(env, design, signe, phrase, signe_label, house_roman):
    design = cartes.design_effectif(design, signe)
    if design == "illustre":
        svg = cartes.og_svg(env, design, signe, phrase, signe_label, house_roman, fond_url=None,
                            sans_fond=True)
        calque = _resvg(svg, cartes.OG_W, cartes.OG_H).convert("RGBA")
        return _encoder(Image.alpha_composite(_fond_og(signe), calque), quantifier=True)
    svg = cartes.og_svg(env, design, signe, phrase, signe_label, house_roman, fond_url=None)
    return png(svg, cartes.OG_W, cartes.OG_H)
