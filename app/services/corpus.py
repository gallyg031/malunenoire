# -*- coding: utf-8 -*-
"""Corpus (spec 03) : chargement, règles d'écriture, résolution (signe, maison).

Les textes sont la propriété de Constance : ils ne sont jamais modifiés ni
complétés par le code. Hors production, une clé absente donne un texte de repli
visiblement non éditorial ; en production, c'est une erreur.
"""

import json
import os
import re
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CORPUS_DIR = os.environ.get("CORPUS_DIR", os.path.join(ROOT, "content", "textes"))

SIGNES = ["belier", "taureau", "gemeaux", "cancer", "lion", "vierge",
          "balance", "scorpion", "sagittaire", "capricorne", "verseau", "poissons"]
CLES = [f"{s}-{m:02d}" for s in SIGNES for m in range(13)]          # 156
STATUTS = ("brouillon", "relu", "publie")
PARTS = ("phrase", "eclat1", "eclat2", "eclat3", "ouverture")

PHRASE_MAX = 110       # spec : 90 ; sagittaire-09 (test de phrase longue) en fait 102 — à trancher
ECLAT = (60, 240)      # spec : 80 ; l’éclat III de scorpion-08 (étalon) en fait 68 — à trancher
OUVERTURE = (100, 260)
COMPLET = (600, 1500)
COMPLET_CHAMPS = ("priape", "soumission", "affirmation", "aspects", "mythe")

# Règle 6 (épicène) : mots accordés au masculin seul ; la liste s'enrichit.
EPICENE_MOTS = ["cicatrisé", "seul", "perdu", "pris", "sûr", "prêt", "fort", "fatigué",
                "blessé", "abandonné", "aimé", "rejeté", "trahi", "enfermé", "heureux",
                "lié", "attaché", "épuisé", "déçu"]
EPICENE_AMORCES = r"tu es|tu te crois|tu te sens|tu restes|tu as été"
MALHEUR = ("perdre", "souffrir", "échouer", "mourir")


class CorpusError(Exception):
    pass


def repli(cle):
    """Texte de repli (spec 03 §4) : jamais servi en production."""
    signe, maison = cle.rsplit("-", 1)
    return {"id": cle, "signe": signe, "maison": int(maison),
            "phrase": "Ce texte n'est pas encore écrit.", "accent": "écrit",
            "eclats": ["[à venir]", "[à venir]", "[à venir]"], "ouverture": "[à venir]",
            "complet": None, "statut": "brouillon", "version": 0, "repli": True}


def cle(signe, maison):
    return f"{signe}-{(maison or 0):02d}"


# ---------------------------------------------------------------- règles

def _plain(s):
    """Minuscules, sans accents, apostrophes droites : pour les chaînes interdites."""
    s = s.replace("’", "'").lower()
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def _textes(d):
    """Tous les champs rédigés, pour les règles qui portent sur l'ensemble."""
    out = [d.get("phrase") or "", d.get("ouverture") or ""] + list(d.get("eclats") or [])
    complet = d.get("complet")
    if isinstance(complet, dict):
        out += [v for v in complet.values() if isinstance(v, str)]
    return [t for t in out if isinstance(t, str)]


def _n_phrases(s):
    return len([p for p in re.split(r"(?<=[.!?…])\s+", s.strip()) if p])


def check(d, nom_fichier=None):
    """Renvoie (erreurs bloquantes, avertissements) pour un texte."""
    err, warn = [], []
    requis = ("id", "signe", "maison", "phrase", "accent", "eclats", "ouverture",
              "complet", "statut", "version")
    manquants = [k for k in requis if k not in d]
    if manquants:
        return [f"champs manquants : {', '.join(manquants)}"], warn

    attendu = cle(d["signe"], d["maison"]) if d["signe"] in SIGNES and \
        isinstance(d["maison"], int) and 0 <= d["maison"] <= 12 else None
    if attendu is None:
        err.append("signe ou maison invalide")
    elif d["id"] != attendu:
        err.append(f"id {d['id']!r} ≠ {attendu!r}")
    if nom_fichier and nom_fichier != f"{d['id']}.json":
        err.append(f"nom de fichier {nom_fichier!r} ≠ {d['id']}.json")
    if d["statut"] not in STATUTS:
        err.append(f"statut inconnu : {d['statut']!r}")
    if not isinstance(d["version"], int) or d["version"] < 1:
        err.append("version : entier ≥ 1")

    phrase = d["phrase"]
    if not isinstance(phrase, str) or not phrase.strip():
        err.append("phrase vide")
    else:
        if len(phrase) > PHRASE_MAX:
            err.append(f"phrase : {len(phrase)} car. > {PHRASE_MAX}")
        if _n_phrases(phrase) > 2:
            err.append("phrase : plus de 2 phrases")
        accent = d["accent"]
        n = len(re.findall(rf"(?<!\w){re.escape(accent)}(?!\w)", phrase)) if accent else 0
        if n != 1:
            err.append(f"accent {accent!r} trouvé {n} fois dans la phrase (attendu : 1)")

    eclats = d["eclats"]
    if not isinstance(eclats, list) or len(eclats) != 3:
        err.append("eclats : exactement 3")
    else:
        for i, e in enumerate(eclats, 1):
            if not isinstance(e, str) or not ECLAT[0] <= len(e) <= ECLAT[1]:
                err.append(f"éclat {i} : {len(e) if isinstance(e, str) else '?'} car. "
                           f"(attendu {ECLAT[0]}–{ECLAT[1]})")

    o = d["ouverture"]
    if not isinstance(o, str) or not OUVERTURE[0] <= len(o) <= OUVERTURE[1]:
        err.append(f"ouverture : {len(o) if isinstance(o, str) else '?'} car. "
                   f"(attendu {OUVERTURE[0]}–{OUVERTURE[1]})")

    complet = d["complet"]
    if complet is not None:
        if not isinstance(complet, dict) or set(complet) != set(COMPLET_CHAMPS):
            err.append(f"complet : champs attendus {', '.join(COMPLET_CHAMPS)}")
        else:
            for k, v in complet.items():
                if v is None and k == "aspects":
                    continue
                if not isinstance(v, str) or not COMPLET[0] <= len(v) <= COMPLET[1]:
                    err.append(f"complet.{k} : longueur hors {COMPLET[0]}–{COMPLET[1]}")

    tout = "\n".join(_textes(d))
    plain = _plain(tout)
    if "vertige d'absolu" in plain:
        err.append("chaîne interdite : « vertige d'absolu »")
    if "lilith" in plain:
        err.append("« Lilith » interdit (dire « Lune Noire »)")
    if re.search(r"<\s*/?\s*[a-zA-Z][^>]*>", tout):
        err.append("HTML interdit")

    # ---- avertissements
    for m in re.finditer(rf"\b(?:{EPICENE_AMORCES})\s+(?:\w+\s+){{0,2}}?({'|'.join(EPICENE_MOTS)})\b(?!·)",
                         tout, re.IGNORECASE):
        warn.append(f"épicène : « {m.group(0)} » (ajouter ·e ou reformuler)")
    hors_citation = re.sub(r"«[^»]*»", "", tout)
    if re.search(r"\bvous\b", hors_citation, re.IGNORECASE):
        warn.append("vouvoiement hors citation")
    if isinstance(o, str):
        po = _plain(o)
        if re.search(r"soumission|te rendre|ceder|abandonner", po) and \
                not re.search(r"\bmais\b|\bsauf\b|et pourtant", po):
            warn.append("l'ouverture semble finir sur la soumission (elle doit nommer l'affirmation)")
    for phrase_ in re.split(r"(?<=[.!?…])\s+", tout):
        if re.search(r"\btu vas\b", phrase_, re.IGNORECASE) and \
                any(w in _plain(phrase_) for w in map(_plain, MALHEUR)):
            warn.append(f"« Tu vas » + malheur : « {phrase_.strip()[:60]} »")
    return err, warn


# ---------------------------------------------------------------- chargement

def lire(dossier=None):
    """{id: (texte | None, erreurs, avertissements)} pour chaque fichier .json du dossier."""
    dossier = dossier or CORPUS_DIR
    out = {}
    if not os.path.isdir(dossier):
        return out
    for f in sorted(os.listdir(dossier)):
        if not f.endswith(".json"):
            continue
        path = os.path.join(dossier, f)
        try:
            with open(path, encoding="utf-8") as fh:
                d = json.load(fh)
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            out[f[:-5]] = (None, [f"JSON/UTF-8 invalide : {e}"], [])
            continue
        err, warn = check(d, f)
        out[d.get("id", f[:-5])] = (d, err, warn)
    # règle 10 : phrases identiques
    vues = {}
    for k, (d, err, warn) in out.items():
        if d and isinstance(d.get("phrase"), str):
            p = d["phrase"].strip()
            if p in vues:
                warn.append(f"phrase identique à {vues[p]}")
            vues.setdefault(p, k)
    return out


def manquants(lus):
    return [k for k in CLES if k not in lus]


class Corpus:
    """Textes valides en mémoire ; `prod` : seuls les `publie`, aucun repli."""

    def __init__(self, dossier=None, prod=False):
        self.prod = prod
        lus = lire(dossier)
        erreurs = {k: e for k, (_, e, _) in lus.items() if e}
        if erreurs:
            raise CorpusError("corpus invalide : " + "; ".join(
                f"{k} : {', '.join(e)}" for k, e in erreurs.items()))
        self.textes = {k: d for k, (d, _, _) in lus.items()
                       if not prod or d["statut"] == "publie"}
        if prod:
            absents = [k for k in CLES if k not in self.textes]
            if absents:
                raise CorpusError(f"{len(absents)} textes non publiés ou manquants "
                                  f"(ex. {', '.join(absents[:3])})")

    def get(self, signe, maison):
        k = cle(signe, maison)
        if k in self.textes:
            return self.textes[k]
        if self.prod:
            raise CorpusError(f"texte manquant en production : {k}")
        return repli(k)

    def __len__(self):
        return len(self.textes)
