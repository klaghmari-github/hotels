#!/usr/bin/env python3
"""
Simulateur hôtel (interface directeur).

  python run_user.py
  python run_user.py --host 127.0.0.1 --port 5056

Par défaut écoute sur 0.0.0.0:5056 (réseau local). Voir le README pour l'accès distant.
"""

from accor.user.app import main

if __name__ == "__main__":
    main()
