# -*- coding: utf-8 -*-
"""Achats (phase 1.5, spec 05 §4) : Stripe Checkout, webhook, instantané du calendrier.

Pas de PCI : la carte ne passe jamais par nos serveurs. L'achat n'est acquis qu'à la
réception du webhook signé `checkout.session.completed` (jamais sur le retour navigateur).
"""

from datetime import datetime, timezone
from types import SimpleNamespace

import stripe
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

import lune
from app import config
from app.services import readings as rd

UTC = timezone.utc
PRODUITS = ("lecture", "calendrier", "bundle")
DONNENT_CALENDRIER = ("calendrier", "bundle")
DONNENT_LECTURE = ("lecture", "bundle")
NOMS = {"lecture": "La lecture complète", "calendrier": "Le calendrier",
        "bundle": "La lecture complète et le calendrier"}
HORIZON_CALENDRIER = 12


class PaiementIndisponible(Exception):
    pass


def creer_session(conn, row, produit, base_url):
    """Crée la session Stripe Checkout et l'achat `pending`. Renvoie l'URL de paiement."""
    if not (config.PAIEMENT_ACTIF and config.STRIPE_SECRET_KEY):
        raise PaiementIndisponible()
    token = row["token"]
    session = stripe.checkout.Session.create(
        api_key=config.STRIPE_SECRET_KEY,
        mode="payment",
        locale="fr",
        line_items=[{"quantity": 1, "price_data": {
            "currency": "eur", "unit_amount": config.PRIX[produit],
            "product_data": {"name": NOMS[produit]}}}],
        success_url=f"{base_url}/l/{token}?achat=ok",
        cancel_url=f"{base_url}/l/{token}",
        client_reference_id=str(row["id"]),
        metadata={"reading_id": str(row["id"]), "product": produit},
    )
    conn.execute("""insert into purchases (reading_id, product, stripe_session_id, amount_cents, status)
                    values (%s, %s, %s, %s, 'pending')""",
                 (row["id"], produit, session["id"], config.PRIX[produit]))
    return session["url"]


def instantane(conn, row):
    """Activations figées à l'achat, sur 12 mois (spec 05 §2 : purchases.snapshot)."""
    start = datetime.now(UTC).date()
    evenements = lune.activations(SimpleNamespace(ln_lon=row["ln_lon"]), start,
                                  months=HORIZON_CALENDRIER, reading_id=str(row["id"]))
    return {"start": start.isoformat(), "events": [
        {**e.to_dict(), "enter": e.enter.isoformat(), "exit": e.exit.isoformat() if e.exit else None,
         "exacts": [x.isoformat() for x in e.exacts]} for e in evenements]}


def confirmer(conn, session):
    """Webhook checkout.session.completed : idempotent (Stripe peut renvoyer l'événement)."""
    if session.get("payment_status") != "paid":
        return False
    cur = conn.cursor(row_factory=dict_row)
    achat = cur.execute("select * from purchases where stripe_session_id = %s", (session["id"],)).fetchone()
    if achat is None or achat["status"] == "paid":
        return False
    row = cur.execute("select * from readings where id = %s", (achat["reading_id"],)).fetchone()
    snapshot = instantane(conn, row) if achat["product"] in DONNENT_CALENDRIER else None
    with conn.transaction():
        conn.execute("""update purchases set status = 'paid', paid_at = now(), snapshot = %s
                        where id = %s""", (Jsonb(snapshot) if snapshot else None, achat["id"]))
        if row["email"] and not row["email_unsub_at"]:
            conn.execute("""insert into email_queue (reading_id, kind, ref, send_after)
                            values (%s, 'purchase', %s, now()) on conflict do nothing""",
                         (row["id"], achat["product"]))
        rd.event(conn, "purchase_paid", {"product": achat["product"]})
    return True


def produits_payes(conn, reading_id):
    return {r[0] for r in conn.execute(
        "select product from purchases where reading_id = %s and status = 'paid'", (reading_id,))}


def a_le_calendrier(produits):
    return bool(set(produits) & set(DONNENT_CALENDRIER))


def a_la_lecture(produits):
    return bool(set(produits) & set(DONNENT_LECTURE))


def evenements_calendrier(conn, reading_id):
    """Événements de l'instantané le plus récent (calendrier ou bundle payé), ou None."""
    achat = conn.cursor(row_factory=dict_row).execute(
        """select snapshot from purchases where reading_id = %s and status = 'paid'
           and product = any(%s) and snapshot is not null order by paid_at desc limit 1""",
        (reading_id, list(DONNENT_CALENDRIER))).fetchone()
    if achat is None:
        return None
    return [lune.Event(**{**e, "enter": datetime.fromisoformat(e["enter"]),
                          "exit": datetime.fromisoformat(e["exit"]) if e["exit"] else None,
                          "exacts": [datetime.fromisoformat(x) for x in e["exacts"]]})
            for e in achat["snapshot"]["events"]], achat["snapshot"]["start"]
