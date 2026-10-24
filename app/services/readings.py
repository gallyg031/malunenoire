# -*- coding: utf-8 -*-
"""Lectures (spec 05) : création, payload de révélation, modifications, effacement."""

import hashlib
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import swisseph as swe
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

import lune
from app import config

UTC = timezone.utc
ROMAN = ["", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"]
TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{22}$")
SHARE_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
DESIGNS = ("illustre", "eclipse", "verdict")
DESIGN_DEFAUT = "illustre"          # D10
HORIZON_MOIS = 13
REFRESH_JOURS = 60
PRODUITS_CALENDRIER = ("calendrier", "bundle")


def engine_version():
    return f"{config.GIT_SHA}+swe{swe.version}"


def deg_min(lon):
    """Degré et minute dans le signe, arrondis comme astro.fmt."""
    total = round((lon % 30.0) * 60)
    d, m = divmod(total, 60)
    return (29, 59) if d >= 30 else (d, m)


def sign_label(i):
    return lune.SIGNS_FR[i]


def house_roman(h):
    return ROMAN[h] if h else None


def mask_email(e):
    if not e:
        return None
    local, _, domain = e.partition("@")
    return f"{local[:1]}•••@{domain}"


def hash_key(*parts):
    raw = "|".join([config.FEEDBACK_SALT, *map(str, parts)])
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


# ---------------------------------------------------------------- calcul

def _cross_json(n):
    return {p: {"sign": a["sign"], "house": a["house"], "lon": a["lon"]} for p, a in n.cross.items()}


def _activations_rows(reading_id, ln_lon, start):
    events = lune.activations(SimpleNamespace(ln_lon=ln_lon), start, months=HORIZON_MOIS,
                              reading_id=reading_id)
    rows = [(e.id, reading_id, e.kind, e.body, e.aspect, e.point, e.sign_to, e.weight,
             e.enter, e.exit, e.exacts) for e in events]
    until = start + timedelta(days=31 * HORIZON_MOIS)
    return rows, until


def _insert_activations(conn, rows):
    conn.cursor().executemany(
        """insert into activations (id, reading_id, kind, body, aspect, point, sign_to, weight,
                                    enter_at, exit_at, exacts)
           values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""", rows)


def event(conn, name, props=None):
    conn.execute("insert into events (name, props) values (%s, %s)",
                 (name, Jsonb(props) if props is not None else None))


def resultat(row):
    """Sortie de POST /api/reading et PATCH (spec 05 §4)."""
    d, m = deg_min(row["ln_lon"])
    return {"ok": True, "token": row["token"], "share_id": row["share_id"],
            "sign": lune.SIGN_IDS[row["ln_sign"]], "sign_label": sign_label(row["ln_sign"]),
            "deg": d, "min": m, "house": row["ln_house"], "house_roman": house_roman(row["ln_house"]),
            "house_reason": row["house_reason"], "sign_changes_today": row["sign_changes_today"]}


def creer(conn, corpus, birth_date, birth_time, place, tz_user):
    n = lune.natal(birth_date, birth_time, place["lat"], place["lon"], place["tz"])
    texte = corpus.get(n.sign_id, n.ln_house)
    rid = str(uuid.uuid4())
    start = datetime.now(UTC).date()
    rows, until = _activations_rows(rid, n.ln_lon, start)
    row = {"id": rid, "token": secrets.token_urlsafe(16), "share_id": secrets.token_urlsafe(8),
           "ln_lon": n.ln_lon, "ln_sign": n.ln_sign, "ln_house": n.ln_house,
           "house_reason": n.house_reason, "sign_changes_today": n.sign_changes_today}
    with conn.transaction():
        conn.execute(
            """insert into readings (id, token, share_id, birth_date, birth_time, place_name, lat, lon,
                   tz_birth, utc_offset_min, tz_user, ln_lon, ln_sign, ln_house, house_reason,
                   sign_changes_today, cross_json, intensity, text_id, text_version, design,
                   activations_until, engine_version)
               values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (rid, row["token"], row["share_id"], birth_date, birth_time, place["name"],
             place["lat"], place["lon"], place["tz"], n.utc_offset_min, tz_user, n.ln_lon,
             n.ln_sign, n.ln_house, n.house_reason, n.sign_changes_today, Jsonb(_cross_json(n)),
             n.intensity, texte["id"], texte["version"], DESIGN_DEFAUT, until, engine_version()))
        _insert_activations(conn, rows)
        event(conn, "reading_created", {"no_time": n.no_time})
    return resultat(row)


def trouver(conn, token):
    """Lecture par token (index unique, comparaison en temps constant)."""
    if not token or not TOKEN_RE.match(token):
        return None
    row = conn.cursor(row_factory=dict_row).execute(
        "select * from readings where token = %s", (token,)).fetchone()
    if row is None or not secrets.compare_digest(row["token"], token):
        return None
    return row


def recalculer(conn, corpus, row, birth_time=None):
    """Nouveau calcul complet (heure retrouvée) : même token, même share_id."""
    t = birth_time if birth_time is not None else row["birth_time"]
    n = lune.natal(row["birth_date"], t, row["lat"], row["lon"], row["tz_birth"])
    texte = corpus.get(n.sign_id, n.ln_house)
    start = datetime.now(UTC).date()
    rows, until = _activations_rows(str(row["id"]), n.ln_lon, start)
    with conn.transaction():
        conn.execute(
            """update readings set birth_time=%s, utc_offset_min=%s, ln_lon=%s, ln_sign=%s,
                   ln_house=%s, house_reason=%s, sign_changes_today=%s, cross_json=%s,
                   intensity=%s, text_id=%s, text_version=%s, activations_until=%s,
                   engine_version=%s
               where id=%s""",
            (t, n.utc_offset_min, n.ln_lon, n.ln_sign, n.ln_house, n.house_reason,
             n.sign_changes_today, Jsonb(_cross_json(n)), n.intensity, texte["id"],
             texte["version"], until, engine_version(), row["id"]))
        conn.execute("delete from activations where reading_id = %s", (row["id"],))
        _insert_activations(conn, rows)
    return conn.cursor(row_factory=dict_row).execute(
        "select * from readings where id = %s", (row["id"],)).fetchone()


def rafraichir_si_besoin(conn, row):
    """Horizon restant < 60 jours : on recalcule les activations (spec 02 §10)."""
    today = datetime.now(UTC).date()
    if row["activations_until"] and row["activations_until"] >= today + timedelta(days=REFRESH_JOURS):
        return
    rows, until = _activations_rows(str(row["id"]), row["ln_lon"], today)
    with conn.transaction():
        conn.execute("delete from activations where reading_id = %s", (row["id"],))
        _insert_activations(conn, rows)
        conn.execute("update readings set activations_until = %s where id = %s", (until, row["id"]))
    row["activations_until"] = until


def evenements(conn, reading_id):
    rows = conn.cursor(row_factory=dict_row).execute(
        "select * from activations where reading_id = %s order by enter_at", (reading_id,)).fetchall()
    return [lune.Event(id=r["id"], kind=r["kind"], body=r["body"], aspect=r["aspect"],
                       point=r["point"], weight=r["weight"], enter=r["enter_at"],
                       exit=r["exit_at"], exacts=list(r["exacts"]), sign_to=r["sign_to"])
            for r in rows]


def tz_affichage(row):
    return ZoneInfo(row["tz_user"] or row["tz_birth"])


def activation_payload(sel, tz):
    """« En ce moment » / « Prochaine activation », formaté + brut (spec 02 §6)."""
    if sel is None:
        return None
    t = lune.ui()["affichage"]
    e = sel.event
    local = lambda dt: dt.astimezone(tz).date()
    today = datetime.now(tz).date()
    fr = lambda dt: lune.date_fr(local(dt), today)
    raw = {"body": e.body, "aspect": e.aspect, "point": e.point, "kind": e.kind,
           "enter": e.enter.isoformat(), "exit": e.exit.isoformat() if e.exit else None,
           "exacts": [x.isoformat() for x in e.exacts], "ics_exact": sel.ics_exact.isoformat()}
    out = {"mode": sel.mode, "phrase": lune.phrase(e), "raw": raw}
    if sel.mode == "now":
        out["jusqu"] = t["jusqu_au"].format(date=fr(e.exit)) if e.exit else t["encore_des_mois"]
    else:
        out["date"] = fr(e.exacts[0])
        out["fenetre"] = (t["fenetre"].format(debut=fr(e.enter), fin=fr(e.exit)) if e.exit
                          else t["fenetre_ouverte"].format(debut=fr(e.enter)))
    return out


def payload(conn, corpus, row):
    """Payload complet de la révélation (GET /api/reading/<token>). Jamais de longitude en V1."""
    rafraichir_si_besoin(conn, row)
    conn.execute("update readings set last_seen_at = now() where id = %s", (row["id"],))
    texte = corpus.get(lune.SIGN_IDS[row["ln_sign"]], row["ln_house"])
    sel = lune.select(evenements(conn, row["id"]))
    act = activation_payload(sel, tz_affichage(row))
    achats = [r[0] for r in conn.execute(
        "select product from purchases where reading_id = %s and status = 'paid'", (row["id"],))]
    croix = {p: {"sign": lune.SIGN_IDS[a["sign"]], "sign_label": sign_label(a["sign"]),
                 "house": a["house"], "house_roman": house_roman(a["house"])}
             for p, a in row["cross_json"].items()}
    out = resultat(row)
    out.pop("deg"), out.pop("min"), out.pop("token")
    out.update({
        "no_time": row["birth_time"] is None,
        "text": {k: texte[k] for k in ("id", "phrase", "accent", "eclats", "ouverture",
                                       "version", "statut")} | {"repli": bool(texte.get("repli"))},
        "cross": croix,
        "activation_now": act if act and act["mode"] == "now" else None,
        "activation_next": act if act and act["mode"] == "next" else None,
        "designs": list(DESIGNS), "design": row["design"],
        "email": mask_email(row["email"]) if row["email"] and not row["email_unsub_at"] else None,
        "purchases": achats,
    })
    return out


def effacer(conn, row):
    """Effacement réel : la lecture et tout ce qui en dépend (cascade)."""
    conn.execute("delete from readings where id = %s", (row["id"],))
