# -*- coding: utf-8 -*-
"""Configuration par variables d'environnement (spec 06 §7, .env.example)."""

import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ENV = os.environ.get("ENV", "local")                     # local | preprod | prod
PROD = ENV == "prod"
DATABASE_URL = os.environ.get("DATABASE_URL")
EPHE_PATH = os.environ.get("EPHE_PATH", os.path.join(ROOT, "data", "ephe"))
BASE_URL = os.environ.get("BASE_URL", "https://malunenoire.fr")
GIT_SHA = os.environ.get("GIT_SHA", "dev")
# Sel des hachages (feedback, limites de débit). Obligatoire hors local.
FEEDBACK_SALT = os.environ.get("FEEDBACK_SALT", "sel-local-non-secret" if ENV == "local" else "")
