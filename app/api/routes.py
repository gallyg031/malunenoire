# -*- coding: utf-8 -*-
"""API JSON (spec 05 §4)."""

import re
from datetime import date, datetime, time, timezone
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field, field_validator
from psycopg.rows import dict_row

import lune
from app import db
from app.services import emails
from app.services import readings as rd
from app.services.corpus import CLES, PARTS

router = APIRouter(prefix="/api")
UTC = timezone.utc

EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")
EVENTS_CLIENT = {"share_click", "share_done", "save_image", "copy_link", "design_change",
                 "ics_click", "sanctuaire_open", "feedback_open"}
PROPS_CLIENT = {"design", "no_time", "from"}

# limites (spec 05 §7) : (nombre, fenêtre en secondes)
LIM_CREATION = (30, 3600)
LIM_FEEDBACK = (60, 3600)
LIM_GEOCODE = (120, 60)
LIM_EMAIL = (5, 3600)


def erreur(status, code, cle_message=None):
    msg = lune.ui()["erreurs"].get(cle_message or code, lune.ui()["erreurs"]["validation"])
    return JSONResponse({"ok": False, "error": code, "message": msg}, status_code=status)


def ip(request: Request):
    h = request.headers
    if h.get("cf-connecting-ip"):
        return h["cf-connecting-ip"]
    if h.get("x-forwarded-for"):
        return h["x-forwarded-for"].split(",")[0].strip()
    return request.client.host if request.client else "?"


def _tz_valide(v):
    try:
        ZoneInfo(v)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError("fuseau")
    return v


# ---------------------------------------------------------------- modèles

class Place(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    tz: str = Field(max_length=64)

    _tz = field_validator("tz")(_tz_valide)


class ReadingIn(BaseModel):
    date: date
    time: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    place: Place
    tz_user: str | None = Field(default=None, max_length=64)

    @field_validator("tz_user")
    @classmethod
    def _tzu(cls, v):
        return _tz_valide(v) if v else v


class ReadingPatch(BaseModel):
    time: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    design: Literal["illustre", "eclipse", "verdict"] | None = None
    tz_user: str | None = Field(default=None, max_length=64)

    @field_validator("tz_user")
    @classmethod
    def _tzu(cls, v):
        return _tz_valide(v) if v else v


class EmailIn(BaseModel):
    email: str = Field(max_length=254)


class FeedbackIn(BaseModel):
    text_id: str = Field(max_length=20)
    text_version: int = Field(ge=0)
    part: str
    vote: Literal[1, -1]
    no_time: bool


class EventIn(BaseModel):
    name: str = Field(max_length=40)
    props: dict | None = None


def _hhmm(s):
    h, m = s.split(":")
    return time(int(h), int(m))


def _corpus(request):
    return request.app.state.corpus


def _no_store(resp):
    resp.headers["Cache-Control"] = "private, no-store"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["X-Robots-Tag"] = "noindex"
    return resp


# ---------------------------------------------------------------- lectures

@router.post("/reading")
def creer(body: ReadingIn, request: Request):
    with db.pool.connection() as conn:
        if not db.limite(conn, rd.hash_key("creation", ip(request)), *LIM_CREATION):
            return erreur(429, "trop")
        try:
            out = rd.creer(conn, _corpus(request), body.date,
                           _hhmm(body.time) if body.time else None,
                           body.place.model_dump(), body.tz_user)
        except ValueError:
            return erreur(400, "validation", "date")
    return _no_store(JSONResponse(out))


@router.get("/reading/{token}")
def lire(token: str, request: Request):
    with db.pool.connection() as conn:
        row = rd.trouver(conn, token)
        if row is None:
            return _no_store(erreur(404, "introuvable"))
        out = rd.payload(conn, _corpus(request), row)
    return _no_store(JSONResponse({"ok": True, **out}))


@router.patch("/reading/{token}")
def modifier(token: str, body: ReadingPatch, request: Request):
    with db.pool.connection() as conn:
        row = rd.trouver(conn, token)
        if row is None:
            return _no_store(erreur(404, "introuvable"))
        if body.design:
            conn.execute("update readings set design = %s where id = %s", (body.design, row["id"]))
        if body.tz_user:
            conn.execute("update readings set tz_user = %s where id = %s", (body.tz_user, row["id"]))
        if body.time:
            row = rd.recalculer(conn, _corpus(request), row, _hhmm(body.time))
        else:
            row = rd.trouver(conn, token)
    return _no_store(JSONResponse(rd.resultat(row)))


@router.delete("/reading/{token}")
def effacer(token: str):
    with db.pool.connection() as conn:
        row = rd.trouver(conn, token)
        if row is None:
            return _no_store(erreur(404, "introuvable"))
        rd.effacer(conn, row)
    return _no_store(JSONResponse({"ok": True}))


def _ics(contenu):
    return _no_store(Response(contenu, media_type="text/calendar; charset=utf-8", headers={
        "Content-Disposition": 'attachment; filename="ma-lune-noire.ics"'}))


@router.get("/reading/{token}/next.ics")
def next_ics(token: str):
    with db.pool.connection() as conn:
        row = rd.trouver(conn, token)
        if row is None:
            return _no_store(erreur(404, "introuvable"))
        rd.rafraichir_si_besoin(conn, row)
        sel = lune.select(rd.evenements(conn, row["id"]))
        if sel is None:
            return _no_store(erreur(404, "aucune_activation"))
        rd.event(conn, "ics_download", {"kind": "next"})
        tz = row["tz_user"] or row["tz_birth"]
    return _ics(lune.ics_next(sel, token, tz))


@router.get("/reading/{token}/calendrier.ics")
def calendrier_ics(token: str):
    """Phase 1.5 : réservé aux achats calendrier / bundle, depuis l'instantané d'achat."""
    with db.pool.connection() as conn:
        row = rd.trouver(conn, token)
        if row is None:
            return _no_store(erreur(404, "introuvable"))
        achat = conn.cursor(row_factory=dict_row).execute(
            """select snapshot, paid_at from purchases where reading_id = %s and status = 'paid'
               and product = any(%s) order by paid_at desc limit 1""",
            (row["id"], list(rd.PRODUITS_CALENDRIER))).fetchone()
        if achat is None or not achat["snapshot"]:
            return _no_store(erreur(403, "not_purchased", "non_achete"))
        rd.event(conn, "ics_download", {"kind": "calendrier"})
        events = [lune.Event(**{**e, "enter": datetime.fromisoformat(e["enter"]),
                                "exit": datetime.fromisoformat(e["exit"]) if e["exit"] else None,
                                "exacts": [datetime.fromisoformat(x) for x in e["exacts"]]})
                  for e in achat["snapshot"]["events"]]
        tz = row["tz_user"] or row["tz_birth"]
    return _ics(lune.ics_calendar(events, token, tz, achat["paid_at"].date()))


# ---------------------------------------------------------------- e-mail (D14)

@router.post("/reading/{token}/email")
def email_optin(token: str, body: EmailIn):
    email = body.email.strip().lower()
    if not EMAIL_RE.match(email):
        return _no_store(erreur(400, "validation", "email"))
    with db.pool.connection() as conn:
        row = rd.trouver(conn, token)
        if row is None:
            return _no_store(erreur(404, "introuvable"))
        if not db.limite(conn, rd.hash_key("email", row["id"]), *LIM_EMAIL):
            return _no_store(erreur(429, "trop"))
        with conn.transaction():
            conn.execute("""update readings set email = %s, email_consent_at = now(),
                            email_unsub_at = null where id = %s""", (email, row["id"]))
            conn.execute(
                """insert into email_queue (reading_id, kind, ref, send_after)
                   values (%s, 'link', 'link', now())
                   on conflict (reading_id, kind, ref) do update
                   set send_after = now(), sent_at = null, attempts = 0, last_error = null""",
                (row["id"],))
            rd.event(conn, "email_optin")
        emails.planifier(conn, rd.trouver(conn, token))     # premiers rappels sans attendre le cron
    return _no_store(JSONResponse({"ok": True, "email": rd.mask_email(email)}))


@router.delete("/reading/{token}/email")
def email_optout(token: str):
    with db.pool.connection() as conn:
        row = rd.trouver(conn, token)
        if row is None:
            return _no_store(erreur(404, "introuvable"))
        with conn.transaction():
            conn.execute("update readings set email_unsub_at = now() where id = %s", (row["id"],))
            conn.execute("delete from email_queue where reading_id = %s and sent_at is null",
                         (row["id"],))
    return _no_store(JSONResponse({"ok": True, "email": None}))


# ---------------------------------------------------------------- feedback, mesure

@router.post("/feedback")
def feedback(body: FeedbackIn, request: Request):
    if body.text_id not in CLES or body.part not in PARTS:
        return erreur(400, "validation")
    addr = ip(request)
    jour = datetime.now(UTC).date().isoformat()
    visitor = rd.hash_key("feedback", addr, request.headers.get("user-agent", ""), jour)
    with db.pool.connection() as conn:
        if not db.limite(conn, rd.hash_key("feedback-ip", addr), *LIM_FEEDBACK):
            return erreur(429, "trop")
        cur = conn.execute(
            """insert into feedback (text_id, text_version, part, vote, no_time, visitor_day)
               values (%s,%s,%s,%s,%s,%s) on conflict (text_id, part, visitor_day) do nothing""",
            (body.text_id, body.text_version, body.part, body.vote, body.no_time, visitor))
    if cur.rowcount == 0:
        return JSONResponse({"ok": True, "duplicate": True})
    return JSONResponse({"ok": True})


@router.post("/event", status_code=204)
def mesure(body: EventIn):
    if body.name not in EVENTS_CLIENT:
        return erreur(400, "validation")
    props = {k: v for k, v in (body.props or {}).items()
             if k in PROPS_CLIENT and isinstance(v, (str, bool, int)) and len(str(v)) <= 40}
    with db.pool.connection() as conn:
        rd.event(conn, body.name, props or None)
    return Response(status_code=204)
