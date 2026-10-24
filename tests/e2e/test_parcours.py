# -*- coding: utf-8 -*-
"""Parcours E2E (spec 07 §5), Chromium en iPhone 13 (390 × 844) et desktop 1280 × 800."""

import time

import pytest

from tests.e2e.conftest import IPHONE, lecture

pytestmark = pytest.mark.e2e

FAUX_PARTAGE = """
  window.__partages = [];
  Object.defineProperty(navigator, 'share', { value: (d) => { window.__partages.push(d); return Promise.resolve(); } });
  Object.defineProperty(navigator, 'canShare', { value: () => false });
"""


def opacite(page, sel):
    return float(page.eval_on_selector(sel, "e => getComputedStyle(e).opacity"))


def test_parcours_complet_mobile(mobile):
    page = mobile
    page.add_init_script(FAUX_PARTAGE)
    page.goto("/")
    assert page.locator("#reveler").is_disabled()
    page.fill("#date", "12 mars 1991")
    page.fill("#heure", "04:37")
    page.click("#lieu")
    page.keyboard.type("L")
    page.wait_for_selector("#suggestions li:has-text('Lyon, France')")
    page.click("#suggestions li:has-text('Lyon, France')")
    assert page.locator("#reveler").is_enabled()

    t0 = time.monotonic()
    page.click("#reveler")
    page.wait_for_selector("#calcul:not([hidden])")
    assert "12 MARS 1991" in page.inner_text("#coordonnees") and "LYON" in page.inner_text("#coordonnees")
    page.wait_for_url("**/l/**", timeout=30000)
    assert time.monotonic() - t0 >= 6.6                         # cérémonie ≥ 6,6 s

    # séquence du héro (spec 01 §6.1) : la phrase n'est pas là à 1 s, elle est là à 7 s
    t1 = time.monotonic()
    page.wait_for_timeout(1000)
    assert opacite(page, ".hero-phrase") < 0.1
    assert opacite(page, ".eclipse") > 0
    page.wait_for_timeout(max(0, 3000 - (time.monotonic() - t1) * 1000))
    assert opacite(page, ".hero-phrase") < 0.5
    page.wait_for_timeout(max(0, 7500 - (time.monotonic() - t1) * 1000))
    assert opacite(page, ".hero-phrase") > 0.95 and opacite(page, ".descends") > 0.5

    # au défilement, les éclats s'allument
    eclat = page.locator(".eclat").first
    assert "on" not in (eclat.get_attribute("class") or "")
    eclat.scroll_into_view_if_needed()
    page.mouse.wheel(0, 200)
    page.wait_for_function("() => document.querySelector('.eclat').classList.contains('on')")
    # le bandeau s'épingle quand le héro a quitté l'écran
    page.evaluate("() => window.scrollTo(0, document.getElementById('hero').offsetHeight + 300)")
    page.wait_for_function("() => document.getElementById('bandeau').classList.contains('visible')")

    # carrousel : glisser change le point actif
    page.locator("#carte").scroll_into_view_if_needed()
    page.eval_on_selector("#carrousel", "c => c.scrollLeft = 286")
    page.wait_for_function("() => document.querySelectorAll('#points i')[1].classList.contains('on')")

    # partager (navigator.share simulé)
    page.click("#partager")
    page.wait_for_function("() => window.__partages.length === 1")
    partage = page.evaluate("window.__partages[0]")
    assert "/c/" in partage["url"] and "d=" in partage["url"] and partage["text"]

    # activation + .ics
    assert page.locator("#activation .module-titre").inner_text().strip()
    with page.expect_download() as dl:
        page.click("a[href$='next.ics']")
    assert dl.value.suggested_filename == "ma-lune-noire.ics"

    # copier mon lien
    page.click("#copier-lien")
    lien = page.evaluate("navigator.clipboard.readText()")
    assert "/l/" in lien and lien.endswith(page.url.rsplit("/", 1)[1])
    assert not page.erreurs, page.erreurs


def test_sans_heure_puis_heure_retrouvee(navigateur, serveur):
    ctx = navigateur.new_context(**IPHONE, base_url=serveur, reduced_motion="reduce")
    page = ctx.new_page()
    page.goto("/")
    page.fill("#date", "2000-01-01")
    page.click("#bascule-heure")
    assert page.is_visible("#note-sans-heure") and page.is_visible("#sans-heure")
    page.click("#lieu")
    page.keyboard.type("Paris")
    page.wait_for_selector("#suggestions li:has-text('Paris, France')")
    page.click("#suggestions li:has-text('Paris, France')")
    page.click("#reveler")
    page.wait_for_url("**/l/**", timeout=30000)
    assert page.inner_text(".hero-signe").strip() == "SAGITTAIRE"
    assert page.is_visible(".note-heure")
    page.click("#ouvrir-heure")
    page.fill("#heure-retrouvee", "13:00")
    page.click("#heure-inline button[type=submit]")
    page.wait_for_function("() => document.querySelector('.hero-signe').textContent.includes('MAISON')")
    assert "MAISON VIII" in page.inner_text(".hero-signe")
    ctx.close()


def test_seconde_visite_sans_sequence(mobile, serveur):
    token = lecture(serveur)["token"]
    mobile.goto(f"/l/{token}")
    mobile.wait_for_timeout(300)
    mobile.goto(f"/l/{token}")
    mobile.wait_for_timeout(450)
    assert "vu" in mobile.get_attribute("body", "class")
    assert opacite(mobile, ".hero-phrase") == 1


def test_mouvement_reduit(navigateur, serveur):
    token = lecture(serveur)["token"]
    ctx = navigateur.new_context(**IPHONE, base_url=serveur, reduced_motion="reduce")
    page = ctx.new_page()
    page.goto(f"/l/{token}")
    page.wait_for_timeout(1000)
    assert opacite(page, ".hero-phrase") > 0.95                 # révélation complète en < 1 s
    ctx.close()


def test_desktop_colonne(navigateur, serveur):
    token = lecture(serveur)["token"]
    ctx = navigateur.new_context(viewport={"width": 1280, "height": 800}, base_url=serveur)
    page = ctx.new_page()
    for url in ("/", f"/l/{token}", f"/l/{token}/sanctuaire"):
        page.goto(url)
        assert page.eval_on_selector(".colonne", "e => e.getBoundingClientRect().width") == 390
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    ctx.close()


def test_feedback_verrouille(mobile, serveur):
    token = lecture(serveur)["token"]
    mobile.goto(f"/l/{token}")
    fb = mobile.locator(".hero .feedback")
    fb.locator(".feedback-vote").first.click()
    assert fb.locator(".feedback-merci").is_visible()
    mobile.reload()
    assert mobile.locator(".hero .feedback .feedback-merci").is_visible()
    assert not mobile.locator(".hero .feedback .feedback-vote").first.is_visible()


def test_effacement(mobile, serveur):
    token = lecture(serveur)["token"]
    mobile.goto(f"/l/{token}/effacer")
    mobile.click("#effacer-bouton")
    mobile.wait_for_selector("#efface:not([hidden])")
    assert "C'est fait." in mobile.inner_text("#efface")
    mobile.goto(f"/l/{token}")
    assert "ne mène à aucune Lune Noire" in mobile.inner_text("body")


def test_aucune_erreur_navigateur(mobile, serveur):
    """CSP stricte : ni script ni style en ligne ne doivent être bloqués."""
    token = lecture(serveur)["token"]
    for url in ("/", f"/l/{token}", f"/l/{token}/sanctuaire", f"/l/{token}/effacer",
                "/mentions", "/confidentialite"):
        mobile.goto(url)
        mobile.wait_for_timeout(200)
    assert not mobile.erreurs, mobile.erreurs
