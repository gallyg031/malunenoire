# syntax=docker/dockerfile:1.7
# Ma Lune Noire — image Cloud Run (spec 06 §3).

ARG PY=python:3.12-slim

# --- dépendances (pyswisseph se compile : gcc nécessaire) ---------------------------
FROM ${PY} AS deps
RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt /tmp/
RUN pip install --no-cache-dir --root-user-action=ignore --prefix=/install -r /tmp/requirements.txt

# --- tests (pytest dans Linux, comme en CI) : docker compose run --rm tests -----------
FROM deps AS dev
COPY requirements-dev.txt /tmp/
RUN cp -r /install/. /usr/local/ \
    && pip install --no-cache-dir --root-user-action=ignore -r /tmp/requirements-dev.txt
WORKDIR /w

# --- base géographique GeoNames (spec 05 §5) ---------------------------------------
FROM ${PY} AS geo
WORKDIR /src
COPY scripts/build_geo.py scripts/
RUN mkdir -p data && python scripts/build_geo.py && rm -rf data/geonames

# --- image finale -------------------------------------------------------------------
FROM ${PY}
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8080 EPHE_PATH=/srv/data/ephe
COPY --from=deps /install /usr/local
WORKDIR /srv
COPY engine/ engine/
COPY app/ app/
COPY db/ db/
COPY data/ephe/ data/ephe/
# golden_prive.json (thèmes validés, privé) est inclus s'il est présent : le self-test du build le vérifie.
COPY tests/engine/golden*.json tests/engine/
COPY --from=geo /src/data/geo.sqlite /src/data/pays.json data/
RUN useradd --system --uid 10001 lune && python engine/selftest.py
USER lune
EXPOSE 8080
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers 1 --proxy-headers --forwarded-allow-ips='*'"]
