# -*- coding: utf-8 -*-
"""Recette automatisée (spec 07 §5) : accessibilité (axe-core) et performance."""

import os

import pytest

from tests.e2e.conftest import IPHONE, lecture

pytestmark = pytest.mark.e2e
AXE = os.path.join(os.path.dirname(__file__), "vendor", "axe.min.js")


def audit(page):
    page.add_script_tag(path=AXE)
    return page.evaluate("""async () => {
        const r = await axe.run(document, { resultTypes: ['violations'] });
        return r.violations.map(v => ({ id: v.id, impact: v.impact, n: v.nodes.length,
                                        cible: v.nodes[0] && v.nodes[0].target.join(' ') }));
    }""")


def test_accessibilite(navigateur, serveur):
    d = lecture(serveur)
    # axe s'injecte par un script : on contourne la CSP pour l'audit seulement
    ctx = navigateur.new_context(**IPHONE, base_url=serveur, bypass_csp=True, reduced_motion="reduce")
    page = ctx.new_page()
    graves = {}
    for url in ("/", f"/l/{d['token']}", f"/l/{d['token']}/sanctuaire", f"/c/{d['share_id']}",
                "/mentions", f"/l/{d['token']}/effacer"):
        page.goto(url)
        page.wait_for_timeout(1200)                      # séquences terminées (mouvement réduit)
        page.evaluate("() => document.querySelectorAll('.allume').forEach(e => e.classList.add('on'))")
        page.wait_for_timeout(600)                       # fin des fondus
        v = [x for x in audit(page) if x["impact"] in ("serious", "critical")]
        if v:
            graves[url] = v
    ctx.close()
    assert not graves, graves


def test_contraste_actionnables(navigateur, serveur):
    """Les éléments actionnables (liens, boutons) ont un contraste ≥ 4,5:1 (axe : color-contrast)."""
    d = lecture(serveur)
    ctx = navigateur.new_context(**IPHONE, base_url=serveur, bypass_csp=True, reduced_motion="reduce")
    page = ctx.new_page()
    page.goto(f"/l/{d['token']}")
    page.wait_for_timeout(1200)
    page.evaluate("() => document.querySelectorAll('.allume').forEach(e => e.classList.add('on'))")
    page.wait_for_timeout(600)
    page.add_script_tag(path=AXE)
    v = page.evaluate("""async () => {
        const r = await axe.run('a, button', { runOnly: ['color-contrast'] });
        return r.violations.flatMap(x => x.nodes.map(n => n.target.join(' ')));
    }""")
    ctx.close()
    assert not v, v


def test_poids_et_lcp_accueil(navigateur, serveur):
    """Accueil : < 400 Ko au total (polices comprises), LCP < 2 s (réseau local)."""
    ctx = navigateur.new_context(**IPHONE, base_url=serveur)
    page = ctx.new_page()
    total = []
    page.on("response", lambda r: total.append(len(r.body())) if r.ok else None)
    page.add_init_script("""
        window.__lcp = 0;
        new PerformanceObserver(l => { for (const e of l.getEntries()) window.__lcp = e.startTime; })
          .observe({ type: 'largest-contentful-paint', buffered: true });
    """)
    page.goto("/", wait_until="networkidle")
    page.wait_for_timeout(500)
    lcp = page.evaluate("() => window.__lcp")
    ctx.close()
    assert sum(total) < 400 * 1024, f"{sum(total) // 1024} Ko"
    assert 0 < lcp < 2000, lcp


def test_cls_revelation(navigateur, serveur):
    d = lecture(serveur)
    ctx = navigateur.new_context(**IPHONE, base_url=serveur)
    page = ctx.new_page()
    page.add_init_script("""
        window.__cls = 0;
        new PerformanceObserver(l => { for (const e of l.getEntries()) if (!e.hadRecentInput) window.__cls += e.value; })
          .observe({ type: 'layout-shift', buffered: true });
    """)
    page.goto(f"/c/{d['share_id']}", wait_until="networkidle")
    page.wait_for_timeout(800)
    cls = page.evaluate("() => window.__cls")
    page.goto("/", wait_until="networkidle")
    page.wait_for_timeout(800)
    cls_entree = page.evaluate("() => window.__cls")
    ctx.close()
    assert cls < 0.05 and cls_entree < 0.05, (cls, cls_entree)
