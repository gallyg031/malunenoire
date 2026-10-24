# -*- coding: utf-8 -*-
"""Tâches planifiées (spec 06 §5-6), appelées par Cloud Scheduler avec l'en-tête X-Cron-Secret.

/cron/emails   tous les jours 08:00 Europe/Paris — file d'envoi, plafond 90
/cron/refresh  hebdomadaire — activations à recalculer, rappels à planifier
/cron/purge    hebdomadaire — durées de conservation (spec 05 §6)
"""

import hmac
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse
from psycopg.rows import dict_row

from app import config, db
from app.services import emails
from app.services import readings as rd

UTC = timezone.utc
log = logging.getLogger("malunenoire.cron")
router = APIRouter(prefix="/cron")
LOT_REFRESH = 500


def _autorise(secret):
    return bool(config.CRON_SECRET) and secret is not None and \
        hmac.compare_digest(secret.encode(), config.CRON_SECRET.encode())


def _refus():
    return JSONResponse({"ok": False, "error": "interdit"}, status_code=403)


def _env():
    from app.web import templates
    return templates.env


# ---------------------------------------------------------------- envoi

def envoyer_file(conn, plafond=None, maintenant=None):
    plafond = plafond or config.EMAIL_PLAFOND
    cur = conn.cursor(row_factory=dict_row)
    eligibles = cur.execute(
        """select count(*) as n from email_queue
           where sent_at is null and send_after <= %s and attempts < 3""",
        (maintenant or datetime.now(UTC),)).fetchone()["n"]
    items = cur.execute(
        """select q.id as qid, q.kind, q.ref, q.reading_id, r.*
           from email_queue q join readings r on r.id = q.reading_id
           where q.sent_at is null and q.send_after <= %s and q.attempts < 3
           order by array_position(%s::text[], q.kind), q.send_after, q.id
           limit %s""",
        (maintenant or datetime.now(UTC), list(emails.PRIORITE), plafond)).fetchall()
    envoyes = echecs = obsoletes = 0
    for it in items:
        # revérifié au moment de l'envoi : jamais à une lecture désinscrite
        if not it["email"] or it["email_unsub_at"]:
            conn.execute("delete from email_queue where id = %s", (it["qid"],))
            continue
        c = emails.contenu(conn, it, it)
        if c is None:
            conn.execute("update email_queue set attempts = 3, last_error = 'obsolète' where id = %s",
                         (it["qid"],))
            obsoletes += 1
            continue
        texte, html, lien_des = emails.rendre(_env(), c[0], c[1], it)
        try:
            emails.envoyer(emails.destinataire(it["email"]), c[0], texte, html, lien_des)
        except Exception as e:                      # fournisseur en panne, réseau…
            conn.execute("""update email_queue set attempts = attempts + 1, last_error = %s
                            where id = %s""", (str(e)[:200], it["qid"]))
            echecs += 1
            continue
        conn.execute("update email_queue set sent_at = now() where id = %s", (it["qid"],))
        envoyes += 1
    if eligibles > plafond:
        _saturation(conn)
    return {"envoyes": envoyes, "echecs": echecs, "obsoletes": obsoletes, "eligibles": eligibles}


def _saturation(conn):
    """Plus de 90 éligibles trois jours de suite : alerte (spec 06 §5)."""
    aujourdhui = datetime.now(UTC).date()
    conn.execute("""insert into events (name, props) select 'file_saturee', jsonb_build_object('jour', %s::text)
                    where not exists (select 1 from events where name = 'file_saturee'
                                      and props->>'jour' = %s::text)""",
                 (aujourdhui.isoformat(), aujourdhui.isoformat()))
    jours = {r[0] for r in conn.execute(
        "select props->>'jour' from events where name = 'file_saturee' and created_at > now() - interval '3 days'")}
    if all((aujourdhui - timedelta(days=i)).isoformat() in jours for i in range(3)):
        log.warning("file d'e-mails saturée depuis trois jours")
        if config.ADMIN_EMAIL:
            ui = emails.lune.ui()["emails"]
            try:
                emails.envoyer(config.ADMIN_EMAIL, ui["alerte_sujet"], "\n\n".join(ui["alerte_corps"]),
                               "<br><br>".join(ui["alerte_corps"]), config.BASE_URL)
            except Exception:
                log.exception("alerte de saturation non envoyée")


@router.get("/emails")
def cron_emails(x_cron_secret: str | None = Header(default=None)):
    if not _autorise(x_cron_secret):
        return _refus()
    with db.pool.connection() as conn:
        bilan = envoyer_file(conn)
    log.info("cron e-mails : %s", bilan)
    return {"ok": True, **bilan}


# ---------------------------------------------------------------- recalcul et planification

def rafraichir(conn):
    cur = conn.cursor(row_factory=dict_row)
    a_recalculer = cur.execute(
        """select * from readings
           where activations_until < current_date + %s
             and (email is not null or last_seen_at > now() - interval '90 days')
           limit %s""", (rd.REFRESH_JOURS, LOT_REFRESH)).fetchall()
    for row in a_recalculer:
        rd.rafraichir_si_besoin(conn, row)
    inscrits = cur.execute(
        """select * from readings where email is not null and email_consent_at is not null
           and email_unsub_at is null""").fetchall()
    planifies = sum(emails.planifier(conn, row) for row in inscrits)
    return {"recalcules": len(a_recalculer), "inscrits": len(inscrits), "planifies": planifies}


@router.get("/refresh")
def cron_refresh(x_cron_secret: str | None = Header(default=None)):
    if not _autorise(x_cron_secret):
        return _refus()
    with db.pool.connection() as conn:
        bilan = rafraichir(conn)
    log.info("cron refresh : %s", bilan)
    return {"ok": True, **bilan}


# ---------------------------------------------------------------- purge (spec 05 §6, 06 §6)

def purger(conn):
    return {
        "lectures": conn.execute("""delete from readings where email is null
                                    and last_seen_at < now() - interval '24 months'""").rowcount,
        "geocache": conn.execute("delete from geocache where created_at < now() - interval '30 days'").rowcount,
        "emails": conn.execute("""delete from email_queue where sent_at is not null
                                  and sent_at < now() - interval '90 days'""").rowcount,
        "ratelimit": conn.execute("delete from ratelimit where bucket < now() - interval '1 day'").rowcount,
    }


@router.get("/purge")
def cron_purge(x_cron_secret: str | None = Header(default=None)):
    if not _autorise(x_cron_secret):
        return _refus()
    with db.pool.connection() as conn:
        bilan = purger(conn)
    log.info("cron purge : %s", bilan)
    return {"ok": True, **bilan}
