#!/usr/bin/env python3
"""
Point d entree de l interface admin Accor Data and Model Studio.

Usage:
    cd accord
    python run_admin.py
    python run_admin.py --host 0.0.0.0 --port 5055 --debug

Delegue a app.main (serveur Flask de developpement).
Les logos marques sont sous data/marques et servis par
GET /api/marques/logos/<chemin relatif>.
Documentation complete: README.md.
"""

from archive.accor_1_0_5.accor_1_0_0.app import main

if __name__ == "__main__":
    main()
