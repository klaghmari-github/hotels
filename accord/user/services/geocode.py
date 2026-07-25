"""
Géocodage adresse → lat/lon (OpenStreetMap Nominatim).

Utilisé quand le directeur saisit l'adresse sans coordonnées.
Stratégies successives (la première qui répond gagne) :
1. Adresse structurée (street + postalcode + city)
2. Texte libre « street, CP, ville, France »
3. Texte libre fourni (q / hotel_name)
"""

from __future__ import annotations

import json
import time
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class Geocoder:
    """Client Nominatim (1 req/s recommandé par OSM)."""

    ENDPOINT = "https://nominatim.openstreetmap.org/search"
    USER_AGENT = "AccordROD-UserSimulator/1.0 (contact: accord-rod-local)"

    def __init__(self, *, timeout: float = 15.0) -> None:
        self.timeout = timeout
        self._last_call = 0.0

    def _throttle(self) -> None:
        elapsed = time.time() - self._last_call
        if elapsed < 1.1:
            time.sleep(1.1 - elapsed)
        self._last_call = time.time()

    @staticmethod
    def _normalize_postal(code: str) -> str:
        """« 6200 » → « 06200 » si 4 chiffres français."""
        c = str(code or "").strip().replace(" ", "").replace(".0", "")
        if c.isdigit() and len(c) == 4:
            return "0" + c
        return c

    def _request(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        self._throttle()
        params = {**params, "format": "json", "limit": 3, "addressdetails": 0}
        url = f"{self.ENDPOINT}?{urlencode(params)}"
        req = Request(url, headers={"User-Agent": self.USER_AGENT, "Accept": "application/json"})
        with urlopen(req, timeout=self.timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        return payload if isinstance(payload, list) else []

    def _hit_to_result(self, hit: dict[str, Any], query: str, strategy: str) -> dict[str, Any]:
        return {
            "ok": True,
            "lat": float(hit["lat"]),
            "lon": float(hit["lon"]),
            "display_name": hit.get("display_name", ""),
            "source": "nominatim",
            "strategy": strategy,
            "query": query,
        }

    def geocode(
        self,
        *,
        street: str = "",
        postal_code: str = "",
        city: str = "",
        country: str = "France",
        free_text: str = "",
        hotel_name: str = "",
    ) -> dict[str, Any]:
        """
        Returns
        -------
        {ok, lat, lon, display_name, source, query, strategy?, error?, attempts?}
        """
        street = str(street or "").strip()
        city = str(city or "").strip()
        postal_code = self._normalize_postal(postal_code)
        free_text = str(free_text or "").strip()
        hotel_name = str(hotel_name or "").strip()

        attempts: list[dict[str, Any]] = []
        strategies: list[tuple[str, dict[str, Any], str]] = []

        if street or postal_code or city:
            strategies.append(
                (
                    "structured",
                    {
                        "street": street,
                        "postalcode": postal_code,
                        "city": city,
                        "country": country,
                        "countrycodes": "fr",
                    },
                    ", ".join(p for p in (street, postal_code, city, country) if p),
                )
            )
            free_addr = ", ".join(
                p for p in (street, postal_code, city, country) if p
            )
            if free_addr:
                strategies.append(
                    (
                        "free_address",
                        {"q": free_addr, "countrycodes": "fr"},
                        free_addr,
                    )
                )

        if free_text:
            strategies.append(
                ("free_text", {"q": free_text, "countrycodes": "fr"}, free_text)
            )

        if hotel_name and city:
            q = f"{hotel_name}, {city}, France"
            strategies.append(("hotel_city", {"q": q, "countrycodes": "fr"}, q))
        elif hotel_name:
            strategies.append(
                (
                    "hotel_name",
                    {"q": f"{hotel_name}, France", "countrycodes": "fr"},
                    f"{hotel_name}, France",
                )
            )

        if not strategies:
            return {
                "ok": False,
                "lat": None,
                "lon": None,
                "display_name": "",
                "source": "nominatim",
                "query": "",
                "error": "Adresse vide — renseignez au moins la rue, la ville ou le nom de l'hôtel.",
                "attempts": [],
            }

        last_error = "Aucun résultat"
        for strategy, params, query in strategies:
            try:
                hits = self._request(params)
                attempts.append(
                    {"strategy": strategy, "query": query, "n_hits": len(hits)}
                )
                if hits:
                    result = self._hit_to_result(hits[0], query, strategy)
                    result["attempts"] = attempts
                    return result
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)
                attempts.append(
                    {"strategy": strategy, "query": query, "error": last_error}
                )

        return {
            "ok": False,
            "lat": None,
            "lon": None,
            "display_name": "",
            "source": "nominatim",
            "query": strategies[0][2] if strategies else "",
            "error": last_error
            if "Erreur" in last_error or "timed" in last_error.lower()
            else "Aucun résultat pour cette adresse. Vérifiez rue / code postal / ville.",
            "attempts": attempts,
        }
