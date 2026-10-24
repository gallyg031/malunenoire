"""E2E (spec 07 §5) : un vrai serveur uvicorn sur la base de test, piloté par Chromium."""

import os
import socket
import subprocess
import sys
import time

import httpx
import pytest

from tests.conftest import CORPUS_TEST, ROOT

TEST_DB = os.environ.get("TEST_DATABASE_URL")
PORT = 8099
BASE = f"http://127.0.0.1:{PORT}"
IPHONE = {"viewport": {"width": 390, "height": 844}, "device_scale_factor": 3, "is_mobile": True,
          "has_touch": True, "locale": "fr-FR", "timezone_id": "Europe/Paris"}

pytestmark = pytest.mark.skipif(not TEST_DB, reason="TEST_DATABASE_URL absent")


@pytest.fixture(scope="session")
def serveur():
    if not TEST_DB:
        pytest.skip("TEST_DATABASE_URL absent")
    env = {**os.environ, "DATABASE_URL": TEST_DB, "ENV": "local", "CORPUS_DIR": CORPUS_TEST}
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(PORT),
                             "--host", "127.0.0.1"], cwd=ROOT, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(100):
        try:
            if httpx.get(f"{BASE}/healthz", timeout=1).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.1)
    else:
        proc.kill()
        raise RuntimeError("le serveur de test ne démarre pas")
    yield BASE
    proc.terminate()
    proc.wait(5)


@pytest.fixture(scope="session")
def navigateur():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@pytest.fixture
def mobile(navigateur, serveur):
    ctx = navigateur.new_context(**IPHONE, base_url=serveur, accept_downloads=True)
    ctx.grant_permissions(["clipboard-read", "clipboard-write"], origin=serveur)
    erreurs = []
    ctx.on("weberror", lambda e: erreurs.append(str(e.error)))
    page = ctx.new_page()
    page.on("console", lambda m: erreurs.append(m.text) if m.type == "error" else None)
    page.erreurs = erreurs
    yield page
    ctx.close()


def lecture(serveur, **surcharges):
    """Crée une lecture par l'API (référence de Paris → sagittaire-08 du corpus de test)."""
    corps = {"date": "2000-01-01", "time": "13:00", "tz_user": "Europe/Paris",
             "place": {"name": "Paris, France", "lat": 48.8566, "lon": 2.3522, "tz": "Europe/Paris"}}
    corps.update(surcharges)
    r = httpx.post(f"{serveur}/api/reading", json=corps,
                   headers={"x-forwarded-for": f"10.7.{time.time_ns() % 250}.{time.time_ns() % 251}"},
                   timeout=30)
    r.raise_for_status()
    return r.json()
