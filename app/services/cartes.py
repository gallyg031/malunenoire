# -*- coding: utf-8 -*-
"""Cartes SVG (spec 04) : mise en page en unités 1080 × 1920, rendu par un gabarit Jinja.

La même source sert au carrousel (inline), au sanctuaire, à /c/ et, au lot 4, au PNG.
"""

import os
import secrets

from app.services import typo

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FONDS = os.path.join(ROOT, "static", "fonds")
DESIGNS = ("illustre", "eclipse", "verdict")

W, H = 1080, 1920
MARGE = 43                      # cadre à 43 px du bord
PAD_X, PAD_HAUT, PAD_BAS = 65, 65, 72
X0, X1 = MARGE + PAD_X, W - MARGE - PAD_X
CX = W / 2
HAUT = MARGE + PAD_HAUT
BAS = H - MARGE - PAD_BAS

SCEAU = 58
MARQUE = {"taille": 29, "esp": 11}
SIGNE = {"taille": 36, "esp": 12.6}
SIGNATURE = {"taille": 29, "esp": 9}
INTERLIGNE = 1.4
ECLIPSE = 475


def fond_existe(signe):
    return os.path.exists(os.path.join(FONDS, f"{signe}.webp"))


def designs_disponibles(signe):
    return [d for d in DESIGNS if d != "illustre" or fond_existe(signe)]


def design_effectif(design, signe):
    """`illustre` sans fond pour ce signe → `eclipse` (spec 04 §3)."""
    if design not in DESIGNS:
        return "illustre" if fond_existe(signe) else "eclipse"
    return "eclipse" if design == "illustre" and not fond_existe(signe) else design


def _marque(y_centre):
    """Sceau + « MA LUNE NOIRE », groupe centré horizontalement autour de y_centre."""
    tw = typo.largeur("MA LUNE NOIRE", MARQUE["taille"], "marcellus", espacement=MARQUE["esp"])
    total = SCEAU + 29 + tw
    x = CX - total / 2
    return {"sceau_cx": x + SCEAU / 2, "sceau_cy": y_centre, "sceau_r": SCEAU / 2,
            "texte_x": x + SCEAU + 29, "texte_y": y_centre + MARQUE["taille"] * 0.35}


def _bloc_bas(taille, n):
    """Positions du bloc texte du bas (de la signature vers le haut)."""
    sig_y = BAS - 4
    filet_y = sig_y - SIGNATURE["taille"] * 0.7 - 47
    lh = taille * INTERLIGNE
    derniere = filet_y - 54 - taille * 0.28
    premiere = derniere - (n - 1) * lh
    signe_y = premiere - taille * 0.72 - 47
    return {"sig_y": sig_y, "filet_y": filet_y, "lh": lh, "premiere": premiere,
            "signe_y": signe_y}


def mise_en_page(design, phrase, accent, signe_label, house_roman):
    sm = f"{signe_label.upper()} — MAISON {house_roman}" if house_roman else signe_label.upper()
    p = {"design": design, "signe_maison": sm, "uid": secrets.token_hex(4),
         "W": W, "H": H, "marge": MARGE, "cx": CX, "X0": X0, "X1": X1,
         "marque_t": MARQUE, "signe_t": SIGNE, "signature_t": SIGNATURE}
    if design == "verdict":
        taille = 112
        lignes = typo.couper_verdict(phrase, accent, taille)
        for t in (96, 84):                       # garde-fou : jamais plus de 7 lignes
            if len(lignes) <= 6:
                break
            taille, lignes = t, typo.couper_verdict(phrase, accent, t)
        bloc = _bloc_bas(taille, 1)
        haut_marque = HAUT + SCEAU / 2
        signe_y = haut_marque + SCEAU / 2 + 43 + SIGNE["taille"] * 0.72
        lh = taille * INTERLIGNE
        zone_haut, zone_bas = signe_y + 20, bloc["filet_y"] - 20
        h_bloc = (len(lignes) - 1) * lh + taille
        libre = zone_bas - zone_haut - h_bloc
        premiere = zone_haut + libre / 2.2 + taille * 0.8
        p.update(marque=_marque(haut_marque), signe_y=signe_y, taille=taille, lh=lh,
                 lignes=[typo.segments_accent(l, accent) for l in lignes], premiere=premiere,
                 filet_y=bloc["filet_y"], sig_y=bloc["sig_y"],
                 etoiles=[(908, 270, 2.7, .4), (195, 1430, 2.7, .35)])
        return p

    taille, lignes = typo.phrase_carte(phrase)
    bloc = _bloc_bas(taille, len(lignes))
    p.update(taille=taille, lignes=[[(l, False)] for l in lignes], **bloc)
    if design == "illustre":
        p["marque"] = _marque(bloc["signe_y"] - SIGNE["taille"] * 0.72 - 43 - SCEAU / 2)
    else:  # eclipse
        haut_marque = HAUT + SCEAU / 2
        p["marque"] = _marque(haut_marque)
        haut, bas = haut_marque + SCEAU / 2, bloc["signe_y"] - SIGNE["taille"]
        libre = bas - haut - ECLIPSE
        p.update(ecl_cy=haut + libre / 2.3 + ECLIPSE / 2, ecl_r=ECLIPSE / 2,
                 etoiles=[(205, 290, 3.6, .5), (858, 486, 2.7, .4), (262, 853, 2.7, .35),
                          (800, 1100, 2.7, .3)])
    return p


def svg(env, design, signe, phrase, accent, signe_label, house_roman, fond_url=None,
        classe="carte"):
    """Carte « version à partager » (cadre + signature), SVG inline."""
    design = design_effectif(design, signe)
    p = mise_en_page(design, phrase, accent, signe_label, house_roman)
    p["fond_url"] = fond_url or f"/static/fonds/{signe}.webp"
    p["classe"] = classe
    return env.get_template("carte/plaque.svg").render(p=p)
