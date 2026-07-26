#!/usr/bin/env python3
"""
Point d'entree user — Simulateur ROD (directeur).

Usage (depuis la racine du projet, avec le venv active) :

    source .venv/bin/activate
    python run_user.py
    python run_user.py --host 0.0.0.0 --port 5056 --debug

    # ou entry point installé
    accor-user
"""

from accor.user.app import main

if __name__ == "__main__":
    main()
