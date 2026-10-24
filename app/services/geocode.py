# -*- coding: utf-8 -*-
"""Géocodage (spec 05 §5) : base GeoNames embarquée, repli Nominatim mis en cache."""

import json
import os
import sqlite3
import threading
import time
import unicodedata

import httpx

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GEO_DB = os.path.join(ROOT, "data", "geo.sqlite")
PAYS_PATH = os.path.join(ROOT, "data", "pays.json")

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "MaLuneNoire/1.0 (contact@malunenoire.fr)"
MAX_Q = 80
LIMIT = 5

_local = threading.local()
_pays = None
_nominatim_lock = threading.Lock()
_nominatim_last = 0.0


def normalize(s):
    """Identique à scripts/build_geo.py:normalize."""
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    for ch in "-'’`.":
        s = s.replace(ch, " ")
    return " ".join(s.split())


def _db():
    if getattr(_local, "db", None) is None:
        _local.db = sqlite3.connect(f"file:{GEO_DB}?mode=ro", uri=True, check_same_thread=False)
    return _local.db


def pays():
    global _pays
    if _pays is None:
        with open(PAYS_PATH, encoding="utf-8") as f:
            _pays = json.load(f)
    return _pays


def _result(name, country_code, admin1, lat, lon, tz):
    country = pays().get(country_code, country_code)
    return {"name": name, "country": country, "admin1": admin1 or "",
            "lat": round(lat, 4), "lon": round(lon, 4), "tz": tz,
            "label": f"{name}, {country}"}


def _disambiguate(results):
    """Deux libellés identiques → on intercale la région."""
    seen = {}
    for r in results:
        seen[r["label"]] = seen.get(r["label"], 0) + 1
    for r in results:
        if seen[r["label"]] > 1 and r["admin1"]:
            r["label"] = f"{r['name']}, {r['admin1']}, {r['country']}"
    return results


def search_local(q):
    n = normalize(q)
    if not n:
        return []
    rows = _db().execute(
        """select c.name, c.fr_name, c.country, c.admin1, c.lat, c.lon, c.tz
           from (select distinct city_id from names where norm >= ? and norm < ?) m
           join cities c on c.id = m.city_id
           order by c.pop desc limit ?""",
        (n, n + "￿", LIMIT)).fetchall()
    return _disambiguate([_result(fr_name or name, cc, a1, lat, lon, tz)
                          for name, fr_name, cc, a1, lat, lon, tz in rows])


def search_nominatim(q, client=None):
    """Repli pour les villages : 1 requête/s au plus, fuseau par timezonefinder."""
    global _nominatim_last
    from timezonefinder import TimezoneFinder
    with _nominatim_lock:
        wait = 1.0 - (time.monotonic() - _nominatim_last)
        if wait > 0:
            time.sleep(wait)
        _nominatim_last = time.monotonic()
        params = {"q": q, "format": "jsonv2", "limit": LIMIT, "accept-language": "fr",
                  "addressdetails": 1}
        own = client is None
        client = client or httpx.Client(timeout=5.0)
        try:
            r = client.get(NOMINATIM_URL, params=params, headers={"User-Agent": USER_AGENT})
            r.raise_for_status()
            data = r.json()
        finally:
            if own:
                client.close()
    tf = TimezoneFinder()
    out = []
    for item in data:
        lat, lon = float(item["lat"]), float(item["lon"])
        tz = tf.timezone_at(lat=lat, lng=lon)
        if not tz:
            continue
        addr = item.get("address", {})
        name = item.get("name") or item["display_name"].split(",")[0]
        cc = (addr.get("country_code") or "").upper()
        out.append(_result(name, cc, addr.get("state", ""), lat, lon, tz))
    return _disambiguate(out)


def geocode(q, cache=None, client=None):
    """cache : objet avec get(qn) -> list|None et put(qn, results) (table geocache)."""
    q = (q or "").strip()[:MAX_Q]
    if not q:
        return []
    results = search_local(q)
    if results or len(q) < 4:
        return results
    qn = normalize(q)
    if cache is not None:
        hit = cache.get(qn)
        if hit is not None:
            return hit
    results = search_nominatim(q, client=client)
    if cache is not None:
        cache.put(qn, results)
    return results
