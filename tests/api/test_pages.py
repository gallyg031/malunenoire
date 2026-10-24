# -*- coding: utf-8 -*-
"""Pages HTML (spec 01, 05 §3) : en-têtes, textes système, pas de fuite de données."""

import html
import re

from tests.api.conftest import needs_db

PARIS = {"name": "Paris, France", "lat": 48.8566, "lon": 2.3522, "tz": "Europe/Paris"}


def creer(client, **s):
    return client.post("/api/reading", json={"date": "2000-01-01", "time": "13:00", "place": PARIS, **s},
                       headers={"x-forwarded-for": "10.3.3.3"}).json()


def test_entree(client):
    r = client.get("/")
    assert r.status_code == 200 and "public" in r.headers["cache-control"]
    assert "La part de toi que personne ne voit." in r.text
    assert "Lilith" not in r.text and "LILITH" not in r.text
    assert "content-security-policy" in r.headers


def test_aucun_style_ni_script_en_ligne(client):
    """La CSP interdit le style et le script en ligne : aucun gabarit ne doit en contenir."""
    for url in ("/", "/mentions", "/confidentialite", "/nimporte"):
        page = client.get(url).text
        assert not re.search(r"\sstyle=", page), url
        assert not re.search(r"<script(?![^>]*\bsrc=)", page), url


def test_404(client):
    r = client.get("/nimporte")
    assert r.status_code == 404 and "Il n'y a rien ici." in html.unescape(r.text)
    assert client.get("/api/nimporte").json()["ok"] is False


def test_pages_legales(client):
    for url, titre in (("/mentions", "Mentions"), ("/confidentialite", "Confidentialité")):
        r = client.get(url)
        assert r.status_code == 200 and titre in r.text and "public" in r.headers["cache-control"]
    assert "AGPL" in client.get("/mentions").text and "GeoNames" in client.get("/mentions").text


@needs_db
def test_revelation(client):
    d = creer(client)
    r = client.get(f"/l/{d['token']}")
    assert r.status_code == 200
    assert r.headers["cache-control"] == "private, no-store"
    assert r.headers["referrer-policy"] == "no-referrer" and r.headers["x-robots-tag"] == "noindex"
    assert "SAGITTAIRE — MAISON VIII" in r.text
    assert "2000-01-01" not in r.text and "13:00" not in r.text and "48.85" not in r.text
    assert r.text.count("<svg") >= 2                       # cartes du carrousel
    assert "Lilith" not in r.text and "vertige d" not in r.text.lower()


@needs_db
def test_revelation_sans_heure(client):
    d = creer(client, time=None)
    page = html.unescape(client.get(f"/l/{d['token']}").text)
    assert "Lu sans ton heure de naissance." in page and "J'AI RETROUVÉ MON HEURE" in page


@needs_db
def test_token_inconnu_et_efface(client):
    r = client.get("/l/" + "A" * 22)
    assert r.status_code == 404 and "ne mène à aucune Lune Noire" in html.unescape(r.text)
    d = creer(client)
    assert client.get(f"/l/{d['token']}/effacer").status_code == 200
    client.delete(f"/api/reading/{d['token']}")
    assert client.get(f"/l/{d['token']}/sanctuaire").status_code == 404


@needs_db
def test_sanctuaire(client):
    d = creer(client)
    r = client.get(f"/l/{d['token']}/sanctuaire")
    assert r.status_code == 200 and "LA BIBLIOTHÈQUE" in r.text and "15 €" in r.text
    assert r.headers["cache-control"] == "private, no-store"
