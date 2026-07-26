#!/usr/bin/env python3
"""
Point d'entrée admin — Accor Data & Model Studio.

Depuis la racine du projet, venv activé :

  python run_admin.py
  python run_admin.py --host 0.0.0.0 --port 5055 --debug
  accor-admin

Délègue à accor.app:main. Doc : README.md.
"""

from accor.app import main

if __name__ == "__main__":
    main()
