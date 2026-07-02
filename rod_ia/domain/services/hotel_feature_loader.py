"""Charge les features ``d_*`` entraînées par hôtel depuis le dataset processed."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from rod_ia.domain.services.ml_column_naming import MLColumnNaming


class HotelFeatureLoader:
    """Fournit les descriptives ML d'un hôtel pivot pour la prédiction IA."""

    def __init__(self, processed_dir: Path) -> None:
        self.processed_dir = Path(processed_dir)
        self._frame: pd.DataFrame | None = None
        self._feature_cols: list[str] = []

    def _ensure_loaded(self) -> None:
        if self._frame is not None:
            return
        x_path = self.processed_dir / "X_descriptive.csv"
        meta_path = self.processed_dir / "dataset_meta.json"
        full_path = self.processed_dir / "ml_dataset_full.csv"
        source = full_path if full_path.exists() else x_path
        if not source.exists():
            self._frame = pd.DataFrame()
            return
        self._frame = pd.read_csv(source).fillna(0.0)
        if meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            self._feature_cols = meta.get("feature_cols", [])
        else:
            self._feature_cols = MLColumnNaming.feature_columns(self._frame.columns)

    def features_for_hotel(self, hotel_id: str) -> dict[str, float]:
        self._ensure_loaded()
        if self._frame is None or self._frame.empty or "hotel_id" not in self._frame.columns:
            return {}
        row = self._frame[self._frame["hotel_id"] == hotel_id]
        if row.empty:
            return {}
        record = row.iloc[0]
        return {
            col: float(record[col])
            for col in self._feature_cols
            if col in record.index
        }