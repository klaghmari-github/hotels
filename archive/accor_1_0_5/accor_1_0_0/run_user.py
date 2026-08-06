#!/usr/bin/env python3
"""
Point d'entrée **User** — Simulateur ROD (interface directeur).

Usage
-----
    cd accord
    python run_user.py
    python run_user.py --host 0.0.0.0 --port 5056 --debug

Parcours
--------
1. Saisie interactive (identité, services, profil clients, corner)
2. Enrichissement auto (géocode, weather, proximity, holidays)
3. Simulation revenus (règles Excel ROD — moteur déterministe)
4. Coûts (technos / annexes / agencement — séparés des revenus)
5. Marge nette + recommandation concept (SIMPLY / LIBERTY / CONNECTED)

Le moteur IA pourra plus tard remplacer uniquement l'étape revenus
en réutilisant le même calcul de coûts.
"""

from archive.accor_1_0_5.accor_1_0_0.user.app import main

if __name__ == "__main__":
    main()
