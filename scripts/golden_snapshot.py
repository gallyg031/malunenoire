# -*- coding: utf-8 -*-
"""
golden_snapshot.py — recalcule les valeurs de référence d'un thème (spec 02 §3)
et les imprime au format des fichiers dorés, validation à false.

Thèmes : 'j2000' (référence publique, tests/engine/golden.json) ou un nom présent
dans tests/engine/golden_prive.json (hors dépôt). Constance relit et valide,
puis on passe "valide_par_constance" à true à la main.

Usage : python scripts/golden_snapshot.py <theme>
"""

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "engine"))

import astro  # noqa: E402
import selftest  # noqa: E402


def snapshot(t):
    jd, off = astro.to_jd(*t["args"])
    c = astro.chart(jd, t["lat"], t["lon"])
    cr = astro.lune_noire_cross(c)
    ln = cr["bras"]["lune_noire"]
    return {
        **{k: t[k] for k in ("args", "lat", "lon") if k in t},
        "utc_offset_min": round(off * 60),
        "ln_lon": round(ln["lon"], 6),
        "fmt": ln["fmt"],
        "maison": ln["maison"],
        "croix": {k: {"lon": round(a["lon"], 6), "fmt": a["fmt"], "maison": a["maison"]}
                  for k, a in cr["bras"].items() if k != "lune_noire"},
        "intensite": round(cr["ecart_moyenne_corrigee"], 4),
        "asc": astro.fmt(c["asc"]), "mc": astro.fmt(c["mc"]),
        "valide_par_constance": False,
    }


if __name__ == "__main__":
    astro.set_ephe(os.path.join(ROOT, "data", "ephe"))
    nom = sys.argv[1] if len(sys.argv) > 1 else "j2000"
    theme = selftest.load_reference() if nom == "j2000" else selftest.load_prive()[nom]
    print(json.dumps({nom: snapshot(theme)}, ensure_ascii=False, indent=2))
