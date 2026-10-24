# -*- coding: utf-8 -*-
"""Mesure et retour à la ligne des phrases des cartes (spec 04 §1).

Les largeurs viennent des polices elles-mêmes (fontTools, avances horizontales),
la coupe se fait sur les espaces, et les lignes sont équilibrées « à la pretty » :
même nombre de lignes que la coupe gloutonne, mais la plus petite largeur maximale.
"""

import functools
import os

from fontTools.ttLib import TTFont

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FONTS = os.path.join(ROOT, "static", "fonts")
FACES = {
    ("cormorant", "normal"): "cormorant-garamond-{sub}-500-normal.woff2",
    ("cormorant", "italic"): "cormorant-garamond-{sub}-500-italic.woff2",
    ("marcellus", "normal"): "marcellus-{sub}-400-normal.woff2",
}


@functools.lru_cache(maxsize=None)
def _avances(famille, style):
    """{caractère: avance en unités/em} sur les sous-ensembles latin + latin-ext."""
    out, upem = {}, 1000
    for sub in ("latin-ext", "latin"):          # latin en dernier : il l'emporte
        f = TTFont(os.path.join(FONTS, FACES[(famille, style)].format(sub=sub)))
        upem = f["head"].unitsPerEm
        hmtx = f["hmtx"]
        for cp, glyph in f.getBestCmap().items():
            out[chr(cp)] = hmtx[glyph][0] / upem
    return out


def largeur(texte, taille, famille="cormorant", style="normal", espacement=0.0):
    av = _avances(famille, style)
    defaut = av.get("n", 0.5)
    return sum(av.get(c, defaut) for c in texte) * taille + espacement * max(len(texte) - 1, 0)


def _glouton(mots, mesure, max_w):
    lignes, cur = [], []
    for m in mots:
        essai = cur + [m]
        if cur and mesure(" ".join(essai)) > max_w:
            lignes.append(cur)
            cur = [m]
        else:
            cur = essai
    if cur:
        lignes.append(cur)
    return lignes


def couper(texte, taille, max_w, famille="cormorant", style="normal", mesure=None):
    """Lignes équilibrées (liste de chaînes)."""
    mesure = mesure or (lambda s: largeur(s, taille, famille, style))
    mots = texte.split()
    n = len(_glouton(mots, mesure, max_w))
    lo, hi = max(mesure(m) for m in mots), max_w
    for _ in range(30):                          # plus petite largeur donnant n lignes
        mid = (lo + hi) / 2
        if len(_glouton(mots, mesure, mid)) <= n:
            hi = mid
        else:
            lo = mid
    return [" ".join(l) for l in _glouton(mots, mesure, hi)]


def phrase_carte(texte, tailles=(72, 65, 58), max_lignes=(3, 5), max_w=850):
    """Taille et lignes de la phrase d'une carte (spec 04 §2) : 72 px jusqu'à 3 lignes, 65 px
    à partir de 4 (la spec écrit « > 4 », mais son test et la maquette passent sagittaire-09,
    4 lignes, en 65 px), 58 px au-delà de 5 lignes."""
    for i, t in enumerate(tailles):
        lignes = couper(texte, t, max_w)
        if i == len(tailles) - 1 or len(lignes) <= max_lignes[i]:
            return t, lignes
    return tailles[-1], lignes


def segments_accent(ligne, accent):
    """Découpe une ligne en [(texte, est_accent)] pour le <tspan> du design verdict."""
    if not accent or accent not in ligne:
        return [(ligne, False)]
    i = ligne.index(accent)
    out = [(ligne[:i], False), (accent, True), (ligne[i + len(accent):], False)]
    return [s for s in out if s[0]]


def couper_verdict(texte, accent, taille=112, max_w=850):
    """Verdict : l'accent est en italique, mesuré comme tel."""
    def mesure(s):
        if accent and accent in s:
            i = s.index(accent)
            return (largeur(s[:i], taille) + largeur(accent, taille, style="italic")
                    + largeur(s[i + len(accent):], taille))
        return largeur(s, taille)
    return couper(texte, taille, max_w, mesure=mesure)
