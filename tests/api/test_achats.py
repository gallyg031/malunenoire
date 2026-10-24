# -*- coding: utf-8 -*-
"""Phase 1.5 : Stripe Checkout (simulé), webhook, calendrier et lecture complète."""

import html

import pytest
import stripe
from icalendar import Calendar

from app import config
from tests.api.conftest import needs_db

pytestmark = needs_db
PARIS = {"name": "Paris, France", "lat": 48.8566, "lon": 2.3522, "tz": "Europe/Paris"}


def creer(client, email=True):
    d = client.post("/api/reading", json={"date": "2000-01-01", "time": "13:00", "place": PARIS},
                    headers={"x-forwarded-for": "10.8.8.8"}).json()
    if email:
        client.post(f"/api/reading/{d['token']}/email", json={"email": "a@exemple.fr"})
    return d


@pytest.fixture
def paiement(monkeypatch):
    monkeypatch.setattr(config, "PAIEMENT_ACTIF", True)
    monkeypatch.setattr(config, "STRIPE_SECRET_KEY", "sk_test_x")
    sessions = []

    def create(**k):
        sid = f"cs_test_{len(sessions)}"
        sessions.append((sid, k))
        return {"id": sid, "url": f"https://checkout.stripe.com/c/pay/{sid}"}
    monkeypatch.setattr(stripe.checkout.Session, "create", staticmethod(create))
    return sessions


def payer(client, monkeypatch, sid):
    evt = {"type": "checkout.session.completed", "data": {"object": {"id": sid, "payment_status": "paid"}}}
    monkeypatch.setattr(stripe.Webhook, "construct_event", staticmethod(lambda *a, **k: evt))
    return client.post("/api/stripe/webhook", content=b"{}", headers={"stripe-signature": "t=1,v1=x"})


def test_paiement_ferme_par_defaut(client):
    d = creer(client)
    r = client.post("/api/checkout", json={"token": d["token"], "product": "lecture"})
    assert r.status_code == 503 and r.json()["error"] == "paiement_indisponible"
    page = client.get(f"/l/{d['token']}").text
    assert "ouvre-bientot" in page and 'class="bouton bouton-laiton achat"' not in page


def test_checkout(client, sql, paiement):
    d = creer(client)
    r = client.post("/api/checkout", json={"token": d["token"], "product": "calendrier"})
    assert r.status_code == 200 and r.json()["url"].startswith("https://checkout.stripe.com/")
    _, k = paiement[0]
    assert k["mode"] == "payment" and k["line_items"][0]["price_data"]["unit_amount"] == 500
    assert k["success_url"].endswith(f"/l/{d['token']}?achat=ok") and k["metadata"]["product"] == "calendrier"
    assert sql("select product, status, amount_cents from purchases") == [("calendrier", "pending", 500)]
    assert client.post("/api/checkout", json={"token": d["token"], "product": "pack"}).status_code == 400
    assert 'class="bouton bouton-laiton achat"' in client.get(f"/l/{d['token']}").text


def test_webhook_signature_invalide(client):
    r = client.post("/api/stripe/webhook", content=b"{}", headers={"stripe-signature": "faux"})
    assert r.status_code == 400


def test_achat_calendrier(client, sql, paiement, monkeypatch):
    d = creer(client)
    client.post("/api/checkout", json={"token": d["token"], "product": "calendrier"})
    assert client.get(f"/l/{d['token']}/calendrier").status_code == 403          # pas encore payé
    assert payer(client, monkeypatch, "cs_test_0").json() == {"ok": True}
    assert sql("select status, snapshot is not null from purchases") == [("paid", True)]
    assert ("purchase", None) in sql("select kind, sent_at from email_queue")
    payer(client, monkeypatch, "cs_test_0")                                       # rejoué : idempotent
    assert sql("select count(*) from email_queue where kind = 'purchase'") == [(1,)]

    ics = client.get(f"/api/reading/{d['token']}/calendrier.ics")
    assert ics.status_code == 200 and len(Calendar.from_ical(ics.content).walk("VEVENT")) >= 8
    page = html.unescape(client.get(f"/l/{d['token']}/calendrier").text)
    assert "Tes douze prochains mois" in page and "sur ta Lune Noire" in page
    assert client.get(f"/l/{d['token']}/lecture").status_code == 403
    rev = html.unescape(client.get(f"/l/{d['token']}").text)
    assert "VOIR MON CALENDRIER" in rev and "LIRE MA LECTURE" not in rev


def test_achat_bundle(client, paiement, monkeypatch):
    d = creer(client, email=False)
    client.post("/api/checkout", json={"token": d["token"], "product": "bundle"})
    payer(client, monkeypatch, "cs_test_0")
    lecture = html.unescape(client.get(f"/l/{d['token']}/lecture").text)
    assert "19°10' Sagittaire" in lecture                       # degrés exacts : lecture complète seulement
    assert "en cours d'écriture" in lecture                      # le corpus « complet » n'existe pas encore
    assert client.get(f"/l/{d['token']}/calendrier").status_code == 200


def test_paiement_non_confirme(client, sql, paiement, monkeypatch):
    d = creer(client)
    client.post("/api/checkout", json={"token": d["token"], "product": "lecture"})
    evt = {"type": "checkout.session.completed", "data": {"object": {"id": "cs_test_0", "payment_status": "unpaid"}}}
    monkeypatch.setattr(stripe.Webhook, "construct_event", staticmethod(lambda *a, **k: evt))
    client.post("/api/stripe/webhook", content=b"{}", headers={"stripe-signature": "x"})
    assert sql("select status from purchases") == [("pending",)]
