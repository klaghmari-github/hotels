#!/usr/bin/env python3
"""Lance le serveur API REST de prédiction ROD-IA (indépendant de l'interface web)."""

from rod_ia.api.api_factory import run_api

if __name__ == "__main__":
    run_api(host="127.0.0.1", port=5002)