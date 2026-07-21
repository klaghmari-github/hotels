"""AllPrep — jointure de **toutes** les sorties prepare → ``hotel_sales_data``.

Grain principal : ``hotel_code × annee × mois`` (lignes ventes).

Ordre de jointure (left = ventes) :
  1. sales_joined          (base, déjà enrichie holidays si SalesPrep l'a fait)
  2. hotel_holidays_data   (compteurs + arrays de jours) — hotel_code, annee, mois
  3. meteo_monthly         — hotel_code, annee, mois
  4. proximity             — hotel_code
  5. rod_hotel_lookup      — hotel_code

**Aucun doublon de colonnes** : une colonne déjà présente à gauche n'est pas
ré-ajoutée (pas de suffixes ``_x``/``_y``/``_prox``).
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import pandas as pd

from prepare._shared.columns import sanitize_dataframe_columns
from prepare._shared.join import drop_duplicate_named_columns, merge_no_duplicate_columns
from prepare.holidays_prep.prep import (
    ARRAY_COLS,
    dates_to_json_array,
    load_hotel_holidays,
    parse_json_array,
)

# Sortie canonique = jointure complète
HOTEL_SALES_XLSX = "hotel_sales_data.xlsx"
HOTEL_SALES_PARQUET = "hotel_sales_data.parquet"
HOTEL_SALES_CSV = "hotel_sales_data.csv"
DATASET_FULL_PARQUET = "dataset_full.parquet"
DATASET_FULL_CSV = "dataset_full.csv"

HOLIDAY_FEATURE_COLS = [
    "zone_scolaire",
    "departement",
    "commune",
    "localisation",
    "nb_jours_feries",
    "nb_jours_vacances_scolaires",
    "nb_jours_vacances_hors_feries",
    "nb_jours_dans_mois",
    "jours_feries",
    "jours_vacances_scolaires",
    "jours_vacances_hors_feries",
]


class AllPrep:
    """Assemble ventes + holidays + météo + proximité + ROD sans colonnes en double."""

    def __init__(self, input_dir: Path, output_dir: Path) -> None:
        self.input_dir = Path(input_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _read_parquet(self, *names: str) -> pd.DataFrame:
        for name in names:
            path = self.input_dir / f"{name}.parquet"
            if path.exists():
                return pd.read_parquet(path)
        return pd.DataFrame()

    def _read_holidays(self) -> pd.DataFrame:
        """Charge hotel_holidays_data (arrays inclus), plusieurs noms possibles."""
        candidates = [
            self.input_dir / "hotel_holidays_data.parquet",
            self.input_dir / "holidays_monthly.parquet",
            self.input_dir / "hotel_holidays_data.xlsx",
        ]
        for path in candidates:
            if path.exists():
                try:
                    frame = load_hotel_holidays(path)
                    return frame
                except Exception:
                    if path.suffix == ".parquet":
                        return pd.read_parquet(path)
        return pd.DataFrame()

    def run(self) -> pd.DataFrame:
        sales = self._read_parquet("sales_joined", "hotel_sales_data")
        holidays = self._read_holidays()
        meteo = self._read_parquet("meteo_monthly")
        proximity = self._read_parquet("proximity")
        rod = self._read_parquet("rod_hotel_lookup")

        if sales.empty:
            # Fallback : rien à joindre
            empty = pd.DataFrame()
            self._write_outputs(empty)
            return empty

        result = drop_duplicate_named_columns(sales)

        # --- Holidays (prioritaire pour arrays + compteurs) ---
        if not holidays.empty:
            keys = ["hotel_code", "annee", "mois"]
            if all(k in holidays.columns for k in keys):
                feat = [c for c in HOLIDAY_FEATURE_COLS if c in holidays.columns]
                hol = holidays[keys + feat].copy()
                # Si sales a déjà des colonnes holidays (SalesPrep), on les
                # remplace par la version hotel_holidays_data (source de vérité).
                replace = [c for c in feat if c in result.columns]
                if replace:
                    result = result.drop(columns=replace)
                result = merge_no_duplicate_columns(result, hol, on=keys, how="left")

        # --- Météo ---
        if not meteo.empty:
            keys = ["hotel_code", "annee", "mois"]
            # Ne pas ramener hotel_name / lat depuis météo si déjà présents
            result = merge_no_duplicate_columns(result, meteo, on=keys, how="left")

        # --- Proximité (statique par hôtel) ---
        if not proximity.empty and "hotel_code" in proximity.columns:
            result = merge_no_duplicate_columns(
                result, proximity, on=["hotel_code"], how="left"
            )

        # --- ROD lookup (attributs hôtel / d_recap_*) ---
        if not rod.empty and "hotel_code" in rod.columns:
            result = merge_no_duplicate_columns(
                result, rod, on=["hotel_code"], how="left"
            )

        result = drop_duplicate_named_columns(result)
        # Sanitize noms (apostrophes, %) — les arrays de jours restent intacts
        # car déjà en snake_case.
        result.columns = sanitize_dataframe_columns(list(result.columns))
        result = drop_duplicate_named_columns(result)

        # Re-parse arrays si le sanitize/Excel path a stringifié (parquet garde list)
        for col in ARRAY_COLS:
            if col in result.columns:
                result[col] = result[col].map(
                    lambda v: v
                    if isinstance(v, list)
                    else (
                        list(v)
                        if isinstance(v, tuple)
                        else parse_json_array(v)
                    )
                )

        self._write_outputs(result)
        return result


    def _write_outputs(self, frame: pd.DataFrame) -> None:
        """Écrit hotel_sales_data (jointure complète) + dataset_full (alias)."""
        if frame is None:
            frame = pd.DataFrame()

        # Parquet : listes natives pour arrays
        frame.to_parquet(self.output_dir / HOTEL_SALES_PARQUET, index=False)
        frame.to_parquet(self.output_dir / DATASET_FULL_PARQUET, index=False)

        excel_df = frame.copy()
        for col in ARRAY_COLS:
            if col in excel_df.columns:
                excel_df[col] = excel_df[col].map(
                    lambda v: dates_to_json_array(v)
                    if isinstance(v, (list, tuple))
                    else dates_to_json_array(parse_json_array(v))
                )

        excel_df.to_csv(self.output_dir / HOTEL_SALES_CSV, index=False)
        excel_df.to_csv(self.output_dir / DATASET_FULL_CSV, index=False)
        excel_df.to_excel(
            self.output_dir / HOTEL_SALES_XLSX,
            index=False,
            sheet_name="hotel_sales",
        )

    # --- API pour tests / notebooks ---
    @staticmethod
    def join_all(
        sales: pd.DataFrame,
        *,
        holidays: pd.DataFrame | None = None,
        meteo: pd.DataFrame | None = None,
        proximity: pd.DataFrame | None = None,
        rod: pd.DataFrame | None = None,
    ) -> pd.DataFrame:
        """Jointure pure en mémoire (mêmes règles que ``run``)."""
        prep = AllPrep(Path("."), Path("."))
        # Réutilise la logique via un mini input virtuel
        result = drop_duplicate_named_columns(sales)
        if holidays is not None and not holidays.empty:
            keys = ["hotel_code", "annee", "mois"]
            feat = [c for c in HOLIDAY_FEATURE_COLS if c in holidays.columns]
            if all(k in holidays.columns for k in keys):
                hol = holidays[keys + feat]
                replace = [c for c in feat if c in result.columns]
                if replace:
                    result = result.drop(columns=replace)
                result = merge_no_duplicate_columns(result, hol, on=keys, how="left")
        if meteo is not None and not meteo.empty:
            result = merge_no_duplicate_columns(
                result, meteo, on=["hotel_code", "annee", "mois"], how="left"
            )
        if proximity is not None and not proximity.empty:
            result = merge_no_duplicate_columns(
                result, proximity, on=["hotel_code"], how="left"
            )
        if rod is not None and not rod.empty:
            result = merge_no_duplicate_columns(
                result, rod, on=["hotel_code"], how="left"
            )
        return drop_duplicate_named_columns(result)
