# -*- coding: utf-8 -*-
"""E-mails (spec 06 §5, D14) : planification, contenu, envoi, désinscription signée.

Un seul consentement : le lien, un rappel 3 jours avant chaque passage exact, une nouvelle
lune par mois. Jamais d'adresse e-mail ni de token dans les journaux.
"""

import hashlib
import hmac
import logging
import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx
from psycopg.rows import dict_row

import lune
from app import config
from app.services import readings as rd

UTC = timezone.utc
log = logging.getLogger("malunenoire.emails")

PRIORITE = ("link", "purchase", "activation", "new_moon", "notify_launch")
RAPPEL_AVANT = timedelta(days=3)
HORIZON_PLANIFICATION = timedelta(days=45)
RESEND_URL = "https://api.resend.com/emails"


class EnvoiImpossible(Exception):
    pass


# ---------------------------------------------------------------- désinscription signée

def cle_desinscription(reading_id):
    rid = str(reading_id)
    sig = hmac.new(config.FEEDBACK_SALT.encode(), f"desinscription:{rid}".encode(),
                   hashlib.sha256).hexdigest()[:24]
    return f"{rid}.{sig}"


def verifier_desinscription(cle):
    """Identifiant de lecture si la signature est bonne, sinon None."""
    rid, _, sig = (cle or "").partition(".")
    try:
        uuid.UUID(rid)
    except ValueError:
        return None
    attendu = cle_desinscription(rid).partition(".")[2]
    return rid if hmac.compare_digest(sig, attendu) else None


def desinscrire(conn, reading_id):
    with conn.transaction():
        n = conn.execute("""update readings set email_unsub_at = coalesce(email_unsub_at, now())
                            where id = %s and email is not null""", (reading_id,)).rowcount
        conn.execute("delete from email_queue where reading_id = %s and sent_at is null", (reading_id,))
    return n > 0


# ---------------------------------------------------------------- planification

def _inscrit(row):
    return row["email"] and row["email_consent_at"] and not row["email_unsub_at"]


def _decalage(reading_id):
    """Lissage des nouvelles lunes : 0 à 4 jours selon la lecture (spec 06 §5)."""
    return int(hashlib.sha1(str(reading_id).encode()).hexdigest()[:8], 16) % 5


def planifier(conn, row, maintenant=None):
    """Met en file les rappels d'activation et de nouvelle lune à venir (idempotent)."""
    if not _inscrit(row):
        return 0
    now = maintenant or datetime.now(UTC)
    fin = now + HORIZON_PLANIFICATION
    lignes = []
    for e in rd.evenements(conn, row["id"]):
        for n, exact in enumerate(e.exacts):
            if now < exact <= fin:
                lignes.append(("activation", f"{e.id}-{n}", max(exact - RAPPEL_AVANT, now)))
    natal = lune.natal(row["birth_date"], row["birth_time"], row["lat"], row["lon"], row["tz_birth"])
    for nm in lune.new_moons(natal, now.date(), months=2):
        envoi = nm.when - timedelta(days=2) + timedelta(days=_decalage(row["id"]))
        if now < nm.when <= fin:
            lignes.append(("new_moon", nm.when.date().isoformat(), max(envoi, now)))
    with conn.transaction():
        for kind, ref, send_after in lignes:
            conn.execute("""insert into email_queue (reading_id, kind, ref, send_after)
                            values (%s, %s, %s, %s) on conflict (reading_id, kind, ref) do nothing""",
                         (row["id"], kind, ref, send_after))
    return len(lignes)


# ---------------------------------------------------------------- contenu

def _minuscule(p):
    return p[0].lower() + p[1:] if p.startswith(("Le ", "Ta ", "Retour ")) else p


def contenu(conn, item, row):
    """(sujet, paragraphes) d'un e-mail, ou None s'il n'a plus d'objet (activation recalculée)."""
    t = lune.ui()["emails"]
    tz = ZoneInfo(row["tz_user"] or row["tz_birth"])
    today = datetime.now(tz).date()
    fr = lambda dt: lune.date_fr(dt.astimezone(tz).date(), today)
    if item["kind"] == "link":
        return t["link_sujet"], list(t["link_corps"])
    if item["kind"] == "activation":
        event_id, _, n = item["ref"].rpartition("-")
        e = next((e for e in rd.evenements(conn, row["id"]) if e.id == event_id), None)
        if e is None or int(n) >= len(e.exacts):
            return None
        exact = e.exacts[int(n)]
        phrase = lune.phrase(e)
        if e.kind == "ln_ingress":
            fenetre = lune.ui()["affichage"]["fenetre_ouverte"].format(debut=fr(e.enter))
        elif e.exit:
            fenetre = lune.ui()["affichage"]["fenetre"].format(debut=fr(e.enter), fin=fr(e.exit))
        else:
            fenetre = lune.ui()["affichage"]["fenetre_ouverte"].format(debut=fr(e.enter))
        sujet = t["activation_sujet"].format(date=fr(exact), phrase=_minuscule(phrase))
        corps = [c.format(fenetre=fenetre, phrase=_minuscule(phrase), date=fr(exact))
                 for c in t["activation_corps"]]
        return sujet, corps
    if item["kind"] == "new_moon":
        natal = lune.natal(row["birth_date"], row["birth_time"], row["lat"], row["lon"], row["tz_birth"])
        jour = datetime.fromisoformat(item["ref"]).replace(tzinfo=UTC)
        nm = next((x for x in lune.new_moons(natal, (jour - timedelta(days=2)).date(), months=1)
                   if abs((x.when - jour).days) <= 1), None)
        if nm is None:
            return None
        signe = lune.SIGNS_FR[nm.sign]
        if nm.touches:
            ligne = t["new_moon_point"].format(date=fr(nm.when), point=lune.ui()["points"][nm.nearest_point])
        elif nm.house:
            ligne = t["new_moon_maison"].format(date=fr(nm.when), signe=signe, maison=rd.house_roman(nm.house))
        else:
            ligne = t["new_moon_signe"].format(date=fr(nm.when), signe=signe)
        return t["new_moon_sujet"].format(signe=signe), [ligne, t["new_moon_fin"]]
    return None


def rendre(env, sujet, paragraphes, row):
    """(texte brut, HTML) avec lien personnel et lien de désinscription."""
    lien = f"{config.BASE_URL}/l/{row['token']}"
    desinscription = f"{config.BASE_URL}/desinscription/{cle_desinscription(row['id'])}"
    ctx = {"sujet": sujet, "paragraphes": paragraphes, "lien": lien, "desinscription": desinscription}
    return (env.get_template("emails/email.txt").render(**ctx),
            env.get_template("emails/email.html").render(**ctx), desinscription)


# ---------------------------------------------------------------- envoi

def destinataire(email):
    if config.ENV == "preprod":
        return config.EMAIL_REDIRECT or None
    return email


def envoyer(a, sujet, texte, html, desinscription):
    """Envoi réel (Resend) hors local ; en local, une ligne de journal sans l'adresse."""
    if config.ENV == "local":
        log.info("e-mail (local, non envoyé) : %s", sujet)
        return
    if not config.RESEND_API_KEY or not a:
        raise EnvoiImpossible("e-mail non configuré")
    r = httpx.post(RESEND_URL, timeout=10, headers={"Authorization": f"Bearer {config.RESEND_API_KEY}"}, json={
        "from": lune.ui()["emails"]["expediteur"], "to": [a], "subject": sujet, "text": texte, "html": html,
        "headers": {"List-Unsubscribe": f"<{desinscription}>",
                    "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"}})
    if r.status_code >= 300:
        raise EnvoiImpossible(f"Resend {r.status_code}")


def masquer(email):
    return rd.mask_email(email)
