# -*- coding: utf-8 -*-
"""Textes d'interface (spec 03 §5, 07 §2, recette R9)."""

import json
import os
import re

from app.services import corpus

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TEMPLATES = os.path.join(ROOT, "app", "templates")
UI = json.load(open(os.path.join(ROOT, "content", "ui.json"), encoding="utf-8"))
METHODES = {"format", "upper", "lower", "items", "get"}


def gabarits():
    for d, _, fichiers in os.walk(TEMPLATES):
        for f in fichiers:
            yield os.path.join(d, f), open(os.path.join(d, f), encoding="utf-8").read()


def chaines(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from chaines(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from chaines(v)


def test_cles_ui_existent():
    """Chaque `ui.a.b` (ou ui.a["b"]) des gabarits existe dans content/ui.json."""
    manquantes = []
    for chemin, texte in gabarits():
        for m in re.finditer(r"\bui((?:\.[A-Za-z_][A-Za-z0-9_]*|\[\"[^\"]+\"\])+)", texte):
            noeud = UI
            for part in re.findall(r"\.([A-Za-z_][A-Za-z0-9_]*)|\[\"([^\"]+)\"\]", m.group(1)):
                cle = part[0] or part[1]
                if cle in METHODES and not (isinstance(noeud, dict) and cle in noeud):
                    break
                if isinstance(noeud, dict) and cle in noeud:
                    noeud = noeud[cle]
                else:
                    manquantes.append(f"{os.path.relpath(chemin, ROOT)} : ui{m.group(1)}")
                    break
    assert not manquantes, manquantes


def test_r9_interface():
    """Recette R9 : ni « Lilith », ni « vertige d'absolu », ni masculin seul dans l'interface."""
    textes = list(chaines(UI)) + [t for _, t in gabarits()]
    tout = "\n".join(textes)
    plat = corpus._plain(tout)
    assert "lilith" not in plat
    assert "vertige d'absolu" not in plat
    for t in chaines(UI):
        _, avert = corpus.check({"id": "x", "signe": "lion", "maison": 1, "phrase": "", "accent": "",
                                 "eclats": [], "ouverture": t, "complet": None, "statut": "brouillon",
                                 "version": 1})
        # « vous » est légitime ici (« vous deux ») : seuls l'épicène et le malheur annoncé comptent
        assert not [a for a in avert if "épicène" in a or "Tu vas" in a], (t, avert)


def test_gravures_maison_en_chiffres_romains():
    """« Maison VIII » en chiffres romains, « maison 8 » nulle part (spec 01 §12)."""
    for chemin, texte in gabarits():
        assert not re.search(r"(?i)maison \d", texte), chemin
    for t in chaines(UI):
        assert not re.search(r"(?i)maison \d", t), t


def test_maison_romaine_dans_les_emails():
    from app.services import readings as rd
    gabarit = UI["emails"]["new_moon_maison"]
    assert "maison VIII" in gabarit.format(date="3 décembre", signe="Scorpion", maison=rd.house_roman(8))
