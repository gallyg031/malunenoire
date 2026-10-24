# -*- coding: utf-8 -*-
"""Cartes (spec 07 §4) : rendu SVG/PNG, typographie, fonds, Open Graph, page publique."""

import hashlib
import io
import os

import pytest
from PIL import Image

from app.services import cartes, rendu, typo

COURTE = "Phrase de test courte, avec un accent."
LONGUE = ("Tu cherches loin ce que tu refuses de voir près. "
          "Et plus l’horizon s’ouvre, plus tu t’absentes de toi.")     # gabarit de sagittaire-09


@pytest.fixture(scope="module")
def env():
    from app.web import templates
    return templates.env


@pytest.mark.parametrize("design", ["illustre", "eclipse", "verdict"])
def test_rendu_png(env, design):
    args = (design, "scorpion", COURTE, "accent", "Scorpion", "VIII")
    a, b = rendu.carte_png(env, *args), rendu.carte_png(env, *args)
    img = Image.open(io.BytesIO(a))
    assert img.format == "PNG" and img.size == (1080, 1920)
    assert hashlib.sha256(a).digest() == hashlib.sha256(b).digest()          # déterministe
    effectif = cartes.design_effectif(design, "scorpion")
    assert len(a) < (900 if effectif == "illustre" else 600) * 1024


def test_phrase_longue(env):
    taille, lignes = typo.phrase_carte(LONGUE)
    assert taille == 65 and len(lignes) <= 5
    p = cartes.mise_en_page("eclipse", LONGUE, "absentes", "Sagittaire", "IX")
    for l in lignes:                                   # aucune ligne ne sort du padding
        assert typo.largeur(l, taille) <= cartes.X1 - cartes.X0
    assert p["premiere"] - taille > p["signe_y"]        # le bloc ne recouvre pas le signe
    assert p["filet_y"] > p["premiere"] + (len(lignes) - 1) * p["lh"]
    assert p["sig_y"] <= cartes.BAS


def test_phrase_courte_72():
    assert typo.phrase_carte(COURTE)[0] == 72


def test_verdict_accent(env):
    svg = cartes.svg(env, "verdict", "scorpion", COURTE, "accent", "Scorpion", "VIII")
    assert '<tspan font-style="italic" fill="#a8505e">accent</tspan>' in svg


def test_accent_obligatoire():
    from app.services import corpus
    from tests.conftest import texte_synthetique
    err, _ = corpus.check(texte_synthetique("scorpion-08", accent=""))
    assert any("accent" in e for e in err)


def test_repli_sans_fond(monkeypatch, tmp_path):
    monkeypatch.setattr(cartes, "FONDS", str(tmp_path))
    assert cartes.design_effectif("illustre", "scorpion") == "eclipse"
    assert "illustre" not in cartes.designs_disponibles("scorpion")


@pytest.mark.skipif(not os.path.isdir(os.path.join(cartes.ROOT, "design", "uploads")),
                    reason="sources des fonds absentes (privées)")
def test_douze_fonds():
    for s in ("belier", "taureau", "gemeaux", "cancer", "lion", "vierge", "balance", "scorpion",
              "sagittaire", "capricorne", "verseau", "poissons"):
        for ext in (".jpg", ".webp", "-390.webp"):
            assert os.path.exists(os.path.join(cartes.FONDS, s + ext)), s + ext
    assert Image.open(os.path.join(cartes.FONDS, "scorpion.jpg")).size == (1080, 1920)


def test_og(env):
    p = cartes.og_mise_en_page("eclipse", COURTE, "Scorpion", "VIII")
    assert p["taille"] == 56 and len(p["lignes"]) <= 3
    tres_longue = LONGUE + " " + LONGUE
    p = cartes.og_mise_en_page("eclipse", tres_longue, "Scorpion", "VIII")
    assert p["taille"] == 48
    img = Image.open(io.BytesIO(rendu.og_png(env, "eclipse", "scorpion", COURTE, "Scorpion", "VIII")))
    assert img.size == (1200, 630)


def test_signature_sans_glyphe_manquant(env):
    """La flèche est dessinée : aucun « → » dans le SVG rendu en PNG."""
    svg = cartes.svg(env, "eclipse", "scorpion", COURTE, "accent", "Scorpion", "VIII", uid="png")
    assert "→" not in svg and "FAIS LA TIENNE" in svg and "MALUNENOIRE.FR" in svg
