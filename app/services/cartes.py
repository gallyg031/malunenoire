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

OG_W, OG_H = 1200, 630
SIGNATURE_GAUCHE, SIGNATURE_DROITE = "FAIS LA TIENNE", "MALUNENOIRE.FR"
FLECHE = 34                     # « → » dessinée (absente des polices)

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


def _signature(y):
    """« FAIS LA TIENNE → MALUNENOIRE.FR » : deux textes et une flèche vectorielle, centrés."""
    t, esp = SIGNATURE["taille"], SIGNATURE["esp"]
    w1 = typo.largeur(SIGNATURE_GAUCHE, t, "marcellus", espacement=esp) + esp
    w2 = typo.largeur(SIGNATURE_DROITE, t, "marcellus", espacement=esp)
    ecart = 22
    x = CX - (w1 + ecart + FLECHE + ecart + w2) / 2
    fx = x + w1 + ecart
    return {"y": y, "x1": x, "x2": fx + FLECHE + ecart, "fx": fx, "fy": y - t * 0.33,
            "gauche": SIGNATURE_GAUCHE, "droite": SIGNATURE_DROITE}


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


def _signe_maison(signe_label, house_roman):
    return f"{signe_label.upper()} — MAISON {house_roman}" if house_roman else signe_label.upper()


def mise_en_page(design, phrase, accent, signe_label, house_roman, uid=None):
    sm = _signe_maison(signe_label, house_roman)
    p = {"design": design, "signe_maison": sm, "uid": uid or secrets.token_hex(4),
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
                 filet_y=bloc["filet_y"], sig_y=bloc["sig_y"], signature=_signature(bloc["sig_y"]),
                 etoiles=[(908, 270, 2.7, .4), (195, 1430, 2.7, .35)])
        return p

    taille, lignes = typo.phrase_carte(phrase)
    bloc = _bloc_bas(taille, len(lignes))
    p.update(taille=taille, lignes=[[(l, False)] for l in lignes], signature=_signature(bloc["sig_y"]),
             **bloc)
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
        classe="carte", uid=None, sans_fond=False):
    """Carte « version à partager » (cadre + signature), SVG inline. `uid` fixe : rendu
    déterministe (PNG)."""
    design = design_effectif(design, signe)
    p = mise_en_page(design, phrase, accent, signe_label, house_roman, uid)
    p["fond_url"] = fond_url or f"/static/fonds/{signe}.webp"
    p["classe"] = classe
    p["sans_fond"] = sans_fond
    return env.get_template("carte/plaque.svg").render(p=p)


# ---------------------------------------------------------------- Open Graph 1200 × 630 (spec 04 §5)

OG_TEXTE_X0, OG_TEXTE_X1 = 560, 1140


def og_mise_en_page(design, phrase, signe_label, house_roman):
    largeur = OG_TEXTE_X1 - OG_TEXTE_X0
    taille, lignes = 56, typo.couper(phrase, 56, largeur)
    if len(lignes) > 3:
        taille, lignes = 48, typo.couper(phrase, 48, largeur)
    lh = taille * 1.35
    h_bloc = 36 + 30 + (len(lignes) - 1) * lh + taille
    haut = (OG_H - h_bloc) / 2
    return {"design": design, "W": OG_W, "H": OG_H, "uid": "og",
            "signe_maison": _signe_maison(signe_label, house_roman), "taille": taille, "lh": lh,
            "lignes": lignes, "x": OG_TEXTE_X0, "signe_y": haut + 20, "premiere": haut + 36 + 30 + taille * 0.8,
            "marque_y": OG_H - 56, "ecl_cx": 290, "ecl_cy": OG_H / 2, "ecl_r": 150,
            "etoiles": [(120, 110, 2.5, .5), (470, 90, 2, .4), (90, 470, 2, .35), (500, 520, 2, .3)]}


def og_svg(env, design, signe, phrase, signe_label, house_roman, fond_url, sans_fond=False):
    p = og_mise_en_page(design_effectif(design, signe), phrase, signe_label, house_roman)
    p["fond_url"] = fond_url
    p["sans_fond"] = sans_fond
    return env.get_template("carte/og.svg").render(p=p)


def eclipse_fond_svg():
    """Fond seul du design éclipse (dégradé radial), pour le cache de rendu."""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}">'
            '<radialGradient id="f" cx="50%" cy="30%" r="72%"><stop offset="0" stop-color="#0e1017"/>'
            '<stop offset="1" stop-color="#07080b"/></radialGradient>'
            f'<rect width="{W}" height="{H}" fill="url(#f)"/></svg>')


def og_fond_svg(fond_url):
    """Fond OG illustré seul (photo recadrée + voile), pour le cache de rendu."""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {OG_W} {OG_H}">'
            '<linearGradient id="v" x1="0" x2="1"><stop offset="0" stop-color="#07080b" stop-opacity=".35"/>'
            '<stop offset=".42" stop-color="#07080b" stop-opacity=".75"/>'
            '<stop offset="1" stop-color="#07080b" stop-opacity=".92"/></linearGradient>'
            f'<rect width="{OG_W}" height="{OG_H}" fill="#07080b"/>'
            f'<image href="{fond_url}" x="0" y="-330" width="{OG_W}" height="2133" '
            'preserveAspectRatio="xMidYMid slice"/>'
            f'<rect width="{OG_W}" height="{OG_H}" fill="url(#v)"/></svg>')
