# -*- coding: utf-8 -*-
"""Pages HTML (spec 01, 05 §3) : entrée, révélation, sanctuaire, effacement, pages légales."""

import functools
import os

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates

import lune
from app import config, db
from app.services import cartes, rendu
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


# ---------------------------------------------------------------- page publique et images (spec 04 §5)

PUBLIC_CARTE = "public, max-age=86400, stale-while-revalidate=604800"
IMMUABLE = "public, max-age=31536000, immutable"


def _public(request, share_id):
    """(ligne, texte, signe, libellé, maison en chiffres romains) ou None."""
    if request.app.state.corpus is None:
        return None
    with db.pool.connection() as conn:
        row = rd.par_share_id(conn, share_id)
    if row is None:
        return None
    signe = lune.SIGN_IDS[row["ln_sign"]]
    texte = request.app.state.corpus.get(signe, row["ln_house"])
    return row, texte, signe, rd.sign_label(row["ln_sign"]), rd.house_roman(row["ln_house"])


def _cache_image(request):
    """Un an, immuable, seulement si l'URL porte la version du texte (?v=)."""
    return IMMUABLE if request.query_params.get("v") else PUBLIC_1J


def _design(d, row, signe):
    return cartes.design_effectif(d if d in cartes.DESIGNS else row["design"], signe)


@router.get("/c/{share_id}", response_class=HTMLResponse)
def publique(request: Request, share_id: str, d: str = ""):
    p = _public(request, share_id)
    if p is None:
        return erreur(request, lune.ui()["systeme"]["404"], entetes={"Cache-Control": "public, max-age=300"})
    row, texte, signe, libelle, romain = p
    design = _design(d, row, signe)
    titre = f"{libelle} — Maison {romain}" if romain else libelle
    carte = cartes.svg(templates.env, design, signe, texte["phrase"], texte["accent"], libelle, romain)
    return page(request, "public.html", entetes={"Cache-Control": PUBLIC_CARTE}, carte=carte,
                titre=titre, phrase=texte["phrase"], share_id=share_id, design=design,
                base_url=config.BASE_URL, version_texte=texte["version"])


@functools.lru_cache(maxsize=64)
def _png_carte(design, signe, phrase, accent, libelle, romain):
    return rendu.carte_png(templates.env, design, signe, phrase, accent, libelle, romain)


@functools.lru_cache(maxsize=64)
def _png_og(design, signe, phrase, libelle, romain):
    return rendu.og_png(templates.env, design, signe, phrase, libelle, romain)


@router.get("/c/{share_id}/carte.png")
def carte_png(request: Request, share_id: str, d: str = ""):
    p = _public(request, share_id)
    if p is None:
        return erreur(request, lune.ui()["systeme"]["404"])
    row, texte, signe, libelle, romain = p
    contenu = _png_carte(_design(d, row, signe), signe, texte["phrase"], texte["accent"], libelle, romain)
    return Response(contenu, media_type="image/png", headers={
        "Cache-Control": _cache_image(request),
        "Content-Disposition": f'attachment; filename="ma-lune-noire-{signe}.png"'})


@router.get("/c/{share_id}/og.png")
def og_png(request: Request, share_id: str, d: str = ""):
    p = _public(request, share_id)
    if p is None:
        return erreur(request, lune.ui()["systeme"]["404"])
    row, texte, signe, libelle, romain = p
    contenu = _png_og(_design(d, row, signe), signe, texte["phrase"], libelle, romain)
    return Response(contenu, media_type="image/png", headers={"Cache-Control": _cache_image(request)})
