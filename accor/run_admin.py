#!/usr/bin/env python3
"""
Point d'entree admin — Accor Data & Model Studio.

Usage (depuis la racine du projet, avec le venv active) :

    source .venv/bin/activate
    python run_admin.py
    python run_admin.py --host 0.0.0.0 --port 5055 --debug

    # ou entry point installé
    accor-admin
"""

from accor.app import main

if __name__ == "__main__":
    main()
