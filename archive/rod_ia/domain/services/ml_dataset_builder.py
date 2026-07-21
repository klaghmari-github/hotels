"""Assemblage du dataset ML wide avec préfixes ``d_`` et ``t_``."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from rod_ia.domain.repositories.identity_registry import HotelIdentityRegistry
from rod_ia.domain.services.ml_column_naming import INFO_COLUMNS, MLColumnNaming
from rod_ia.domain.services.sales_mix_extractor import SalesMixExtractor
from rod_ia.domain.services.sales_percentage_service import SalesPercentageService


class MLDatasetBuilder:
    """Construit le dataset d'entraînement à partir des ventes et du registre."""

    def __init__(
        self,
        sales_path: Path,
        identity_registry: HotelIdentityRegistry,
        output_dir: Path,
    ) -> None:
        self.sales_path = sales_path
        self.identity_registry = identity_registry
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def build(self, exclude_year: int = 2026) -> pd.DataFrame:
        extractor = SalesMixExtractor(self.sales_path, self.identity_registry)
        monthly_avg = extractor.monthly_average_targets(exclude_year=exclude_year)

        pct_service = SalesPercentageService(monthly_avg)
        pct_wide, _ = pct_service.compute_all()
        targets_wide = self._targets_to_wide(monthly_avg)

        dataset = targets_wide.merge(pct_wide, on="hotel_id", how="left")
        dataset = self._attach_info_columns(dataset)

        feature_cols = MLColumnNaming.feature_columns(dataset.columns)
        target_cols = MLColumnNaming.target_columns(dataset.columns)
        MLColumnNaming.assert_no_target_leakage(feature_cols)

        manifest = MLColumnNaming.build_manifest(dataset.columns, source="ml_dataset_builder")
        manifest_path = self.output_dir / "column_manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

        dataset.to_csv(self.output_dir / "ml_dataset_full.csv", index=False)
        dataset[feature_cols].to_csv(self.output_dir / "X_descriptive.csv", index=False)
        dataset[target_cols].to_csv(self.output_dir / "y_targets.csv", index=False)

        meta = {
            "n_rows": len(dataset),
            "n_features": len(feature_cols),
            "n_targets": len(target_cols),
            "feature_cols": feature_cols,
            "target_cols": target_cols,
        }
        (self.output_dir / "dataset_meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return dataset

    def _targets_to_wide(self, monthly_avg: pd.DataFrame) -> pd.DataFrame:
        buckets: dict[str, dict] = {}
        for _, row in monthly_avg.iterrows():
            hotel_id = str(row["hotel_id"])
            month = int(row["month"])
            type_label = str(row["TYPE"])
            gamme = str(row["GAMME"])
            entry = buckets.setdefault(hotel_id, {"hotel_id": hotel_id})
            entry[
                MLColumnNaming.target_month_type_gamme(month, type_label, gamme, "montant")
            ] = float(row["avg_montant"])
            entry[
                MLColumnNaming.target_month_type_gamme(month, type_label, gamme, "nbr_ventes")
            ] = float(row["avg_nbr_ventes"])
        if not buckets:
            return pd.DataFrame(columns=["hotel_id"])
        return pd.DataFrame(buckets.values()).fillna(0.0)

    def _attach_info_columns(self, dataset: pd.DataFrame) -> pd.DataFrame:
        info_rows = []
        for hotel_id in dataset["hotel_id"].unique():
            record = self.identity_registry.get(hotel_id)
            if not record:
                continue
            info_rows.append(
                {
                    "hotel_id": hotel_id,
                    "name_display": record.name_display,
                    "name_ventes": record.name_ventes,
                    "name_rod": record.name_rod,
                    "city": record.city,
                    "brand": record.brand,
                    "lat": record.lat_canonical,
                    "lon": record.lon_canonical,
                    "geo_source": record.geo_source,
                }
            )
        if not info_rows:
            return dataset
        info_frame = pd.DataFrame(info_rows)
        merged = dataset.merge(info_frame, on="hotel_id", how="left")
        for col in INFO_COLUMNS:
            if col not in merged.columns:
                continue
        return merged