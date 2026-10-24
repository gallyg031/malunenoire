# -*- coding: utf-8 -*-
"""Socle phase 0 : /healthz, migrations, géocodage (spec 07 §3)."""

import os

import pytest
from fastapi.testclient import TestClient

from app.services import geocode as geo

TEST_DB = os.environ.get("TEST_DATABASE_URL")


@pytest.fixture
def client(monkeypatch):
    import app.main as main
    monkeypatch.setattr(main, "DATABASE_URL", TEST_DB)
    monkeypatch.setitem(main.state, "db", TEST_DB is not None)
    with TestClient(main.app) as c:
        yield c


@pytest.mark.parametrize("path", ["/healthz", "/health"])
def test_healthz(client, path):
    r = client.get(path)
    assert r.status_code == 200
    assert r.json()["golden"] is True


def test_geocode_lyon(client):
    r = client.get("/api/geocode", params={"q": "lyo"})
    assert r.status_code == 200
    assert r.json()[0]["label"] == "Lyon, France"
    assert r.json()[0]["tz"] == "Europe/Paris"
    assert "public" in r.headers["cache-control"]


def test_geocode_exonyme(client):
    r = client.get("/api/geocode", params={"q": "lisb"})
    assert r.json()[0]["label"] == "Lisbonne, Portugal"


def test_geocode_court_sans_nominatim(client, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("Nominatim appelé")
    monkeypatch.setattr(geo, "search_nominatim", boom)
    assert client.get("/api/geocode", params={"q": "zzz"}).json() == []


def test_geocode_longueur(client):
    assert client.get("/api/geocode", params={"q": "x" * 81}).status_code == 422


def test_nominatim_repli_et_cache(monkeypatch):
    calls = []

    def fake(q, client=None):
        calls.append(q)
        return [{"name": "Saint-Martin-de-la-Brasque", "country": "France", "admin1": "",
                 "lat": 43.77, "lon": 5.53, "tz": "Europe/Paris",
                 "label": "Saint-Martin-de-la-Brasque, France"}]

    class Cache(dict):
        def put(self, q, r):
            self[q] = r

    monkeypatch.setattr(geo, "search_local", lambda q: [])
    monkeypatch.setattr(geo, "search_nominatim", fake)
    cache = Cache()
    r1 = geo.geocode("saint-martin-de-la-brasque", cache=cache)
    r2 = geo.geocode("saint-martin-de-la-brasque", cache=cache)
    assert r1 == r2 and len(calls) == 1
    assert "saint martin de la brasque" in cache


@pytest.mark.skipif(not TEST_DB, reason="TEST_DATABASE_URL absent")
def test_migrations_idempotentes(client):
    from db.migrate import migrate
    assert migrate(TEST_DB) == []          # déjà appliquées au démarrage
    import psycopg
    with psycopg.connect(TEST_DB) as conn:
        tables = {r[0] for r in conn.execute(
            "select tablename from pg_tables where schemaname = 'public'")}
    assert {"readings", "activations", "feedback", "events", "email_queue",
            "purchases", "geocache", "schema_migrations"} <= tables
    assert client.get("/healthz").json()["db"] is True
