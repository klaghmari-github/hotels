#!/usr/bin/env python3
"""
Liste hôtels programme de fidélité ALL (page optin-htl).

Source API (utilisée par la page
https://all.accor.com/loyalty-program/optin-htl/index.fr.shtml ) :

    GET https://api.accor.com/catalog/v1/hotels
        ?enlarge=false&range=0-99&q=france
        &fields=results.hotel.id,name,brand,city,country

18 pages × 100 lignes ≈ 1747 hôtels (filtre par défaut « france »).

Produit :
* ``data/marques/hotels/loyalty_optin_all.xlsx`` — liste complète API
* ``data/marques/hotels/loyalty_optin_missing.xlsx`` — absents de hotels_all.xlsx
* ``data/marques/hotels/loyalty_optin_missing.csv`` — idem CSV

Matching contre hotels_all :
1. code Accor normalisé (0785 ↔ 785)
2. sinon (nom + ville) normalisés
"""

from __future__ import annotations

import gzip
import json
import re
import time
import unicodedata
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
HOTELS_DIR = ROOT / "data" / "marques" / "hotels"
EXISTING_XLSX = HOTELS_DIR / "hotels_all.xlsx"

API_BASE = "https://api.accor.com"
API_KEY = "l7xx8785261b2a33457db88959a8679a1307"
PAGE_SIZE = 100
# Même mapping que le JS de la page optin-htl
BRAND_CODES: dict[str, str] = {
    "RAF": "RAFFLES",
    "FAI": "FAIRMONT",
    "BAN": "BANYAN TREE",
    "SOL": "SOFITEL LEGEND",
    "SOS": "SO SOFITEL",
    "SOF": "SOFITEL",
    "RIX": "RIXOS HOTELS",
    "MGA": "MGALLERY",
    "PUL": "PULLMAN",
    "SWI": "SWISSÔTEL",
    "ANG": "ANGSANA",
    "ADP": "ADAGIO PREMIUM",
    "TWF": "25HOURS",
    "MEI": "GRAND MERCURE",
    "DHA": "DHAWA",
    "CAS": "CASSIA",
    "SEB": "SEBEL",
    "NOV": "NOVOTEL",
    "SUI": "NOVOTEL SUITES",
    "MER": "MERCURE",
    "MSH": "MAMA SHELTER",
    "ORB": "ORBIS",
    "ADG": "ADAGIO",
    "IBH": "IBIS",
    "IBS": "IBIS STYLES",
    "ADA": "ADAGIO ACCESS",
    "IBB": "IBIS BUDGET",
    "JOE": "JO&JOE",
    "FOR": "HOTELF1",
    "HOF": "HOTELF1",
    "COR": "CORALIA",
    "MOV": "MÖVENPICK",
    "MTS": "MANTIS",
    "MTA": "MANTRA",
    "OEX": "ORIENT EXPRESS",
    "GRE": "GREET",
    "SBE": "SBE",
    "TRI": "TRIBE",
    "PEP": "PEPPERS",
    "BKF": "BREAKFREE",
    "ART": "ART SERIES",
    "SO": "SO/",
    "HYD": "HYDE",
    "DEL": "DELANO",
    "SLH": "SLS",
}


def _norm_text(s: Any) -> str:
    text = str(s or "").strip().upper()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _norm_code(code: Any) -> str:
    """Normalise un code hôtel pour jointure (0785 → 785, H1142 → 1142)."""
    s = str(code or "").strip().upper()
    s = re.sub(r"^H", "", s)
    if s.isdigit():
        return str(int(s))  # drop leading zeros
    return s


def _fetch_page(q: str, range_spec: str) -> tuple[list[dict[str, Any]], int]:
    fields = (
        "results.hotel.id,results.hotel.name,"
        "results.hotel.localization.address.city,"
        "results.hotel.localization.address.country,"
        "results.hotel.brand"
    )
    url = (
        f"{API_BASE}/catalog/v1/hotels"
        f"?enlarge=false&range={range_spec}&q={q}&fields={fields}"
    )
    headers = {
        "apiKey": API_KEY,
        "Accept-Language": "fr",
        "User-Agent": "Mozilla/5.0 (compatible; AccorDataStudio/1.0)",
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "Origin": "https://all.accor.com",
        "Referer": "https://all.accor.com/loyalty-program/optin-htl/index.fr.shtml",
    }
    req = Request(url, headers=headers)
    with urlopen(req, timeout=40) as resp:
        raw = resp.read()
        total = int(resp.headers.get("x-total-count") or 0)
        if raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        payload = json.loads(raw.decode("utf-8"))
    rows = []
    for item in payload.get("results") or []:
        h = item.get("hotel") or {}
        loc = (h.get("localization") or {}).get("address") or {}
        brand_code = str(h.get("brand") or "").strip().upper()
        brand_name = BRAND_CODES.get(brand_code, brand_code)
        hid = str(h.get("id") or "").strip()
        rows.append(
            {
                "hotel_code_accor": hid,
                "hotel_code_norm": _norm_code(hid),
                "hotel_name": str(h.get("name") or "").strip(),
                "hotel_brand_code": brand_code,
                "hotel_brand": brand_name.upper() if brand_name else "",
                "hotel_city": str(loc.get("city") or "").strip().upper(),
                "hotel_country": str(loc.get("country") or "").strip(),
                "url_hotel": f"https://all.accor.com/hotel/{hid}/index.fr.shtml"
                if hid
                else "",
                "source_query": q,
            }
        )
    return rows, total


def fetch_all_loyalty_hotels(
    *,
    q: str = "france",
    page_size: int = PAGE_SIZE,
    pause_s: float = 0.25,
) -> pd.DataFrame:
    """Télécharge toutes les pages (18 pour q=france)."""
    first, total = _fetch_page(q, f"0-{page_size - 1}")
    all_rows = list(first)
    print(f"[loyalty] total API x-total-count={total}, page0={len(first)}")
    if total <= 0:
        total = len(first)
    start = page_size
    while start < total:
        end = min(start + page_size - 1, total - 1)
        range_spec = f"{start}-{end}"
        time.sleep(pause_s)
        try:
            rows, _ = _fetch_page(q, range_spec)
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            print(f"[loyalty] erreur range {range_spec}: {exc}")
            rows = []
        all_rows.extend(rows)
        print(f"[loyalty] {range_spec} → +{len(rows)} (cumul {len(all_rows)})")
        start += page_size
        if not rows:
            # stop if empty page
            break

    frame = pd.DataFrame(all_rows)
    if not frame.empty:
        frame = frame.drop_duplicates(subset=["hotel_code_accor"], keep="first")
        frame["hotel_name_norm"] = frame["hotel_name"].map(_norm_text)
        frame["city_norm"] = frame["hotel_city"].map(_norm_text)
    return frame.reset_index(drop=True)


def load_existing_hotels(path: Path | None = None) -> pd.DataFrame:
    path = path or EXISTING_XLSX
    if not path.exists():
        return pd.DataFrame()
    try:
        df = pd.read_excel(path, sheet_name="hotels")
    except ValueError:
        df = pd.read_excel(path, sheet_name=0)
    if df.empty:
        return df
    out = df.copy()
    if "hotel_code_accor" in out.columns:
        out["hotel_code_norm"] = out["hotel_code_accor"].map(_norm_code)
    else:
        out["hotel_code_norm"] = ""
    name_col = "hotel_name" if "hotel_name" in out.columns else None
    city_col = "hotel_city" if "hotel_city" in out.columns else None
    out["hotel_name_norm"] = out[name_col].map(_norm_text) if name_col else ""
    out["city_norm"] = out[city_col].map(_norm_text) if city_col else ""
    return out


def find_missing(
    loyalty: pd.DataFrame, existing: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Retourne (missing, matched)."""
    if loyalty.empty:
        return loyalty, loyalty
    if existing.empty:
        miss = loyalty.copy()
        miss["match_type"] = "none_existing"
        return miss, loyalty.iloc[0:0].copy()

    existing_codes = set(
        existing["hotel_code_norm"].dropna().astype(str).tolist()
    )
    existing_keys = set(
        zip(
            existing["hotel_name_norm"].fillna(""),
            existing["city_norm"].fillna(""),
        )
    )

    matched_rows = []
    missing_rows = []
    for _, row in loyalty.iterrows():
        code = str(row.get("hotel_code_norm") or "")
        key = (row.get("hotel_name_norm") or "", row.get("city_norm") or "")
        if code and code in existing_codes:
            r = row.to_dict()
            r["match_type"] = "code"
            matched_rows.append(r)
        elif key[0] and key in existing_keys:
            r = row.to_dict()
            r["match_type"] = "name_city"
            matched_rows.append(r)
        else:
            r = row.to_dict()
            r["match_type"] = "missing"
            missing_rows.append(r)

    return pd.DataFrame(missing_rows), pd.DataFrame(matched_rows)


def run(
    *,
    q: str = "france",
    out_dir: Path | None = None,
) -> dict[str, Any]:
    out_dir = out_dir or HOTELS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    loyalty = fetch_all_loyalty_hotels(q=q)
    existing = load_existing_hotels()
    missing, matched = find_missing(loyalty, existing)

    all_path = out_dir / "loyalty_optin_all.xlsx"
    miss_path = out_dir / "loyalty_optin_missing.xlsx"
    miss_csv = out_dir / "loyalty_optin_missing.csv"
    match_path = out_dir / "loyalty_optin_matched.xlsx"

    loyalty.to_excel(all_path, index=False, sheet_name="loyalty")
    missing.to_excel(miss_path, index=False, sheet_name="missing")
    missing.to_csv(miss_csv, index=False)
    matched.to_excel(match_path, index=False, sheet_name="matched")

    summary = {
        "ok": True,
        "query": q,
        "n_loyalty": len(loyalty),
        "n_existing_scraped": int(existing["hotel_code_norm"].nunique())
        if not existing.empty and "hotel_code_norm" in existing.columns
        else len(existing),
        "n_matched": len(matched),
        "n_missing": len(missing),
        "loyalty_all": str(all_path),
        "missing_xlsx": str(miss_path),
        "missing_csv": str(miss_csv),
        "matched_xlsx": str(match_path),
        "sample_missing_codes": missing["hotel_code_accor"].head(15).tolist()
        if not missing.empty
        else [],
    }
    (out_dir / "loyalty_optin_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return summary


def main() -> None:
    import argparse

    p = argparse.ArgumentParser(description="Liste loyalty Accor vs hotels_all")
    p.add_argument(
        "--q",
        default="france",
        help="Query catalog (défaut page optin: france)",
    )
    args = p.parse_args()
    result = run(q=args.q)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
