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
# Sel des hachages (feedback, limites de débit, signature des désinscriptions). Obligatoire hors local.
FEEDBACK_SALT = os.environ.get("FEEDBACK_SALT", "sel-local-non-secret" if ENV == "local" else "")

# Tâches planifiées (Cloud Scheduler → /cron/*, en-tête X-Cron-Secret)
CRON_SECRET = os.environ.get("CRON_SECRET", "cron-local" if ENV == "local" else "")

# E-mails (spec 06 §5, §7) : local → journal ; preprod → tout vers EMAIL_REDIRECT ; prod → Resend
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
EMAIL_REDIRECT = os.environ.get("EMAIL_REDIRECT", "")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "")
EMAIL_PLAFOND = int(os.environ.get("EMAIL_PLAFOND", "90"))     # Resend gratuit : 100/jour

# Phase 1.5 — paiement (désactivé tant que PAIEMENT=on n'est pas posé : prix, compte Stripe et
# mentions légales à valider par Constance). Prix en centimes (D13, indicatifs).
PAIEMENT_ACTIF = os.environ.get("PAIEMENT", "off") == "on"
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
PRIX = {"lecture": 700, "calendrier": 500, "bundle": 1000}
