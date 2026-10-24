# -*- coding: utf-8 -*-
"""Connexion PostgreSQL (Neon) : un pool par processus, ouvert au démarrage."""

from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

pool = None


def open_pool(database_url):
    global pool
    # Neon met la base en veille : on vérifie la connexion avant de la prêter.
    pool = ConnectionPool(database_url, min_size=0, max_size=5, open=True,
                          check=ConnectionPool.check_connection,
                          kwargs={"autocommit": True})
    return pool


def close_pool():
    global pool
    if pool is not None:
        pool.close()
        pool = None


def ping():
    with pool.connection() as conn:
        return conn.execute("select 1").fetchone()[0] == 1


def limite(conn, key, nombre, fenetre_s):
    """Compte une demande pour `key` dans la fenêtre fixe courante ; False au-delà de `nombre`."""
    row = conn.execute(
        """insert into ratelimit (key, bucket, count)
           values (%s, to_timestamp(floor(extract(epoch from now()) / %s) * %s), 1)
           on conflict (key, bucket) do update set count = ratelimit.count + 1
           returning count""", (key, fenetre_s, fenetre_s)).fetchone()
    return row[0] <= nombre


class GeoCache:
    """Table geocache (spec 05 §5), entrées valables 30 jours."""

    def get(self, q):
        with pool.connection() as conn:
            row = conn.execute("""select results from geocache
                                  where q = %s and created_at > now() - interval '30 days'""",
                               (q,)).fetchone()
        return row[0] if row else None

    def put(self, q, results):
        with pool.connection() as conn:
            conn.execute("""insert into geocache (q, results) values (%s, %s)
                            on conflict (q) do update set results = excluded.results,
                                                         created_at = now()""",
                         (q, Jsonb(results)))
