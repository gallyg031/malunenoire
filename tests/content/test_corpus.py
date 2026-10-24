# -*- coding: utf-8 -*-
"""Corpus (spec 07 §2) : validateur et chargeur."""

import json

import pytest

from app.services import corpus
from tests.conftest import texte_synthetique


def check(**surcharges):
    return corpus.check(texte_synthetique("scorpion-08", **surcharges), "scorpion-08.json")


def test_fixture_valide():
    assert check() == ([], [])


@pytest.mark.parametrize("surcharges,attendu", [
    ({"phrase": "x" * 111, "accent": "x"}, "phrase"),
    ({"phrase": "Un. Deux. Trois. Avec accent.", "accent": "accent"}, "plus de 2 phrases"),
    ({"accent": "absent"}, "accent"),
    ({"phrase": "Un accent et un accent encore.", "accent": "accent"}, "2 fois"),
    ({"eclats": ["trop court", "b" * 100, "c" * 100]}, "éclat 1"),
    ({"eclats": ["a" * 100, "b" * 100]}, "exactement 3"),
    ({"ouverture": "courte"}, "ouverture"),
    ({"ouverture": "Ouverture avec un vertige d’Absolu dedans, ce qui est interdit par la charte du site."},
     "vertige"),
    ({"phrase": "Ta LILITH en accent.", "accent": "accent"}, "Lilith"),
    ({"phrase": "Une <b>phrase</b> avec accent.", "accent": "accent"}, "HTML"),
    ({"statut": "fini"}, "statut"),
    ({"version": 0}, "version"),
    ({"id": "scorpion-09"}, "id"),
])
def test_regles_bloquantes(surcharges, attendu):
    err, _ = check(**surcharges)
    assert any(attendu.lower() in e.lower() for e in err), err


def test_champ_manquant():
    d = texte_synthetique("scorpion-08")
    del d["ouverture"]
    assert "manquants" in corpus.check(d)[0][0]


def test_epicene():
    def avert(eclat):
        return check(eclats=[eclat + " " + "x" * 60, "b" * 100, "c" * 100])[1]
    assert any("épicène" in w for w in avert("Tu te crois cicatrisé, un rien rouvre tout."))
    assert not any("épicène" in w for w in avert("Tu te crois cicatrisé·e, un rien rouvre tout."))
    assert not any("épicène" in w for w in avert("Tu te crois à l’abri, un rien rouvre tout."))


def test_avertissements():
    _, w = check(ouverture="Et tu finis par céder, par te rendre, comme toujours dans ces moments-là, sans autre issue.")
    assert any("soumission" in x for x in w)
    _, w = check(eclats=["Tu vas tout perdre si tu continues ainsi, et rien ne pourra l’empêcher.",
                         "b" * 100, "c" * 100])
    assert any("Tu vas" in x for x in w)
    _, w = check(eclats=["Vous êtes ici dans un texte de test qui vouvoie, ce qui est à éviter.",
                         "b" * 100, "c" * 100])
    assert any("vouvoiement" in x for x in w)


def test_phrases_identiques(tmp_path):
    for k in ("lion-05", "lion-06"):
        (tmp_path / f"{k}.json").write_text(json.dumps(texte_synthetique(k)), encoding="utf-8")
    lus = corpus.lire(str(tmp_path))
    assert any("identique" in w for _, _, ws in lus.values() for w in ws)


def test_json_invalide(tmp_path):
    (tmp_path / "lion-05.json").write_text("{pas du json", encoding="utf-8")
    assert "JSON" in corpus.lire(str(tmp_path))["lion-05"][1][0]


def test_chargeur(tmp_path):
    for k in ("scorpion-08", "scorpion-00"):
        (tmp_path / f"{k}.json").write_text(json.dumps(texte_synthetique(k)), encoding="utf-8")
    c = corpus.Corpus(str(tmp_path))
    assert c.get("scorpion", 8)["id"] == "scorpion-08"
    assert c.get("scorpion", None)["id"] == "scorpion-00"
    r = c.get("lion", 5)
    assert r["repli"] and r["phrase"] == "Ce texte n'est pas encore écrit."
    with pytest.raises(corpus.CorpusError):
        corpus.Corpus(str(tmp_path), prod=True)          # 154 manquants


def test_prod_sert_seulement_publie(tmp_path):
    for k in corpus.CLES:
        statut = "brouillon" if k == "lion-05" else "publie"
        (tmp_path / f"{k}.json").write_text(json.dumps(texte_synthetique(
            k, phrase=f"Phrase de test {k} avec accent.", statut=statut)), encoding="utf-8")
    with pytest.raises(corpus.CorpusError):
        corpus.Corpus(str(tmp_path), prod=True)
    (tmp_path / "lion-05.json").write_text(json.dumps(texte_synthetique(
        "lion-05", phrase="Phrase de test lion-05 avec accent.")), encoding="utf-8")
    assert len(corpus.Corpus(str(tmp_path), prod=True)) == 156


def test_corpus_invalide_refuse(tmp_path):
    (tmp_path / "lion-05.json").write_text(json.dumps(texte_synthetique("lion-05", accent="zz")),
                                           encoding="utf-8")
    with pytest.raises(corpus.CorpusError):
        corpus.Corpus(str(tmp_path))


def test_validateur_cli(tmp_path, capsys):
    import scripts.valider_corpus as v
    (tmp_path / "lion-05.json").write_text(json.dumps(texte_synthetique("lion-05")), encoding="utf-8")
    assert v.main(["--dossier", str(tmp_path), "--strict"]) == 0
    assert v.main(["--dossier", str(tmp_path), "--prod"]) == 1
    (tmp_path / "lion-06.json").write_text(json.dumps(texte_synthetique("lion-06", accent="zz")),
                                           encoding="utf-8")
    assert v.main(["--dossier", str(tmp_path), "--strict"]) == 1
    assert "CORPUS REFUSÉ" in capsys.readouterr().out
