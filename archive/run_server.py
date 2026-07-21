#!/usr/bin/env python3
"""Lance l'interface simulateur pour les directeurs d'hôtel."""

from rod_ia.api.app_factory import run

if __name__ == "__main__":
    run(mode="user", port=5000)