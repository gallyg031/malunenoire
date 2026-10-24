# -*- coding: utf-8 -*-
"""E-mails, file d'envoi, crons, désinscription (spec 06 §5-6, 07 §3)."""

from datetime import datetime, timedelta, timezone

import pytest

from app import config
from app.services import emails
from tests.api.conftest import needs_db

pytestmark = needs_db
UTC = timezone.utc
PARIS = {"name": "Paris, France", "lat": 48.8566, "lon": 2.3522, "tz": "Europe/Paris"}
SECRET = {"x-cron-secret": "cron-local"}


def inscrit(client, email="a@exemple.fr", ip="10.5.5.5"):
    d = client.post("/api/reading", json={"date": "2000-01-01", "time": "13:00", "place": PARIS},
                    headers={"x-forwarded-for": ip}).json()
    client.post(f"/api/reading/{d['token']}/email", json={"email": email})
    return d


def rid(sql, token):
    return sql("select id from readings where token = %s", token)[0][0]


# ---------------------------------------------------------------- crons : accès

@pytest.mark.parametrize("chemin", ["/cron/emails", "/cron/refresh", "/cron/purge"])
def test_cron_sans_secret(client, chemin):
    assert client.get(chemin).status_code == 403
    assert client.get(chemin, headers={"x-cron-secret": "faux"}).status_code == 403


# ---------------------------------------------------------------- file d'envoi

def test_plafond_et_priorite(client, sql, monkeypatch):
    d = inscrit(client)
    r = rid(sql, d["token"])
    sql("delete from email_queue")
    passe = datetime.now(UTC) - timedelta(hours=1)
    for kind, n in (("new_moon", 50), ("activation", 50), ("link", 20)):
        for i in range(n):
            sql("insert into email_queue (reading_id, kind, ref, send_after) values (%s,%s,%s,%s)",
                r, kind, f"{kind}-{i}", passe - timedelta(minutes=i))
    monkeypatch.setattr(emails, "contenu", lambda conn, it, row: ("sujet", ["paragraphe"]))
    bilan = client.get("/cron/emails", headers=SECRET).json()
    assert bilan["envoyes"] == 90 and bilan["eligibles"] == 120
    envoyes = dict(sql("select kind, count(*) from email_queue where sent_at is not null group by kind"))
    assert envoyes == {"link": 20, "activation": 50, "new_moon": 20}
    # les nouvelles lunes envoyées sont les plus anciennes
    (plus_recente_envoyee,), = sql("select max(send_after) from email_queue where kind='new_moon' and sent_at is not null")
    (plus_ancienne_restante,), = sql("select min(send_after) from email_queue where kind='new_moon' and sent_at is null")
    assert plus_recente_envoyee <= plus_ancienne_restante


def test_echec_fournisseur(client, sql, monkeypatch):
    inscrit(client)
    def panne(*a, **k):
        raise emails.EnvoiImpossible("Resend 503")
    monkeypatch.setattr(emails, "envoyer", panne)
    bilan = client.get("/cron/emails", headers=SECRET).json()
    assert bilan["echecs"] >= 1 and bilan["envoyes"] == 0
    assert sql("select attempts, last_error from email_queue where kind = 'link'") == [(1, "Resend 503")]


def test_jamais_apres_desinscription(client, sql, monkeypatch):
    d = inscrit(client)
    envoyes = []
    monkeypatch.setattr(emails, "envoyer", lambda *a, **k: envoyes.append(a))
    client.delete(f"/api/reading/{d['token']}/email")
    r = rid(sql, d["token"])                      # une ligne revenue en file malgré tout
    sql("insert into email_queue (reading_id, kind, ref, send_after) values (%s,'link','x', now())", r)
    client.get("/cron/emails", headers=SECRET)
    assert envoyes == [] and sql("select count(*) from email_queue where sent_at is null") == [(0,)]


def test_envoi_reel_du_lien(client, sql, monkeypatch):
    d = inscrit(client, email="c@exemple.fr")
    envoyes = []
    monkeypatch.setattr(emails, "envoyer", lambda a, sujet, texte, html, des: envoyes.append((a, sujet, texte, html, des)))
    client.get("/cron/emails", headers=SECRET)
    a, sujet, texte, html, des = next(e for e in envoyes if e[1] == "Ton lien")
    assert a == "c@exemple.fr"
    assert f"/l/{d['token']}" in texte and f"/l/{d['token']}" in html
    assert "/desinscription/" in texte and des in html
    assert sql("select sent_at is not null from email_queue where kind = 'link'") == [(True,)]


def test_destinataire_preprod(monkeypatch):
    monkeypatch.setattr(config, "ENV", "preprod")
    monkeypatch.setattr(config, "EMAIL_REDIRECT", "constance@exemple.fr")
    assert emails.destinataire("visiteur@exemple.fr") == "constance@exemple.fr"


# ---------------------------------------------------------------- planification et contenu

def test_planification(client, sql):
    d = inscrit(client)
    r = rid(sql, d["token"])
    lignes = sql("select kind, ref, send_after from email_queue where reading_id = %s and kind = 'activation'", r)
    for _, ref, send_after in lignes:
        event_id, _, n = ref.rpartition("-")
        (exacts,), = sql("select exacts from activations where id = %s", event_id)
        assert abs((exacts[int(n)] - timedelta(days=3)) - send_after) < timedelta(seconds=2) \
            or send_after <= datetime.now(UTC) + timedelta(seconds=5)
    avant = sql("select count(*) from email_queue")
    from app.services import readings as rd
    import app.main as main
    with main.db.pool.connection() as conn:
        emails.planifier(conn, rd.trouver(conn, d["token"]))
    assert sql("select count(*) from email_queue") == avant            # idempotent


def test_contenu_activation(client, sql):
    d = inscrit(client)
    r = rid(sql, d["token"])
    (eid, exacts), = sql("select id, exacts from activations where reading_id = %s and kind = 'transit' limit 1", r)
    import app.main as main
    from app.services import readings as rd
    with main.db.pool.connection() as conn:
        row = rd.trouver(conn, d["token"])
        sujet, corps = emails.contenu(conn, {"kind": "activation", "ref": f"{eid}-0"}, row)
        assert sujet.startswith("Le ") and "Lune Noire" in sujet
        assert "Exact le" in corps[0]
        assert emails.contenu(conn, {"kind": "activation", "ref": "inconnu-0"}, row) is None
        nm = emails.contenu(conn, {"kind": "new_moon", "ref": (datetime.now(UTC) + timedelta(days=1)).date().isoformat()}, row)
        assert nm is None or nm[0].startswith("Nouvelle lune en ")


# ---------------------------------------------------------------- désinscription

def test_desinscription(client, sql):
    d = inscrit(client)
    r = rid(sql, d["token"])
    cle = emails.cle_desinscription(r)
    page = client.get(f"/desinscription/{cle}")
    assert page.status_code == 200 and 'method="post"' in page.text
    assert sql("select email_unsub_at from readings where id = %s", r) == [(None,)]   # GET ne fait rien
    fait = client.post(f"/desinscription/{cle}")
    assert fait.status_code == 200 and "Ton lien reste valable" in fait.text.replace("&#39;", "'")
    assert sql("select email_unsub_at is not null from readings where id = %s", r) == [(True,)]
    assert sql("select count(*) from email_queue where sent_at is null") == [(0,)]
    assert client.get(f"/l/{d['token']}").status_code == 200                       # le lien reste valable


def test_desinscription_signature():
    cle = emails.cle_desinscription("6f9619ff-8b86-d011-b42d-00cf4fc964ff")
    assert emails.verifier_desinscription(cle) == "6f9619ff-8b86-d011-b42d-00cf4fc964ff"
    assert emails.verifier_desinscription(cle[:-1] + ("0" if cle[-1] != "0" else "1")) is None
    assert emails.verifier_desinscription("pas-un-uuid.abc") is None


def test_desinscription_invalide(client):
    assert client.get("/desinscription/nimporte.quoi").status_code == 404
    assert client.post("/desinscription/nimporte.quoi").status_code == 404


# ---------------------------------------------------------------- refresh et purge

def test_refresh(client, sql):
    d = inscrit(client)
    r = rid(sql, d["token"])
    sql("update readings set activations_until = current_date - 1 where id = %s", r)
    sql("delete from email_queue where reading_id = %s and kind <> 'link'", r)
    bilan = client.get("/cron/refresh", headers=SECRET).json()
    assert bilan["recalcules"] == 1 and bilan["inscrits"] == 1
    (until,), = sql("select activations_until from readings where id = %s", r)
    assert until > datetime.now(UTC).date() + timedelta(days=300)


def test_purge(client, sql):
    vieux = client.post("/api/reading", json={"date": "2000-01-01", "time": "13:00", "place": PARIS},
                        headers={"x-forwarded-for": "10.6.6.6"}).json()
    garde = inscrit(client, ip="10.6.6.7")
    sql("update readings set last_seen_at = now() - interval '25 months'")
    sql("insert into geocache (q, results, created_at) values ('vieux', '[]', now() - interval '31 days')")
    bilan = client.get("/cron/purge", headers=SECRET).json()
    assert bilan["lectures"] == 1 and bilan["geocache"] == 1
    assert sql("select token from readings") == [(garde["token"],)]
    assert vieux["token"] != garde["token"]
