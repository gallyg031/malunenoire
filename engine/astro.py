# -*- coding: utf-8 -*-
"""
astro.py — moteur de calcul astrologique (wrapper Swiss Ephemeris).

Règles d'usage (voir SKILL.md) :
- Toujours entrer un instant via to_jd(y,mo,d,h,mi,tz_name) — JAMAIS de calcul
  d'offset à la main.
- Toujours vérifier un aspect via aspect() avant d'en écrire un mot.
- Défauts maison : Koch ('koch'), nœuds vrais ('true'), Lune Noire moyenne ('mean').
  Variantes Lilith : 'mean' (moyenne), 'true' (vraie/osculatrice),
  'interp' (corrigée/interpolée, SE_INTP_APOG).

Dépendance : pip install pyswisseph --break-system-packages
Sans fichiers d'éphémérides (set_ephe non appelé), repli automatique sur
l'éphéméride analytique Moshier : précision largement suffisante (< 1″ planètes),
mais Chiron indisponible (nécessite les fichiers Swiss Ephemeris).
"""

from zoneinfo import ZoneInfo
from datetime import datetime, timedelta
import swisseph as swe

# ---------------------------------------------------------------- configuration

_FLAGS = swe.FLG_MOSEPH | swe.FLG_SPEED   # repli Moshier par défaut
_EPHE_SET = False

SIGNS_FR = ["Bélier", "Taureau", "Gémeaux", "Cancer", "Lion", "Vierge",
            "Balance", "Scorpion", "Sagittaire", "Capricorne", "Verseau", "Poissons"]

PLANETS = [
    ("Soleil", swe.SUN), ("Lune", swe.MOON), ("Mercure", swe.MERCURY),
    ("Vénus", swe.VENUS), ("Mars", swe.MARS), ("Jupiter", swe.JUPITER),
    ("Saturne", swe.SATURN), ("Uranus", swe.URANUS), ("Neptune", swe.NEPTUNE),
    ("Pluton", swe.PLUTO),
]

HSYS = {"placidus": b"P", "koch": b"K", "whole": b"W", "equal": b"E",
        "regiomontanus": b"R", "campanus": b"C", "porphyry": b"O"}

LILITH_MODES = {"mean": swe.MEAN_APOG, "true": swe.OSCU_APOG, "interp": swe.INTP_APOG}
NODE_MODES = {"true": swe.TRUE_NODE, "mean": swe.MEAN_NODE}

# --- données pour dignités et dominantes ----------------------------------------
ELEMENT = {0: "Feu", 1: "Terre", 2: "Air", 3: "Eau", 4: "Feu", 5: "Terre",
           6: "Air", 7: "Eau", 8: "Feu", 9: "Terre", 10: "Air", 11: "Eau"}
MODE = {0: "Cardinal", 1: "Fixe", 2: "Mutable", 3: "Cardinal", 4: "Fixe",
        5: "Mutable", 6: "Cardinal", 7: "Fixe", 8: "Mutable", 9: "Cardinal",
        10: "Fixe", 11: "Mutable"}

# maîtrises traditionnelles (un maître par signe) — base de la tradition française
RULERS_TRAD = {"Bélier": "Mars", "Taureau": "Vénus", "Gémeaux": "Mercure",
               "Cancer": "Lune", "Lion": "Soleil", "Vierge": "Mercure",
               "Balance": "Vénus", "Scorpion": "Mars", "Sagittaire": "Jupiter",
               "Capricorne": "Saturne", "Verseau": "Saturne", "Poissons": "Jupiter"}
RULERS_MOD = dict(RULERS_TRAD, Scorpion="Pluton", Verseau="Uranus", Poissons="Neptune")

# dignités essentielles (signes)
DOMICILE = {"Soleil": ["Lion"], "Lune": ["Cancer"], "Mercure": ["Gémeaux", "Vierge"],
            "Vénus": ["Taureau", "Balance"], "Mars": ["Bélier", "Scorpion"],
            "Jupiter": ["Sagittaire", "Poissons"], "Saturne": ["Capricorne", "Verseau"]}
EXALT = {"Soleil": "Bélier", "Lune": "Taureau", "Mercure": "Vierge",
         "Vénus": "Poissons", "Mars": "Capricorne", "Jupiter": "Cancer",
         "Saturne": "Balance"}
EXIL = {"Soleil": ["Verseau"], "Lune": ["Capricorne"], "Mercure": ["Sagittaire", "Poissons"],
        "Vénus": ["Scorpion", "Bélier"], "Mars": ["Balance", "Taureau"],
        "Jupiter": ["Gémeaux", "Vierge"], "Saturne": ["Cancer", "Lion"]}
CHUTE = {"Soleil": "Balance", "Lune": "Scorpion", "Mercure": "Poissons",
         "Vénus": "Vierge", "Mars": "Cancer", "Jupiter": "Capricorne", "Saturne": "Bélier"}

# Familles d'aspects : angle -> (nom, orbe par défaut)
ASPECTS_MAJOR = {0: ("conjonction", 8.0), 60: ("sextile", 5.0), 90: ("carré", 7.0),
                 120: ("trigone", 7.0), 180: ("opposition", 8.0)}
ASPECTS_MINOR = {30: ("semi-sextile", 2.0), 45: ("semi-carré", 2.0),
                 135: ("sesqui-carré", 2.0), 150: ("quinconce", 2.5)}
ASPECTS_QUINTILE = {72: ("quintile", 1.5), 144: ("biquintile", 1.5)}
ASPECTS_NOVILE = {40: ("novile", 1.5), 80: ("binovile", 1.5), 160: ("quadrinovile", 1.5)}

FAMILIES = {"major": ASPECTS_MAJOR, "minor": ASPECTS_MINOR,
            "quintile": ASPECTS_QUINTILE, "novile": ASPECTS_NOVILE}


def set_ephe(path):
    """Pointe vers des fichiers Swiss Ephemeris (active SWIEPH, débloque Chiron)."""
    global _FLAGS, _EPHE_SET
    swe.set_ephe_path(path)
    _FLAGS = swe.FLG_SWIEPH | swe.FLG_SPEED
    _EPHE_SET = True


def _aspect_table(family="major"):
    """family: nom, liste de noms, ou 'all'."""
    if family == "all":
        names = list(FAMILIES)
    elif isinstance(family, str):
        names = ["major"] if family == "major" else ["major", family]
    else:
        names = list(family)
    table = {}
    for n in names:
        table.update(FAMILIES[n])
    return table

# ---------------------------------------------------------------- temps

def to_jd(y, mo, d, h, mi, tz_name, s=0):
    """LA SEULE façon correcte d'entrer une heure locale.

    Retourne (jd_ut, offset_utc_en_heures). L'offset (DST historique compris)
    est résolu par la base IANA via zoneinfo — ne jamais le calculer soi-même.
    """
    local = datetime(y, mo, d, h, mi, s, tzinfo=ZoneInfo(tz_name))
    off = local.utcoffset().total_seconds() / 3600.0
    ut = local.astimezone(ZoneInfo("UTC"))
    jd = swe.julday(ut.year, ut.month, ut.day,
                    ut.hour + ut.minute / 60.0 + ut.second / 3600.0)
    return jd, off


def jd_to_utc(jd):
    """jd (UT) -> datetime UTC (pour affichage)."""
    y, mo, d, h = swe.revjul(jd)
    hh = int(h); mm = int((h - hh) * 60); ss = int(round(((h - hh) * 60 - mm) * 60))
    if ss == 60: ss = 0; mm += 1
    if mm == 60: mm = 0; hh += 1
    return datetime(y, mo, d, tzinfo=ZoneInfo("UTC")) + timedelta(hours=hh, minutes=mm, seconds=ss)

# ---------------------------------------------------------------- calcul de base

def _calc(jd, body):
    (lon, lat, dist, slon, slat, sdist), _ = swe.calc_ut(jd, body, _FLAGS)
    return lon % 360.0, slon


def chart(jd, lat, lon, hsys="koch", node="true", lilith="mean", chiron=True):
    """Thème complet : positions, vitesses, cuspides, ASC, MC.

    Inclut TOUJOURS les trois variantes de Lune Noire dans c['lilith_variants']
    (clé 'mean'/'true'/'interp') ; 'Lune Noire' dans c['pos'] est la variante
    choisie, 'Priape' son point opposé (axe de la croix de la Lune Noire).
    """
    pos, speed = {}, {}
    for name, code in PLANETS:
        pos[name], speed[name] = _calc(jd, code)

    nn, nns = _calc(jd, NODE_MODES[node])
    pos["Nœud Nord"], speed["Nœud Nord"] = nn, nns
    pos["Nœud Sud"], speed["Nœud Sud"] = (nn + 180.0) % 360.0, nns

    lilith_variants = {}
    for k, code in LILITH_MODES.items():
        try:
            lilith_variants[k], _ = _calc(jd, code)
        except Exception:
            lilith_variants[k] = None
    bml = lilith_variants[lilith]
    pos["Lune Noire"] = bml
    speed["Lune Noire"] = 0.0
    pos["Priape"] = (bml + 180.0) % 360.0 if bml is not None else None

    if chiron:
        try:
            pos["Chiron"], speed["Chiron"] = _calc(jd, swe.CHIRON)
        except Exception:
            pass  # indisponible sans fichiers d'éphémérides

    cusps, ascmc = swe.houses_ex(jd, lat, lon, HSYS[hsys])
    return {
        "jd": jd, "lat": lat, "lon": lon,
        "hsys": hsys, "node": node, "lilith": lilith,
        "pos": pos, "speed": speed,
        "cusps": list(cusps[:12]), "asc": ascmc[0], "mc": ascmc[1],
        "lilith_variants": lilith_variants,
    }


def house_of(lon, cusps):
    """Numéro de maison (1–12) d'une longitude écliptique."""
    for i in range(12):
        a, b = cusps[i], cusps[(i + 1) % 12]
        if a <= b:
            if a <= lon < b:
                return i + 1
        else:  # la cuspide enjambe 0° Bélier
            if lon >= a or lon < b:
                return i + 1
    return 12


def fmt(lon, speed=None):
    """280.37 -> \"10°22' Capricorne\" (+ ' ℞' si vitesse négative)."""
    lon %= 360.0
    sign = int(lon // 30)
    deg_in = lon - 30 * sign
    d = int(deg_in)
    m = int(round((deg_in - d) * 60))
    if m == 60: d += 1; m = 0
    r = " ℞" if (speed is not None and speed < 0) else ""
    return f"{d}°{m:02d}' {SIGNS_FR[sign]}{r}"


def print_chart(c):
    """Impression lisible du thème + hypothèses (à montrer à l'utilisatrice)."""
    print(f"[hypothèses] maisons={c['hsys']}, nœud={c['node']}, Lune Noire={c['lilith']}")
    print(f"ASC {fmt(c['asc'])}   MC {fmt(c['mc'])}")
    for name, lo in c["pos"].items():
        if lo is None:
            continue
        h = house_of(lo, c["cusps"])
        print(f"{name:12s} {fmt(lo, c['speed'].get(name)):24s} maison {h}")

# ---------------------------------------------------------------- aspects

def _delta(a, b):
    """Séparation angulaire 0–180."""
    d = abs((a - b) % 360.0)
    return 360.0 - d if d > 180.0 else d


def aspect(a, b, orbs=None, family="major"):
    """Vérifie l'aspect entre deux longitudes. Retourne (nom, orbe_exact) ou (None, None).

    family : 'major' (défaut), 'minor', 'quintile', 'novile', liste, ou 'all'.
    orbs : dict {angle: orbe_max} pour surcharger les orbes par défaut.
    """
    table = _aspect_table(family)
    d = _delta(a, b)
    best = (None, None)
    for ang, (name, default_orb) in table.items():
        max_orb = (orbs or {}).get(ang, default_orb)
        o = abs(d - ang)
        if o <= max_orb and (best[1] is None or o < best[1]):
            best = (name, round(o, 2))
    return best


def is_applying(jd, lon_a, speed_a, lon_b, speed_b, angle):
    """L'aspect (angle exact donné) se resserre-t-il ? True = appliquant."""
    now = abs(_delta(lon_a, lon_b) - angle)
    dt = 0.01
    later = abs(_delta(lon_a + speed_a * dt, lon_b + speed_b * dt) - angle)
    return later < now


_ANGLE_BY_NAME = {name: ang for fam in FAMILIES.values() for ang, (name, _) in fam.items()}


def aspect_grid(posA, posB, orbs=None, family="major", speedA=None, speedB=None):
    """Tous les inter-aspects entre deux jeux de positions, triés orbe croissant.

    Retourne [(nomA, nomB, aspect, orbe, appliquant|None), ...]."""
    out = []
    for na, la in posA.items():
        if la is None: continue
        for nb, lb in posB.items():
            if lb is None: continue
            name, orb = aspect(la, lb, orbs, family)
            if name:
                app = None
                if speedA is not None and speedB is not None:
                    app = is_applying(0, la, speedA.get(na, 0.0), lb,
                                      speedB.get(nb, 0.0), _ANGLE_BY_NAME[name])
                out.append((na, nb, name, orb, app))
    return sorted(out, key=lambda t: t[3])

# ---------------------------------------------------------------- lunaisons

def lunation_phase(jd):
    """Élongation Lune−Soleil, 0–360 anti-horaire (0=NL, 90=PQ, 180=PL, 270=DQ)."""
    s, _ = _calc(jd, swe.SUN)
    m, _ = _calc(jd, swe.MOON)
    return (m - s) % 360.0


def phase_name(p):
    names = ["Nouvelle Lune", "Croissante", "Premier Quartier", "Gibbeuse croissante",
             "Pleine Lune", "Gibbeuse décroissante", "Dernier Quartier", "Balsamique"]
    return names[int(((p + 22.5) % 360) // 45)]


def find_lunation(jd, target):
    """Prochain instant (jd UT) où l'élongation atteint `target` (0=NL, 180=PL)."""
    def f(t):
        return ((lunation_phase(t) - target + 180.0) % 360.0) - 180.0
    t0, step = jd, 0.5
    v0 = f(t0)
    for _ in range(80):  # ~40 jours
        t1 = t0 + step
        v1 = f(t1)
        if v0 <= 0.0 <= v1 or (v0 <= 0.0 and v1 < v0 - 180):  # croisement croissant
            lo, hi = t0, t1
            for _ in range(60):
                mid = (lo + hi) / 2
                if f(mid) < 0: lo = mid
                else: hi = mid
            return (lo + hi) / 2
        t0, v0 = t1, v1
    raise RuntimeError("lunaison non trouvée")

# ---------------------------------------------------------------- techniques

def solar_return(natal_jd, year, lat, lon, hsys="koch", node="true", lilith="mean"):
    """Révolution solaire de l'année donnée, au LIEU où la personne se trouve
    (toujours demander où elle sera à son anniversaire)."""
    nsun, _ = _calc(natal_jd, swe.SUN)
    y0, mo0, d0, _ = swe.revjul(natal_jd)
    guess = swe.julday(year, mo0, d0, 0.0)

    def f(t):
        s, _ = _calc(t, swe.SUN)
        return ((s - nsun + 180.0) % 360.0) - 180.0

    lo, hi = guess - 4.0, guess + 4.0
    while f(lo) > 0: lo -= 1.0
    while f(hi) < 0: hi += 1.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if f(mid) < 0: lo = mid
        else: hi = mid
    return chart((lo + hi) / 2, lat, lon, hsys, node, lilith)


def secondary_progressed(natal_jd, target_jd, lat, lon, hsys="koch",
                          node="true", lilith="mean"):
    """Progressions secondaires (1 jour = 1 an), maisons au lieu natal par défaut."""
    years = (target_jd - natal_jd) / 365.2425
    return chart(natal_jd + years, lat, lon, hsys, node, lilith)


# ---------------------------------------------------------------- arc solaire

def solar_arc(natal_jd, target_jd):
    """Arc solaire (°) à la date cible : distance parcourue par le Soleil progressé
    depuis sa position natale. Croît de façon monotone (~1°/an de vie)."""
    natal_sun, _ = _calc(natal_jd, swe.SUN)
    years = (target_jd - natal_jd) / 365.2425
    prog_sun, _ = _calc(natal_jd + years, swe.SUN)   # 1 jour = 1 an
    return (prog_sun - natal_sun) % 360.0


def directed_chart(natal_chart, target_jd):
    """Thème dirigé par arc solaire : tous les points natals (planètes, ASC, MC,
    cuspides) avancés du même arc. Retourne pos/asc/mc/cusps dirigés + l'arc."""
    arc = solar_arc(natal_chart["jd"], target_jd)
    pos = {k: (v + arc) % 360.0 for k, v in natal_chart["pos"].items() if v is not None}
    return {
        "arc": arc, "target_jd": target_jd,
        "pos": pos,
        "asc": (natal_chart["asc"] + arc) % 360.0,
        "mc": (natal_chart["mc"] + arc) % 360.0,
        "cusps": [(c + arc) % 360.0 for c in natal_chart["cusps"]],
    }


def _date_for_arc(natal_jd, arc_need, jd_lo, jd_hi):
    """Date où l'arc solaire vaut arc_need, dans [jd_lo, jd_hi] (arc monotone)."""
    def f(t):
        return solar_arc(natal_jd, t) - arc_need
    if f(jd_lo) > 0 or f(jd_hi) < 0:
        return None   # arc hors de la fenêtre
    return _refine_root(f, jd_lo, jd_hi)


def solar_arc_directions(natal_chart, jd_start, jd_end, family="major", orbs=None,
                         include_angles=True, moving=None):
    """Contacts dirigé→natal qui se perfectionnent dans la fenêtre, avec date EXACTE.

    L'arc étant monotone, chaque contact perfectionne une seule fois. Très précis :
    l'arc bouge d'~1°/an, donc une conjonction dirigée date l'année quasi au mois.

    moving : points dirigés à considérer (défaut : tous, angles compris). Les plus
    parlants sont le Soleil/MC/ASC dirigés et tout dirigé arrivant sur un angle natal.

    Retourne [{mobile, point_natal, aspect, orbe_exact:0, exact_jd, arc}, ...] trié.
    """
    natal_jd = natal_chart["jd"]
    targets = dict(natal_chart["pos"])
    if include_angles:
        targets["ASC"] = natal_chart["asc"]
        targets["MC"] = natal_chart["mc"]
    movers = dict(natal_chart["pos"])
    if include_angles:
        movers["ASC"] = natal_chart["asc"]
        movers["MC"] = natal_chart["mc"]
    if moving is not None:
        movers = {k: movers[k] for k in moving if k in movers}

    arc_lo = solar_arc(natal_jd, jd_start)
    arc_hi = solar_arc(natal_jd, jd_end)
    table = _aspect_table(family)
    out = []
    for mname, m0 in movers.items():
        if m0 is None:
            continue
        for tname, tlon in targets.items():
            if tlon is None or tname == mname:
                continue
            for ang, (aname, default_orb) in table.items():
                needs = {(tlon + ang - m0) % 360.0}
                if ang not in (0.0, 180.0):
                    needs.add((tlon - ang - m0) % 360.0)
                for arc_need in needs:
                    if not (arc_lo <= arc_need <= arc_hi):
                        continue
                    jx = _date_for_arc(natal_jd, arc_need, jd_start, jd_end)
                    if jx is not None:
                        out.append({"mobile": mname, "point_natal": tname,
                                    "aspect": aname, "exact_jd": jx,
                                    "arc": round(arc_need, 3)})
    return sorted(out, key=lambda h: h["exact_jd"])


def print_solar_arc(items):
    """Affichage lisible des directions par arc solaire."""
    for h in items:
        print(f"{jd_to_utc(h['exact_jd']):%Y-%m-%d}  {h['mobile']} dirigé "
              f"{h['aspect']} {h['point_natal']} natal   (arc {h['arc']}°)")


def transits(natal_chart, jd, orbs=None, family="major", include_angles=True):
    """Aspects transit→natal au moment jd, triés par orbe, avec appliquant/séparant.

    Retourne [(planète_transit, point_natal, aspect, orbe, appliquant), ...]."""
    t = chart(jd, natal_chart["lat"], natal_chart["lon"],
              natal_chart["hsys"], natal_chart["node"], natal_chart["lilith"])
    targets = dict(natal_chart["pos"])
    if include_angles:
        targets["ASC"] = natal_chart["asc"]
        targets["MC"] = natal_chart["mc"]
    tspeed = t["speed"]
    nspeed = {k: 0.0 for k in targets}
    return aspect_grid(t["pos"], targets, orbs, family, tspeed, nspeed)


# ---------------------------------------------------------------- transits dans le temps

# vitesse max approximative (°/jour) pour calibrer le pas d'échantillonnage
_MAX_SPEED = {"Lune": 15.0, "Mercure": 2.2, "Vénus": 1.3, "Soleil": 1.05,
              "Mars": 0.8, "Jupiter": 0.25, "Saturne": 0.14, "Chiron": 0.06,
              "Uranus": 0.06, "Neptune": 0.04, "Pluton": 0.04,
              "Nœud Nord": 0.06, "Nœud Sud": 0.06, "Lune Noire": 0.12, "Priape": 0.12}

SLOW_TRANSITERS = ["Mars", "Jupiter", "Saturne", "Chiron",
                   "Uranus", "Neptune", "Pluton"]

_BODY_CODE = {n: c for n, c in PLANETS}
_BODY_CODE["Chiron"] = swe.CHIRON


def _wrap180(x):
    return ((x + 180.0) % 360.0) - 180.0


def _lon_at(jd, body_code):
    (lon, *_), _ = swe.calc_ut(jd, body_code, _FLAGS)
    return lon % 360.0


def _refine_root(g, a, b, iters=50):
    """Racine de g sur [a,b] (g(a), g(b) de signes opposés) par bissection."""
    ga = g(a)
    for _ in range(iters):
        m = (a + b) / 2
        gm = g(m)
        if (ga <= 0) == (gm <= 0):
            a, ga = m, gm
        else:
            b = m
    return (a + b) / 2


def scan_transits(natal_chart, jd_start, jd_end, planets=None, targets=None,
                  family="major", orbs=None, include_angles=True, step_days=None,
                  require_exact=False):
    """Balaye une période et renvoie chaque contact transit→natal avec ses dates
    EXACTES (passages multiples direct–rétro–direct inclus) et sa fenêtre d'orbe active.

    Retourne une liste de contacts triés par date du premier passage exact :
      {transitant, point_natal, aspect, angle, exact_jds:[...], n_passages,
       enter_jd, exit_jd, orbe_max, deja_actif}
    enter_jd / exit_jd bornent la période où l'orbe est sous le maximum.
    deja_actif = True si l'aspect était déjà dans l'orbe au début de la fenêtre.

    require_exact=True : ne garde que les contacts qui se perfectionnent DANS la
    fenêtre (utile pour « qu'est-ce qui devient exact entre telle et telle date »).

    planets : liste de transitants (défaut SLOW_TRANSITERS, Chiron ignoré si absent).
    targets : dict {nom: longitude} des points natals visés (défaut = thème natal).
    """
    if targets is None:
        targets = dict(natal_chart["pos"])
        if include_angles:
            targets["ASC"] = natal_chart["asc"]
            targets["MC"] = natal_chart["mc"]
    if planets is None:
        planets = [p for p in SLOW_TRANSITERS
                   if p != "Chiron" or "Chiron" in natal_chart["pos"]]

    table = _aspect_table(family)
    fastest = max(_MAX_SPEED.get(p, 1.0) for p in planets)
    if step_days is None:
        step_days = min(1.0, 5.0 / fastest)   # < ~5° de mouvement par pas

    contacts = []
    for pname in planets:
        code = _BODY_CODE.get(pname)
        if code is None:
            continue

        def lonf(t, _c=code):
            return _lon_at(t, _c)

        for tname, tlon in targets.items():
            if tlon is None:
                continue
            for ang, (aname, default_orb) in table.items():
                max_orb = (orbs or {}).get(ang, default_orb)
                # longitudes que le transitant doit atteindre pour cet aspect
                cible_lons = {(tlon + ang) % 360.0}
                if ang not in (0.0, 180.0):
                    cible_lons.add((tlon - ang) % 360.0)

                for L in cible_lons:
                    def g(t, _L=L, _lf=lonf):
                        return _wrap180(_lf(t) - _L)

                    # échantillonnage + détection des changements de signe
                    samples = []
                    t = jd_start
                    while t <= jd_end + step_days:
                        samples.append((min(t, jd_end), g(min(t, jd_end))))
                        t += step_days

                    exacts, in_orb_pts = [], []
                    for (t0, v0), (t1, v1) in zip(samples, samples[1:]):
                        if abs(v0) <= max_orb:
                            in_orb_pts.append(t0)
                        # vrai croisement de zéro : signes opposés ET petit écart
                        # (le saut de wrap à ±180 fait ~360° → exclu)
                        if (v0 <= 0) != (v1 <= 0) and abs(v0 - v1) < 90.0:
                            exacts.append(_refine_root(g, t0, t1))
                    if abs(samples[-1][1]) <= max_orb:
                        in_orb_pts.append(samples[-1][0])

                    if not exacts and not in_orb_pts:
                        continue

                    # fenêtre d'orbe active : entrée avant le 1er point sous orbe,
                    # sortie après le dernier (racines de |g|−orbe)
                    enter_jd = exit_jd = None
                    if in_orb_pts:
                        first, last = in_orb_pts[0], in_orb_pts[-1]
                        gh = lambda t: abs(g(t)) - max_orb
                        a = max(jd_start, first - step_days)
                        if gh(a) > 0 and gh(first) <= 0:
                            enter_jd = _refine_root(gh, a, first)
                        else:
                            enter_jd = first
                        b = min(jd_end, last + step_days)
                        if gh(last) <= 0 and gh(b) > 0:
                            exit_jd = _refine_root(gh, last, b)
                        else:
                            exit_jd = last

                    if exacts or enter_jd is not None:
                        deja_actif = enter_jd is not None and enter_jd <= jd_start + step_days
                        if require_exact and not exacts:
                            continue
                        contacts.append({
                            "transitant": pname, "point_natal": tname,
                            "aspect": aname, "angle": ang,
                            "exact_jds": sorted(exacts), "n_passages": len(exacts),
                            "enter_jd": enter_jd, "exit_jd": exit_jd,
                            "orbe_max": max_orb, "deja_actif": deja_actif,
                        })

    def _sort_key(c):
        return c["exact_jds"][0] if c["exact_jds"] else (c["enter_jd"] or jd_start)
    return sorted(contacts, key=_sort_key)


def stations(planet, jd_start, jd_end, step_days=2.0):
    """Dates des stations (vitesse longitudinale = 0) d'une planète sur la période.

    Retourne [(jd, 'rétrograde'|'directe', longitude), ...]. Une station
    'rétrograde' = la planète s'arrête puis recule ; 'directe' = reprend le direct.
    """
    code = _BODY_CODE.get(planet)
    if code is None:
        raise ValueError(f"corps inconnu : {planet}")

    def spd(t):
        (_, _, _, slon, *_), _ = swe.calc_ut(t, code, _FLAGS)
        return slon

    out, t = [], jd_start
    prev = spd(t)
    while t <= jd_end:
        t1 = min(t + step_days, jd_end)
        cur = spd(t1)
        if (prev <= 0) != (cur <= 0):
            jd0 = _refine_root(lambda x: spd(x), t, t1)
            kind = "rétrograde" if cur < 0 else "directe"
            out.append((jd0, kind, _lon_at(jd0, code)))
        prev = cur
        if t1 >= jd_end:
            break
        t = t1
    return out


# ---------------------------------------------------------------- éclipses

def _eclipse_label(rc, lunar):
    """Décode le masque de bits Swiss Ephemeris en libellé lisible."""
    if lunar:
        if rc & swe.ECL_TOTAL: base = "totale"
        elif rc & swe.ECL_PARTIAL: base = "partielle"
        elif rc & swe.ECL_PENUMBRAL: base = "par la pénombre"
        else: base = "lunaire"
        return f"Lune {base}"
    else:
        if rc & swe.ECL_TOTAL: base = "totale"
        elif rc & swe.ECL_ANNULAR: base = "annulaire"
        elif rc & swe.ECL_ANNULAR_TOTAL: base = "hybride (annulaire-totale)"
        elif rc & swe.ECL_PARTIAL: base = "partielle"
        else: base = "solaire"
        central = " centrale" if rc & swe.ECL_CENTRAL else ""
        return f"Soleil {base}{central}"


def eclipses(jd_start, jd_end, node="true"):
    """Toutes les éclipses (solaires ET lunaires) sur la période, triées par date.

    Retourne [{jd, kind:'solaire'|'lunaire', type, lon, signe, maison_node}, ...].
    lon = degré écliptique de l'éclipse (Soleil pour solaire, Lune pour lunaire).
    Une éclipse tombe toujours près de l'axe des nœuds : c'est ce qui en fait un
    marqueur de timing si elle contacte un point natal (voir eclipses_on_natal).
    """
    out = []
    # solaires
    t = jd_start
    while t < jd_end:
        rc, tret = swe.sol_eclipse_when_glob(t, _FLAGS, 0)
        mx = tret[0]
        if mx > jd_end:
            break
        lon, _ = _calc(mx, swe.SUN)
        out.append({"jd": mx, "kind": "solaire", "type": _eclipse_label(rc, False),
                    "lon": lon, "signe": SIGNS_FR[int(lon // 30)]})
        t = mx + 1.0
    # lunaires
    t = jd_start
    while t < jd_end:
        rc, tret = swe.lun_eclipse_when(t, _FLAGS, 0)
        mx = tret[0]
        if mx > jd_end:
            break
        lon, _ = _calc(mx, swe.MOON)
        out.append({"jd": mx, "kind": "lunaire", "type": _eclipse_label(rc, True),
                    "lon": lon, "signe": SIGNS_FR[int(lon // 30)]})
        t = mx + 1.0
    return sorted(out, key=lambda e: e["jd"])


def eclipses_on_natal(natal_chart, jd_start, jd_end, orb=3.0,
                      family="major", include_angles=True):
    """Éclipses de la période qui contactent un point natal (dans l'orbe donné).

    Retourne [{eclipse..., point_natal, aspect, orbe}, ...] trié par date.
    Une éclipse conjointe/opposée à un luminaire ou un angle natal est l'un des
    marqueurs de timing les plus parlants — mais reste un thème, pas un verdict.
    """
    targets = dict(natal_chart["pos"])
    if include_angles:
        targets["ASC"] = natal_chart["asc"]
        targets["MC"] = natal_chart["mc"]
    eorbs = {k: orb for k in _aspect_table(family)}  # orbe serré, propre aux éclipses
    out = []
    for e in eclipses(jd_start, jd_end, natal_chart["node"]):
        for tname, tlon in targets.items():
            if tlon is None:
                continue
            name, o = aspect(e["lon"], tlon, eorbs, family)
            if name:
                hit = dict(e)
                hit.update({"point_natal": tname, "aspect": name, "orbe": o})
                out.append(hit)
    return sorted(out, key=lambda h: (h["jd"], h["orbe"]))


def print_eclipses(items):
    """Affichage lisible d'une liste d'éclipses (brutes ou contacts natals)."""
    for e in items:
        base = f"{jd_to_utc(e['jd']):%Y-%m-%d %H:%M} TU  Éclipse {e['type']:22s} {fmt(e['lon'])}"
        if "point_natal" in e:
            base += f"  →  {e['aspect']} {e['point_natal']} natal (orbe {e['orbe']}°)"
        print(base)


# ---------------------------------------------------------------- cycle nodal

def nodal_cycle(natal_chart, jd_start, jd_end, orb=2.0, extra_points=None):
    """Retours et renversements nodaux + contacts des nœuds transitants aux points
    sensibles natals, sur la période.

    Les nœuds transitants rétrogradent (~18,6 ans pour un tour). Repères :
      - nœud transitant conjoint au nœud natal de MÊME nom = RETOUR NODAL (~18,6 ans)
      - conjoint au nœud natal OPPOSÉ = RENVERSEMENT NODAL (~9,3 ans, demi-cycle)
    extra_points : dict {nom: lon} supplémentaires à surveiller (défaut : Soleil,
    Lune, ASC, MC — les points où un nœud transitant active la sensibilité éclipse).

    Retourne [{jd, evenement, point_natal, aspect}, ...] trié par date.
    """
    code = NODE_MODES[natal_chart["node"]]
    nn_nat = natal_chart["pos"]["Nœud Nord"]
    targets = {"Nœud Nord": nn_nat, "Nœud Sud": (nn_nat + 180.0) % 360.0}
    pts = extra_points if extra_points is not None else {
        "Soleil": natal_chart["pos"]["Soleil"], "Lune": natal_chart["pos"]["Lune"],
        "ASC": natal_chart["asc"], "MC": natal_chart["mc"]}
    targets.update(pts)

    def nlon(t):
        return _lon_at(t, code)

    out, step = [], 3.0
    for tname, tlon in targets.items():
        is_node = tname in ("Nœud Nord", "Nœud Sud")
        for ang, label_ang in ((0.0, "conjonction"), (180.0, "opposition")):
            # nœud↔nœud : la conjonction suffit (l'opposition est le même instant d'axe)
            if is_node and ang == 180.0:
                continue
            L = (tlon + ang) % 360.0
            t = jd_start
            prev = _wrap180(nlon(t) - L)
            while t < jd_end:
                t1 = min(t + step, jd_end)
                cur = _wrap180(nlon(t1) - L)
                if (prev <= 0) != (cur <= 0) and abs(prev - cur) < 90.0:
                    jx = _refine_root(lambda x: _wrap180(nlon(x) - L), t, t1)
                    ev = label_ang
                    if tname == "Nœud Nord" and ang == 0.0:
                        ev = "RETOUR NODAL"
                    elif tname == "Nœud Nord" and ang == 180.0:
                        ev = "renversement nodal"
                    elif tname == "Nœud Sud" and ang == 0.0:
                        ev = "renversement nodal"
                    out.append({"jd": jx, "evenement": ev,
                                "point_natal": tname, "aspect": label_ang})
                prev = cur
                if t1 >= jd_end:
                    break
                t = t1
    # dédup (le renversement apparaît via NN-opp et NS-conj : garder une occurrence)
    seen, dedup = set(), []
    for e in sorted(out, key=lambda h: h["jd"]):
        key = (round(e["jd"]), e["evenement"])
        if key not in seen:
            seen.add(key)
            dedup.append(e)
    return dedup


def print_nodal_cycle(items):
    for e in items:
        print(f"{jd_to_utc(e['jd']):%Y-%m-%d}  {e['evenement']:20s} "
              f"(nœud transitant {e['aspect']} {e['point_natal']} natal)")


def print_transit_timeline(contacts):
    """Affichage lisible d'un scan : une ligne par contact, dates exactes + fenêtre."""
    for c in contacts:
        passages = ", ".join(jd_to_utc(j).strftime("%Y-%m-%d") for j in c["exact_jds"]) or "—"
        win = ""
        if c["enter_jd"] is not None and c["exit_jd"] is not None:
            win = (f"  [orbe {c['orbe_max']:.0f}° : "
                   f"{jd_to_utc(c['enter_jd']):%Y-%m-%d} → {jd_to_utc(c['exit_jd']):%Y-%m-%d}]")
        tag = f" ×{c['n_passages']}" if c["n_passages"] > 1 else ""
        tag += "  (déjà actif au départ)" if c.get("deja_actif") and not c["exact_jds"] else ""
        print(f"{c['transitant']:9s} {c['aspect']:12s} {c['point_natal']:11s} natal"
              f"  exact: {passages}{tag}{win}")


def synastry(chartA, chartB, orbs=None, family="major", include_angles=True):
    """Tous les inter-aspects A×B (orbes serrés d'abord)."""
    pa, pb = dict(chartA["pos"]), dict(chartB["pos"])
    if include_angles:
        pa["ASC"], pa["MC"] = chartA["asc"], chartA["mc"]
        pb["ASC"], pb["MC"] = chartB["asc"], chartB["mc"]
    return aspect_grid(pa, pb, orbs, family)


def overlay_houses(planets_chart, houses_chart):
    """Dans quelle maison de B tombent les planètes de A ? -> {planète: maison}."""
    return {name: house_of(lo, houses_chart["cusps"])
            for name, lo in planets_chart["pos"].items() if lo is not None}


def harmonic_chart(c, n):
    """Carte harmonique n : longitudes × n mod 360 (lire les conjonctions).

    Pour la famille novile, n=9 (Rudhyar / Tierney / Bigé) : toute conjonction
    en H9 correspond à un novile/binovile/quadrinovile (ou aspect majeur) en radix.
    """
    pos = {k: (v * n) % 360.0 for k, v in c["pos"].items() if v is not None}
    return {"pos": pos, "harmonic": n, "source_jd": c["jd"]}


# ---------------------------------------------------------------- composite & Davison

def _midpoint(a, b):
    """Mi-point sur le plus court arc (le mi-point « proche »)."""
    d = ((b - a + 180.0) % 360.0) - 180.0
    return (a + d / 2.0) % 360.0


def _geo_midpoint(latA, lonA, latB, lonB):
    """Milieu géographique sur la sphère (grand cercle) — correct même loin /
    de part et d'autre de l'antiméridien, contrairement à une moyenne lat/lon."""
    from math import radians, degrees, sin, cos, atan2, sqrt
    la, lb = radians(latA), radians(latB)
    dlon = radians(lonB - lonA)
    bx = cos(lb) * cos(dlon)
    by = cos(lb) * sin(dlon)
    lat = atan2(sin(la) + sin(lb),
                sqrt((cos(la) + bx) ** 2 + by ** 2))
    lon = radians(lonA) + atan2(by, cos(la) + bx)
    return degrees(lat), (degrees(lon) + 540.0) % 360.0 - 180.0


def davison(chartA, chartB, hsys=None, node=None, lilith=None):
    """Thème de Davison : VRAI thème au milieu temporel et géographique des deux
    naissances. Étant un instant réel du ciel, il accepte transits / progressions /
    arc solaire (passe le dict retourné comme un thème natal ordinaire).

    Hérite par défaut du système de maisons / nœud / Lilith du thème A.
    """
    jd_mid = (chartA["jd"] + chartB["jd"]) / 2.0
    lat_mid, lon_mid = _geo_midpoint(chartA["lat"], chartA["lon"],
                                     chartB["lat"], chartB["lon"])
    c = chart(jd_mid, lat_mid, lon_mid,
              hsys=hsys or chartA["hsys"],
              node=node or chartA["node"],
              lilith=lilith or chartA["lilith"])
    c["davison"] = True
    return c


def composite(chartA, chartB, include_angles=True):
    """Thème composite par MI-POINTS : chaque point = mi-point (arc court) des deux
    positions natales. Ce n'est PAS un instant réel du ciel — donc PAS de transits
    ni de progressions dessus (utiliser Davison pour ça). Bon pour la structure
    relationnelle « moyenne » du couple.

    Retourne pos + asc + mc (mi-points des angles). Pas de cuspides intermédiaires
    fiables sans choisir une convention de maisons composites — à faire à part.
    """
    pos = {}
    for k in chartA["pos"]:
        a, b = chartA["pos"].get(k), chartB["pos"].get(k)
        if a is not None and b is not None:
            pos[k] = _midpoint(a, b)
    out = {"pos": pos, "composite": True}
    if include_angles:
        out["asc"] = _midpoint(chartA["asc"], chartB["asc"])
        out["mc"] = _midpoint(chartA["mc"], chartB["mc"])
    return out


# ---------------------------------------------------------------- dominantes

# Pondération PAR DÉFAUT — c'est une CONVENTION, pas une vérité objective.
# Tunable : passer un dict à dominants(weights=...). Inspirée de la tradition
# française (angularité + aspects + dignité + maîtrises des points clés).
DEFAULT_DOMINANT_WEIGHTS = {
    "angle_max": 12.0, "angle_orb": 10.0,        # conj à un angle : 12 pts à 0°, 0 à 10°
    "house_angular": 5.0, "house_succedent": 3.0, "house_cadent": 1.0,
    "aspect": {"conjonction": 5.0, "opposition": 4.0, "carré": 4.0,
               "trigone": 3.0, "sextile": 2.0},
    "aspect_minor": 1.0,
    "aspect_lum_mult": 1.5,                       # ×1.5 si l'autre point est Soleil/Lune/ASC/MC
    "dignity_domicile": 5.0, "dignity_exalt": 4.0,
    "dignity_exil": -3.0, "dignity_chute": -4.0,
    "ruler_asc": 8.0, "ruler_mc": 4.0, "ruler_sun": 3.0, "ruler_moon": 3.0,
    "luminary_base": 5.0,
}
# pondération des corps pour l'équilibre éléments/modes (convention courante)
ELEM_BODY_WEIGHTS = {"Soleil": 3, "Lune": 3, "ASC": 3, "Mercure": 2, "Vénus": 2,
                     "Mars": 2, "Jupiter": 1, "Saturne": 1, "MC": 1,
                     "Uranus": 1, "Neptune": 1, "Pluton": 1}
_PLANETS10 = ["Soleil", "Lune", "Mercure", "Vénus", "Mars",
              "Jupiter", "Saturne", "Uranus", "Neptune", "Pluton"]
_LUMINOUS = {"Soleil", "Lune", "ASC", "MC"}


def _sign_idx(lon):
    return int(lon // 30) % 12


def _house_class_weight(h, w):
    if h in (1, 4, 7, 10): return w["house_angular"]
    if h in (2, 5, 8, 11): return w["house_succedent"]
    return w["house_cadent"]


def dominants(c, weights=None, rulers="trad", bodies=None, family="major", orbs=None):
    """Calcule les dominantes planétaires (score pondéré), l'équilibre élémentaire
    (Feu/Terre/Air/Eau) et modal (Cardinal/Fixe/Mutable).

    ⚠ La pondération est une CONVENTION explicite et réglable (weights=...), pas une
    mesure objective. À utiliser comme POINT DE DÉPART de synthèse, jamais comme
    verdict. rulers : 'trad' (maîtrises traditionnelles) ou 'mod' (modernes).

    Retourne {ranking:[(planète, score, pct)], scores, percent, elements, modes,
              maitre_asc, details}. details[planète] = ventilation des points.
    """
    w = dict(DEFAULT_DOMINANT_WEIGHTS, **(weights or {}))
    rul = RULERS_MOD if rulers == "mod" else RULERS_TRAD
    bodies = bodies or _PLANETS10

    asc, mc = c["asc"], c["mc"]
    angles = {"ASC": asc, "MC": mc, "DSC": (asc + 180) % 360, "IC": (mc + 180) % 360}
    pts = dict(c["pos"]); pts["ASC"] = asc; pts["MC"] = mc

    sun_sign = SIGNS_FR[_sign_idx(c["pos"]["Soleil"])]
    moon_sign = SIGNS_FR[_sign_idx(c["pos"]["Lune"])]
    asc_sign = SIGNS_FR[_sign_idx(asc)]
    mc_sign = SIGNS_FR[_sign_idx(mc)]
    maitre_asc = rul[asc_sign]

    scores, details = {}, {}
    for p in bodies:
        lon = c["pos"].get(p)
        if lon is None:
            continue
        d = {"angularité": 0.0, "maison": 0.0, "aspects": 0.0,
             "dignité": 0.0, "maîtrises": 0.0, "base": 0.0}

        # base luminaires
        if p in ("Soleil", "Lune"):
            d["base"] += w["luminary_base"]

        # angularité (proximité aux 4 angles)
        for alon in angles.values():
            sep = _delta(lon, alon)
            if sep <= w["angle_orb"]:
                d["angularité"] += w["angle_max"] * (1 - sep / w["angle_orb"])

        # maison occupée
        d["maison"] += _house_class_weight(house_of(lon, c["cusps"]), w)

        # aspects aux autres points (tightness + bonus luminaire)
        for q, qlon in pts.items():
            if q == p or qlon is None:
                continue
            name, orb = aspect(lon, qlon, orbs, family)
            if not name:
                continue
            base = w["aspect"].get(name, w["aspect_minor"])
            max_orb = (orbs or {}).get(_ANGLE_BY_NAME.get(name, 0),
                                       _aspect_table(family).get(_ANGLE_BY_NAME.get(name, 0),
                                       (None, 8.0))[1])
            tight = max(0.0, 1 - orb / max_orb) if max_orb else 1.0
            v = base * (0.5 + 0.5 * tight)            # 50 % fixe + 50 % selon serrage
            if q in _LUMINOUS:
                v *= w["aspect_lum_mult"]
            d["aspects"] += v

        # dignité essentielle
        psign = SIGNS_FR[_sign_idx(lon)]
        if psign in DOMICILE.get(p, []): d["dignité"] += w["dignity_domicile"]
        if EXALT.get(p) == psign: d["dignité"] += w["dignity_exalt"]
        if psign in EXIL.get(p, []): d["dignité"] += w["dignity_exil"]
        if CHUTE.get(p) == psign: d["dignité"] += w["dignity_chute"]

        # maîtrise des points clés
        if rul.get(asc_sign) == p: d["maîtrises"] += w["ruler_asc"]
        if rul.get(mc_sign) == p: d["maîtrises"] += w["ruler_mc"]
        if rul.get(sun_sign) == p: d["maîtrises"] += w["ruler_sun"]
        if rul.get(moon_sign) == p: d["maîtrises"] += w["ruler_moon"]

        scores[p] = max(0.0, sum(d.values()))
        details[p] = {k: round(v, 2) for k, v in d.items()}

    total = sum(scores.values()) or 1.0
    percent = {p: 100.0 * s / total for p, s in scores.items()}
    ranking = sorted(((p, round(scores[p], 2), round(percent[p], 1)) for p in scores),
                     key=lambda t: -t[1])

    # équilibre éléments / modes (corps + ASC/MC pondérés)
    elements = {"Feu": 0.0, "Terre": 0.0, "Air": 0.0, "Eau": 0.0}
    modes = {"Cardinal": 0.0, "Fixe": 0.0, "Mutable": 0.0}
    for p, bw in ELEM_BODY_WEIGHTS.items():
        lon = pts.get(p)
        if lon is None:
            continue
        si = _sign_idx(lon)
        elements[ELEMENT[si]] += bw
        modes[MODE[si]] += bw
    es = sum(elements.values()) or 1.0
    ms = sum(modes.values()) or 1.0
    elements_pct = {k: round(100 * v / es, 1) for k, v in elements.items()}
    modes_pct = {k: round(100 * v / ms, 1) for k, v in modes.items()}

    return {"ranking": ranking, "scores": scores, "percent": percent,
            "elements": elements_pct, "modes": modes_pct,
            "maitre_asc": maitre_asc, "details": details}


def print_dominants(dom, top=5):
    """Affichage lisible des dominantes + équilibres."""
    print(f"Maître de l'Ascendant : {dom['maitre_asc']}")
    print("Dominantes (score pondéré — convention réglable) :")
    for p, s, pct in dom["ranking"][:top]:
        print(f"  {p:9s} {s:6.1f}  ({pct:.1f} %)")
    el = "  ".join(f"{k} {v:.0f}%" for k, v in dom["elements"].items())
    mo = "  ".join(f"{k} {v:.0f}%" for k, v in dom["modes"].items())
    print("Éléments :", el)
    print("Modes    :", mo)


# ---------------------------------------------------------------- croix de la Lune Noire

def lune_noire_cross(c, variant="interp"):
    """Croix de la Lune Noire : croix GÉOMÉTRIQUE bâtie sur la Lune Noire corrigée.

    À NE PAS confondre avec la croix des Nœuds (objet distinct). Quatre bras à 90°
    sur la longitude L de la Lune Noire (par défaut la corrigée / interpolée) :

        Lune Noire  = L
        Priape      = L + 180   (opposition : compensation)
        Affirmation = L - 90    (carré décroissant)
        Soumission  = L + 90    (carré croissant)

    Chaque bras est rendu avec signe + maison + position formatée. Renvoie aussi
    l'écart moyenne↔corrigée (intensité). Les bras dérivés sont calculés
    géométriquement depuis L : la croix est exacte par définition et présente dans
    tout thème. Si la croix porte sur une variante différente, passer variant=.
    """
    L = c["lilith_variants"].get(variant)
    if L is None:
        L = c["pos"].get("Lune Noire")
    if L is None:
        raise ValueError("Lune Noire indisponible : impossible de calculer la croix.")
    cusps = c.get("cusps")

    def arm(lon):
        lon %= 360.0
        a = {"lon": lon, "signe": SIGNS_FR[int(lon // 30) % 12], "fmt": fmt(lon)}
        if cusps:
            a["maison"] = house_of(lon, cusps)
        return a

    bras = {
        "lune_noire":  arm(L),
        "priape":      arm((L + 180.0) % 360.0),
        "affirmation": arm((L - 90.0) % 360.0),
        "soumission":  arm((L + 90.0) % 360.0),
    }

    mean = c["lilith_variants"].get("mean")
    ecart = abs(_wrap180(L - mean)) if mean is not None else None

    return {"variante": variant, "bras": bras, "ecart_moyenne_corrigee": ecart}


def print_lune_noire_cross(cr):
    """Impression lisible de la croix de la Lune Noire."""
    print(f"[croix de la Lune Noire — sur la {cr['variante']}]")
    for nom, a in cr["bras"].items():
        h = f"maison {a['maison']}" if "maison" in a else "(maison n/d — heure inconnue)"
        print(f"  {nom:12s} {a['fmt']:24s} {h}")
    if cr["ecart_moyenne_corrigee"] is not None:
        print(f"  écart moyenne↔corrigée : {cr['ecart_moyenne_corrigee']:.2f}°  (intensité)")
