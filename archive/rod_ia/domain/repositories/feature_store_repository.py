"""Persistance par hôtel — enrichissement, saisies directeur, simulations."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from rod_ia.domain.models.simulation import EnrichedHotelFeatures, SimulationResult
from rod_ia.domain.models.store import StoreConfiguration


class FeatureStoreRepository:
    """Feature store fichier par ``hotel_id`` (JSON + Parquet-ready structure)."""

    def __init__(self, base_dir: str | Path) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def hotel_dir(self, hotel_id: str) -> Path:
        path = self.base_dir / hotel_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _write_json(self, hotel_id: str, relative: str, payload: dict) -> Path:
        target = self.hotel_dir(hotel_id) / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return target

    def _read_json(self, hotel_id: str, relative: str) -> Optional[dict]:
        target = self.hotel_dir(hotel_id) / relative
        if not target.exists():
            return None
        return json.loads(target.read_text(encoding="utf-8"))

    def exists(self, hotel_id: str) -> bool:
        return self.hotel_dir(hotel_id).exists()

    def save_meta(self, hotel_id: str, extra: dict | None = None) -> None:
        meta = {
            "hotel_id": hotel_id,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            **(extra or {}),
        }
        self._write_json(hotel_id, "meta.json", meta)

    def load_meta(self, hotel_id: str) -> Optional[dict]:
        return self._read_json(hotel_id, "meta.json")

    def has_valid_enrichment(self, hotel_id: str) -> bool:
        """True si POI/météo déjà calculés et persistés pour cet hôtel."""
        enriched = self.load_enriched(hotel_id)
        return enriched is not None and enriched.lat is not None

    def load_enriched(self, hotel_id: str) -> Optional[EnrichedHotelFeatures]:
        data = self._read_json(hotel_id, "geo/enriched.json")
        return EnrichedHotelFeatures.from_dict(data) if data else None

    def save_enriched(
        self,
        hotel_id: str,
        features: EnrichedHotelFeatures,
        fingerprint: str | None = None,
    ) -> None:
        self._write_json(hotel_id, "geo/enriched.json", features.to_dict())
        extra: dict[str, Any] = {"enriched": features.lat is not None}
        if fingerprint:
            extra["enrichment_fingerprint"] = fingerprint
        self.save_meta(hotel_id, extra)

    def enrichment_fingerprint_matches(self, hotel_id: str, fingerprint: str) -> bool:
        """Vérifie que le cache correspond à la même saisie nom/adresse/ville."""
        meta = self.load_meta(hotel_id)
        if not meta:
            return False
        return meta.get("enrichment_fingerprint") == fingerprint

    def save_director_inputs(self, hotel_id: str, inputs: dict) -> None:
        self._write_json(hotel_id, "rod_input/director_inputs.json", inputs)
        self.save_meta(hotel_id)

    def load_director_inputs(self, hotel_id: str) -> Optional[dict]:
        return self._read_json(hotel_id, "rod_input/director_inputs.json")

    def save_store_config(self, hotel_id: str, config: StoreConfiguration) -> None:
        self._write_json(hotel_id, "rod_input/store_config.json", config.to_dict())

    def load_store_config(self, hotel_id: str) -> Optional[StoreConfiguration]:
        data = self._read_json(hotel_id, "rod_input/store_config.json")
        return StoreConfiguration.from_dict(data) if data else None

    def append_simulation(self, hotel_id: str, result: SimulationResult) -> None:
        history_path = self.hotel_dir(hotel_id) / "simulations" / "history.jsonl"
        history_path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(result.to_dict(), ensure_ascii=False)
        with history_path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    def save_sales_targets(self, hotel_id: str, monthly_avg: list[dict], monthly_pct: list[dict]) -> None:
        self._write_json(hotel_id, "sales_targets/monthly_avg.json", {"rows": monthly_avg})
        self._write_json(hotel_id, "sales_targets/monthly_pct.json", {"rows": monthly_pct})

    def load_sales_targets(self, hotel_id: str) -> dict[str, Any]:
        return {
            "monthly_avg": self._read_json(hotel_id, "sales_targets/monthly_avg.json"),
            "monthly_pct": self._read_json(hotel_id, "sales_targets/monthly_pct.json"),
        }

    def save_recap_features(self, hotel_id: str, features: dict[str, float]) -> None:
        self._write_json(hotel_id, "recap/features.json", {"features": features})
        self.save_meta(hotel_id, {"has_recap_features": bool(features)})

    def load_recap_features(self, hotel_id: str) -> dict[str, float]:
        data = self._read_json(hotel_id, "recap/features.json")
        if not data:
            return {}
        return {str(k): float(v) for k, v in (data.get("features") or {}).items()}