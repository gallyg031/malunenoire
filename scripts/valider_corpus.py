# -*- coding: utf-8 -*-
"""
valider_corpus.py — contrôle du corpus (spec 03 §3).

Usage :
  python scripts/valider_corpus.py [--dossier content/textes] [--strict] [--prod]

  --strict : code de sortie 1 si une règle bloquante échoue (utilisé au build).
  --prod   : exige en plus les 156 textes, tous au statut « publie » (mise en ligne).

Sortie : un tableau par texte (longueurs, statut, avertissements) et un résumé.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services import corpus  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dossier", default=corpus.CORPUS_DIR)
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--prod", action="store_true")
    a = ap.parse_args(argv)

    lus = corpus.lire(a.dossier)
    n_err = 0
    print(f"{'texte':15s} {'statut':9s} {'phr':>4s} {'éc1':>4s} {'éc2':>4s} {'éc3':>4s} {'ouv':>4s}  remarques")
    for k, (d, err, warn) in sorted(lus.items()):
        if d:
            ec = list(d.get("eclats") or []) + ["", "", ""]
            longueurs = [len(d.get("phrase") or ""), *(len(e) for e in ec[:3]),
                         len(d.get("ouverture") or "")]
            print(f"{k:15s} {str(d.get('statut')):9s} " + " ".join(f"{n:4d}" for n in longueurs))
        else:
            print(f"{k:15s} {'?':9s}")
        for e in err:
            print(f"{'':15s} ✗ {e}")
        for w in warn:
            print(f"{'':15s} ⚠ {w}")
        n_err += len(err)

    statuts = {s: sum(1 for d, _, _ in lus.values() if d and d.get("statut") == s)
               for s in corpus.STATUTS}
    absents = corpus.manquants(lus)
    print()
    print(f"publiés {statuts['publie']} · relus {statuts['relu']} · brouillons {statuts['brouillon']}"
          f" · manquants {len(absents)} / {len(corpus.CLES)} · erreurs {n_err}")

    if a.prod:
        non_publies = [k for k, (d, _, _) in lus.items() if d and d.get("statut") != "publie"]
        if absents or non_publies:
            print(f"✗ production : {len(absents)} manquants, {len(non_publies)} non publiés")
            n_err += len(absents) + len(non_publies)
    if (a.strict or a.prod) and n_err:
        print("CORPUS REFUSÉ")
        return 1
    print("CORPUS OK" if not n_err else "corpus : erreurs (mode non strict)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
