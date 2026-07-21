"""Package ``prepare`` — pipeline de préparation des données modèle.

Architecture (RodPrep en premier, les autres consomment son output) ::

    RodPrep ──► MeteoPrep ──┐
            ├──► ProximityPrep ┼──► AllPrep → dataset_full
            └──► SalesPrep ───┘

Sous-packages importables :

- :mod:`prepare.rod_prep` — code Accor, noms, géoloc (source de vérité)
- :mod:`prepare.meteo_prep` — météo mensuelle sur ``hotel_lat``/``hotel_lon``
- :mod:`prepare.proximity_prep` — POI / plage sur les mêmes coords
- :mod:`prepare.sales_prep` — agrégations ventes + attache ``hotel_code``
- :mod:`prepare.all_prep` — jointure finale
- :mod:`prepare._shared` — utilitaires colonnes / mois / chargement ventes

Exemple ::

    from prepare import PreparePipeline, RodPrep, MeteoPrep, ProximityPrep, SalesPrep

    result = PreparePipeline().run(skip_meteo=False, skip_proximity=False)
    print(result.dataset_path)
"""

from __future__ import annotations

from prepare.all_prep import AllPrep
from prepare.meteo_prep import (
    HOTEL_IDENTITY_COLS as METEO_HOTEL_IDENTITY_COLS,
    MeteoPrep,
    MonthlyWeather,
)
from prepare.paths import PACKAGE_DIR, PROJECT_ROOT, PreparePaths, default_paths
from prepare.pipeline import PreparePipeline, PrepareResult, run_pipeline
from prepare.proximity_prep import (
    HOTEL_IDENTITY_COLS as PROXIMITY_HOTEL_IDENTITY_COLS,
    ProximityPrep,
)
from prepare.rod_prep import RodPrep
from prepare.sales_prep import SalesPrep

__all__ = [
    "AllPrep",
    "METEO_HOTEL_IDENTITY_COLS",
    "MeteoPrep",
    "MonthlyWeather",
    "PACKAGE_DIR",
    "PROJECT_ROOT",
    "PROXIMITY_HOTEL_IDENTITY_COLS",
    "PreparePaths",
    "PreparePipeline",
    "PrepareResult",
    "ProximityPrep",
    "RodPrep",
    "SalesPrep",
    "default_paths",
    "run_pipeline",
]

__version__ = "0.2.0"
