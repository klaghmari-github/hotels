"""Pipeline SalesPrep — étapes 1 à 7 et jointure finale."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from prepare.sales_prep import aggregations as agg
from prepare._shared.columns import sanitize_dataframe_columns
from prepare._shared.sales_base import load_sales_frame


class SalesPrep:
    """Préparation des ventes selon consignes.txt (agrégations et imputations)."""

    def __init__(
        self,
        sales_path: Path,
        output_dir: Path,
        rod_lookup: pd.DataFrame | None = None,
        holdout_year: int | None = None,
        feature_store_dir: Path | None = None,
    ) -> None:
        self.sales_path = Path(sales_path)
        self.output_dir = Path(output_dir)
        self.rod_lookup = rod_lookup
        self.holdout_year = holdout_year
        self.feature_store_dir = Path(feature_store_dir) if feature_store_dir else None
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._artifacts: dict[str, pd.DataFrame] = {}

    def run(self) -> pd.DataFrame:
        holdout = self.holdout_year
        if holdout is None:
            raw_all = load_sales_frame(self.sales_path, exclude_year=None)
            holdout = int(raw_all["annee"].max())

        raw = load_sales_frame(self.sales_path, exclude_year=holdout)
        # Les agrégations groupent par nom_hotel uniquement ; hotel_code
        # est ré-attaché après chaque table (code Accor RodPrep, jamais le nom).
        raw = self._attach_hotel_code(raw)

        s1a = self._attach_hotel_code(agg.step_1a_annual_raw(raw))
        s1b = self._attach_hotel_code(agg.step_1b_annual_normalized(s1a))
        s1c = self._attach_hotel_code(agg.step_1c_annual_divided_by_12(s1a))
        s2a = self._attach_hotel_code(agg.step_2a_monthly_raw(raw))
        s2b = self._attach_hotel_code(agg.step_2b_monthly_imputed(s2a))
        s3a = self._attach_hotel_code(agg.step_3a_category_monthly(raw))
        s3b = self._attach_hotel_code(agg.step_3b_category_imputed(s3a, s2a))
        s3c = self._attach_hotel_code(agg.step_3c_category_wide(s3b))
        s4a = self._attach_hotel_code(agg.step_4a_hourly(s3b, raw))
        s4b = self._attach_hotel_code(agg.step_4b_hourly_imputed(s4a, s2a))
        s4c = self._attach_hotel_code(agg.step_4c_hourly_wide(s4b))
        s5a = self._attach_hotel_code(agg.step_5a_weekend(raw))
        s5b = self._attach_hotel_code(agg.step_5b_weekend_imputed(s5a, s2a))
        s5c = self._attach_hotel_code(agg.step_5c_weekend_wide(s5b))
        s6a = self._attach_hotel_code(agg.step_6a_holiday(raw))
        s6b = self._attach_hotel_code(agg.step_6b_holiday_imputed(s6a, s2a))
        s6c = self._attach_hotel_code(agg.step_6c_holiday_wide(s6b))

        joined = self._join_all(
            [s2b, s3c, s4c, s5c, s6c],
            keys=["nom_hotel", "hotel_code", "annee", "mois"],
        )
        joined = self._attach_hotel_code(joined)

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
            "step_6a": s6a,
            "step_6b": s6b,
            "step_6c": s6c,
            "joined": joined,
        }
        self._persist()
        self._write_feature_store(joined)
        return joined

    def _attach_hotel_code(self, frame: pd.DataFrame) -> pd.DataFrame:
        """Attache le code Accor RodPrep via ``nom_hotel``.

        Ne remplit **jamais** ``hotel_code`` avec le nom de l'hôtel : le vrai
        code est dans les sorties RodPrep (``code_h`` → ``hotel_code``).
        """
        if frame is None or frame.empty:
            return frame
        out = frame.copy()
        if "hotel_code" in out.columns:
            # Retirer d'éventuels faux codes (= noms) avant re-jointure
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
        # Normaliser codes vides → NA (pas de string "None")
        map_df = map_df.copy()
        map_df["hotel_code"] = map_df["hotel_code"].apply(self._clean_code)

        if "nom_hotel" not in out.columns:
            out["hotel_code"] = pd.NA
            return out

        merged = out.merge(map_df, on="nom_hotel", how="left")
        return merged

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
            result = result.merge(table, on=join_keys, how="outer")
        result.columns = sanitize_dataframe_columns(list(result.columns))
        return result

    def _persist(self) -> None:
        meta = {"holdout_year": self.holdout_year, "steps": list(self._artifacts.keys())}
        (self.output_dir / "meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        for name, df in self._artifacts.items():
            path = self.output_dir / f"{name}.parquet"
            df.to_parquet(path, index=False)
            df.to_csv(self.output_dir / f"{name}.csv", index=False)

    def _write_feature_store(self, joined: pd.DataFrame) -> None:
        if self.feature_store_dir is None or joined.empty:
            return
        if "hotel_code" not in joined.columns:
            return
        for hotel_code, group in joined.groupby("hotel_code", dropna=False):
            target = self.feature_store_dir / str(hotel_code) / "sales_prep"
            target.mkdir(parents=True, exist_ok=True)
            group.to_parquet(target / "monthly_features.parquet", index=False)
            group.to_csv(target / "monthly_features.csv", index=False)

    @property
    def artifacts(self) -> dict[str, pd.DataFrame]:
        return dict(self._artifacts)