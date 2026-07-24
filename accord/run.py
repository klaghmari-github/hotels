#!/usr/bin/env python3
"""
Point d'entrée CLI d'**Accord · Data & Model Studio**.

Usage
-----
    cd accord
    python run.py
    python run.py --host 0.0.0.0 --port 8080 --debug

Délègue entièrement à :func:`app.main` (serveur Flask de développement).

Ce module ne contient volontairement aucune logique métier : il permet de
lancer l'application avec ``python run.py`` depuis le répertoire ``accord/``.
"""

from app import main

if __name__ == "__main__":
    main()
