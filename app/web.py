# -*- coding: utf-8 -*-
"""Pages HTML (spec 01, 05 §3) : entrée, révélation, sanctuaire, effacement, pages légales."""

import os

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

import lune
from app import config, db
from app.services import cartes
from app.services import readings as rd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
templates = Jinja2Templates(directory=os.path.join(ROOT, "app", "templates"))
templates.env.globals.update(ui=lune.ui(), version=config.GIT_SHA)

router = APIRouter()

PUBLIC_1H = "public, max-age=3600"
PUBLIC_1J = "public, max-age=86400"
PRIVE = {"Cache-Control": "private, no-store", "Referrer-Policy": "no-referrer",
         "X-Robots-Tag": "noindex"}


def page(request, gabarit, statut=200, entetes=None, **ctx):
    resp = templates.TemplateResponse(request, gabarit, ctx, status_code=statut)
    for k, v in (entetes or {}).items():
        resp.headers[k] = v
    return resp


def erreur(request, message, statut=404, entetes=None):
    return page(request, "erreur.html", statut, entetes or {"Cache-Control": "no-store"},
                message=message)


def _brouillon(texte):
    return not config.PROD and texte.get("statut") != "publie"


def _lecture(request, token):
    """(row, payload) ou (None, None) ; le corpus doit être chargé."""
    if request.app.state.corpus is None:
        return None, None
    with db.pool.connection() as conn:
        row = rd.trouver(conn, token)
        if row is None:
            return None, None
        return row, rd.payload(conn, request.app.state.corpus, row)


def _carte(design, r, classe="carte"):
    return cartes.svg(templates.env, design, r["sign"], r["text"]["phrase"], r["text"]["accent"],
                      r["sign_label"], r["house_roman"], classe=classe)


@router.get("/", response_class=HTMLResponse)
def entree(request: Request):
    return page(request, "entree.html", entetes={"Cache-Control": PUBLIC_1H})


@router.get("/l/{token}", response_class=HTMLResponse)
def revelation(request: Request, token: str):
    row, r = _lecture(request, token)
    if r is None:
        return erreur(request, lune.ui()["systeme"]["token_inconnu"], entetes=PRIVE)
    signe = r["sign"]
    designs = cartes.designs_disponibles(signe)
    fond = f"/static/fonds/{signe}-390.webp" if cartes.fond_existe(signe) else None
    return page(request, "revelation.html", entetes=PRIVE, token=token, r=r,
                cartes=[(d, _carte(d, r)) for d in designs],
                design=cartes.design_effectif(r["design"], signe), fond_mini=fond,
                brouillon=_brouillon(r["text"]))


@router.get("/l/{token}/sanctuaire", response_class=HTMLResponse)
def sanctuaire(request: Request, token: str):
    row, r = _lecture(request, token)
    if r is None:
        return erreur(request, lune.ui()["systeme"]["token_inconnu"], entetes=PRIVE)
    return page(request, "sanctuaire.html", entetes=PRIVE, token=token, r=r,
                vignette=_carte(r["design"], r, "carte carte-vignette"),
                brouillon=_brouillon(r["text"]))


@router.get("/l/{token}/effacer", response_class=HTMLResponse)
def effacer(request: Request, token: str):
    with db.pool.connection() as conn:
        if rd.trouver(conn, token) is None:
            return erreur(request, lune.ui()["systeme"]["token_inconnu"], entetes=PRIVE)
    return page(request, "effacer.html", entetes=PRIVE, token=token)


@router.get("/mentions", response_class=HTMLResponse)
def mentions(request: Request):
    return page(request, "page.html", entetes={"Cache-Control": PUBLIC_1J},
                page=lune.ui()["pages"]["mentions"])


@router.get("/confidentialite", response_class=HTMLResponse)
def confidentialite(request: Request):
    return page(request, "page.html", entetes={"Cache-Control": PUBLIC_1J},
                page=lune.ui()["pages"]["confidentialite"])
