"""AllPrep — jointure finale des sorties prepare."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from prepare._shared.columns import sanitize_dataframe_columns


class AllPrep:
    """Joint sales, météo et proximité sans dupliquer les lignes ventes."""

    def __init__(self, input_dir: Path, output_dir: Path) -> None:
        self.input_dir = Path(input_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _read(self, name: str) -> pd.DataFrame:
        path = self.input_dir / f"{name}.parquet"
        if not path.exists():
            return pd.DataFrame()
        return pd.read_parquet(path)

    def run(self) -> pd.DataFrame:
        sales = self._read("sales_joined")
        meteo = self._read("meteo_monthly")
        proximity = self._read("proximity")
        holidays = self._read("holidays_monthly")
        rod = self._read("rod_hotel_lookup")

        result = sales
        if not meteo.empty and not result.empty:
            keys = [k for k in ("hotel_code", "annee", "mois") if k in result.columns and k in meteo.columns]
            if keys:
                result = result.merge(meteo, on=keys, how="left", suffixes=("", "_meteo"))

        if not proximity.empty and not result.empty and "hotel_code" in result.columns:
            result = result.merge(proximity, on="hotel_code", how="left", suffixes=("", "_prox"))

        if not holidays.empty and not result.empty:
            keys = [
                k
                for k in ("hotel_code", "annee", "mois")
                if k in result.columns and k in holidays.columns
            ]
            if keys:
                # Ne garder que les compteurs (évite de dupliquer lat/lon/zone en conflit)
                hol_cols = keys + [
                    c
                    for c in (
                        "nb_jours_feries",
                        "nb_jours_vacances_scolaires",
                        "nb_jours_vacances_hors_feries",
                        "zone_scolaire",
                        "departement",
                    )
                    if c in holidays.columns and c not in keys
                ]
                result = result.merge(
                    holidays[hol_cols], on=keys, how="left", suffixes=("", "_hol")
                )

        if not rod.empty and not result.empty and "hotel_code" in result.columns:
            rod_keys = [c for c in rod.columns if c not in result.columns or c == "hotel_code"]
            result = result.merge(rod[rod_keys], on="hotel_code", how="left", suffixes=("", "_rod"))

        result.columns = sanitize_dataframe_columns(list(result.columns))
        result.to_parquet(self.output_dir / "dataset_full.parquet", index=False)
        result.to_csv(self.output_dir / "dataset_full.csv", index=False)
        return result
