"""
Géocodage adresse → lat/lon.

Stratégies (ordre) :
1. **BAN** — ``api-adresse.data.gouv.fr`` (meilleur pour adresses FR)
2. **Fiche Accor** — si code hôtel numérique / URL all.accor.com/hotel/{id}
3. **Nominatim** OSM (fallback, multi-requêtes)

Nominatim seul rate souvent les rues type « Allée Bienvenue » alors que
la BAN les trouve ; d’où le basculement.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class Geocoder:
    """Client multi-sources pour localiser un hôtel en France."""

    BAN_ENDPOINT = "https://api-adresse.data.gouv.fr/search/"
    NOMINATIM_ENDPOINT = "https://nominatim.openstreetmap.org/search"
    ACCOR_HOTEL_URL = "https://all.accor.com/hotel/{code}/index.fr.shtml"
    USER_AGENT = "AccordROD-UserSimulator/1.1 (geocode; hotels-sim)"

    def __init__(self, *, timeout: float = 15.0) -> None:
        self.timeout = timeout
        self._last_nominatim = 0.0

    # ------------------------------------------------------------------ HTTP
    def _get_json(self, url: str, *, headers: dict[str, str] | None = None) -> Any:
        hdrs = {"User-Agent": self.USER_AGENT, "Accept": "application/json"}
        if headers:
            hdrs.update(headers)
        req = Request(url, headers=hdrs)
        with urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))

    def _get_text(self, url: str) -> str:
        req = Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (compatible; AccordROD/1.1; +local-geocode)"
                ),
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "fr-FR,fr;q=0.9",
            },
        )
        with urlopen(req, timeout=self.timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")

    def _throttle_nominatim(self) -> None:
        elapsed = time.time() - self._last_nominatim
        if elapsed < 1.1:
            time.sleep(1.1 - elapsed)
        self._last_nominatim = time.time()

    # ------------------------------------------------------------------ utils
    @staticmethod
    def _normalize_postal(code: str) -> str:
        c = str(code or "").strip().replace(" ", "").replace(".0", "")
        if c.isdigit() and len(c) == 4:
            return "0" + c
        return c

    @staticmethod
    def _extract_accor_code(*values: str) -> str | None:
        """
        Extrait un code hôtel Accor (ex. 1545) depuis code hôtel, URL, etc.

        Accepte : ``1545``, ``H1545``, ``https://all.accor.com/hotel/1545/...``
        """
        for raw in values:
            text = str(raw or "").strip()
            if not text:
                continue
            m = re.search(
                r"all\.accor\.com/hotel/(\d+)", text, flags=re.IGNORECASE
            )
            if m:
                return m.group(1)
            m = re.fullmatch(r"[Hh]?0*(\d{3,5})", text)
            if m:
                return m.group(1)
        return None

    @staticmethod
    def _compose_query(
        street: str, postal_code: str, city: str, hotel_name: str = ""
    ) -> str:
        parts = [p for p in (street, postal_code, city) if p]
        if hotel_name and not parts:
            return hotel_name
        if hotel_name and parts:
            return f"{hotel_name}, " + ", ".join(parts)
        return ", ".join(parts)

    # ------------------------------------------------------------------ BAN
    def _geocode_ban(self, query: str) -> dict[str, Any] | None:
        if not query.strip():
            return None
        url = f"{self.BAN_ENDPOINT}?{urlencode({'q': query, 'limit': 5})}"
        try:
            payload = self._get_json(url)
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError):
            return None
        features = payload.get("features") or []
        if not features:
            return None

        # Préférer housenumber / street avec score correct
        best = None
        best_score = -1.0
        for feat in features:
            props = feat.get("properties") or {}
            score = float(props.get("score") or 0)
            typ = str(props.get("type") or "")
            # Pénaliser les matches trop flous (type street sans numéro si on a un n°)
            if typ in {"housenumber", "street", "locality", "municipality"}:
                if score > best_score:
                    best_score = score
                    best = feat
        if best is None:
            best = features[0]
            props = best.get("properties") or {}
            best_score = float(props.get("score") or 0)

        if best_score < 0.35:
            return None

        coords = (best.get("geometry") or {}).get("coordinates") or [None, None]
        lon, lat = coords[0], coords[1]
        if lat is None or lon is None:
            return None
        props = best.get("properties") or {}
        return {
            "ok": True,
            "lat": float(lat),
            "lon": float(lon),
            "display_name": str(props.get("label") or query),
            "source": "ban",
            "strategy": "ban",
            "query": query,
            "score": best_score,
            "ban_type": props.get("type"),
        }

    # ------------------------------------------------------------------ Accor
    def _geocode_accor(self, hotel_code: str) -> dict[str, Any] | None:
        code = self._extract_accor_code(hotel_code)
        if not code:
            return None
        url = self.ACCOR_HOTEL_URL.format(code=code)
        try:
            html = self._get_text(url)
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            return {
                "ok": False,
                "error": f"Fiche Accor {code} inaccessible : {exc}",
                "source": "accor",
                "strategy": "accor_page",
                "query": url,
            }

        lat = lon = None
        # meta geo.position
        m = re.search(
            r'geo\.position["\scontent=\']+([0-9.\-]+)\s*;\s*([0-9.\-]+)',
            html,
            flags=re.I,
        )
        if m:
            lat, lon = float(m.group(1)), float(m.group(2))
        if lat is None:
            mlat = re.search(r'latitude["\s:=]+([0-9]+\.[0-9]+)', html, flags=re.I)
            mlon = re.search(r'longitude["\s:=]+([0-9]+\.[0-9]+)', html, flags=re.I)
            if mlat and mlon:
                lat, lon = float(mlat.group(1)), float(mlon.group(1))

        name = ""
        m = re.search(r'"hotelName"\s*:\s*"([^"]+)"', html)
        if m:
            name = m.group(1)
        if not name:
            m = re.search(r"<h1[^>]*>\s*([^<]+?)\s*</h1>", html, flags=re.I | re.S)
            if m:
                name = re.sub(r"\s+", " ", m.group(1)).strip()

        address_bits = []
        for key in ("streetAddress", "postalCode", "addressLocality"):
            m = re.search(rf'"{key}"\s*:\s*"([^"]+)"', html)
            if m:
                address_bits.append(m.group(1))

        if lat is None or lon is None:
            # fallback : géocode l'adresse lue sur la fiche Accor via BAN
            addr = ", ".join(address_bits)
            if addr:
                ban = self._geocode_ban(addr)
                if ban and ban.get("ok"):
                    ban["strategy"] = "accor_address_ban"
                    ban["source"] = "accor+ban"
                    ban["query"] = f"{url} → {addr}"
                    ban["hotel_name"] = name
                    ban["accor_code"] = code
                    return ban
            return {
                "ok": False,
                "error": f"Coordonnées introuvables sur la fiche Accor {code}.",
                "source": "accor",
                "strategy": "accor_page",
                "query": url,
            }

        display = name or f"Hôtel Accor {code}"
        if address_bits:
            display = f"{display}, " + ", ".join(address_bits)

        return {
            "ok": True,
            "lat": lat,
            "lon": lon,
            "display_name": display,
            "source": "accor",
            "strategy": "accor_page",
            "query": url,
            "hotel_name": name,
            "accor_code": code,
            "address": ", ".join(address_bits),
        }

    # ------------------------------------------------------------------ Nominatim
    def _nominatim_search(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        self._throttle_nominatim()
        params = {**params, "format": "json", "limit": 3}
        url = f"{self.NOMINATIM_ENDPOINT}?{urlencode(params)}"
        try:
            payload = self._get_json(url)
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError):
            return []
        return payload if isinstance(payload, list) else []

    def _geocode_nominatim(
        self,
        *,
        street: str,
        postal_code: str,
        city: str,
        free_text: str,
        hotel_name: str,
    ) -> dict[str, Any] | None:
        attempts: list[dict[str, Any]] = []
        queries: list[tuple[str, dict[str, Any]]] = []

        free_addr = ", ".join(p for p in (street, postal_code, city, "France") if p)
        if free_addr:
            queries.append(("nom_free", {"q": free_addr, "countrycodes": "fr"}))
            queries.append(("nom_free_world", {"q": free_addr}))
        if street and city:
            queries.append(
                (
                    "nom_street_city",
                    {
                        "street": street,
                        "city": city,
                        "postalcode": postal_code,
                        "country": "France",
                        "countrycodes": "fr",
                    },
                )
            )
        if hotel_name and city:
            queries.append(
                (
                    "nom_hotel",
                    {"q": f"{hotel_name}, {city}, France", "countrycodes": "fr"},
                )
            )
        if free_text:
            queries.append(("nom_q", {"q": free_text, "countrycodes": "fr"}))

        for strategy, params in queries:
            hits = self._nominatim_search(params)
            attempts.append(
                {"strategy": strategy, "params": params, "n_hits": len(hits)}
            )
            if not hits:
                continue
            hit = hits[0]
            # Refuser un résultat purement « city » si une rue était fournie
            cls = str(hit.get("class") or "")
            typ = str(hit.get("type") or "")
            if street and cls == "place" and typ in {"city", "town", "village", "municipality"}:
                continue
            return {
                "ok": True,
                "lat": float(hit["lat"]),
                "lon": float(hit["lon"]),
                "display_name": hit.get("display_name", ""),
                "source": "nominatim",
                "strategy": strategy,
                "query": params.get("q") or free_addr,
                "attempts": attempts,
            }
        return None

    # ------------------------------------------------------------------ public
    def geocode(
        self,
        *,
        street: str = "",
        postal_code: str = "",
        city: str = "",
        country: str = "France",
        free_text: str = "",
        hotel_name: str = "",
        hotel_code: str = "",
        accor_url: str = "",
    ) -> dict[str, Any]:
        """
        Returns
        -------
        {ok, lat, lon, display_name, source, strategy, query, error?, attempts?}
        """
        street = str(street or "").strip()
        city = str(city or "").strip()
        postal_code = self._normalize_postal(postal_code)
        free_text = str(free_text or "").strip()
        hotel_name = str(hotel_name or "").strip()
        hotel_code = str(hotel_code or "").strip()
        accor_url = str(accor_url or "").strip()
        _ = country  # réservé

        attempts: list[dict[str, Any]] = []

        # 0) Fiche Accor (code ou URL)
        accor_code = self._extract_accor_code(hotel_code, accor_url, free_text)
        if accor_code:
            accor = self._geocode_accor(accor_code)
            attempts.append({"strategy": "accor", "code": accor_code})
            if accor and accor.get("ok"):
                accor["attempts"] = attempts
                return accor
            if accor and accor.get("error"):
                attempts[-1]["error"] = accor["error"]

        # 1) BAN — plusieurs formulations
        ban_queries = []
        q1 = self._compose_query(street, postal_code, city)
        if q1:
            ban_queries.append(q1)
        if street and city:
            ban_queries.append(f"{street} {postal_code} {city}".strip())
        if free_text and free_text not in ban_queries:
            ban_queries.append(free_text)
        if hotel_name and city:
            ban_queries.append(f"{hotel_name}, {city}")

        for q in ban_queries:
            ban = self._geocode_ban(q)
            attempts.append(
                {
                    "strategy": "ban",
                    "query": q,
                    "ok": bool(ban and ban.get("ok")),
                    "score": (ban or {}).get("score"),
                }
            )
            if ban and ban.get("ok"):
                # Si on avait une rue, refuser un match purement commune trop faible
                if street and ban.get("ban_type") in {"municipality", "locality"}:
                    if float(ban.get("score") or 0) < 0.7:
                        continue
                ban["attempts"] = attempts
                return ban

        # 2) Nominatim fallback
        nom = self._geocode_nominatim(
            street=street,
            postal_code=postal_code,
            city=city,
            free_text=free_text,
            hotel_name=hotel_name,
        )
        if nom and nom.get("ok"):
            nom["attempts"] = attempts + list(nom.get("attempts") or [])
            return nom

        # Message d'aide
        hint = (
            "Aucun résultat. Essayez : adresse complète (n°, rue, CP, ville), "
            "ou le code hôtel Accor (ex. 1545), "
            "ou l’URL all.accor.com/hotel/1545/…"
        )
        return {
            "ok": False,
            "lat": None,
            "lon": None,
            "display_name": "",
            "source": "none",
            "query": q1 or free_text or hotel_name,
            "error": hint,
            "attempts": attempts,
        }
