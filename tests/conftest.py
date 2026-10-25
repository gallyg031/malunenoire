import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "engine"))
sys.path.insert(0, ROOT)


def texte_synthetique(cle, **surcharges):
    """Texte de test neutre (jamais un texte du corpus réel), conforme aux règles."""
    signe, maison = cle.rsplit("-", 1)
    d = {"id": cle, "signe": signe, "maison": int(maison),
         "phrase": "Phrase de test numéro un. Elle porte un accent.",
         "accent": "accent",
         "eclats": ["Premier éclat de test : une structure décrite en assez de mots pour passer la règle."] * 1
         + ["Deuxième éclat de test : un mécanisme décrit en assez de mots pour passer la règle."]
         + ["Troisième éclat de test : une faille décrite en assez de mots pour passer la règle."],
         "ouverture": "Ouverture de test : elle nomme une sortie, un geste juste, et elle compte bien assez de caractères pour la règle.",
         "complet": None, "statut": "publie", "version": 3}
    d.update(surcharges)
    return d


# Corpus de test : écrit avant tout import de l'application (CORPUS_DIR est lu à l'import).
CORPUS_TEST = tempfile.mkdtemp(prefix="corpus-test-")
for _cle in ("capricorne-11", "sagittaire-08", "sagittaire-00"):
    with open(os.path.join(CORPUS_TEST, f"{_cle}.json"), "w", encoding="utf-8") as _f:
        json.dump(texte_synthetique(_cle), _f, ensure_ascii=False)
os.environ["CORPUS_DIR"] = CORPUS_TEST

import astro  # noqa: E402

astro.set_ephe(os.environ.get("EPHE_PATH", os.path.join(ROOT, "data", "ephe")))


def _creer_base_de_test():
    """La base de test est distincte de celle du serveur local (créée si absente)."""
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        return
    import psycopg
    base = url.rsplit("/", 1)[1].split("?")[0]
    try:
        with psycopg.connect(url.rsplit("/", 1)[0] + "/postgres", autocommit=True) as conn:
            if not conn.execute("select 1 from pg_database where datname = %s", (base,)).fetchone():
                conn.execute(f'create database "{base}"')
    except psycopg.Error:
        pass


_creer_base_de_test()
