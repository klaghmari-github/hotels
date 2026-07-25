#!/usr/bin/env python3
"""
Extraction d'une fiche hôtel Accor : ``/hotel/{id}/index.fr.shtml``.

Champs :
* code Accor, nom, marque
* adresse / complément / CP / ville / pays
* lat / lon
* amenities brutes + flags F_B / N_F_B
"""

from __future__ import annotations

import json
import re
from html import unescape
from typing import Any
from urllib.error import HTTPError

from scrape_accor.http_util import fetch

HOTEL_URL = "https://all.accor.com/hotel/{code}/index.fr.shtml"

# Catégorisation amenities → F&B / NON-F&B
FB_KEYWORDS = (
    "restaurant",
    "bar",
    "petit-déjeuner",
    "petit dejeuner",
    "breakfast",
    "room service",
    "service en chambre",
    "minibar",
    "snack",
    "café",
    "cafe",
    "cuisine",
)
NFB_KEYWORDS = (
    "piscine",
    "pool",
    "parking",
    "wifi",
    "wi-fi",
    "spa",
    "salle de sport",
    "fitness",
    "gym",
    "air conditionné",
    "climatisation",
    "clim",
    "accessible",
    "animaux",
    "navette",
    "salle de réunion",
    "meeting",
    "buanderie",
    "laverie",
    "conciergerie",
    "non-fumeur",
    "non fumeur",
)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", unescape(s or "")).strip()


def _split_address(street: str) -> tuple[str, str]:
    """
    Sépare rue / complément naïvement (2e partie après virgule).
    """
    street = _norm(street)
    if not street:
        return "", ""
    if "," in street:
        a, b = street.split(",", 1)
        return a.strip(), b.strip()
    return street, ""


def _classify_amenity(name: str) -> str:
    n = name.lower()
    for kw in FB_KEYWORDS:
        if kw in n:
            return "F_B"
    for kw in NFB_KEYWORDS:
        if kw in n:
            return "N_F_B"
    return "AUTRE"


def _parse_ld_hotel(html: str) -> dict[str, Any] | None:
    blocks = re.findall(
        r'<script type="application/ld\+json"[^>]*>(.*?)</script>',
        html,
        flags=re.S | re.I,
    )
    for block in blocks:
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and str(item.get("@type", "")).lower() in {
                    "hotel",
                    "lodgingbusiness",
                }:
                    return item
        if isinstance(data, dict):
            t = str(data.get("@type", "")).lower()
            if t in {"hotel", "lodgingbusiness"}:
                return data
    return None


def parse_hotel_html(html: str, code: int | str) -> dict[str, Any] | None:
    """Parse HTML fiche → dict colonnes, ou None si page invalide / fermée."""
    if not html or len(html) < 500:
        return None
    low = html.lower()
    closed_markers = (
        "n'existe plus",
        "n’existe plus",
        "no longer available",
        "hotel not found",
        "page introuvable",
        "n'est plus disponible",
        "n’est plus disponible",
        "has been closed",
    )
    if any(m in low for m in closed_markers):
        return None

    ld = _parse_ld_hotel(html)
    name = ""
    brand = ""
    country = city = postal = street = ""
    lat = lon = None
    amenities: list[str] = []
    email = ""
    phone = ""
    description = ""

    if ld:
        # JSON-LD "name" est souvent un titre SEO long → préférer hotelName meta
        name = _norm(str(ld.get("name") or ""))
        brand_obj = ld.get("brand") or {}
        if isinstance(brand_obj, dict):
            brand = _norm(str(brand_obj.get("name") or ""))
        addr = ld.get("address") or {}
        if isinstance(addr, dict):
            street = _norm(str(addr.get("streetAddress") or ""))
            city = _norm(str(addr.get("addressLocality") or ""))
            postal = _norm(str(addr.get("postalCode") or ""))
            country = _norm(str(addr.get("addressCountry") or ""))
        geo = ld.get("geo") or {}
        if isinstance(geo, dict):
            try:
                lat = float(geo.get("latitude"))
                lon = float(geo.get("longitude"))
            except (TypeError, ValueError):
                pass
        for am in ld.get("amenityFeature") or []:
            if isinstance(am, dict) and am.get("name"):
                amenities.append(_norm(str(am["name"])))
        email = _norm(str(ld.get("email") or ""))
        phone = _norm(str(ld.get("telephone") or ""))
        description = _norm(str(ld.get("description") or ""))[:500]

    # Nom canonique Accor (plus propre que le titre SEO)
    m = re.search(r'"hotelName"\s*:\s*"([^"]+)"', html)
    if m:
        hn = _norm(m.group(1))
        if hn and (not name or len(hn) < len(name) or "|" in name or " - ALL" in name):
            name = hn
    if lat is None:
        m = re.search(r'latitude["\s:=]+([0-9.\-]+)', html, re.I)
        if m:
            try:
                lat = float(m.group(1))
            except ValueError:
                pass
    if lon is None:
        m = re.search(r'longitude["\s:=]+([0-9.\-]+)', html, re.I)
        if m:
            try:
                lon = float(m.group(1))
            except ValueError:
                pass
    if not street:
        m = re.search(r'"streetAddress"\s*:\s*"([^"]+)"', html)
        if m:
            street = _norm(m.group(1))
    if not city:
        m = re.search(r'"addressLocality"\s*:\s*"([^"]+)"', html)
        if m:
            city = _norm(m.group(1))
    if not postal:
        m = re.search(r'"postalCode"\s*:\s*"([^"]+)"', html)
        if m:
            postal = _norm(m.group(1))
    if not brand:
        m = re.search(r'"brand"\s*:\s*\{[^}]*"name"\s*:\s*"([^"]+)"', html, re.S)
        if m:
            brand = _norm(m.group(1))

    # Page sans identité utile = pas un hôtel valide
    if not name and lat is None:
        return None

    adrs, complement = _split_address(street)

    # Flags services
    am_join = " | ".join(amenities).lower()
    def has(*keys: str) -> int:
        return int(any(k in am_join for k in keys))

    fb_list = [a for a in amenities if _classify_amenity(a) == "F_B"]
    nfb_list = [a for a in amenities if _classify_amenity(a) == "N_F_B"]
    other_list = [a for a in amenities if _classify_amenity(a) == "AUTRE"]

    return {
        "hotel_code_accor": str(code),
        "hotel_name": name,
        "hotel_brand": brand,
        "hotel_adresse": adrs,
        "hotel_adresse_complement": complement,
        "hotel_code_postal": postal,
        "hotel_city": city,
        "hotel_country": country,
        "hotel_lat": lat,
        "hotel_lon": lon,
        "hotel_email": email,
        "hotel_phone": phone,
        "url": HOTEL_URL.format(code=code),
        "services_raw": " | ".join(amenities),
        "services_f_b": " | ".join(fb_list),
        "services_n_f_b": " | ".join(nfb_list),
        "services_autre": " | ".join(other_list),
        "has_restaurant": has("restaurant"),
        "has_bar": has("bar"),
        "has_petit_dejeuner": has("petit-déjeuner", "petit dejeuner", "breakfast"),
        "has_room_service": has("room service", "service en chambre"),
        "has_piscine": has("piscine", "pool"),
        "has_parking": has("parking"),
        "has_wifi": has("wifi", "wi-fi"),
        "has_clim": has("air conditionné", "climatisation", "clim"),
        "has_spa": has("spa"),
        "has_fitness": has("salle de sport", "fitness", "gym"),
        "n_amenities": len(amenities),
        "description_short": description,
    }


def fetch_hotel(code: int, *, pause_s: float = 0.4) -> dict[str, Any]:
    """
    Tente d'extraire l'hôtel ``code``.

    Returns
    -------
    dict with keys status in {ok, missing, error} + fields if ok
    """
    url = HOTEL_URL.format(code=code)
    try:
        status, html = fetch(url, pause_s=pause_s, timeout=30)
    except Exception as exc:  # noqa: BLE001
        return {
            "hotel_code_accor": str(code),
            "status": "error",
            "error": str(exc),
            "url": url,
        }

    if status in {404, 410}:
        return {
            "hotel_code_accor": str(code),
            "status": "missing",
            "http_status": status,
            "url": url,
        }
    if status != 200:
        return {
            "hotel_code_accor": str(code),
            "status": "error",
            "http_status": status,
            "url": url,
        }

    parsed = parse_hotel_html(html, code)
    if not parsed:
        return {
            "hotel_code_accor": str(code),
            "status": "missing",
            "http_status": status,
            "url": url,
            "note": "page sans données hôtel / fermé",
        }
    parsed["status"] = "ok"
    parsed["http_status"] = status
    return parsed
