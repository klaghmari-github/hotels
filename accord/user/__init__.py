"""
Package **User** — simulateur ROD pour directeurs d'hôtel.

Architecture
------------
* ``models``        — structures d'entrée / sortie (POO, dataclasses)
* ``reference``     — constantes Excel (``data/rod_reference.json``)
* ``rules``         — revenus · coûts · recommandation (séparés)
* ``services``      — catalogue admin, géocode, enrichissement, orchestrateur
* ``app``           — Flask API + UI wizard

Séparation volontaire revenus / coûts : l'étape IA future remplacera
uniquement le moteur de revenus, en réutilisant ``rules.costs``.
"""

__all__ = ["__version__"]
__version__ = "1.0.0"
