"""Orchestrateur du pipeline prepare.

Ordre imposé (RodPrep en premier — source de vérité identité / codeH / géo) :

  1. RodPrep        → hotel_lookup (hotel_code Accor, lat/lon, nom_hotel, …)
  2. MeteoPrep      ← hotel_lookup (coords)
  3. ProximityPrep  ← hotel_lookup (coords + code Accor)
  4. SalesPrep      ← nom_hotel ↔ hotel_code (lookup RodPrep)
  5. AllPrep        ← jointure des sorties

Usage :

```python
from prepare import PreparePipeline

result = PreparePipeline().run(skip_meteo=True, skip_proximity=True)
```
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from prepare.all_prep import AllPrep
from prepare.meteo_prep import MeteoPrep
from prepare.paths import PreparePaths, default_paths
from prepare.proximity_prep import ProximityPrep
from prepare.rod_prep import RodPrep
from prepare.sales_prep import SalesPrep
from rod_ia.config.settings import Settings, get_settings


@dataclass
class PrepareResult:
    """Sorties agrégées d'un run pipeline."""

    hotel_lookup: pd.DataFrame
    meteo: pd.DataFrame | None
    proximity: pd.DataFrame | None
    sales_joined: pd.DataFrame
    dataset_full: pd.DataFrame
    paths: PreparePaths
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def dataset_path(self) -> Path:
        return self.paths.all_output / "dataset_full.parquet"


class PreparePipeline:
    """Pipeline complet prepare/ — RodPrep alimente les étapes suivantes."""

    def __init__(
        self,
        paths: PreparePaths | None = None,
        settings: Settings | None = None,
        *,
        holdout_year: int = 2026,
    ) -> None:
        self.paths = paths or default_paths()
        self.settings = settings or get_settings()
        self.holdout_year = holdout_year

    # ------------------------------------------------------------------
    # Étapes unitaires (utilisables séparément / notebooks)
    # ------------------------------------------------------------------

    def run_rod(self, *, geocode_missing: bool = True) -> pd.DataFrame:
        """Étape 1 — source de vérité identité hôtel + code Accor + géo."""
        rod = RodPrep(self.paths.rod_input, self.paths.rod_output, settings=self.settings)
        rod.seed_input_from_sources()
        return rod.run(geocode_missing=geocode_missing)

    def run_meteo(
        self,
        rod_output: Path | None = None,
        *,
        target_years: tuple[int, ...] | None = None,
    ) -> pd.DataFrame:
        """Étape 2 — météo mensuelle sur coords RodPrep."""
        years = target_years
        if years is None:
            current = datetime.utcnow().year
            years = tuple(range(current - 3, current + 1))
        meteo = MeteoPrep(
            self.paths.meteo_input,
            self.paths.meteo_output,
            target_years=years,
        )
        meteo.fill_input_from_rod(rod_output or self.paths.rod_output)
        return meteo.run()

    def run_proximity(self, rod_output: Path | None = None) -> pd.DataFrame:
        """Étape 3 — POI / plage sur coords RodPrep (code Accor)."""
        prox = ProximityPrep(
            self.paths.proximity_input,
            self.paths.proximity_output,
            settings=self.settings,
        )
        prox.fill_input_from_rod(rod_output or self.paths.rod_output)
        return prox.run()

    def run_sales(self, hotel_lookup: pd.DataFrame) -> pd.DataFrame:
        """Étape 4 — agrégations ventes + attache hotel_code Accor."""
        sales_path = self.settings.sales_csv_path
        self.paths.sales_input.mkdir(parents=True, exist_ok=True)
        sales_input_copy = self.paths.sales_input / "ventes.csv"
        if not sales_input_copy.exists() and sales_path.exists():
            sales_input_copy.write_bytes(sales_path.read_bytes())

        lookup_cols = hotel_lookup[["nom_hotel", "hotel_code"]].drop_duplicates()
        sales = SalesPrep(
            sales_path=sales_path,
            output_dir=self.paths.sales_output,
            rod_lookup=lookup_cols,
            holdout_year=self.holdout_year,
            feature_store_dir=self.settings.feature_store_dir,
        )
        return sales.run()

    def run_all(
        self,
        *,
        hotel_lookup: pd.DataFrame,
        sales_joined: pd.DataFrame,
        meteo: pd.DataFrame | None = None,
        proximity: pd.DataFrame | None = None,
    ) -> pd.DataFrame:
        """Étape 5 — jointure finale sur hotel_code (et annee/mois si dispo)."""
        self.paths.all_input.mkdir(parents=True, exist_ok=True)
        sales_joined.to_parquet(
            self.paths.all_input / "sales_joined.parquet", index=False
        )
        hotel_lookup.to_parquet(
            self.paths.all_input / "rod_hotel_lookup.parquet", index=False
        )
        if meteo is not None and not meteo.empty:
            meteo.to_parquet(
                self.paths.all_input / "meteo_monthly.parquet", index=False
            )
        if proximity is not None and not proximity.empty:
            proximity.to_parquet(
                self.paths.all_input / "proximity.parquet", index=False
            )
        return AllPrep(self.paths.all_input, self.paths.all_output).run()

    # ------------------------------------------------------------------
    # Pipeline complet
    # ------------------------------------------------------------------

    def run(
        self,
        *,
        skip_meteo: bool = False,
        skip_proximity: bool = False,
        geocode_missing: bool = True,
        meteo_years: tuple[int, ...] | None = None,
    ) -> PrepareResult:
        """Exécute le pipeline dans l'ordre Rod → Meteo → Proximity → Sales → All."""
        print("[prepare] Step 1 — RodPrep")
        hotel_lookup = self.run_rod(geocode_missing=geocode_missing)
        n_codes = hotel_lookup["hotel_code"].notna().sum() if "hotel_code" in hotel_lookup.columns else 0
        print(f"  → {len(hotel_lookup)} hôtels ({n_codes} avec hotel_code Accor)")

        meteo_frame: pd.DataFrame | None = None
        if not skip_meteo:
            print("[prepare] Step 2 — MeteoPrep")
            meteo_frame = self.run_meteo(target_years=meteo_years)
            years = sorted(meteo_frame["annee"].unique().tolist()) if not meteo_frame.empty and "annee" in meteo_frame.columns else []
            print(f"  → {len(meteo_frame)} lignes météo (années {years})")
        else:
            print("[prepare] Step 2 — MeteoPrep (skip)")

        prox_frame: pd.DataFrame | None = None
        if not skip_proximity:
            print("[prepare] Step 3 — ProximityPrep")
            prox_frame = self.run_proximity()
            print(f"  → {len(prox_frame)} hôtels proximité")
        else:
            print("[prepare] Step 3 — ProximityPrep (skip)")

        print("[prepare] Step 4 — SalesPrep")
        sales_joined = self.run_sales(hotel_lookup)
        print(f"  → {len(sales_joined)} lignes jointes ventes")

        print("[prepare] Step 5 — AllPrep")
        dataset = self.run_all(
            hotel_lookup=hotel_lookup,
            sales_joined=sales_joined,
            meteo=meteo_frame,
            proximity=prox_frame,
        )
        print(f"[prepare] Terminé — dataset final : {len(dataset)} lignes")
        print(f"[prepare] Sortie : {self.paths.all_output / 'dataset_full.parquet'}")

        return PrepareResult(
            hotel_lookup=hotel_lookup,
            meteo=meteo_frame,
            proximity=prox_frame,
            sales_joined=sales_joined,
            dataset_full=dataset,
            paths=self.paths,
            meta={
                "skip_meteo": skip_meteo,
                "skip_proximity": skip_proximity,
                "holdout_year": self.holdout_year,
                "n_hotels": len(hotel_lookup),
                "n_sales_rows": len(sales_joined),
                "n_dataset_rows": len(dataset),
            },
        )


def run_pipeline(
    *,
    skip_meteo: bool = False,
    skip_proximity: bool = False,
    holdout_year: int = 2026,
    geocode_missing: bool = True,
) -> PrepareResult:
    """Point d'entrée fonctionnel (équivalent CLI ``run_prepare.py``)."""
    return PreparePipeline(holdout_year=holdout_year).run(
        skip_meteo=skip_meteo,
        skip_proximity=skip_proximity,
        geocode_missing=geocode_missing,
    )
