# -*- coding: utf-8 -*-
"""
Ma Lune Noire — application FastAPI.

Au démarrage : éphémérides, self-test allégé (thèmes de référence), migrations,
corpus. Si le test doré échoue, l'application refuse de démarrer ; si le corpus
est invalide, /health répond 500.
"""

import logging
import os
import re
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "engine"))
sys.path.insert(0, ROOT)

import selftest  # noqa: E402
import lune  # noqa: E402
from app import config, cron, db, web  # noqa: E402
from app.api import routes  # noqa: E402
from app.services import corpus as corpus_mod  # noqa: E402
from app.services import geocode as geo  # noqa: E402

ENV = config.ENV
DATABASE_URL = config.DATABASE_URL

log = logging.getLogger("malunenoire")
state = {"golden": False, "db": DATABASE_URL is not None, "corpus": False}


class MasqueTokens(logging.Filter):
    """Jamais de token dans un log (spec 05 §1) : /l/<token>, /api/reading/<token>, désinscription."""
    MOTIF = re.compile(r"/(l|api/reading|desinscription)/[A-Za-z0-9_-]{8,}")

    def filter(self, record):
        if record.args:
            record.args = tuple(self.MOTIF.sub(r"/\1/•", a) if isinstance(a, str) else a
                                for a in record.args)
        record.msg = self.MOTIF.sub(r"/\1/•", str(record.msg))
        return True


logging.getLogger("uvicorn.access").addFilter(MasqueTokens())


@asynccontextmanager
async def lifespan(app):
    fails = selftest.run(config.EPHE_PATH, leger=True)
    if fails:
        for f in fails:
            log.critical("self-test : %s", f)
        raise RuntimeError("test doré en échec : démarrage refusé")
    state["golden"] = True
    try:
        app.state.corpus = corpus_mod.Corpus(prod=config.PROD)
        state["corpus"] = True
    except corpus_mod.CorpusError as e:
        log.critical("%s", e)
        app.state.corpus, state["corpus"] = None, False
    if DATABASE_URL:
        from db.migrate import migrate
        for name in migrate(DATABASE_URL):
            log.warning("migration appliquée : %s", name)
        db.open_pool(DATABASE_URL)
    yield
    db.close_pool()


app = FastAPI(title="Ma Lune Noire", lifespan=lifespan, docs_url=None, redoc_url=None,
              openapi_url=None)
app.include_router(routes.router)
app.include_router(web.router)
app.include_router(cron.router)
app.mount("/static", StaticFiles(directory=os.path.join(ROOT, "static")), name="static")

CHAMP_MESSAGE = {"date": "date", "time": "heure", "lat": "lieu", "lon": "lieu", "name": "lieu",
                 "place": "lieu", "tz": "fuseau", "tz_user": "fuseau", "email": "email"}


@app.exception_handler(RequestValidationError)
async def validation(request: Request, exc: RequestValidationError):
    cle = "validation"
    for err in exc.errors():
        for part in reversed(err.get("loc", ())):
            if part in CHAMP_MESSAGE:
                cle = CHAMP_MESSAGE[part]
                break
        if cle != "validation":
            break
    return routes.erreur(400, "validation", cle)


@app.exception_handler(StarletteHTTPException)
async def http_erreur(request: Request, exc: StarletteHTTPException):
    if request.url.path.startswith("/api/"):
        code = "introuvable" if exc.status_code == 404 else "validation"
        return routes.erreur(exc.status_code, code)
    if exc.status_code == 404:
        return web.erreur(request, lune.ui()["systeme"]["404"])
    return web.erreur(request, lune.ui()["systeme"]["hors_ligne"], exc.status_code)


@app.exception_handler(Exception)
async def interne(request: Request, exc: Exception):
    log.exception("erreur interne")
    return routes.erreur(500, "interne")


@app.middleware("http")
async def entetes(request: Request, call_next):
    chemin = request.url.path
    if getattr(request.app.state, "corpus", None) is None and state["golden"]:
        if chemin.startswith("/api/reading"):
            return routes.erreur(500, "interne")
        if chemin.startswith("/l/"):
            return web.erreur(request, lune.ui()["systeme"]["hors_ligne"], 500)
    resp = await call_next(request)
    h = resp.headers
    if chemin.startswith("/static/"):
        immuable = chemin.startswith("/static/fonts/") or "v=" in request.url.query
        h["Cache-Control"] = ("public, max-age=31536000, immutable" if immuable
                              else "public, max-age=86400")
    h.setdefault("X-Content-Type-Options", "nosniff")
    h.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    h.setdefault("Content-Security-Policy",
                 "default-src 'self'; img-src 'self' data:; script-src 'self'; "
                 "style-src 'self'; frame-ancestors 'none'; base-uri 'self'")
    if ENV != "local":
        h.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return resp


@app.get("/health")   # Cloud Run réserve /healthz sur ses URL : /health est la sonde en production
@app.get("/healthz")
def healthz():
    checks = {"golden": state["golden"], "corpus": state["corpus"], "db": None}
    if state["db"]:
        try:
            checks["db"] = db.ping()
        except Exception:
            log.exception("base injoignable")
            checks["db"] = False
    ok = checks["golden"] and checks["corpus"] and checks["db"] is not False
    if ENV != "local" and not state["db"]:
        ok = False
    return JSONResponse({"ok": ok, "env": ENV, **checks}, status_code=200 if ok else 500)


@app.get("/api/geocode")
def api_geocode(request: Request, q: str = Query("", max_length=geo.MAX_Q)):
    cache = None
    if db.pool is not None:
        cache = db.GeoCache()
        with db.pool.connection() as conn:
            if not db.limite(conn, routes.rd.hash_key("geocode", routes.ip(request)),
                             *routes.LIM_GEOCODE):
                return routes.erreur(429, "trop")
    results = geo.geocode(q, cache=cache)
    return JSONResponse(results, headers={"Cache-Control": "public, max-age=86400"})
