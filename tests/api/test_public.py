# -*- coding: utf-8 -*-
"""Page publique /c/<share_id> et images (spec 04 §5, 07 §4)."""

import html
import io

from PIL import Image

from tests.api.conftest import needs_db

pytestmark = needs_db

PARIS = {"name": "Paris, France", "lat": 48.8566, "lon": 2.3522, "tz": "Europe/Paris"}


def creer(client, **s):
    return client.post("/api/reading", json={"date": "2000-01-01", "time": "13:00", "place": PARIS, **s},
                       headers={"x-forwarded-for": "10.4.4.4"}).json()


def test_page_publique(client):
    d = creer(client)
    r = client.get(f"/c/{d['share_id']}?d=verdict")
    assert r.status_code == 200
    page = html.unescape(r.text)
    assert "public" in r.headers["cache-control"] and "stale-while-revalidate" in r.headers["cache-control"]
    # aucune donnée de naissance, pas de token, pas de degré
    for interdit in (d["token"], "2000-01-01", "13:00", "Paris, France", "48.85", "19°", "19 °"):
        assert interdit not in page, interdit
    assert "FAIS LA TIENNE" in page and "<svg" in r.text
    for balise in ("og:title", "og:description", "og:image", "og:image:width", "og:image:height",
                   "og:type", "og:url", "og:site_name", "twitter:card"):
        assert f'"{balise}"' in r.text, balise
    assert 'content="Sagittaire — Maison VIII"' in page
    assert f"/c/{d['share_id']}/og.png?d=verdict" in page
    assert "feedback" not in r.text


def test_page_publique_sans_heure(client):
    d = creer(client, time=None)
    page = html.unescape(client.get(f"/c/{d['share_id']}").text)
    assert 'property="og:title" content="Sagittaire"' in page


def test_share_id_inconnu(client):
    assert client.get("/c/AAAAAAAAAAA").status_code == 404
    assert client.get("/c/court").status_code == 404
    assert client.get("/c/AAAAAAAAAAA/carte.png").status_code == 404


def test_carte_png(client):
    d = creer(client)
    r = client.get(f"/c/{d['share_id']}/carte.png?d=eclipse&v=3")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert 'filename="ma-lune-noire-sagittaire.png"' in r.headers["content-disposition"]
    assert "immutable" in r.headers["cache-control"]
    assert Image.open(io.BytesIO(r.content)).size == (1080, 1920)
    sans_version = client.get(f"/c/{d['share_id']}/carte.png?d=eclipse")
    assert "immutable" not in sans_version.headers["cache-control"]


def test_og_png(client):
    d = creer(client)
    r = client.get(f"/c/{d['share_id']}/og.png?d=verdict&v=3")
    assert r.status_code == 200 and Image.open(io.BytesIO(r.content)).size == (1200, 630)
