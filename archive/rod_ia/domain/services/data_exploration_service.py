"""Echantillons des etapes du pipeline de donnees pour l interface d exploration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from rod_ia.domain.repositories.feature_store_repository import FeatureStoreRepository
from rod_ia.domain.repositories.identity_registry import HotelIdentityRegistry


class DataExplorationService:
    """Expose des extraits tabulaires a chaque etape de construction du dataset ML."""

    STAGES = (
        ("source", "Donnees source ventes"),
        ("user_inputs", "Saisie utilisateur et registre"),
        ("rod_brand", "Enrichissement ROD et marques"),
        ("geo_weather", "Meteo et geolocalisation commerce"),
        ("numeric_clean", "Format numerique nettoye"),
        ("with_targets", "Ajout des variables cibles"),
        ("percentages", "Conversion en pourcentages"),
    )

    def __init__(
        self,
        settings,
        identity_registry: HotelIdentityRegistry,
        feature_store: FeatureStoreRepository,
        *,
        sample_rows: int = 8,
        sample_cols: int = 18,
    ) -> None:
        self._settings = settings
        self._registry = identity_registry
        self._feature_store = feature_store
        self._sample_rows = sample_rows
        self._sample_cols = sample_cols

    @staticmethod
    def _json_safe_value(val: Any) -> Any:
        """Convertit les valeurs pandas/numpy en types JSON valides (null si NaN)."""
        if val is None:
            return None
        try:
            if pd.isna(val):
                return None
        except (TypeError, ValueError):
            pass
        if hasattr(val, "item") and not isinstance(val, (str, bytes)):
            return DataExplorationService._json_safe_value(val.item())
        if isinstance(val, bool):
            return val
        if isinstance(val, int):
            return val
        if isinstance(val, float):
            return round(val, 4) if abs(val) < 1e6 else round(val, 2)
        return val

    def _pack_frame(
        self,
        frame: pd.DataFrame,
        *,
        description: str,
        columns: list[str] | None = None,
    ) -> dict[str, Any]:
        if frame is None or frame.empty:
            return {
                "description": description,
                "columns": [],
                "rows": [],
                "n_rows_total": 0,
                "n_cols_total": 0,
                "truncated_cols": False,
            }
        use_cols = columns or list(frame.columns)
        use_cols = [c for c in use_cols if c in frame.columns]
        truncated = len(use_cols) > self._sample_cols
        show_cols = use_cols[: self._sample_cols]
        subset = frame[show_cols].head(self._sample_rows).copy()
        rows = []
        for record in subset.to_dict(orient="records"):
            rows.append({k: self._json_safe_value(v) for k, v in record.items()})
        return {
            "description": description,
            "columns": show_cols,
            "rows": rows,
            "n_rows_total": int(len(frame)),
            "n_cols_total": int(len(use_cols)),
            "truncated_cols": truncated,
        }

    def _hotel_filter(self, frame: pd.DataFrame, hotel_id: str | None) -> pd.DataFrame:
        if not hotel_id or frame is None or frame.empty or "hotel_id" not in frame.columns:
            return frame
        filtered = frame[frame["hotel_id"].astype(str) == str(hotel_id)]
        return filtered if not filtered.empty else frame

    def _load_full_dataset(self) -> pd.DataFrame:
        path = self._settings.data_processed_dir / "ml_dataset_full.csv"
        if not path.exists():
            return pd.DataFrame()
        return pd.read_csv(path)

    def _load_x_descriptive(self) -> pd.DataFrame:
        path = self._settings.data_processed_dir / "X_descriptive.csv"
        if not path.exists():
            return pd.DataFrame()
        x = pd.read_csv(path)
        full = self._load_full_dataset()
        if not full.empty and "hotel_id" in full.columns and len(full) == len(x):
            x.insert(0, "hotel_id", full["hotel_id"].values)
            if "name_display" in full.columns:
                x.insert(1, "name_display", full["name_display"].values)
        return x

    def _stage_source(self, hotel_id: str | None) -> dict[str, Any]:
        path = self._settings.sales_csv_path
        if not path.exists():
            return self._pack_frame(pd.DataFrame(), description="Fichier ventes absent")
        raw = pd.read_csv(path, nrows=500)
        cols = [
            c
            for c in raw.columns
            if c
            in {
                "NOM BOUTIQUE",
                "DATETIME",
                "TYPE",
                "GAMME",
                "PRIX TTC",
                "QUANTITE",
                "ORDER ID (TICKET DE CAISSE)",
            }
        ]
        if not cols:
            cols = list(raw.columns[:10])
        frame = raw[cols].copy()
        if hotel_id:
            record = self._registry.get(hotel_id)
            if record and record.name_ventes:
                mask = frame.get("NOM BOUTIQUE", pd.Series(dtype=str)).astype(str) == record.name_ventes
                narrowed = frame[mask]
                if not narrowed.empty:
                    frame = narrowed
        return self._pack_frame(
            frame,
            description="Extrait brut du fichier de ventes avant aggregation",
        )

    def _stage_user_inputs(self, hotel_id: str | None) -> dict[str, Any]:
        rows: list[dict] = []
        for record in self._registry.all_records():
            hid = record.hotel_id
            if hotel_id and hid != hotel_id:
                continue
            saved = self._feature_store.load_director_inputs(hid) or {}
            op = saved.get("operating") or saved
            rows.append(
                {
                    "hotel_id": hid,
                    "name_display": record.name_display,
                    "brand": record.brand,
                    "city": record.city,
                    "nb_chambres": record.nb_chambres,
                    "taux_occupation": op.get("taux_occupation"),
                    "guests_per_chambre": op.get("guests_per_chambre"),
                    "adults_per_room": (saved.get("general") or {}).get("adults_per_room"),
                    "children_per_room": (saved.get("general") or {}).get("children_per_room"),
                }
            )
        frame = pd.DataFrame(rows)
        return self._pack_frame(
            frame,
            description="Parametres saisis ou issus du registre identite",
        )

    def _stage_rod_brand(self, hotel_id: str | None) -> dict[str, Any]:
        brand_path = self._settings.brand_projections_path
        brands: dict = {}
        if brand_path.exists():
            brands = json.loads(brand_path.read_text(encoding="utf-8")).get("brands", {})

        rows: list[dict] = []
        for record in self._registry.all_records():
            hid = record.hotel_id
            if hotel_id and hid != hotel_id:
                continue
            row: dict[str, Any] = {
                "hotel_id": hid,
                "brand": record.brand,
                "nb_chambres": record.nb_chambres,
            }
            stats = brands.get((record.brand or "").upper().replace("_", " "), {})
            row["marque_total_hotels"] = stats.get("total_hotels")
            for band, count in (stats.get("size_bands") or {}).items():
                safe = band.replace(" ", "_").replace(".", "")
                row[f"marque_{safe}"] = count
            recap = self._feature_store.load_recap_features(hid)
            for key, val in list(recap.items())[:8]:
                short = key.replace("d_recap_", "")[:40]
                row[f"recap_{short}"] = self._json_safe_value(val)
            rows.append(row)
        return self._pack_frame(
            pd.DataFrame(rows),
            description="Projections marque Excel et champs recap ROD",
        )

    def _stage_geo_weather(self, hotel_id: str | None) -> dict[str, Any]:
        rows: list[dict] = []
        for record in self._registry.all_records():
            hid = record.hotel_id
            if hotel_id and hid != hotel_id:
                continue
            row: dict[str, Any] = {
                "hotel_id": hid,
                "lat": record.lat_canonical,
                "lon": record.lon_canonical,
                "geo_source": record.geo_source,
            }
            enriched = self._feature_store.load_enriched(hid)
            if enriched:
                row["lat_enrichi"] = enriched.lat
                row["lon_enrichi"] = enriched.lon
                for k, v in list((enriched.poi or {}).items())[:6]:
                    row[k] = v
                for k, v in list((enriched.weather_monthly or {}).items())[:10]:
                    row[k] = self._json_safe_value(
                        round(float(v), 3) if isinstance(v, (int, float)) else v
                    )
            rows.append(row)
        return self._pack_frame(
            pd.DataFrame(rows),
            description="Coordonnees, POI de proximite et meteo mensuelle cachees",
        )

    def _stage_numeric_clean(self, hotel_id: str | None) -> dict[str, Any]:
        frame = self._load_x_descriptive()
        frame = self._hotel_filter(frame, hotel_id)
        meta_path = self._settings.data_processed_dir / "feature_selection_report.json"
        note = "Variables categorielles retirees, champs constants et doublons exclus"
        if meta_path.exists():
            report = json.loads(meta_path.read_text(encoding="utf-8"))
            removed = report.get("n_removed_constant", 0) + report.get("n_removed_duplicate", 0)
            note = f"{note} ({removed} colonnes retirees)"
        packed = self._pack_frame(frame, description=note)
        packed["feature_count"] = int(len(frame.columns)) if not frame.empty else 0
        return packed

    def _stage_with_targets(self, hotel_id: str | None) -> dict[str, Any]:
        frame = self._load_full_dataset()
        frame = self._hotel_filter(frame, hotel_id)
        if frame.empty:
            return self._pack_frame(frame, description="Dataset complet absent")
        feature_cols = [c for c in frame.columns if c.startswith("d_")]
        target_cols = [c for c in frame.columns if c.startswith("t_")]
        show = ["hotel_id", "name_display", "brand"] if "name_display" in frame.columns else ["hotel_id"]
        show += feature_cols[:6] + target_cols[:6]
        return self._pack_frame(
            frame,
            description="Features descriptives et cibles mensuelles assemblees",
            columns=show,
        )

    def _stage_percentages(self, hotel_id: str | None) -> dict[str, Any]:
        path = self._settings.data_processed_dir / "train_percentages_long.csv"
        if not path.exists():
            return self._pack_frame(pd.DataFrame(), description="Pourcentages absents")
        long_df = pd.read_csv(path)
        long_df = self._hotel_filter(long_df, hotel_id)
        if long_df.empty:
            return self._pack_frame(long_df, description="Aucun pourcentage pour cet hotel")
        pivot = (
            long_df.pivot_table(
                index=["hotel_id", "month"],
                columns="column",
                values="pct",
                aggfunc="first",
            )
            .reset_index()
        )
        return self._pack_frame(
            pivot,
            description="Repartitions mensuelles type et gamme en pourcentage",
        )

    def explore(self, hotel_id: str | None = None) -> dict[str, Any]:
        builders = {
            "source": self._stage_source,
            "user_inputs": self._stage_user_inputs,
            "rod_brand": self._stage_rod_brand,
            "geo_weather": self._stage_geo_weather,
            "numeric_clean": self._stage_numeric_clean,
            "with_targets": self._stage_with_targets,
            "percentages": self._stage_percentages,
        }
        stages = []
        for key, title in self.STAGES:
            data = builders[key](hotel_id)
            stages.append({"id": key, "title": title, **data})
        hotels = [
            {"hotel_id": rec.hotel_id, "name": rec.name_display, "brand": rec.brand}
            for rec in self._registry.all_records()
            if rec.has_rod or rec.name_ventes
        ]
        return {
            "hotel_id": hotel_id,
            "hotels": hotels,
            "stages": stages,
            "hint": "Chaque etape montre un echantillon. Les colonnes peuvent etre tronquees pour la lisibilite.",
        }