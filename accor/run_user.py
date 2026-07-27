#!/usr/bin/env python3
"""
Point d'entrée user — simulateur ROD (directeur).

Depuis la racine du projet, venv activé :

  python run_user.py                     # écoute 0.0.0.0:5056 (LAN + public)
  python run_user.py --host 127.0.0.1    # local uniquement
  python run_user.py --port 5056 --debug
  accor-user

Exposition publique : ouvrir le port routeur/firewall, ou tunnel
(cloudflared / ngrok). Voir README § Accès réseau.

Délègue à accor.user.app:main. Doc : README.md.
"""

from accor.user.app import main

if __name__ == "__main__":
    main()
