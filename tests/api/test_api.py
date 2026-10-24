# -*- coding: utf-8 -*-
"""API (spec 07 §3)."""

import json
import logging

import pytest
from icalendar import Calendar

from tests.api.conftest import needs_db

pytestmark = needs_db

PARIS = {"name": "Paris, France", "lat": 48.8566, "lon": 2.3522, "tz": "Europe/Paris"}
VALIDE = {"date": "2000-01-01", "time": "13:00", "place": PARIS, "tz_user": "Europe/Paris"}


def creer(client, ip="10.0.0.1", **surcharges):
    return client.post("/api/reading", json={**VALIDE, **surcharges},
                       headers={"x-forwarded-for": ip})


def cles(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from cles(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from cles(v)


# ---------------------------------------------------------------- création

def test_creation(client, sql):
    r = creer(client)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ok"] and len(d["token"]) == 22 and len(d["share_id"]) == 11
    assert d["sign"] == "sagittaire" and d["sign_label"] == "Sagittaire"
    assert 0 <= d["deg"] <= 29 and (d["deg"], d["min"]) == (19, 10)
    assert d["house"] == 8 and d["house_roman"] == "VIII" and d["house_reason"] is None
    (n,), = sql("select count(*) from activations a join readings r on r.id = a.reading_id "
                "where r.token = %s", d["token"])
    assert n >= 8
    assert sql("select count(*) from events where name = 'reading_created'") == [(1,)]
    assert r.headers["cache-control"] == "private, no-store"


def test_creation_sans_heure(client):
    d = creer(client, time=None).json()
    assert d["house"] is None and d["house_reason"] == "no_time"


@pytest.mark.parametrize("surcharges,message", [
    ({"date": "1991-02-30"}, "date"),
    ({"date": "1899-12-31"}, "date"),
    ({"time": "25:00"}, "heure"),
    ({"place": {**PARIS, "tz": "Europe/Atlantide"}}, "fuseau"),
    ({"place": {**PARIS, "lat": 95}}, "lieu"),
])
def test_validation(client, surcharges, message):
    r = creer(client, **surcharges)
    assert r.status_code == 400
    d = r.json()
    assert d["ok"] is False and d["error"] == "validation"
    from lune import ui
    assert d["message"] == ui()["erreurs"][message]


def test_limite_creation(client, sql):
    from app.services import readings as rd
    sql("""insert into ratelimit (key, bucket, count)
           values (%s, to_timestamp(floor(extract(epoch from now()) / 3600) * 3600), 30)""",
        rd.hash_key("creation", "10.9.9.9"))
    assert creer(client, ip="10.9.9.9").status_code == 429
    assert creer(client, ip="10.9.9.8").status_code == 200


# ---------------------------------------------------------------- lecture

def test_lecture(client):
    token = creer(client).json()["token"]
    r = client.get(f"/api/reading/{token}")
    assert r.status_code == 200
    d = r.json()
    assert d["text"]["id"] == "sagittaire-08" and d["text"]["version"] == 3
    assert d["text"]["statut"] == "publie" and d["text"]["repli"] is False
    assert set(d["cross"]) == {"lune_noire", "priape", "affirmation", "soumission"}
    assert d["cross"]["priape"]["sign"] == "gemeaux"
    assert not ({"lon", "ln_lon", "deg", "min"} & set(cles(d)))      # pas de longitude en V1
    assert (d["activation_now"] or d["activation_next"])["phrase"]
    assert "token" not in d and "birth_date" not in json.dumps(d)
    assert r.headers["referrer-policy"] == "no-referrer"
    assert r.headers["x-robots-tag"] == "noindex"


def test_lecture_repli_hors_corpus(client):
    token = creer(client, date="1991-03-12", time="04:37").json()["token"]
    d = client.get(f"/api/reading/{token}").json()
    assert d["text"]["repli"] is True


def test_token_inconnu_ou_tronque(client):
    token = creer(client).json()["token"]
    assert client.get("/api/reading/" + "A" * 22).status_code == 404
    assert client.get(f"/api/reading/{token[:-1]}").status_code == 404


# ---------------------------------------------------------------- modifications

def test_patch_heure(client, sql):
    d = creer(client, time=None).json()
    (text_avant, lon_avant), = sql("select text_id, ln_lon from readings where token = %s", d["token"])
    assert text_avant == "sagittaire-00"
    (t0,), = sql("select max(a.created_at) from activations a join readings r "
                 "on r.id = a.reading_id where r.token = %s", d["token"])
    r = client.patch(f"/api/reading/{d['token']}", json={"time": "13:00"})
    assert r.status_code == 200
    e = r.json()
    assert e["token"] == d["token"] and e["share_id"] == d["share_id"]
    assert e["house"] == 8 and e["house_reason"] is None
    (text_id, lon, heure), = sql("select text_id, ln_lon, birth_time::text from readings "
                                 "where token = %s", d["token"])
    assert text_id == "sagittaire-08" and heure == "13:00:00" and lon != lon_avant
    (n, t1), = sql("select count(*), min(a.created_at) from activations a join readings r "
                   "on r.id = a.reading_id where r.token = %s", d["token"])
    assert n >= 8 and t1 > t0                       # activations recalculées


def test_patch_design(client, sql):
    token = creer(client).json()["token"]
    assert client.patch(f"/api/reading/{token}", json={"design": "verdict"}).status_code == 200
    assert sql("select design from readings where token = %s", token) == [("verdict",)]
    assert client.patch(f"/api/reading/{token}", json={"design": "rose"}).status_code == 400


def test_effacement(client, sql):
    token = creer(client).json()["token"]
    client.post(f"/api/reading/{token}/email", json={"email": "a@exemple.fr"})
    assert client.delete(f"/api/reading/{token}").json() == {"ok": True}
    assert client.get(f"/api/reading/{token}").status_code == 404
    assert sql("select count(*) from readings") == [(0,)]
    assert sql("select count(*) from activations") == [(0,)]
    assert sql("select count(*) from email_queue") == [(0,)]


# ---------------------------------------------------------------- calendrier

def test_next_ics(client):
    token = creer(client).json()["token"]
    r = client.get(f"/api/reading/{token}/next.ics")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/calendar")
    assert 'filename="ma-lune-noire.ics"' in r.headers["content-disposition"]
    assert len(Calendar.from_ical(r.content).walk("VEVENT")) == 1


def test_calendrier_non_achete(client):
    token = creer(client).json()["token"]
    r = client.get(f"/api/reading/{token}/calendrier.ics")
    assert r.status_code == 403 and r.json()["error"] == "not_purchased"


# ---------------------------------------------------------------- e-mail

def test_email(client, sql):
    token = creer(client).json()["token"]
    r = client.post(f"/api/reading/{token}/email", json={"email": "  Constance@Exemple.FR "})
    assert r.json() == {"ok": True, "email": "c•••@exemple.fr"}
    assert sql("select email, email_consent_at is not null from readings") == [("constance@exemple.fr", True)]
    assert sql("select kind, sent_at from email_queue") == [("link", None)]
    assert client.get(f"/api/reading/{token}").json()["email"] == "c•••@exemple.fr"
    assert client.post(f"/api/reading/{token}/email", json={"email": "pas-un-email"}).status_code == 400
    assert client.delete(f"/api/reading/{token}/email").json()["ok"]
    assert sql("select email_unsub_at is not null from readings") == [(True,)]
    assert sql("select count(*) from email_queue where sent_at is null") == [(0,)]
    assert client.get(f"/api/reading/{token}").json()["email"] is None


# ---------------------------------------------------------------- feedback, mesure

FB = {"text_id": "sagittaire-08", "text_version": 3, "part": "phrase", "vote": 1, "no_time": False}


def test_feedback(client, monkeypatch, sql):
    h = {"x-forwarded-for": "10.1.1.1", "user-agent": "test"}
    assert client.post("/api/feedback", json=FB, headers=h).json() == {"ok": True}
    assert client.post("/api/feedback", json=FB, headers=h).json() == {"ok": True, "duplicate": True}
    import app.api.routes as routes
    from datetime import datetime as vrai, timedelta

    class Demain(vrai):
        @classmethod
        def now(cls, tz=None):
            return vrai.now(tz) + timedelta(days=1)
    monkeypatch.setattr(routes, "datetime", Demain)
    assert client.post("/api/feedback", json=FB, headers=h).json() == {"ok": True}
    assert sql("select count(*) from feedback") == [(2,)]
    assert client.post("/api/feedback", json={**FB, "part": "titre"}, headers=h).status_code == 400
    assert client.post("/api/feedback", json={**FB, "vote": 2}, headers=h).status_code == 400


def test_event(client, sql):
    r = client.post("/api/event", json={"name": "share_click", "props": {"design": "verdict", "email": "x"}})
    assert r.status_code == 204
    assert sql("select props from events where name = 'share_click'") == [({"design": "verdict"},)]
    assert client.post("/api/event", json={"name": "inconnu"}).status_code == 400


# ---------------------------------------------------------------- santé, journaux

def test_health_corpus_casse(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    import app.main as main
    from app.services import corpus
    (tmp_path / "lion-05.json").write_text("{cassé", encoding="utf-8")
    monkeypatch.setattr(corpus, "CORPUS_DIR", str(tmp_path))
    with TestClient(main.app) as c:
        r = c.get("/health")
        assert r.status_code == 500 and r.json()["corpus"] is False
        assert creer(c).status_code == 500


def test_tokens_masques_dans_les_journaux():
    from app.main import MasqueTokens
    rec = logging.LogRecord("uvicorn.access", logging.INFO, "", 0, '%s - "%s %s"', (
        "1.2.3.4", "GET", "/api/reading/AbCdEfGhIjKlMnOpQrStUv/next.ics"), None)
    MasqueTokens().filter(rec)
    assert "AbCdEf" not in rec.getMessage() and "/api/reading/•/next.ics" in rec.getMessage()
