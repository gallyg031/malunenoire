# -*- coding: utf-8 -*-
"""Tests dorés (spec 07 §1).

Les thèmes validés par Constance sont dans golden_prive.json, qui ne quitte jamais
son poste (vérifié avant chaque push par un hook local) ; le dépôt public ne porte
qu'une référence neutre (J2000, Paris).
"""

import os
import subprocess
import sys

import pytest

import astro
import selftest

PRIVE = selftest.load_prive()
SANS_PRIVE = pytest.mark.skipif(not PRIVE, reason="golden_prive.json absent (fichier privé)")


def test_reference_j2000():
    fails = []
    selftest.check_theme("référence J2000", selftest.load_reference(), fails)
    assert fails == []


@SANS_PRIVE
def test_golden_prive():
    fails = []
    for nom, g in PRIVE.items():
        assert g.get("valide_par_constance"), f"{nom} non validé par Constance"
        selftest.check_theme(nom, g, fails)
    assert fails == []


def test_selftest():
    out = subprocess.run([sys.executable, os.path.join(selftest.HERE, "selftest.py")],
                         capture_output=True, text=True, encoding="utf-8")
    assert out.returncode == 0, out.stdout + out.stderr
    assert "SELF-TEST RÉUSSI" in out.stdout


def test_fmt():
    assert astro.fmt(259.1639) == "19°10' Sagittaire"


def test_swieph_actif():
    fails = []
    selftest.check_ephe(fails)
    assert fails == []
