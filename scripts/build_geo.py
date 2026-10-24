# -*- coding: utf-8 -*-
"""
build_geo.py — construit data/geo.sqlite et data/pays.json depuis GeoNames (CC BY 4.0).

Sources (data/geonames/, téléchargées si absentes) :
  cities5000.zip, alternateNamesV2.zip (filtré sur 'fr'), countryInfo.txt, admin1CodesASCII.txt

Tables :
  cities(id, name, ascii, fr_name, fr_names, country, admin1, lat, lon, tz, pop)
  names(norm, city_id)   -- une ligne par nom normalisé (local, ascii, exonymes fr) ;
                         -- index B-tree : la recherche par préfixe est un range scan.

Usage : python scripts/build_geo.py
"""

import csv
import io
import json
import os
import sqlite3
import sys
import unicodedata
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "data", "geonames")
OUT_DB = os.path.join(ROOT, "data", "geo.sqlite")
OUT_PAYS = os.path.join(ROOT, "data", "pays.json")
BASE_URL = "https://download.geonames.org/export/dump/"
FILES = ["cities5000.zip", "alternateNamesV2.zip", "countryInfo.txt", "admin1CodesASCII.txt"]

csv.field_size_limit(sys.maxsize if sys.maxsize < 2**31 else 2**31 - 1)


def normalize(s):
    """Minuscules, sans accents, tirets et apostrophes → espace."""
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    for ch in "-'’`.":
        s = s.replace(ch, " ")
    return " ".join(s.split())


def fetch_sources():
    os.makedirs(SRC, exist_ok=True)
    for f in FILES:
        path = os.path.join(SRC, f)
        if not os.path.exists(path):
            print("téléchargement", f)
            urllib.request.urlretrieve(BASE_URL + f, path)


def read_tsv_lines(lines):
    for line in lines:
        if line.startswith("#") or not line.strip():
            continue
        yield line.rstrip("\n").split("\t")


def load_cities():
    cities = {}
    with zipfile.ZipFile(os.path.join(SRC, "cities5000.zip")) as z:
        with z.open("cities5000.txt") as f:
            for r in read_tsv_lines(io.TextIOWrapper(f, encoding="utf-8")):
                gid = int(r[0])
                cities[gid] = {
                    "id": gid, "name": r[1], "ascii": r[2],
                    "lat": float(r[4]), "lon": float(r[5]),
                    "country": r[8], "admin1_code": r[10],
                    "pop": int(r[14] or 0), "tz": r[17],
                }
    return cities


def load_countries():
    countries = {}
    with open(os.path.join(SRC, "countryInfo.txt"), encoding="utf-8") as f:
        for r in read_tsv_lines(f):
            countries[r[0]] = {"name": r[4], "gid": int(r[16]) if r[16] else None}
    return countries


def load_admin1():
    admin1 = {}
    with open(os.path.join(SRC, "admin1CodesASCII.txt"), encoding="utf-8") as f:
        for r in read_tsv_lines(f):
            admin1[r[0]] = {"name": r[1], "gid": int(r[3])}
    return admin1


def load_fr_names(wanted):
    """{geonameid: [(rang, nom)]} pour isolanguage == 'fr', hors historiques/familiers."""
    out = {}
    with zipfile.ZipFile(os.path.join(SRC, "alternateNamesV2.zip")) as z:
        with z.open("alternateNamesV2.txt") as f:
            for line in io.TextIOWrapper(f, encoding="utf-8"):
                r = line.rstrip("\n").split("\t")
                if r[2] != "fr":
                    continue
                gid = int(r[1])
                if gid not in wanted:
                    continue
                preferred, short, colloquial, historic = (r[4] == "1", r[5] == "1",
                                                          r[6] == "1", r[7] == "1")
                if colloquial or historic:
                    continue
                rank = 0 if preferred else (1 if short else 2)
                out.setdefault(gid, []).append((rank, r[3]))
    for gid in out:
        out[gid].sort()
    return out


def best(fr, gid, default):
    names = fr.get(gid)
    return names[0][1] if names else default


def build():
    fetch_sources()
    cities = load_cities()
    countries = load_countries()
    admin1 = load_admin1()
    wanted = set(cities) | {c["gid"] for c in countries.values() if c["gid"]} \
        | {a["gid"] for a in admin1.values()}
    fr = load_fr_names(wanted)

    pays = {code: best(fr, c["gid"], c["name"]) for code, c in countries.items()}
    with open(OUT_PAYS, "w", encoding="utf-8") as f:
        json.dump(pays, f, ensure_ascii=False, indent=1, sort_keys=True)

    if os.path.exists(OUT_DB):
        os.remove(OUT_DB)
    db = sqlite3.connect(OUT_DB)
    db.executescript("""
        create table cities (id integer primary key, name text, ascii text, fr_name text,
            fr_names text, country text, admin1 text, lat real, lon real, tz text, pop integer);
        create table names (norm text not null, city_id integer not null,
            primary key (norm, city_id)) without rowid;
    """)
    rows, names = [], set()
    for gid, c in cities.items():
        fr_list = [n for _, n in fr.get(gid, [])]
        fr_name = fr_list[0] if fr_list else None
        a1 = admin1.get(f"{c['country']}.{c['admin1_code']}")
        a1_name = best(fr, a1["gid"], a1["name"]) if a1 else ""
        rows.append((gid, c["name"], c["ascii"], fr_name, "|".join(fr_list), c["country"],
                     a1_name, c["lat"], c["lon"], c["tz"], c["pop"]))
        for n in [c["name"], c["ascii"], *fr_list]:
            nn = normalize(n)
            if nn:
                names.add((nn, gid))
    db.executemany("insert into cities values (?,?,?,?,?,?,?,?,?,?,?)", rows)
    db.executemany("insert into names values (?,?)", sorted(names))
    db.commit()
    db.execute("vacuum")
    db.close()
    print(f"geo.sqlite : {len(rows)} villes, {len(names)} noms ; pays.json : {len(pays)} pays")


if __name__ == "__main__":
    build()
