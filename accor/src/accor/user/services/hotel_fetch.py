"""
Recuperation a la demande d un hotel Accor absent de hotel_data.

Source : https://all.accor.com/hotel/{code}/index.fr.shtml
(scrape_accor.hotels.fetch_hotel)

En cas de succes : upsert dans data/hotel_data.xlsx + invalidation caches.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd

from accor.data_io import DATA_DIR, read_excel

HOTEL_XLSX = DATA_DIR / "hotel_data.xlsx"


def normalize_lookup_code(code: str) -> str:
    """Normalise saisie user : H0338, 0338, 338 → formes candidates."""
    s = str(code or "").strip().upper()
    if s.endswith(".0") and s[:-2].replace("-", "").isdigit():
        s = s[:-2]
    return s


def code_variants(code: str) -> list[str]:
    """Variantes de code pour matching hotel_data et URL Accor."""
    raw = normalize_lookup_code(code)
    if not raw:
        return []
    variants: list[str] = []
    bare = raw[1:] if raw.startswith("H") and len(raw) > 1 else raw
    for v in (raw, bare, f"H{bare}" if bare and not bare.startswith("H") else ""):
        if v and v not in variants:
            variants.append(v)
    # zero-pad numerique
    if bare.isdigit():
        z4 = bare.zfill(4)
        for v in (z4, f"H{z4}", bare.lstrip("0") or "0", f"H{bare.lstrip('0') or '0'}"):
            if v and v not in variants:
                variants.append(v)
    return variants


def scrape_to_hotel_row(scraped: dict[str, Any]) -> dict[str, Any]:
    """Mappe le dict scrape_accor vers colonnes hotel_data."""
    code_raw = str(scraped.get("hotel_code_accor") or "").strip()
    # stocke avec prefixe H si numerique (convention hotel_data)
    bare = code_raw.lstrip("H").lstrip("h")
    if bare.isdigit():
        hotel_code = f"H{bare.zfill(4)}" if int(bare) < 10000 else f"H{bare}"
        # garder longueur naturelle si deja long
        if len(bare) >= 4:
            hotel_code = f"H{bare}"
    else:
        hotel_code = f"H{code_raw}" if not code_raw.upper().startswith("H") else code_raw.upper()

    def flag(key: str, default: int = 0) -> int:
        v = scraped.get(key)
        if v is None:
            return default
        try:
            return int(v)
        except (TypeError, ValueError):
            return default

    return {
        "hotel_code": hotel_code,
        "hotel_name": scraped.get("hotel_name") or "",
        "hotel_brand": scraped.get("hotel_brand") or "",
        "hotel_adresse_postale_1": scraped.get("hotel_adresse") or "",
        "hotel_adresse_postale_2": scraped.get("hotel_adresse_complement") or "",
        "hotel_code_postal": scraped.get("hotel_code_postal") or "",
        "hotel_city": scraped.get("hotel_city") or "",
        "hotel_country": scraped.get("hotel_country") or "",
        "hotel_lat": scraped.get("hotel_lat"),
        "hotel_lon": scraped.get("hotel_lon"),
        "hotel_f_b_bar": flag("has_bar"),
        "hotel_f_b_restaurant": flag("has_restaurant"),
        "hotel_f_b_room_service": flag("has_room_service"),
        "hotel_f_b_minibar": 0,
        "hotel_non_f_b_piscine": flag("has_piscine"),
        "hotel_non_f_b_salle_de_sport": flag("has_fitness"),
        "hotel_non_f_b_spa": flag("has_spa"),
        "hotel_non_f_b_salles_de_reunion": flag("has_reunion"),
        "hotel_has_parking": flag("has_parking"),
        "hotel_has_wifi": flag("has_wifi"),
        "hotel_has_clim": flag("has_clim"),
        "hotel_has_petit_dejeuner": flag("has_petit_dejeuner"),
        "hotel_has_accessible": flag("has_accessible"),
        "hotel_has_animaux": flag("has_animaux"),
        "hotel_has_non_fumeur": flag("has_non_fumeur"),
        "hotel_has_navette": flag("has_navette"),
        "hotel_has_reunion": flag("has_reunion"),
    }


def hotel_exists(code: str) -> str | None:
    """Retourne le hotel_code stocke si present, sinon None."""
    path = HOTEL_XLSX
    if not path.exists():
        return None
    df = read_excel(path, sheet=0, dtype={"hotel_code": str})
    if df.empty or "hotel_code" not in df.columns:
        return None
    codes = df["hotel_code"].astype(str).str.strip()
    for v in code_variants(code):
        hit = df.loc[codes.str.upper() == v.upper()]
        if not hit.empty:
            return str(hit.iloc[0]["hotel_code"]).strip()
    return None


def fetch_and_upsert_hotel(code: str) -> dict[str, Any]:
    """
    Scrape Accor + upsert hotel_data.

    Returns
    -------
    dict : ok, hotel_code, source, row, error?
    """
    from accor.scrape_accor.hotels import code_for_url, fetch_hotel

    raw = normalize_lookup_code(code)
    if not raw or len(re.sub(r"[^A-Z0-9]", "", raw)) < 2:
        return {"ok": False, "error": "Code hotel invalide", "hotel_code": raw}

    existing = hotel_exists(raw)
    if existing:
        return {
            "ok": True,
            "hotel_code": existing,
            "source": "hotel_data",
            "scraped": False,
        }

    url_code = code_for_url(raw.lstrip("H").lstrip("h") if raw.upper().startswith("H") else raw)
    # tenter aussi le code tel quel
    attempts = [url_code]
    bare = raw[1:] if raw.upper().startswith("H") else raw
    if bare not in attempts:
        attempts.append(bare)
    if bare.isdigit() and bare.zfill(4) not in attempts:
        attempts.append(bare.zfill(4))

    last_err = "introuvable"
    scraped: dict[str, Any] | None = None
    for c in attempts:
        result = fetch_hotel(c, pause_s=0.2)
        status = result.get("status")
        if status == "ok":
            scraped = result
            break
        last_err = str(result.get("error") or status or "echec scrape")

    if not scraped:
        return {
            "ok": False,
            "error": f"Hotel {raw} introuvable sur all.accor.com ({last_err})",
            "hotel_code": raw,
            "scraped": True,
        }

    row = scrape_to_hotel_row(scraped)
    path = HOTEL_XLSX
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists():
        df = read_excel(path, sheet=0, dtype={"hotel_code": str})
        if df.empty:
            df = pd.DataFrame([row])
        else:
            # align columns
            for col in row:
                if col not in df.columns:
                    df[col] = None
            for col in df.columns:
                if col not in row:
                    row[col] = None
            # drop existing same code
            mask = df["hotel_code"].astype(str).str.strip().str.upper() == str(
                row["hotel_code"]
            ).upper()
            df = df.loc[~mask]
            df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    else:
        df = pd.DataFrame([row])

    # hotel_code as text
    df["hotel_code"] = df["hotel_code"].astype(str)
    df.to_excel(path, index=False)

    # invalidate admin store + catalogs
    try:
        from accor.store import reload_dataset

        reload_dataset("hotel")
    except Exception:
        pass

    return {
        "ok": True,
        "hotel_code": row["hotel_code"],
        "source": "all.accor.com",
        "scraped": True,
        "row": row,
        "url": scraped.get("url") or f"https://all.accor.com/hotel/{url_code}/index.fr.shtml",
    }
