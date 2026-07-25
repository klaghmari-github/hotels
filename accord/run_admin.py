#!/usr/bin/env python3
"""
Point d'entrée CLI d'**Accor · Data & Model Studio** (admin).

Usage
-----
    cd accord
    python run_admin.py
    python run_admin.py --host 0.0.0.0 --port 5055 --debug

Délègue entièrement à :func:`app.main` (serveur Flask de développement).

Chemins logos
-------------
Les logos sont sous ``accord/data/marques/{categorie}/{slug}.png``.
``hotel_brand_data.xlsx`` stocke un chemin **relatif** à ce dossier
(ex. ``economy/ibis.png``), servi par
``GET /api/marques/logos/<path>`` — résolution ancrée sur le répertoire
de ``app.py`` (pas sur le cwd du shell).
"""

from app import main

if __name__ == "__main__":
    main()
