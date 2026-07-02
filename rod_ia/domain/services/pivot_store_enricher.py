"""Enrichit le feature store des hôtels pivots (références ROD + targets train)."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from rod_ia.domain.repositories.feature_store_repository import FeatureStoreRepository
from rod_ia.domain.repositories.identity_registry import HotelIdentityRegistry
from rod_ia.domain.repositories.reference_repository import ReferenceRepository
from rod_ia.domain.services.sales_targets_pipeline import SalesTargetsPipeline


class PivotStoreEnricher:
    """Persiste dans le feature store les données exploitées par le simulateur."""

    def __init__(
        self,
        identity_registry: HotelIdentityRegistry,
        reference_repository: ReferenceRepository,
        feature_store: FeatureStoreRepository,
        sales_pipeline: SalesTargetsPipeline,
    ) -> None:
        self._registry = identity_registry
        self._reference = reference_repository
        self._feature_store = feature_store
        self._sales_pipeline = sales_pipeline

    def enrich_all_pivots(self) -> dict:
        rod_snapshot = self._reference.data
        count = self._sales_pipeline.persist_hotel_targets()
        recap_persisted = self._persist_recap_features()
        pivot_ids: list[str] = []
        for record in self._registry.all_records():
            if record.has_rod or record.has_sales:
                pivot_ids.append(record.hotel_id)
                self._feature_store.save_meta(
                    record.hotel_id,
                    {
                        "is_pivot": True,
                        "brand": record.brand,
                        "nb_chambres": record.nb_chambres,
                        "has_sales": record.has_sales,
                        "has_rod": record.has_rod,
                    },
                )
                rod_dir = self._feature_store.hotel_dir(record.hotel_id) / "rod_reference"
                rod_dir.mkdir(parents=True, exist_ok=True)
                (rod_dir / "concepts.json").write_text(
                    json.dumps(rod_snapshot.get("concepts", {}), ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
        return {
            "pivot_hotels": pivot_ids,
            "sales_targets_persisted": count,
            "recap_features_persisted": recap_persisted,
        }

    def _persist_recap_features(self) -> int:
        """Écrit les ``d_recap_*`` imputés dans le feature store (dataset processed)."""
        processed = self._sales_pipeline.output_dir
        full_path = processed / "ml_dataset_full.csv"
        meta_path = processed / "dataset_meta.json"
        if not full_path.exists() or not meta_path.exists():
            return 0
        frame = json.loads(meta_path.read_text(encoding="utf-8"))
        feature_cols = frame.get("feature_cols", [])
        if not feature_cols:
            return 0
        dataset = pd.read_csv(full_path)
        operating_cols = {
            "d_nb_chambres",
            "d_taux_occupation",
            "d_guests_per_chambre",
            "d_clients_mois",
            "d_taux_acheteur",
        }
        selected_cols = [c for c in feature_cols if c.startswith("d_recap_") or c in operating_cols]
        count = 0
        for hotel_id in dataset["hotel_id"].unique():
            row = dataset[dataset["hotel_id"] == hotel_id].iloc[0]
            payload: dict[str, float] = {}
            for col in selected_cols:
                if col not in row.index or pd.isna(row[col]):
                    continue
                numeric = pd.to_numeric(row[col], errors="coerce")
                if pd.notna(numeric):
                    payload[col] = float(numeric)
            if payload:
                self._feature_store.save_recap_features(str(hotel_id), payload)
                count += 1
        return count