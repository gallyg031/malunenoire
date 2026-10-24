# -*- coding: utf-8 -*-
"""
Ma Lune Noire — application FastAPI (phase 0 : socle).

Au démarrage : éphémérides, self-test allégé (thèmes de référence), migrations.
Si le test doré échoue, l'application refuse de démarrer.
"""

import logging
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "engine"))
sys.path.insert(0, ROOT)

import selftest  # noqa: E402
from app import db  # noqa: E402
from app.services import geocode as geo  # noqa: E402

ENV = os.environ.get("ENV", "local")
EPHE_PATH = os.environ.get("EPHE_PATH", os.path.join(ROOT, "data", "ephe"))
DATABASE_URL = os.environ.get("DATABASE_URL")

log = logging.getLogger("malunenoire")
state = {"golden": False, "db": DATABASE_URL is not None}


@asynccontextmanager
async def lifespan(app):
    fails = selftest.run(EPHE_PATH, leger=True)
    if fails:
        for f in fails:
            log.critical("self-test : %s", f)
        raise RuntimeError("test doré en échec : démarrage refusé")
    state["golden"] = True
    if DATABASE_URL:
        from db.migrate import migrate
        for name in migrate(DATABASE_URL):
            log.warning("migration appliquée : %s", name)
        db.open_pool(DATABASE_URL)
    yield
    db.close_pool()


app = FastAPI(title="Ma Lune Noire", lifespan=lifespan, docs_url=None, redoc_url=None)


def error(status, code, message):
    return JSONResponse({"ok": False, "error": code, "message": message}, status_code=status)


@app.get("/health")   # Cloud Run réserve /healthz sur ses URL : /health est la sonde en production
@app.get("/healthz")
def healthz():
    checks = {"golden": state["golden"], "db": None}
    if state["db"]:
        try:
            checks["db"] = db.ping()
        except Exception:
            log.exception("base injoignable")
            checks["db"] = False
    ok = checks["golden"] and checks["db"] is not False
    if ENV != "local" and not state["db"]:
        ok = False
    return JSONResponse({"ok": ok, "env": ENV, **checks}, status_code=200 if ok else 500)


@app.get("/api/geocode")
def api_geocode(q: str = Query("", max_length=geo.MAX_Q)):
    cache = db.GeoCache() if db.pool is not None else None
    try:
        results = geo.geocode(q, cache=cache)
    except Exception:
        log.exception("géocodage")
        return error(500, "geocode", "La recherche de lieu ne répond pas. Réessaie dans un instant.")
    return JSONResponse(results, headers={"Cache-Control": "public, max-age=86400"})
