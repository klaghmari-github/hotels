"""
Géocodage adresse → lat/lon (OpenStreetMap Nominatim).

Utilisé quand le directeur saisit l'adresse sans coordonnées.
Si lat/lon sont déjà fournis, le géocode est ignoré.
"""

from __future__ import annotations

import time
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import json


class Geocoder:
    """Client Nominatim simple (1 req/s recommandé)."""

    ENDPOINT = "https://nominatim.openstreetmap.org/search"
    USER_AGENT = "AccordROD-UserSimulator/1.0 (hotel retail)"

    def __init__(self, *, timeout: float = 12.0) -> None:
        self.timeout = timeout
        self._last_call = 0.0

    def _throttle(self) -> None:
        elapsed = time.time() - self._last_call
        if elapsed < 1.05:
            time.sleep(1.05 - elapsed)
        self._last_call = time.time()

    def geocode(
        self,
        *,
        street: str = "",
        postal_code: str = "",
        city: str = "",
        country: str = "France",
        free_text: str = "",
    ) -> dict[str, Any]:
        """
        Returns
        -------
        {ok, lat, lon, display_name, source, query, error?}
        """
        if free_text.strip():
            q = free_text.strip()
            params = {"q": q, "format": "json", "limit": 1, "countrycodes": "fr"}
        else:
            parts = [street, postal_code, city, country]
            q = ", ".join(p for p in parts if p and str(p).strip())
            params = {
                "street": street,
                "postalcode": postal_code,
                "city": city,
                "country": country,
                "format": "json",
                "limit": 1,
            }
        if not q.strip():
            return {
                "ok": False,
                "lat": None,
                "lon": None,
                "display_name": "",
                "source": "nominatim",
                "query": "",
                "error": "Adresse vide",
            }

        self._throttle()
        url = f"{self.ENDPOINT}?{urlencode(params)}"
        req = Request(url, headers={"User-Agent": self.USER_AGENT})
        try:
            with urlopen(req, timeout=self.timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            return {
                "ok": False,
                "lat": None,
                "lon": None,
                "display_name": "",
                "source": "nominatim",
                "query": q,
                "error": str(exc),
            }

        if not payload:
            return {
                "ok": False,
                "lat": None,
                "lon": None,
                "display_name": "",
                "source": "nominatim",
                "query": q,
                "error": "Aucun résultat",
            }
        hit = payload[0]
        return {
            "ok": True,
            "lat": float(hit["lat"]),
            "lon": float(hit["lon"]),
            "display_name": hit.get("display_name", ""),
            "source": "nominatim",
            "query": q,
        }
