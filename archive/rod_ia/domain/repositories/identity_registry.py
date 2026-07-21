"""Registre d'identité — résolution des libellés hôtel et coordonnées canoniques."""

from __future__ import annotations

import json
import math
import re
import unicodedata
from pathlib import Path
from typing import Optional

from rod_ia.domain.models.identity import GeoCoordinates, HotelRecord


class HotelIdentityRegistry:
    """Résout les noms bruts de chaque source vers un ``hotel_id`` canonique.

    Toute jointure inter-datasets DOIT passer par ce registre — jamais par
    égalité de chaîne sur ``HOTEL_NAME`` ou ``NOM BOUTIQUE``.
    """

    def __init__(self, registry_path: str | Path) -> None:
        self.registry_path = Path(registry_path)
        self._records: dict[str, HotelRecord] = {}
        self._alias_index: dict[str, str] = {}
        if self.registry_path.exists():
            self.load()

    def load(self) -> None:
        payload = json.loads(self.registry_path.read_text(encoding="utf-8"))
        self._records.clear()
        self._alias_index.clear()
        for item in payload.get("hotels", []):
            record = HotelRecord.from_dict(item)
            self._records[record.hotel_id] = record
            for label in self._all_labels(record):
                key = self._normalize_label(label)
                if key in self._alias_index and self._alias_index[key] != record.hotel_id:
                    raise ValueError(
                        f"Alias ambigu '{label}' → {self._alias_index[key]} et {record.hotel_id}"
                    )
                self._alias_index[key] = record.hotel_id

    def save(self) -> None:
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "hotels": [r.to_dict() for r in self._records.values()],
        }
        self.registry_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def register(self, record: HotelRecord) -> None:
        self._records[record.hotel_id] = record
        for label in self._all_labels(record):
            self._alias_index[self._normalize_label(label)] = record.hotel_id

    def get(self, hotel_id: str) -> Optional[HotelRecord]:
        return self._records.get(hotel_id)

    def all_records(self) -> list[HotelRecord]:
        return list(self._records.values())

    def resolve(
        self,
        source: str,
        raw_name: str,
        city: str | None = None,
    ) -> Optional[str]:
        """Résout un libellé brut vers ``hotel_id``.

        Parameters
        ----------
        source:
            ``ventes``, ``rod``, ``display`` ou ``any``.
        raw_name:
            Libellé tel qu'il apparaît dans la source.
        city:
            Ville optionnelle pour lever une ambiguïté.
        """
        if not raw_name:
            return None
        key = self._normalize_label(raw_name)
        if key in self._alias_index:
            return self._alias_index[key]
        if city:
            composite = self._normalize_label(f"{raw_name} {city}")
            if composite in self._alias_index:
                return self._alias_index[composite]
        for record in self._records.values():
            if source == "ventes" and record.name_ventes:
                if self._normalize_label(record.name_ventes) == key:
                    return record.hotel_id
            if source == "rod" and record.name_rod:
                if self._normalize_label(record.name_rod) == key:
                    return record.hotel_id
        return None

    def get_canonical_coords(self, hotel_id: str) -> Optional[GeoCoordinates]:
        record = self.get(hotel_id)
        if not record:
            return None
        return record.canonical_coords()

    def update_nominatim_coords(
        self, hotel_id: str, lat: float, lon: float
    ) -> list[str]:
        """Met à jour les coordonnées Nominatim et retourne les avertissements géo."""
        record = self._records.get(hotel_id)
        if not record:
            return [f"hotel_id inconnu: {hotel_id}"]
        warnings: list[str] = []
        record.lat_nominatim = lat
        record.lon_nominatim = lon
        if record.lat_canonical is None:
            record.lat_canonical = lat
            record.lon_canonical = lon
            record.geo_source = "nominatim"
        elif record.lat_rod is not None and record.lon_rod is not None:
            dist = self._haversine_m(
                record.lat_rod, record.lon_rod, lat, lon
            )
            if dist > 200:
                warnings.append(
                    f"Écart géo ROD/Nominatim = {dist:.0f} m pour {hotel_id}"
                )
        return warnings

    @staticmethod
    def _normalize_label(value: str) -> str:
        text = unicodedata.normalize("NFKD", value)
        text = "".join(c for c in text if not unicodedata.combining(c))
        text = text.lower().strip()
        text = re.sub(r"[^a-z0-9]+", " ", text)
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _all_labels(record: HotelRecord) -> list[str]:
        labels = [record.name_display, record.hotel_id]
        if record.name_ventes:
            labels.append(record.name_ventes)
        if record.name_rod:
            labels.append(record.name_rod)
        labels.extend(record.aliases)
        return [label for label in labels if label]

    @staticmethod
    def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        r = 6371000.0
        p1, p2 = math.radians(lat1), math.radians(lat2)
        dp = math.radians(lat2 - lat1)
        dl = math.radians(lon2 - lon1)
        a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
        return 2 * r * math.asin(math.sqrt(a))