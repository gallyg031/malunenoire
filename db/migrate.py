# -*- coding: utf-8 -*-
"""
migrate.py — applique db/migrations/*.sql dans l'ordre, une seule fois chacune.

Idempotent : la table schema_migrations garde les fichiers appliqués ; un verrou
consultatif évite que deux conteneurs migrent en même temps.

Usage : DATABASE_URL=… python db/migrate.py
"""

import os
import sys

import psycopg

HERE = os.path.dirname(os.path.abspath(__file__))
MIGRATIONS = os.path.join(HERE, "migrations")
LOCK_ID = 4_242_424_242


def pending(conn):
    conn.execute("""create table if not exists schema_migrations (
        name text primary key, applied_at timestamptz not null default now())""")
    done = {r[0] for r in conn.execute("select name from schema_migrations")}
    files = sorted(f for f in os.listdir(MIGRATIONS) if f.endswith(".sql"))
    return [f for f in files if f not in done]


def migrate(database_url):
    """Renvoie la liste des migrations appliquées."""
    applied = []
    with psycopg.connect(database_url, autocommit=True) as conn:
        conn.execute("select pg_advisory_lock(%s)", (LOCK_ID,))
        try:
            for name in pending(conn):
                with open(os.path.join(MIGRATIONS, name), encoding="utf-8") as f:
                    sql = f.read()
                with conn.transaction():
                    conn.execute(sql)
                    conn.execute("insert into schema_migrations (name) values (%s)", (name,))
                applied.append(name)
        finally:
            conn.execute("select pg_advisory_unlock(%s)", (LOCK_ID,))
    return applied


if __name__ == "__main__":
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL manquant")
    for name in migrate(url):
        print("appliquée :", name)
    print("migrations à jour")
