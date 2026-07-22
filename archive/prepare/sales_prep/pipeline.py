"""
Pipeline SalesPrep — étapes 1 → 5, étape 6 = holidays, jointure finale.

Étapes
------
1.a–1.c  Agrégats annuels
2.a–2.b  Mensuel brut + imputation mois manquants (moyennes → décimales possibles)
3.a–3.c  Catégories / sous-catégories wide + **pct** (inputs modèle)
4.a–4.c  Heure
5.a–5.c  Weekend
6        Jointure ``hotel_holidays_data`` (jours fériés / vacances scolaires)
7        Jointure finale des tables 2b+3c+4c+5c+holidays → ``hotel_sales_data.xlsx``

Note sur les décimales de ``nombre_ventes``
------------------------------------------
Les quantités brutes sont entières. Les valeurs à virgule apparaissent après
l'étape **2.b** : les mois hors plage [premier, dernier] sont imputés par la
**moyenne** des mois actifs (ex. 94/4 = 23.5). Ce n'est pas un bug d'import.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pandas as pd

from prepare.holidays_prep.prep import (
    ARRAY_COLS,
    dates_to_json_array,
    load_hotel_holidays,
    parse_json_array,
)
from prepare.sales_prep import aggregations as agg
from prepare._shared.columns import sanitize_dataframe_columns
from prepare._shared.sales_base import load_sales_frame

SALES_OUTPUT_XLSX = "hotel_sales_data.xlsx"
SALES_OUTPUT_PARQUET = "hotel_sales_data.parquet"
SALES_OUTPUT_CSV = "hotel_sales_data.csv"
SALES_JOINED_PARQUET = "joined.parquet"
SALES_JOINED_CSV = "joined.csv"

# Colonnes holidays (étape 6) — basées sur hotel_holidays_data, pas is_holiday raw
HOLIDAY_FEATURE_COLS = [
    "zone_scolaire",
    "departement",
    "nb_jours_feries",
    "nb_jours_vacances_scolaires",
    "nb_jours_vacances_hors_feries",
    "nb_jours_dans_mois",
    "jours_feries",
    "jours_vacances_scolaires",
    "jours_vacances_hors_feries",
]


class SalesPrep:
    """Préparation des ventes (consignes) + holidays + export Excel."""

    def __init__(
        self,
        sales_path: Path,
        output_dir: Path,
        rod_lookup: pd.DataFrame | None = None,
        holdout_year: int | None = None,
        feature_store_dir: Path | None = None,
        holidays_path: Path | None = None,
        holidays: pd.DataFrame | None = None,
        copy_to: Path | None = None,
    ) -> None:
        self.sales_path = Path(sales_path)
        self.output_dir = Path(output_dir)
        self.rod_lookup = rod_lookup
        self.holdout_year = holdout_year
        self.feature_store_dir = Path(feature_store_dir) if feature_store_dir else None
        self.holidays_path = Path(holidays_path) if holidays_path else None
        self.holidays = holidays
        self.copy_to = Path(copy_to) if copy_to else None
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._artifacts: dict[str, pd.DataFrame] = {}

    def run(self) -> pd.DataFrame:
        holdout = self.holdout_year
        if holdout is None:
            raw_all = load_sales_frame(self.sales_path, exclude_year=None)
            holdout = int(raw_all["annee"].max())
            self.holdout_year = holdout

        raw = load_sales_frame(self.sales_path, exclude_year=holdout)
        raw = self._attach_hotel_code(raw)

        # --- Étapes 1 à 5 ---
        s1a = self._attach_hotel_code(agg.step_1a_annual_raw(raw))
        s1b = self._attach_hotel_code(agg.step_1b_annual_normalized(s1a))
        s1c = self._attach_hotel_code(agg.step_1c_annual_divided_by_12(s1a))
        s2a = self._attach_hotel_code(agg.step_2a_monthly_raw(raw))
        s2b = self._attach_hotel_code(agg.step_2b_monthly_imputed(s2a))
        s3a = self._attach_hotel_code(agg.step_3a_category_monthly(raw))
        s3b = self._attach_hotel_code(agg.step_3b_category_imputed(s3a, s2a))
        s3c = self._attach_hotel_code(agg.step_3c_category_wide(s3b))  # + pcts
        s4a = self._attach_hotel_code(agg.step_4a_hourly(s3b, raw))
        s4b = self._attach_hotel_code(agg.step_4b_hourly_imputed(s4a, s2a))
        s4c = self._attach_hotel_code(agg.step_4c_hourly_wide(s4b))
        s5a = self._attach_hotel_code(agg.step_5a_weekend(raw))
        s5b = self._attach_hotel_code(agg.step_5b_weekend_imputed(s5a, s2a))
        s5c = self._attach_hotel_code(agg.step_5c_weekend_wide(s5b))

        # --- Étape 6 : holidays (plus d'agrégat is_holiday raw) ---
        # Jointure des tables ventes 2b+3c+4c+5c d'abord
        joined = self._join_all(
            [s2b, s3c, s4c, s5c],
            keys=["nom_hotel", "hotel_code", "annee", "mois"],
        )
        joined = self._attach_hotel_code(joined)
        # 6 = enrichissement calendrier holidays
        joined = self._attach_holidays(joined)
        s6 = joined[
            [
                c
                for c in ["nom_hotel", "hotel_code", "annee", "mois", *HOLIDAY_FEATURE_COLS]
                if c in joined.columns
            ]
        ].copy()

        self._artifacts = {
            "step_1a": s1a,
            "step_1b": s1b,
            "step_1c": s1c,
            "step_2a": s2a,
            "step_2b": s2b,
            "step_3a": s3a,
            "step_3b": s3b,
            "step_3c": s3c,
            "step_4a": s4a,
            "step_4b": s4b,
            "step_4c": s4c,
            "step_5a": s5a,
            "step_5b": s5b,
            "step_5c": s5c,
            "step_6_holidays": s6,
            "joined": joined,
        }
        self._persist()
        self._write_hotel_sales_data(joined)
        self._write_feature_store(joined)
        self._copy_to_accord(joined)
        return joined

    def _load_holidays(self) -> pd.DataFrame | None:
        if self.holidays is not None and not self.holidays.empty:
            frame = self.holidays.copy()
            for col in ARRAY_COLS:
                if col in frame.columns:
                    frame[col] = frame[col].map(
                        lambda v: v if isinstance(v, list) else parse_json_array(v)
                    )
            return frame
        if self.holidays_path is None:
            return None
        path = self.holidays_path
        if not path.exists() and path.is_dir():
            return None
        if path.is_dir():
            return load_hotel_holidays(path)
        if not path.exists():
            return None
        return load_hotel_holidays(path)

    def _attach_holidays(self, frame: pd.DataFrame) -> pd.DataFrame:
        """Étape 6 — joint ``hotel_holidays_data`` sur hotel_code × annee × mois."""
        if frame is None or frame.empty:
            return frame
        holidays = self._load_holidays()
        if holidays is None or holidays.empty:
            return frame

        keys = ["hotel_code", "annee", "mois"]
        if not all(k in frame.columns for k in keys):
            return frame
        if not all(k in holidays.columns for k in keys):
            return frame

        feat_cols = [c for c in HOLIDAY_FEATURE_COLS if c in holidays.columns]
        hol = holidays[keys + feat_cols].drop_duplicates(subset=keys)
        drop = [c for c in feat_cols if c in frame.columns]
        out = frame.drop(columns=drop) if drop else frame.copy()

        out = out.copy()
        hol = hol.copy()
        out["hotel_code"] = out["hotel_code"].astype(str)
        hol["hotel_code"] = hol["hotel_code"].astype(str)
        out["annee"] = pd.to_numeric(out["annee"], errors="coerce").astype("Int64")
        out["mois"] = pd.to_numeric(out["mois"], errors="coerce").astype("Int64")
        hol["annee"] = pd.to_numeric(hol["annee"], errors="coerce").astype("Int64")
        hol["mois"] = pd.to_numeric(hol["mois"], errors="coerce").astype("Int64")
        return out.merge(hol, on=keys, how="left")

    def _attach_hotel_code(self, frame: pd.DataFrame) -> pd.DataFrame:
        if frame is None or frame.empty:
            return frame
        out = frame.copy()
        if "hotel_code" in out.columns:
            out = out.drop(columns=["hotel_code"])
        if self.rod_lookup is None or self.rod_lookup.empty:
            out["hotel_code"] = pd.NA
            return out
        lookup = self.rod_lookup.copy()
        if "nom_hotel" not in lookup.columns and "name_ventes" in lookup.columns:
            lookup = lookup.rename(columns={"name_ventes": "nom_hotel"})
        if "nom_hotel" not in lookup.columns or "hotel_code" not in lookup.columns:
            out["hotel_code"] = pd.NA
            return out
        map_df = (
            lookup[["nom_hotel", "hotel_code"]]
            .dropna(subset=["nom_hotel"])
            .drop_duplicates(subset=["nom_hotel"])
        )
        map_df = map_df.copy()
        map_df["hotel_code"] = map_df["hotel_code"].apply(self._clean_code)
        if "nom_hotel" not in out.columns:
            out["hotel_code"] = pd.NA
            return out
        return out.merge(map_df, on="nom_hotel", how="left")

    @staticmethod
    def _clean_code(value: object) -> object:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return pd.NA
        text = str(value).strip()
        if not text or text.lower() in {"none", "nan", "null"}:
            return pd.NA
        return text

    @staticmethod
    def _join_all(tables: list[pd.DataFrame], keys: list[str]) -> pd.DataFrame:
        valid = [t for t in tables if not t.empty]
        if not valid:
            return pd.DataFrame(columns=keys)
        result = valid[0]
        for table in valid[1:]:
            join_keys = [k for k in keys if k in table.columns and k in result.columns]
            # Anti-doublons : ne garder de la table que les nouvelles colonnes
            new_cols = [c for c in table.columns if c not in result.columns or c in join_keys]
            result = result.merge(table[new_cols], on=join_keys, how="outer")
        result.columns = sanitize_dataframe_columns(list(result.columns))
        return result

    def _persist(self) -> None:
        meta = {
            "holdout_year": self.holdout_year,
            "steps": list(self._artifacts.keys()),
            "note_decimals": (
                "nombre_ventes peut être décimal après 2.b (imputation moyenne mois actifs)"
            ),
            "holidays_attached": self.holidays is not None
            or (self.holidays_path is not None and Path(self.holidays_path).exists()),
        }
        (self.output_dir / "meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        for name, df in self._artifacts.items():
            path = self.output_dir / f"{name}.parquet"
            df.to_parquet(path, index=False)
            csv_df = df.copy()
            for col in ARRAY_COLS:
                if col in csv_df.columns:
                    csv_df[col] = csv_df[col].map(
                        lambda v: dates_to_json_array(v)
                        if isinstance(v, (list, tuple))
                        else dates_to_json_array(parse_json_array(v))
                    )
            csv_df.to_csv(self.output_dir / f"{name}.csv", index=False)

    def _write_hotel_sales_data(self, joined: pd.DataFrame) -> None:
        if joined is None or joined.empty:
            return
        joined.to_parquet(self.output_dir / SALES_JOINED_PARQUET, index=False)
        joined.to_parquet(self.output_dir / SALES_OUTPUT_PARQUET, index=False)
        excel_df = joined.copy()
        for col in ARRAY_COLS:
            if col in excel_df.columns:
                excel_df[col] = excel_df[col].map(
                    lambda v: dates_to_json_array(v)
                    if isinstance(v, (list, tuple))
                    else dates_to_json_array(parse_json_array(v))
                )
        excel_df.to_csv(self.output_dir / SALES_JOINED_CSV, index=False)
        excel_df.to_csv(self.output_dir / SALES_OUTPUT_CSV, index=False)
        excel_df.to_excel(
            self.output_dir / SALES_OUTPUT_XLSX,
            index=False,
            sheet_name="hotel_sales",
        )

    def _copy_to_accord(self, joined: pd.DataFrame) -> None:
        """Copie propre de hotel_sales_data vers accord/data/."""
        if self.copy_to is None:
            return
        self.copy_to.mkdir(parents=True, exist_ok=True)
        src = self.output_dir / SALES_OUTPUT_XLSX
        if src.exists():
            shutil.copy2(src, self.copy_to / SALES_OUTPUT_XLSX)
        pq = self.output_dir / SALES_OUTPUT_PARQUET
        if pq.exists():
            shutil.copy2(pq, self.copy_to / SALES_OUTPUT_PARQUET)

    def _write_feature_store(self, joined: pd.DataFrame) -> None:
        if self.feature_store_dir is None or joined.empty:
            return
        if "hotel_code" not in joined.columns:
            return
        for hotel_code, group in joined.groupby("hotel_code", dropna=False):
            target = self.feature_store_dir / str(hotel_code) / "sales_prep"
            target.mkdir(parents=True, exist_ok=True)
            group.to_parquet(target / "monthly_features.parquet", index=False)

    @property
    def artifacts(self) -> dict[str, pd.DataFrame]:
        return dict(self._artifacts)
