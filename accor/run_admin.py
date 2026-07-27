#!/usr/bin/env python3
"""
Point d'entrée admin — Accor Data & Model Studio.

Depuis la racine du projet, venv activé :

  python run_admin.py                    # écoute 0.0.0.0:5055 (LAN + public)
  python run_admin.py --host 127.0.0.1   # local uniquement
  python run_admin.py --port 5055 --debug
  accor-admin

Exposition publique : ouvrir le port routeur/firewall, ou tunnel
(cloudflared / ngrok). Voir README § Accès réseau.

Délègue à accor.app:main. Doc : README.md.
"""

from accor.app import main

if __name__ == "__main__":
    main()
