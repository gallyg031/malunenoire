# -*- coding: utf-8 -*-
"""
lune.py — Lune Noire corrigée : natal, croix, activations, nouvelles lunes, .ics (spec 02).

Construit au-dessus d'astro.py (copie intacte du skill, jamais modifiée).
Toutes les positions viennent de Swiss Ephemeris ; l'heure locale passe par
astro.to_jd (zoneinfo) ; les instants rendus sont des datetime UTC.
"""

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import swisseph as swe

import astro

UTC = timezone.utc
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI_PATH = os.path.join(ROOT, "content", "ui.json")

SIGN_IDS = ["belier", "taureau", "gemeaux", "cancer", "lion", "vierge",
            "balance", "scorpion", "sagittaire", "capricorne", "verseau", "poissons"]
SIGNS_FR = astro.SIGNS_FR
POINTS = ("lune_noire", "priape", "affirmation", "soumission")
MIN_DATE = date(1900, 1, 1)
MINUTE = 1.0 / 1440.0


# ---------------------------------------------------------------- temps

def jd_from_dt(dt):
    """datetime aware -> jd UT."""
    u = dt.astimezone(UTC)
    return swe.julday(u.year, u.month, u.day,
                      u.hour + u.minute / 60.0 + (u.second + u.microsecond / 1e6) / 3600.0)


def dt_from_jd(jd):
    """jd UT -> datetime UTC à la seconde."""
    y, mo, d, h = swe.revjul(jd)
    return (datetime(y, mo, d, tzinfo=UTC) + timedelta(seconds=round(h * 3600.0)))


def _wrap180(x):
    return (x + 180.0) % 360.0 - 180.0


# ---------------------------------------------------------------- natal (§2)

@dataclass
class Natal:
    jd: float
    utc_offset_min: int
    ln_lon: float
    ln_sign: int
    ln_deg: float
    ln_house: int | None
    house_reason: str | None          # None | "no_time" | "polar"
    cross: dict                        # point -> {lon, sign, deg, house}
    intensity: float
    no_time: bool
    sign_changes_today: bool
    cusps: list | None = field(default=None, repr=False)

    @property
    def sign_id(self):
        return SIGN_IDS[self.ln_sign]


def _ln_interp(jd):
    lon, _ = astro._calc(jd, astro.LILITH_MODES["interp"])
    return lon


def _chart(jd, lat, lon):
    """Thème Koch ; au-delà du cercle polaire Koch n'existe pas → None (pas de maisons)."""
    try:
        return astro.chart(jd, lat, lon), None
    except swe.Error:
        return astro.chart(jd, lat, lon, hsys="porphyry"), "polar"


def natal(birth_date, birth_time, lat, lon, tz):
    """birth_time None = heure inconnue : calcul à 12:00 locale, sans maison (D5)."""
    if not isinstance(birth_date, date) or isinstance(birth_date, datetime):
        raise ValueError("date de naissance invalide")
    today = datetime.now(ZoneInfo(tz)).date()
    if not MIN_DATE <= birth_date <= today:
        raise ValueError("date de naissance hors plage (1900 → aujourd'hui)")
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        raise ValueError("coordonnées invalides")
    no_time = birth_time is None
    t = time(12, 0) if no_time else birth_time
    jd, off = astro.to_jd(birth_date.year, birth_date.month, birth_date.day,
                          t.hour, t.minute, tz)
    c, reason = _chart(jd, lat, lon)
    if no_time:
        reason = "no_time"
    cr = astro.lune_noire_cross(c)
    L = cr["bras"]["lune_noire"]["lon"]
    houses = reason is None

    cross = {}
    for p in POINTS:
        a = cr["bras"][p]
        cross[p] = {"lon": a["lon"], "sign": int(a["lon"] // 30), "deg": a["lon"] % 30,
                    "house": a.get("maison") if houses else None}

    changes = False
    if no_time:
        d = birth_date
        jd0, _ = astro.to_jd(d.year, d.month, d.day, 0, 0, tz)
        jd1, _ = astro.to_jd(d.year, d.month, d.day, 23, 59, tz)
        changes = int(_ln_interp(jd0) // 30) != int(_ln_interp(jd1) // 30)

    return Natal(jd=jd, utc_offset_min=round(off * 60), ln_lon=L, ln_sign=int(L // 30),
                 ln_deg=L % 30, ln_house=cross["lune_noire"]["house"], house_reason=reason,
                 cross=cross, intensity=cr["ecart_moyenne_corrigee"], no_time=no_time,
                 sign_changes_today=changes, cusps=c["cusps"] if houses else None)


# ---------------------------------------------------------------- activations (§5)

# corps suivis : (id, code swe, poids, pas d'échantillonnage en jours)
# Pas ≤ 1/5 de la plus courte période possible (orbe 1,5° / vitesse max) : aucune
# période ne peut tomber entre deux échantillons ; bornes et exacts sont ensuite
# affinés à la minute. (Spec §5.2 : 1 j / 6 h ; élargi pour tenir 300 ms avec le
# regroupement des boucles rétrogrades.)
BODIES = [
    ("pluton", swe.PLUTO, 8, 5.0),       # ≥ 75 j dans l'orbe la plus étroite
    ("neptune", swe.NEPTUNE, 7, 5.0),    # ≥ 75 j
    ("uranus", swe.URANUS, 6, 5.0),      # ≥ 50 j
    ("saturne", swe.SATURN, 5, 3.0),     # ≥ 23 j
    ("jupiter", swe.JUPITER, 4, 2.0),    # ≥ 12 j
    ("lune_noire", swe.MEAN_APOG, 3, 1.0),
    ("mars", swe.MARS, 2, 0.75),         # ≥ 3,7 j
    ("soleil", swe.SUN, 1, 0.5),         # ≥ 2,9 j
]
WEIGHT = {b[0]: b[2] for b in BODIES}

# k -> (aspect, orbe, bras touché)
TARGETS = {
    0: ("conjonction", 3.0, "lune_noire"),
    6: ("opposition", 3.0, "priape"),
    3: ("carre", 2.0, "soumission"),
    9: ("carre", 2.0, "affirmation"),
    4: ("trigone", 2.0, None),
    8: ("trigone", 2.0, None),
    2: ("sextile", 1.5, None),
    10: ("sextile", 1.5, None),
}

PAD_DAYS = 10.0          # marge d'échantillonnage de part et d'autre (§5.3)
MERGE_DAYS = 7.0         # fusion de deux périodes proches (§5.3 étape 5)
# Passages d'une même boucle rétrograde regroupés en une activation (décision du
# 24/10/2026) : on échantillonne plus large pour retrouver les passages voisins.
# Marge = durée max entre le 1er et le 3e passage d'une boucle.
LOOP_PAD = {"mars": 200.0, "jupiter": 330.0, "saturne": 330.0,
            "uranus": 400.0, "neptune": 400.0, "pluton": 400.0}
LOOP_DAYS = 200.0        # écart max entre deux passages consécutifs d'une même boucle
EXTEND_MAX_DAYS = 6 * 365.25   # recherche des vraies bornes d'une période en cours


@dataclass
class Event:
    id: str
    kind: str                  # "transit" | "ln_ingress"
    body: str
    aspect: str | None
    point: str | None
    weight: int
    enter: datetime
    exit: datetime | None      # None : au-delà de l'horizon
    exacts: list
    k: int | None = None
    sign_to: int | None = None

    def to_dict(self):
        return {"id": self.id, "kind": self.kind, "body": self.body, "aspect": self.aspect,
                "point": self.point, "weight": self.weight, "enter": self.enter,
                "exit": self.exit, "exacts": list(self.exacts), "k": self.k,
                "sign_to": self.sign_to}


def event_id(reading_id, body, k, enter):
    raw = f"{reading_id}|{body}|{k}|{enter.date().isoformat()}"
    return hashlib.sha1(raw.encode()).hexdigest()[:12]


def _lon(jd, code):
    (lon, *_), _ = swe.calc_ut(jd, code, astro._FLAGS)
    return lon % 360.0


def _bisect(g, a, b):
    """Racine de g sur [a, b] (signes opposés), à moins d'une minute près."""
    ga = g(a)
    while b - a > MINUTE / 4:
        m = (a + b) / 2
        gm = g(m)
        if (ga <= 0) == (gm <= 0):
            a, ga = m, gm
        else:
            b = m
    return (a + b) / 2


def _crosses(v0, v1):
    """Vrai passage par zéro (le saut ±180 du wrap est exclu)."""
    return (v0 <= 0) != (v1 <= 0) and abs(v0 - v1) < 90.0


def _extend(d, t, step, direction, orb):
    """Depuis t (dans l'orbe), avance jusqu'à sortir de l'orbe.

    Renvoie (instant de sortie affiné | None si plafond atteint, zéros rencontrés).
    """
    zeros = []
    t0, v0 = t, d(t)
    limit = t + direction * EXTEND_MAX_DAYS
    while (limit - t0) * direction > 0:
        t1 = t0 + direction * step
        v1 = d(t1)
        if _crosses(v0, v1):
            lo, hi = sorted((t0, t1))
            zeros.append(_bisect(d, lo, hi))
        if abs(v1) > orb:
            lo, hi = sorted((t0, t1))
            return _bisect(lambda x: abs(d(x)) - orb, lo, hi), zeros
        t0, v0 = t1, v1
    return None, zeros


def _periods(d, ts, vs, orb, step):
    """Périodes maximales |d| ≤ orbe sur l'échantillon, bornes et passages exacts affinés.

    Renvoie [(enter_jd, exit_jd | None, [exact_jd])] ; exit None = toujours dans l'orbe
    au-delà du plafond de recherche.
    """
    out = []
    n = len(ts)
    i = 0
    while i < n:
        if abs(vs[i]) > orb:
            i += 1
            continue
        j = i
        while j + 1 < n and abs(vs[j + 1]) <= orb:
            j += 1
        zeros = [_bisect(d, ts[m], ts[m + 1]) for m in range(i, j) if _crosses(vs[m], vs[m + 1])]
        if i == 0:
            enter, z = _extend(d, ts[0], step, -1, orb)
            zeros = sorted(z) + zeros
        else:
            enter = _bisect(lambda x: abs(d(x)) - orb, ts[i - 1], ts[i])
            if _crosses(vs[i - 1], vs[i]):
                zeros.insert(0, _bisect(d, ts[i - 1], ts[i]))
        if j == n - 1:
            exit_, z = _extend(d, ts[-1], step, +1, orb)
            zeros += z
        else:
            exit_ = _bisect(lambda x: abs(d(x)) - orb, ts[j], ts[j + 1])
            if _crosses(vs[j], vs[j + 1]):
                zeros.append(_bisect(d, ts[j], ts[j + 1]))
        out.append([enter, exit_, sorted(set(zeros))])
        i = j + 1
    return out


def _speed(jd, code):
    (_, _, _, slon, *_), _ = swe.calc_ut(jd, code, astro._FLAGS)
    return slon


def _same_loop(code, exit_, enter):
    """Deux périodes appartiennent à la même boucle rétrograde si le corps a changé
    de sens entre la sortie de l'une et l'entrée de l'autre, à moins d'une boucle d'écart."""
    return enter - exit_ < LOOP_DAYS and (_speed(exit_, code) < 0) != (_speed(enter, code) < 0)


def _merge(periods, code=None):
    """Fusionne deux périodes séparées de moins de MERGE_DAYS (§5.3 étape 5), et,
    si `code` est donné, les périodes d'une même boucle rétrograde."""
    merged = []
    for p in periods:
        if merged and merged[-1][1] is not None and p[0] is not None and (
                p[0] - merged[-1][1] < MERGE_DAYS
                or (code is not None and _same_loop(code, merged[-1][1], p[0]))):
            merged[-1][1] = p[1]
            merged[-1][2] = sorted(set(merged[-1][2] + p[2]))
        else:
            merged.append(p)
    return merged


def _horizon(start, months):
    t0 = datetime.combine(start, time(0), UTC) if not isinstance(start, datetime) \
        else start.astimezone(UTC)
    return t0, t0 + timedelta(days=31 * months)


def activations(natal_, start, months=13, reading_id=""):
    """Transits des corps suivis aux huit positions L + k·30° (§5) + ingrès (§5.4).

    natal_ : objet portant ln_lon (Natal). start : date ou datetime.
    Tri par date d'entrée.
    """
    t_start, t_end = _horizon(start, months)
    jd_start, jd_end = jd_from_dt(t_start), jd_from_dt(t_end)
    L = natal_.ln_lon
    events = []

    for body, code, weight, step in BODIES:
        retro = body in LOOP_PAD
        pad = LOOP_PAD.get(body, PAD_DAYS)
        a, b = jd_start - pad, jd_end + pad
        count = int((b - a) / step) + 1
        ts = [a + i * step for i in range(count + 1)]
        lons = [_lon(t, code) for t in ts]
        for k, (aspect, orb, point) in TARGETS.items():
            target = (L + 30.0 * k) % 360.0

            def d(t, _c=code, _tg=target):
                return _wrap180(_lon(t, _c) - _tg)

            vs = [_wrap180(x - target) for x in lons]
            for enter, exit_, exacts in _merge(_periods(d, ts, vs, orb, step),
                                               code if retro else None):
                if exit_ is not None and exit_ < jd_start:
                    continue
                if enter is not None and enter > jd_end:
                    continue
                if not exacts:
                    continue   # frôlement sans perfection : pas une activation (cf. écarts)
                enter_dt = dt_from_jd(enter) if enter is not None else None
                exit_dt = dt_from_jd(exit_) if exit_ is not None and exit_ <= jd_end else None
                if enter_dt is None:
                    enter_dt = dt_from_jd(jd_start - EXTEND_MAX_DAYS)
                events.append(Event(
                    id=event_id(reading_id, body, k, enter_dt), kind="transit", body=body,
                    aspect=aspect, point=point, weight=weight, enter=enter_dt, exit=exit_dt,
                    exacts=[dt_from_jd(x) for x in exacts], k=k))

    events += ln_ingress(t_start, t_end, reading_id)
    events.sort(key=lambda e: (e.enter, -e.weight))
    return events


def ln_ingress(t_start, t_end, reading_id=""):
    """Changements de signe de la Lune Noire moyenne en transit dans [t_start, t_end]."""
    a, b = jd_from_dt(t_start), jd_from_dt(t_end)
    code = swe.MEAN_APOG
    out = []
    t0, s0 = a, int(_lon(a, code) // 30)
    while t0 < b:
        t1 = min(t0 + 1.0, b)
        s1 = int(_lon(t1, code) // 30)
        if s1 != s0:
            def g(t, _s=s1):
                return -1.0 if int(_lon(t, code) // 30) != _s else 1.0
            ti = _bisect(g, t0, t1)
            when = dt_from_jd(ti)
            out.append(Event(id=event_id(reading_id, "lune_noire", f"in{s1}", when),
                             kind="ln_ingress", body="lune_noire", aspect=None, point=None,
                             weight=WEIGHT["lune_noire"], enter=when, exit=when,
                             exacts=[when], sign_to=s1))
        t0, s0 = t1, s1
    return out


# ---------------------------------------------------------------- sélection (§6)

@dataclass
class Selection:
    mode: str              # "now" | "next"
    event: Event
    ics_exact: datetime    # date portée par le .ics gratuit
    ics_event: Event       # événement porteur de cette date (peut différer en « now »)


def _active(e, now):
    return e.enter <= now and (e.exit is None or now <= e.exit)


def select(events, now=None):
    """En ce moment (corps le plus lent) ; sinon prochaine (entrée minimale, le plus lent)."""
    now = now or datetime.now(UTC)
    active = [e for e in events if _active(e, now)]
    if active:
        def closeness(e):
            return min(abs((x - now).total_seconds()) for x in e.exacts)
        ev = max(active, key=lambda e: (e.weight, -closeness(e)))
        future = [x for x in ev.exacts if x >= now]
        if future:
            return Selection("now", ev, future[0], ev)
        nxt = _next(events, now)
        if nxt is None:
            return Selection("now", ev, ev.exacts[-1], ev)
        return Selection("now", ev, nxt.exacts[0], nxt)
    nxt = _next(events, now)
    if nxt is None:
        return None
    return Selection("next", nxt, nxt.exacts[0], nxt)


def _next(events, now):
    upcoming = [e for e in events if e.enter > now]
    if not upcoming:
        return None
    first_day = min(e.enter for e in upcoming).date()
    same_day = [e for e in upcoming if e.enter.date() == first_day]
    return max(same_day, key=lambda e: (e.weight, -e.enter.timestamp()))


# ---------------------------------------------------------------- nouvelles lunes (§8)

@dataclass
class NewMoon:
    when: datetime
    lon: float
    sign: int
    house: int | None
    nearest_point: str
    distance: float

    @property
    def touches(self):
        """Distance ≤ 3° : « cette nouvelle lune tombe sur ton <point> »."""
        return self.distance <= 3.0


def new_moons(natal_, start, months=12):
    t_start, t_end = _horizon(start, months)
    jd, end = jd_from_dt(t_start), jd_from_dt(t_end)
    out = []
    while True:
        nm = astro.find_lunation(jd, 0.0)
        if nm > end:
            return out
        lon, _ = astro._calc(nm, swe.SUN)
        dist = {p: abs(_wrap180(lon - natal_.cross[p]["lon"])) for p in POINTS}
        p = min(dist, key=dist.get)
        house = astro.house_of(lon, natal_.cusps) if natal_.cusps else None
        out.append(NewMoon(dt_from_jd(nm), lon, int(lon // 30), house, p, dist[p]))
        jd = nm + 1.0


# ---------------------------------------------------------------- libellés (§7)

_ui = None


def ui():
    global _ui
    if _ui is None:
        with open(UI_PATH, encoding="utf-8") as f:
            _ui = json.load(f)
    return _ui


def phrase(e):
    """« Saturne carré ta Lune Noire, sur ton point de soumission »."""
    t = ui()["activation"]
    if e.kind == "ln_ingress":
        return t["ln_ingress"].format(signe=SIGNS_FR[e.sign_to])
    if e.body == "lune_noire" and e.aspect == "conjonction":
        return t["retour"]
    corps = t["corps"][e.body]
    if e.aspect == "carre":
        return t["carre"][e.point].format(corps=corps)
    return t[e.aspect].format(corps=corps)


# ---------------------------------------------------------------- .ics (§9)

MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
        "septembre", "octobre", "novembre", "décembre"]
BASE_URL = "https://malunenoire.fr"


def date_fr(d):
    """date -> « 1er décembre », « 3 décembre »."""
    jour = "1er" if d.day == 1 else str(d.day)
    return f"{jour} {MOIS[d.month - 1]}"


def _esc(s):
    return (s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
            .replace("\r\n", "\\n").replace("\n", "\\n"))


def _fold(line):
    """Plie à 75 octets (RFC 5545 §3.1) sans couper un caractère UTF-8."""
    out, cur, size = [], "", 0
    for ch in line:
        n = len(ch.encode("utf-8"))
        limit = 75 if not out else 74          # la suite commence par une espace
        if size + n > limit:
            out.append(cur)
            cur, size = "", 0
        cur += ch
        size += n
    out.append(cur)
    return "\r\n ".join(out)


def _description(e, exact, tz):
    local = lambda dt: dt.astimezone(tz).date()
    p = phrase(e)
    if p.startswith(("Le ", "Ta ", "Retour ")):        # en milieu de phrase
        p = p[0].lower() + p[1:]
    if e.kind == "ln_ingress":
        return f"{p} le {date_fr(local(exact))}."
    d0 = local(e.enter)
    debut = date_fr(d0)
    if e.exit is None:
        fenetre = f"À partir du {debut}, pendant encore des mois"
    else:
        d1 = local(e.exit)
        if (d0.year, d0.month) == (d1.year, d1.month):
            debut = "1er" if d0.day == 1 else str(d0.day)    # « Du 6 au 9 février »
        fenetre = f"Du {debut} au {date_fr(d1)}"
    return f"{fenetre}, {p}. Exact le {date_fr(local(exact))}."


def _vevent(e, n, exact, token, tz, stamp):
    day = exact.astimezone(tz).date()
    url = f"{BASE_URL}/l/{token}"
    desc = f"{_description(e, exact, tz)}\nRelire ma Lune Noire : {url}"
    return [
        "BEGIN:VEVENT",
        f"UID:{e.id}-{n}@malunenoire.fr",
        f"DTSTAMP:{stamp}",
        f"DTSTART;VALUE=DATE:{day.strftime('%Y%m%d')}",
        f"DTEND;VALUE=DATE:{(day + timedelta(days=1)).strftime('%Y%m%d')}",
        f"SUMMARY:{_esc('Ma Lune Noire — ' + phrase(e))}",
        f"DESCRIPTION:{_esc(desc)}",
        f"URL:{url}",
        "BEGIN:VALARM",
        "ACTION:DISPLAY",
        f"DESCRIPTION:{_esc('Ma Lune Noire — aujourd’hui')}",
        "TRIGGER:PT9H",          # 9 h le jour même (décision du 24/10/2026)
        "END:VALARM",
        "END:VEVENT",
    ]


def _calendar(vevents):
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Ma Lune Noire//malunenoire.fr//FR",
             "CALSCALE:GREGORIAN", "METHOD:PUBLISH", "X-WR-CALNAME:Ma Lune Noire"]
    for v in vevents:
        lines += v
    lines.append("END:VCALENDAR")
    return "".join(_fold(l) + "\r\n" for l in lines)


def ics_next(selection, token, tz_user, now=None):
    """next.ics gratuit : un seul VEVENT, sur la date exacte (§6, §9)."""
    tz = ZoneInfo(tz_user)
    stamp = (now or datetime.now(UTC)).strftime("%Y%m%dT%H%M%SZ")
    e, exact = selection.ics_event, selection.ics_exact
    return _calendar([_vevent(e, e.exacts.index(exact), exact, token, tz, stamp)])


def ics_calendar(events, token, tz_user, start, months=12, now=None):
    """calendrier.ics (payant) : un VEVENT par passage exact dans l'horizon + ingrès."""
    tz = ZoneInfo(tz_user)
    stamp = (now or datetime.now(UTC)).strftime("%Y%m%dT%H%M%SZ")
    t_start, t_end = _horizon(start, months)
    vevents = []
    for e in events:
        for n, x in enumerate(e.exacts):
            if t_start <= x <= t_end:
                vevents.append((x, _vevent(e, n, x, token, tz, stamp)))
    vevents.sort(key=lambda v: v[0])
    return _calendar([v for _, v in vevents])
