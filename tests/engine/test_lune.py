# -*- coding: utf-8 -*-
"""engine/lune.py — spec 07 §1 (croix et maisons, activations, nouvelles lunes, ICS).

Thème de test public : référence de Paris (époque J2000). Les thèmes privés
(golden_prive.json) sont couverts par test_golden.py.
"""

import random
import re
import statistics
import time as clock
from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace

import pytest
import swisseph as swe
from icalendar import Calendar

import astro
import lune

UTC = timezone.utc
PARIS = (48.8566, 2.3522, "Europe/Paris")
START = date(2026, 12, 16)
T_START = datetime(2026, 12, 16, tzinfo=UTC)


def wrap180(x):
    return (x + 180.0) % 360.0 - 180.0


@pytest.fixture(scope="module")
def ref():
    return lune.natal(date(2000, 1, 1), time(13, 0), *PARIS)


@pytest.fixture(scope="module")
def events(ref):
    return lune.activations(ref, START, months=13, reading_id="test")


def lon_at(body, dt):
    code = dict((b, c) for b, c, _, _ in lune.BODIES)[body]
    return lune._lon(lune.jd_from_dt(dt), code)


# ---------------------------------------------------------------- natal, croix, maisons

def test_natal_reference(ref):
    assert astro.fmt(ref.ln_lon) == "19°10' Sagittaire"
    assert ref.sign_id == "sagittaire" and ref.ln_house == 8
    assert ref.house_reason is None and not ref.no_time and ref.utc_offset_min == 60


def test_croix_proprietes():
    rnd = random.Random(42)
    for _ in range(200):
        d = date(1900, 1, 1) + timedelta(days=rnd.randrange((date(2026, 1, 1) - date(1900, 1, 1)).days))
        n = lune.natal(d, time(rnd.randrange(24), rnd.randrange(60)),
                       rnd.uniform(-60, 60), rnd.uniform(-180, 180), "UTC")
        L = n.ln_lon
        assert abs(wrap180(n.cross["priape"]["lon"] - (L + 180) % 360)) < 1e-9
        assert abs(wrap180(n.cross["affirmation"]["lon"] - (L - 90) % 360)) < 1e-9
        assert abs(wrap180(n.cross["soumission"]["lon"] - (L + 90) % 360)) < 1e-9
        assert 1 <= n.ln_house <= 12
        for p in lune.POINTS:
            assert 1 <= n.cross[p]["house"] <= 12
        # house_of cohérent avec les cuspides : chaque cuspide ouvre sa maison
        for i, c in enumerate(n.cusps):
            assert astro.house_of(c, n.cusps) == i + 1


def test_polaire():
    n = lune.natal(date(1990, 6, 1), time(12, 0), 70.0, 25.0, "Europe/Oslo")
    assert n.ln_house is None and n.house_reason == "polar"
    assert all(n.cross[p]["house"] is None for p in lune.POINTS)


def test_sans_heure():
    n = lune.natal(date(1991, 3, 12), None, 45.76, 4.84, "Europe/Paris")
    assert n.ln_house is None and n.house_reason == "no_time" and n.no_time
    jd, _ = astro.to_jd(1991, 3, 12, 12, 0, "Europe/Paris")
    assert n.jd == jd


def test_changement_de_signe_dans_la_journee():
    # fixture trouvée par balayage (1990-08-15, Paris), figée
    assert lune.natal(date(1990, 8, 15), None, *PARIS).sign_changes_today is True
    assert lune.natal(date(1990, 8, 14), None, *PARIS).sign_changes_today is False


@pytest.mark.parametrize("d", [date(1899, 12, 31), date.today() + timedelta(days=2)])
def test_date_hors_plage(d):
    with pytest.raises(ValueError):
        lune.natal(d, time(12, 0), *PARIS)


# ---------------------------------------------------------------- activations

def test_exacts_et_bornes(events, ref):
    for e in events:
        if e.kind != "transit":
            continue
        target = (ref.ln_lon + 30 * e.k) % 360
        orb = lune.TARGETS[e.k][1]
        assert e.exacts, e
        for x in e.exacts:
            assert abs(wrap180(lon_at(e.body, x) - target)) < 0.02
        assert abs(abs(wrap180(lon_at(e.body, e.enter) - target)) - orb) < 0.02
        if e.exit is not None:
            assert abs(abs(wrap180(lon_at(e.body, e.exit) - target)) - orb) < 0.02


def test_soleil_huit_cibles_par_an(events):
    fin = T_START + timedelta(days=365)
    compte = {}
    for e in events:
        if e.body == "soleil":
            for x in e.exacts:
                if T_START <= x < fin:
                    compte[e.aspect] = compte.get(e.aspect, 0) + 1
    assert compte == {"conjonction": 1, "opposition": 1, "carre": 2, "trigone": 2, "sextile": 2}


def test_mars(events):
    assert 3 <= sum(e.body == "mars" for e in events) <= 10


def test_points_nommes(events):
    for e in events:
        if e.kind != "transit":
            continue
        attendu = {"conjonction": "lune_noire", "opposition": "priape"}.get(e.aspect)
        if e.aspect == "carre":
            assert e.point in ("soumission", "affirmation")
        elif e.aspect in ("trigone", "sextile"):
            assert e.point is None
        else:
            assert e.point == attendu


def test_sans_doublon_et_tri(events):
    cles = [(e.body, e.k, e.enter) for e in events if e.kind == "transit"]
    assert len(cles) == len(set(cles))
    assert [e.enter for e in events] == sorted(e.enter for e in events)
    assert len({e.id for e in events}) == len(events)


def test_evenement_en_cours_a_start():
    # Lune Noire natale placée là où se trouve Saturne au départ : période en cours
    L = lune._lon(lune.jd_from_dt(T_START), swe.SATURN)
    ev = lune.activations(SimpleNamespace(ln_lon=L), START, months=13)
    conj = [e for e in ev if e.body == "saturne" and e.k == 0]
    assert conj and conj[0].enter < T_START and conj[0].exacts


@pytest.mark.parametrize("body,nom", [("jupiter", "Jupiter"), ("saturne", "Saturne"),
                                      ("uranus", "Uranus")])
def test_retrograde_trois_exacts(body, nom):
    # Jupiter et Saturne sortent de l'orbe entre deux passages (boucle plus large
    # que 2 × 3°) : les passages d'une même boucle sont regroupés (décision du 24/10).
    jd0 = lune.jd_from_dt(T_START)
    st = astro.stations(nom, jd0 - 365, jd0 + 365)
    retro = next(s for s in st if s[1] == "rétrograde")
    direct = next(s for s in st if s[1] == "directe" and s[0] > retro[0])
    L = (retro[2] + wrap180(direct[2] - retro[2]) / 2) % 360   # milieu de la boucle
    ev = lune.activations(SimpleNamespace(ln_lon=L), START, months=13)
    conj = [e for e in ev if e.body == body and e.k == 0]
    assert conj and len(conj[0].exacts) == 3


@pytest.mark.parametrize("body,nom", [("jupiter", "Jupiter"), ("saturne", "Saturne")])
def test_reference_croisee_scan_transits(body, nom):
    jd0 = lune.jd_from_dt(T_START)
    L = lune._lon(jd0 + 120, dict((b, c) for b, c, _, _ in lune.BODIES)[body])
    ev = [e for e in lune.activations(SimpleNamespace(ln_lon=L), START, months=13)
          if e.body == body and e.k == 0]
    ref = [c for c in astro.scan_transits(None, jd0 - 10, jd0 + 31 * 13 + 10, planets=[nom],
                                          targets={"LN": L}, orbs={0: 3.0})
           if c["aspect"] == "conjonction"]
    nos = sorted(lune.jd_from_dt(x) for e in ev for x in e.exacts
                 if jd0 - 10 <= lune.jd_from_dt(x) <= jd0 + 31 * 13 + 10)
    leurs = sorted(j for c in ref for j in c["exact_jds"])
    assert nos and len(nos) == len(leurs)
    for a, b in zip(nos, leurs):
        assert abs(a - b) < 2 * lune.MINUTE


def test_ingres_lune_noire_moyenne():
    t0 = T_START
    ing = lune.ln_ingress(t0, t0 + timedelta(days=730))
    assert 2 <= len(ing) <= 3
    for e in ing:
        before = lune._lon(lune.jd_from_dt(e.exacts[0]) - lune.MINUTE, swe.MEAN_APOG)
        after = lune._lon(lune.jd_from_dt(e.exacts[0]) + lune.MINUTE, swe.MEAN_APOG)
        assert int(before // 30) != int(after // 30) == e.sign_to


def test_performance(ref):
    lune.activations(ref, START)            # premier chargement des fichiers
    durees = []
    for _ in range(5):
        t = clock.perf_counter()
        lune.activations(ref, START)
        durees.append(clock.perf_counter() - t)
    assert statistics.median(durees) < 0.300


# ---------------------------------------------------------------- sélection (§6)

def ev(body, enter, exit_, exacts, aspect="conjonction"):
    d = lambda s: datetime.fromisoformat(s).replace(tzinfo=UTC)
    return lune.Event(id=body + enter, kind="transit", body=body, aspect=aspect,
                      point="lune_noire", weight=lune.WEIGHT[body], enter=d(enter),
                      exit=d(exit_) if exit_ else None, exacts=[d(x) for x in exacts], k=0)


NOW = datetime(2027, 3, 1, tzinfo=UTC)


def test_selection_en_ce_moment_le_plus_lent():
    s = lune.select([ev("soleil", "2027-02-27", "2027-03-03", ["2027-03-02"]),
                     ev("saturne", "2027-02-01", "2027-04-01", ["2027-03-10"])], NOW)
    assert s.mode == "now" and s.event.body == "saturne"
    assert s.ics_exact.date() == date(2027, 3, 10)


def test_selection_prochaine_meme_jour():
    s = lune.select([ev("mars", "2027-03-05T03:00", "2027-03-12", ["2027-03-08"]),
                     ev("jupiter", "2027-03-05T20:00", "2027-04-20", ["2027-04-01"]),
                     ev("pluton", "2027-06-01", None, ["2027-09-01"])], NOW)
    assert s.mode == "next" and s.event.body == "jupiter"
    assert s.ics_exact.date() == date(2027, 4, 1)


def test_selection_exact_passe():
    s = lune.select([ev("saturne", "2027-01-01", "2027-05-01",
                        ["2027-01-20", "2027-03-15", "2027-04-10"]),
                     ev("mars", "2027-06-01", "2027-06-09", ["2027-06-05"])], NOW)
    assert s.mode == "now" and s.ics_exact.date() == date(2027, 3, 15)
    s = lune.select([ev("saturne", "2027-01-01", "2027-05-01", ["2027-01-20"]),
                     ev("mars", "2027-06-01", "2027-06-09", ["2027-06-05"])], NOW)
    assert s.ics_event.body == "mars" and s.ics_exact.date() == date(2027, 6, 5)


# ---------------------------------------------------------------- nouvelles lunes (§8)

def test_nouvelles_lunes(ref):
    nms = lune.new_moons(ref, START, months=12)
    assert 12 <= len(nms) <= 14
    for nm in nms:
        assert astro.lunation_phase(lune.jd_from_dt(nm.when)) < 0.01 or \
            astro.lunation_phase(lune.jd_from_dt(nm.when)) > 359.99
        assert nm.sign == int(nm.lon // 30) and 1 <= nm.house <= 12
        assert nm.nearest_point in lune.POINTS and 0 <= nm.distance <= 45


# ---------------------------------------------------------------- .ics (§9)

TOKEN = "AbCdEfGhIjKlMnOpQrStUv"


def _check_format(raw):
    assert raw.endswith("\r\n") and "\n" not in raw.replace("\r\n", "")
    for line in raw.split("\r\n"):
        assert len(line.encode("utf-8")) <= 75


def test_ics_next(events):
    s = lune.select(events, T_START)
    raw = lune.ics_next(s, TOKEN, "Europe/Paris", now=T_START)
    _check_format(raw)
    cal = Calendar.from_ical(raw)
    vevents = cal.walk("VEVENT")
    assert len(vevents) == 1
    v = vevents[0]
    assert v["DTSTART"].params["VALUE"] == "DATE"
    assert v.decoded("DTSTART") == s.ics_exact.astimezone(lune.ZoneInfo("Europe/Paris")).date()
    assert str(v["URL"]) == f"https://malunenoire.fr/l/{TOKEN}"
    assert "\\," in raw                    # virgule échappée dans DESCRIPTION
    assert len(v.walk("VALARM")) == 1


def test_ics_calendrier(events):
    raw = lune.ics_calendar(events, TOKEN, "Europe/Paris", START, months=12, now=T_START)
    _check_format(raw)
    vevents = Calendar.from_ical(raw).walk("VEVENT")
    fin = T_START + timedelta(days=31 * 12)
    attendus = sum(T_START <= x <= fin for e in events for x in e.exacts)
    assert len(vevents) == attendus
    assert len({str(v["UID"]) for v in vevents}) == len(vevents)
    assert any("entre en" in str(v["SUMMARY"]) for v in vevents)      # ingrès inclus


def test_date_fr_annee():
    assert lune.date_fr(date(2027, 7, 1)) == "1er juillet"
    assert lune.date_fr(date(2027, 7, 11), date(2027, 1, 5)) == "11 juillet"
    assert lune.date_fr(date(2027, 7, 11), date(2026, 10, 24)) == "11 juillet 2027"


def test_ics_pliage_utf8():
    ligne = "DESCRIPTION:" + "é" * 100
    plie = lune._fold(ligne)
    for part in plie.split("\r\n"):
        assert len(part.encode("utf-8")) <= 75
    assert plie.replace("\r\n ", "") == ligne


def test_phrases():
    e = ev("saturne", "2027-01-01", "2027-02-01", ["2027-01-15"], aspect="carre")
    e.point = "soumission"
    assert lune.phrase(e) == "Saturne carré ta Lune Noire, sur ton point de soumission"
    e = ev("soleil", "2027-01-01", "2027-02-01", ["2027-01-15"])
    assert lune.phrase(e) == "Le Soleil sur ta Lune Noire"
    assert lune.phrase(ev("lune_noire", "2027-01-01", "2027-02-01", ["2027-01-15"])) \
        == "Retour de ta Lune Noire"
    assert not re.search(r"lilith", lune.phrase(e), re.I)
