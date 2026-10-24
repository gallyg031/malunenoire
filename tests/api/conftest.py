import os

import pytest
from fastapi.testclient import TestClient

TEST_DB = os.environ.get("TEST_DATABASE_URL")
TABLES = "readings, activations, feedback, events, email_queue, purchases, geocache, ratelimit"


@pytest.fixture
def client(monkeypatch):
    import app.main as main
    monkeypatch.setattr(main, "DATABASE_URL", TEST_DB)
    monkeypatch.setitem(main.state, "db", TEST_DB is not None)
    with TestClient(main.app) as c:
        if TEST_DB:
            with main.db.pool.connection() as conn:
                conn.execute(f"truncate {TABLES} restart identity cascade")
        yield c


@pytest.fixture
def sql():
    """Requête directe sur la base de test."""
    import psycopg

    def run(q, *args):
        with psycopg.connect(TEST_DB, autocommit=True) as conn:
            cur = conn.execute(q, args)
            return cur.fetchall() if cur.description else cur.rowcount
    return run


needs_db = pytest.mark.skipif(not TEST_DB, reason="TEST_DATABASE_URL absent")
