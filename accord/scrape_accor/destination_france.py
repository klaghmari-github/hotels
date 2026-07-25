#!/usr/bin/env python3
"""
Hôtels France — page destination + API catalog.

Page :
  https://all.accor.com/a/fr/destination/country/hotels-france-pfr.html
  Pagination HTML : ?pageIndex=1..50 (~6 hôtels/page SSR, ~300 max).

Source complète (même catalogue Accor) :
  GET https://api.accor.com/catalog/v1/hotels?q=france&range=0-99&...
  ≈ 1747 hôtels (x-total-count).

Produit dans data/marques/hotels/ :
* france_destination_all.xlsx     — liste complète (API + enrichissement HTML)
* france_destination_missing.xlsx — absents de hotels_all.xlsx
* france_destination_missing.csv
* france_destination_matched.xlsx
* france_destination_summary.json

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

DEST_URL = (
    "https://all.accor.com/a/fr/destination/country/hotels-france-pfr.html"
)
DEST_MAX_PAGES = 50  # pageIndex max observé avec hôtels

# Mapping marques (page destination / catalog)
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
        return str(int(s))
    return s


def _http_get(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: float = 40.0,
) -> tuple[bytes, dict[str, str]]:
    hdrs = {
        "User-Agent": "Mozilla/5.0 (compatible; AccordDataStudio/1.0)",
        "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.5",
        "Accept-Encoding": "gzip",
    }
    if headers:
        hdrs.update(headers)
    req = Request(url, headers=hdrs)
    with urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        meta = {k.lower(): v for k, v in resp.headers.items()}
        if raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        return raw, meta


# ── API catalog (liste complète France) ──────────────────────────────────────


def _fetch_api_page(q: str, range_spec: str) -> tuple[list[dict[str, Any]], int]:
    fields = (
        "results.hotel.id,results.hotel.name,"
        "results.hotel.localization.address.city,"
        "results.hotel.localization.address.country,"
        "results.hotel.localization.address.street,"
        "results.hotel.localization.address.zipCode,"
        "results.hotel.brand"
    )
    url = (
        f"{API_BASE}/catalog/v1/hotels"
        f"?enlarge=false&range={range_spec}&q={q}&fields={fields}"
    )
    headers = {
        "apiKey": API_KEY,
        "Accept": "application/json",
        "Origin": "https://all.accor.com",
        "Referer": DEST_URL,
    }
    raw, meta = _http_get(url, headers=headers)
    total = int(meta.get("x-total-count") or 0)
    payload = json.loads(raw.decode("utf-8"))
    rows: list[dict[str, Any]] = []
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
                "hotel_adresse": str(loc.get("street") or "").strip(),
                "hotel_code_postal": str(loc.get("zipCode") or "").strip(),
                "url_hotel": f"https://all.accor.com/hotel/{hid}/index.fr.shtml"
                if hid
                else "",
                "source": "catalog_api",
                "source_query": q,
            }
        )
    return rows, total


def fetch_catalog_france(
    *,
    q: str = "france",
    page_size: int = PAGE_SIZE,
    pause_s: float = 0.25,
) -> pd.DataFrame:
    """Télécharge tout le catalogue q=france (~1747)."""
    first, total = _fetch_api_page(q, f"0-{page_size - 1}")
    all_rows = list(first)
    print(f"[dest-fr/api] x-total-count={total}, page0={len(first)}")
    if total <= 0:
        total = len(first)
    start = page_size
    while start < total:
        end = min(start + page_size - 1, total - 1)
        range_spec = f"{start}-{end}"
        time.sleep(pause_s)
        try:
            rows, _ = _fetch_api_page(q, range_spec)
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            print(f"[dest-fr/api] erreur range {range_spec}: {exc}")
            rows = []
        all_rows.extend(rows)
        print(f"[dest-fr/api] {range_spec} → +{len(rows)} (cumul {len(all_rows)})")
        start += page_size
        if not rows:
            break

    frame = pd.DataFrame(all_rows)
    if not frame.empty:
        frame = frame.drop_duplicates(subset=["hotel_code_accor"], keep="first")
        frame["hotel_name_norm"] = frame["hotel_name"].map(_norm_text)
        frame["city_norm"] = frame["hotel_city"].map(_norm_text)
    return frame.reset_index(drop=True)


# ── HTML destination (pagination pageIndex) ──────────────────────────────────


def _parse_dest_html(html: str) -> list[dict[str, Any]]:
    """Extrait les hôtels du JSON-LD ItemList de la page destination."""
    rows: list[dict[str, Any]] = []
    blocks = re.findall(
        r'<script type="application/ld\+json">\s*(.*?)\s*</script>',
        html,
        re.S,
    )
    for block in blocks:
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue
        items = data.get("itemListElement") if isinstance(data, dict) else None
        if not items:
            continue
        for entry in items:
            if not isinstance(entry, dict):
                continue
            item = entry.get("item") or {}
            if not isinstance(item, dict):
                continue
            if item.get("@type") != "Hotel" and not item.get("@id"):
                continue
            hid = str(item.get("@id") or "").strip()
            if not hid:
                # fallback url
                m = re.search(r"/hotel/([A-Za-z0-9]+)/", str(item.get("url") or ""))
                hid = m.group(1) if m else ""
            if not hid:
                continue
            addr = item.get("address") or {}
            if not isinstance(addr, dict):
                addr = {}
            rating = item.get("aggregateRating") or {}
            if not isinstance(rating, dict):
                rating = {}
            rows.append(
                {
                    "hotel_code_accor": hid,
                    "hotel_code_norm": _norm_code(hid),
                    "hotel_name": str(item.get("name") or "").strip(),
                    "hotel_city": str(addr.get("addressLocality") or "").strip().upper(),
                    "hotel_country": str(addr.get("addressCountry") or "").strip(),
                    "hotel_adresse": str(addr.get("streetAddress") or "").strip(),
                    "hotel_code_postal": str(addr.get("postalCode") or "").strip(),
                    "rating_value": rating.get("ratingvalue") or rating.get("ratingValue"),
                    "review_count": rating.get("reviewCount"),
                    "url_hotel": str(item.get("url") or "")
                    or f"https://all.accor.com/hotel/{hid}/index.fr.shtml",
                    "source": "destination_html",
                }
            )
    # dédup par code (JSON-LD + cards parfois en double)
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for r in rows:
        c = r["hotel_code_accor"]
        if c in seen:
            continue
        seen.add(c)
        unique.append(r)
    return unique


def fetch_destination_html_pages(
    *,
    max_pages: int = DEST_MAX_PAGES,
    pause_s: float = 0.4,
) -> pd.DataFrame:
    """Parcourt pageIndex=1..max_pages de la page destination France."""
    all_rows: list[dict[str, Any]] = []
    empty_streak = 0
    for page in range(1, max_pages + 1):
        url = DEST_URL if page == 1 else f"{DEST_URL}?pageIndex={page}"
        if page > 1:
            time.sleep(pause_s)
        try:
            raw, _ = _http_get(
                url,
                headers={
                    "Accept": "text/html,application/xhtml+xml",
                    "Referer": DEST_URL,
                },
            )
            html = raw.decode("utf-8", errors="replace")
            rows = _parse_dest_html(html)
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            print(f"[dest-fr/html] page {page}: erreur {exc}")
            rows = []
            empty_streak += 1
            if empty_streak >= 2:
                break
            continue

        if not rows:
            empty_streak += 1
            print(f"[dest-fr/html] page {page}: 0 hôtel")
            if empty_streak >= 2:
                break
            continue

        empty_streak = 0
        for r in rows:
            r["page_index"] = page
        all_rows.extend(rows)
        print(
            f"[dest-fr/html] page {page}: +{len(rows)} "
            f"(cumul raw {len(all_rows)})"
        )

    frame = pd.DataFrame(all_rows)
    if not frame.empty:
        frame = frame.drop_duplicates(subset=["hotel_code_accor"], keep="first")
        frame["hotel_name_norm"] = frame["hotel_name"].map(_norm_text)
        frame["city_norm"] = frame["hotel_city"].map(_norm_text)
        if "hotel_brand" not in frame.columns:
            frame["hotel_brand"] = ""
            frame["hotel_brand_code"] = ""
    return frame.reset_index(drop=True)


def merge_sources(
    api: pd.DataFrame, html: pd.DataFrame
) -> pd.DataFrame:
    """API = base complète ; HTML enrichit rating / adresse si manquant."""
    if api.empty and html.empty:
        return pd.DataFrame()
    if api.empty:
        out = html.copy()
        out["source"] = "destination_html"
        return out
    if html.empty:
        return api.copy()

    html_idx = html.set_index("hotel_code_accor", drop=False)
    enriched = api.copy()
    for col in ("rating_value", "review_count", "page_index"):
        if col in html.columns:
            enriched[col] = enriched["hotel_code_accor"].map(
                html_idx[col] if col in html_idx.columns else {}
            )

    # hôtels HTML absents de l'API (rare)
    api_codes = set(api["hotel_code_accor"].astype(str))
    extras = html[~html["hotel_code_accor"].astype(str).isin(api_codes)].copy()
    if not extras.empty:
        extras["source"] = "destination_html_only"
        extras["source_query"] = api["source_query"].iloc[0] if "source_query" in api.columns else "france"
        if "hotel_brand" not in extras.columns:
            extras["hotel_brand"] = ""
        if "hotel_brand_code" not in extras.columns:
            extras["hotel_brand_code"] = ""
        enriched = pd.concat([enriched, extras], ignore_index=True, sort=False)

    # flags source
    html_codes = set(html["hotel_code_accor"].astype(str))
    enriched["in_destination_html"] = enriched["hotel_code_accor"].astype(str).isin(
        html_codes
    )
    if "source" in enriched.columns:
        enriched["source"] = enriched["source"].fillna("catalog_api")
    return enriched.reset_index(drop=True)


# ── Matching hotels_all ──────────────────────────────────────────────────────


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
    france: pd.DataFrame, existing: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Retourne (missing, matched)."""
    if france.empty:
        return france, france
    if existing.empty:
        miss = france.copy()
        miss["match_type"] = "none_existing"
        return miss, france.iloc[0:0].copy()

    existing_codes = set(
        existing["hotel_code_norm"].dropna().astype(str).tolist()
    )
    existing_keys = set(
        zip(
            existing["hotel_name_norm"].fillna(""),
            existing["city_norm"].fillna(""),
        )
    )

    matched_rows: list[dict[str, Any]] = []
    missing_rows: list[dict[str, Any]] = []
    for _, row in france.iterrows():
        code = str(row.get("hotel_code_norm") or "")
        key = (row.get("hotel_name_norm") or "", row.get("city_norm") or "")
        r = row.to_dict()
        if code and code in existing_codes:
            r["match_type"] = "code"
            matched_rows.append(r)
        elif key[0] and key in existing_keys:
            r["match_type"] = "name_city"
            matched_rows.append(r)
        else:
            r["match_type"] = "missing"
            missing_rows.append(r)

    return pd.DataFrame(missing_rows), pd.DataFrame(matched_rows)


def run(
    *,
    q: str = "france",
    max_html_pages: int = DEST_MAX_PAGES,
    skip_html: bool = False,
    out_dir: Path | None = None,
) -> dict[str, Any]:
    out_dir = out_dir or HOTELS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    api = fetch_catalog_france(q=q)
    if skip_html:
        html = pd.DataFrame()
        print("[dest-fr/html] skip (--skip-html)")
    else:
        html = fetch_destination_html_pages(max_pages=max_html_pages)

    france = merge_sources(api, html)
    if not france.empty and "hotel_name_norm" not in france.columns:
        france["hotel_name_norm"] = france["hotel_name"].map(_norm_text)
        france["city_norm"] = france["hotel_city"].map(_norm_text)

    existing = load_existing_hotels()
    missing, matched = find_missing(france, existing)

    all_path = out_dir / "france_destination_all.xlsx"
    miss_path = out_dir / "france_destination_missing.xlsx"
    miss_csv = out_dir / "france_destination_missing.csv"
    match_path = out_dir / "france_destination_matched.xlsx"

    france.to_excel(all_path, index=False, sheet_name="france")
    missing.to_excel(miss_path, index=False, sheet_name="missing")
    missing.to_csv(miss_csv, index=False)
    matched.to_excel(match_path, index=False, sheet_name="matched")

    summary: dict[str, Any] = {
        "ok": True,
        "query": q,
        "dest_url": DEST_URL,
        "n_catalog_api": int(len(api)),
        "n_destination_html": int(len(html)),
        "n_france_merged": int(len(france)),
        "n_html_only": int(
            (france["source"] == "destination_html_only").sum()
        )
        if not france.empty and "source" in france.columns
        else 0,
        "n_existing_scraped": int(existing["hotel_code_norm"].nunique())
        if not existing.empty and "hotel_code_norm" in existing.columns
        else len(existing),
        "n_matched": int(len(matched)),
        "n_missing": int(len(missing)),
        "france_all": str(all_path),
        "missing_xlsx": str(miss_path),
        "missing_csv": str(miss_csv),
        "matched_xlsx": str(match_path),
        "sample_missing_codes": missing["hotel_code_accor"].head(20).tolist()
        if not missing.empty
        else [],
        "sample_missing_urls": missing["url_hotel"].head(10).tolist()
        if not missing.empty and "url_hotel" in missing.columns
        else [],
    }
    (out_dir / "france_destination_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return summary


def main() -> None:
    import argparse

    p = argparse.ArgumentParser(
        description="Hôtels France (destination + catalog API) vs hotels_all"
    )
    p.add_argument("--q", default="france", help="Query catalog (défaut: france)")
    p.add_argument(
        "--max-html-pages",
        type=int,
        default=DEST_MAX_PAGES,
        help=f"Pages HTML pageIndex max (défaut {DEST_MAX_PAGES})",
    )
    p.add_argument(
        "--skip-html",
        action="store_true",
        help="Ne scrape que l'API catalog (plus rapide)",
    )
    args = p.parse_args()
    result = run(
        q=args.q,
        max_html_pages=args.max_html_pages,
        skip_html=args.skip_html,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
