#!/usr/bin/env python3
"""
Point d'entrée user — simulateur ROD (directeur).

Depuis la racine du projet, venv activé :

  python run_user.py
  python run_user.py --host 0.0.0.0 --port 5056 --debug
  accor-user

Délègue à accor.user.app:main. Doc : README.md.
"""

from accor.user.app import main

if __name__ == "__main__":
    main()
