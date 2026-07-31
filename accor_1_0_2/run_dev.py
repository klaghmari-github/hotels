#!/usr/bin/env python3
"""
Point d'entrée — console Grok Web (Dev).

  python run_dev.py
  python run_dev.py --port 5500
  accor-dev

Écoute 0.0.0.0:**5500** par défaut (LAN + exposable ; watchdog gère ce port).
Interface web pour discuter avec Grok (headless) sur le projet.

Watchdog (garde l'app up, met à jour README) :
  python scripts/dev_watchdog.py
"""

from accor.dev_app import main

if __name__ == "__main__":
    main()
