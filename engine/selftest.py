# -*- coding: utf-8 -*-
"""
selftest.py — contrôle du moteur avant tout calcul servi au public.

Imprime « SELF-TEST RÉUSSI » si tout est vert, sinon la liste des échecs
(code de sortie 1). Vérifie :
- les fichiers Swiss Ephemeris sont bien lus (drapeau SWIEPH rendu par swe) ;
- to_jd résout l'offset par zoneinfo (hiver, été, 1943) ;
- fmt ;
- le thème de référence public (tests/engine/golden.json, époque J2000) ;
- les thèmes dorés validés par Constance (tests/engine/golden_prive.json),
  s'ils sont présents : ce fichier est hors dépôt public, injecté en CI.

Usage : python engine/selftest.py [--ephe data/ephe] [--leger]
`run(leger=True)` est appelé au démarrage de l'application.
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import astro  # noqa: E402
import swisseph as swe  # noqa: E402

GOLDEN_PATH = os.path.join(ROOT, "tests", "engine", "golden.json")
GOLDEN_PRIVE_PATH = os.path.join(ROOT, "tests", "engine", "golden_prive.json")
DEFAULT_EPHE = os.path.join(ROOT, "data", "ephe")

TOL_ARC = 1.0 / 60.0     # ± 1'
TOL_CROSS = 0.001        # croix géométrique


def _wrap180(x):
    return (x + 180.0) % 360.0 - 180.0


def _load(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None


def load_reference():
    """Thème de référence public."""
    return _load(GOLDEN_PATH)["j2000"]


def load_prive():
    """{nom: thème} validés par Constance, ou {} si le fichier privé est absent."""
    data = _load(GOLDEN_PRIVE_PATH)
    return data["themes"] if data else {}


def natal_cross(args, lat, lon):
    jd, off = astro.to_jd(*args)
    c = astro.chart(jd, lat, lon)
    cr = astro.lune_noire_cross(c)
    return jd, off, c, cr


def check_ephe(fails):
    if not astro._EPHE_SET:
        fails.append("éphémérides : set_ephe non appelé (repli Moshier)")
        return
    jd, _ = astro.to_jd(2000, 1, 1, 12, 0, "UTC")
    _, ret = swe.calc_ut(jd, swe.SATURN, astro._FLAGS)
    if not ret & swe.FLG_SWIEPH:
        fails.append("éphémérides : fichiers .se1 introuvables, swe est retombé sur Moshier")


def check_time(fails):
    cas = [((1991, 3, 12, 4, 37, "Europe/Paris"), 1.0),
           ((1991, 7, 12, 4, 37, "Europe/Paris"), 2.0),
           ((1943, 6, 1, 12, 0, "Europe/Paris"), 2.0)]
    for args, off_attendu in cas:
        _, off = astro.to_jd(*args)
        if off != off_attendu:
            fails.append(f"to_jd{args} : offset {off} ≠ {off_attendu}")


def check_fmt(fails):
    if astro.fmt(259.1639) != "19°10' Sagittaire":
        fails.append(f"fmt(259.1639) = {astro.fmt(259.1639)!r}")


def check_theme(name, g, fails, maisons=True):
    """Lune Noire corrigée ± 1', croix exacte et cohérente, maisons figées."""
    _, off, _, cr = natal_cross(tuple(g["args"]), g["lat"], g["lon"])
    ln = cr["bras"]["lune_noire"]
    if round(off * 60) != g["utc_offset_min"]:
        fails.append(f"{name} : offset {off * 60:.0f} min ≠ {g['utc_offset_min']}")
    if abs(_wrap180(ln["lon"] - g["ln_lon"])) > TOL_ARC:
        fails.append(f"{name} : {ln['fmt']} ≠ {g['fmt']}")
    if maisons and ln.get("maison") != g["maison"]:
        fails.append(f"{name} : maison {ln.get('maison')} ≠ {g['maison']}")
    L = ln["lon"]
    geometrie = {"priape": L + 180.0, "affirmation": L - 90.0, "soumission": L + 90.0}
    for bras, attendu in g["croix"].items():
        a = cr["bras"][bras]
        if abs(_wrap180(a["lon"] - geometrie[bras])) > TOL_CROSS:
            fails.append(f"{name} : bras {bras} hors géométrie")
        if abs(_wrap180(a["lon"] - attendu["lon"])) > TOL_ARC:
            fails.append(f"{name} : bras {bras} {a['fmt']} ≠ {attendu['fmt']}")
        if maisons and a.get("maison") != attendu["maison"]:
            fails.append(f"{name} : bras {bras} maison {a.get('maison')} ≠ {attendu['maison']}")


def run(ephe=DEFAULT_EPHE, leger=False):
    """Renvoie la liste des échecs (vide = réussi)."""
    if ephe:
        astro.set_ephe(ephe)
    fails = []
    check_ephe(fails)
    check_theme("référence J2000", load_reference(), fails)
    for name, g in load_prive().items():
        check_theme(name, g, fails, maisons=bool(g.get("valide_par_constance")))
    if not leger:
        check_time(fails)
        check_fmt(fails)
    return fails


def main(argv):
    ephe = DEFAULT_EPHE
    if "--ephe" in argv:
        ephe = argv[argv.index("--ephe") + 1]
    fails = run(ephe, leger="--leger" in argv)
    if fails:
        print("SELF-TEST ÉCHOUÉ")
        for f in fails:
            print("  ✗", f)
        return 1
    prive = load_prive()
    print(f"pyswisseph {swe.version} — éphémérides : {ephe}")
    print("référence J2000 : vérifiée")
    if prive:
        for name, g in prive.items():
            etat = "vérifié" if g.get("valide_par_constance") else "maisons non validées"
            print(f"thème doré {name} : {etat}")
    else:
        print("thèmes dorés privés : fichier absent (non vérifiés)")
    print("SELF-TEST RÉUSSI")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
