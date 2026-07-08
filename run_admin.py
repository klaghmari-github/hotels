#!/usr/bin/env python3
"""Lance l'interface d'administration (exploration, interprétation, évaluation)."""

from rod_ia.api.app_factory import run

if __name__ == "__main__":
    run(mode="admin", port=5001)