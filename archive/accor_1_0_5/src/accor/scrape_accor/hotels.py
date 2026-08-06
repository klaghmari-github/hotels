#!/usr/bin/env python3
"""
Extraction d'une fiche hôtel Accor : /hotel/{code}/index.fr.shtml.

API publique principale
-----------------------
  fetch_hotel(code)       GET + parse → dict
  parse_hotel_html(html)  parse hors réseau
  normalize_hotel_code / code_for_url
  write_hotels_xlsx       écriture batch (usage archive / plages)

Champs extraits : code, nom, marque, adresse, CP, ville, pays, lat/lon,
amenities brutes + classification F&B / non-F&B (mots-clés).

En prod le parcours user passe par user.services.hotel_fetch
(fetch_and_upsert_hotel) qui mappe vers le schéma hotel_data.
"""

from __future__ import annotations

import json
import re
from html import unescape
from typing import Any
from urllib.error import HTTPError

from archive.accor_1_0_5.src.accor.scrape_accor.http_util import fetch

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
        "has_spa": has("spa", "wellness", "hammam", "sauna"),
        # Accor FR : « Centre de remise en forme » (pas « fitness »)
        "has_fitness": has(
            "salle de sport",
            "fitness",
            "gym",
            "remise en forme",
            "musculation",
        ),
        "has_accessible": has(
            "fauteuil roulant",
            "accessible",
            "pmr",
            "wheelchair",
        ),
        "has_animaux": has("animaux acceptés", "animaux acceptes", "pets allowed"),
        "has_non_fumeur": has(
            "non-fumeurs",
            "non fumeurs",
            "entièrement non-fumeurs",
            "non-smoking",
        ),
        "has_navette": has("navette", "shuttle"),
        "has_reunion": has("réunion", "reunion", "meeting"),
        "n_amenities": len(amenities),
        "description_short": description,
    }


def normalize_hotel_code(code: int | str, *, pad4: bool = False) -> str:
    """
    Formate un code pour l'URL Accor.

    Codes souvent sur 4 caractères : ``785`` → ``0785`` si pad4=True.
    Accepte aussi alphanumériques ``A7L5``, ``B625``.
    """
    s = str(code).strip().upper()
    # pandas/excel peut renvoyer "339.0"
    if s.endswith(".0") and s[:-2].replace("-", "").isdigit():
        s = s[:-2]
    s = s.removeprefix("H") if s.startswith("H") and len(s) > 1 else s
    if pad4 and s.isdigit():
        return s.zfill(4)
    return s


def code_for_url(code: int | str) -> str:
    """
    Code à utiliser dans l'URL fiche hôtel.

    Règle Accor observée : codes purement numériques < 1000
    nécessitent les zéros à gauche sur 4 caractères
    (``785`` / ``339`` → 404 ; ``0785`` / ``0339`` → OK).
    """
    s = normalize_hotel_code(code, pad4=False)
    if s.isdigit() and int(s) < 1000:
        return s.zfill(4)
    return s


def write_hotels_xlsx(
    path: Any,
    ok_rows: list[dict[str, Any]],
    log_rows: list[dict[str, Any]] | None = None,
) -> None:
    """Écrit un xlsx en forçant ``hotel_code_accor`` en texte (garde 0785)."""
    import pandas as pd
    from pathlib import Path

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    def _prep(rows: list[dict[str, Any]]) -> "pd.DataFrame":
        df = pd.DataFrame(rows)
        if df.empty:
            return df
        if "hotel_code_accor" in df.columns:
            df["hotel_code_accor"] = df["hotel_code_accor"].map(
                lambda x: code_for_url(x) if pd.notna(x) and str(x).strip() != "" else x
            )
        return df

    ok_df = _prep(ok_rows)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        ok_df.to_excel(writer, index=False, sheet_name="hotels")
        if log_rows is not None:
            _prep(log_rows).to_excel(writer, index=False, sheet_name="log")
        # force text format on hotel_code_accor columns
        for sheet_name in writer.sheets:
            ws = writer.sheets[sheet_name]
            headers = [c.value for c in ws[1]]
            if "hotel_code_accor" not in headers:
                continue
            col_idx = headers.index("hotel_code_accor") + 1
            for row in range(2, ws.max_row + 1):
                cell = ws.cell(row=row, column=col_idx)
                if cell.value is None:
                    continue
                cell.number_format = "@"
                cell.value = str(cell.value)


def fetch_hotel(
    code: int | str,
    *,
    pause_s: float = 0.4,
    pad4: bool = False,
    try_unpadded: bool = False,
) -> dict[str, Any]:
    """
    Tente d'extraire l'hôtel ``code``.

    Parameters
    ----------
    pad4 :
        Si True et code purement numérique, force 4 chiffres (``785`` → ``0785``).
    try_unpadded :
        Si pad4 et 404, retente sans zéros à gauche (rare).

    Returns
    -------
    dict with keys status in {ok, missing, error} + fields if ok
    """
    # Toujours pad4 pour <1000 (sinon Accor renvoie 404 / page vide)
    if pad4:
        code_str = normalize_hotel_code(code, pad4=True)
    else:
        code_str = code_for_url(code)
    candidates = [code_str]
    if try_unpadded and code_str.isdigit() and code_str != str(int(code_str)):
        candidates.append(str(int(code_str)))

    last: dict[str, Any] = {}
    for i, c in enumerate(candidates):
        url = HOTEL_URL.format(code=c)
        try:
            # pause seulement sur la 1re tentative
            status, html = fetch(url, pause_s=pause_s if i == 0 else 0.15, timeout=30)
        except Exception as exc:  # noqa: BLE001
            last = {
                "hotel_code_accor": c,
                "status": "error",
                "error": str(exc),
                "url": url,
            }
            continue

        if status in {404, 410}:
            last = {
                "hotel_code_accor": c,
                "status": "missing",
                "http_status": status,
                "url": url,
            }
            continue
        if status != 200:
            last = {
                "hotel_code_accor": c,
                "status": "error",
                "http_status": status,
                "url": url,
            }
            continue

        parsed = parse_hotel_html(html, c)
        if not parsed:
            last = {
                "hotel_code_accor": c,
                "status": "missing",
                "http_status": status,
                "url": url,
                "note": "page sans données hôtel / fermé",
            }
            continue
        parsed["status"] = "ok"
        parsed["http_status"] = status
        return parsed

    return last or {
        "hotel_code_accor": code_str,
        "status": "error",
        "error": "no attempt",
        "url": HOTEL_URL.format(code=code_str),
    }
