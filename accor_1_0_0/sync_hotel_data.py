#!/usr/bin/env python3
"""
Alimente ``data/hotel_data.xlsx`` depuis le scrape Accor
(``data/marques/hotels/hotels_all.xlsx``).

Conserve les lignes pilotes déjà saisies (TO, corner, mix…) et y fusionne
l'identité / équipements scrapés. Ajoute tous les autres hôtels avec les
champs disponibles (le reste reste vide).

Colonnes remplies depuis le scrape
----------------------------------
* hotel_code, hotel_name, hotel_brand (MAJUSCULES)
* hotel_adresse_postale_1 / _2, hotel_code_postal, hotel_city, hotel_country
* hotel_lat, hotel_lon
* binaires F&B / non-F&B mappés + parking / wifi / clim / petit-déj

Usage
-----
    cd accord
    python -m sync_hotel_data
    python -m sync_hotel_data --force-identity  # écrase aussi identité des pilotes
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import pandas as pd

from schemas import DATA_DIR, _HOTEL_BOOL, _HOTEL_EDITABLE

ROOT = Path(__file__).resolve().parent
HOTELS_ALL = DATA_DIR / "marques" / "hotels" / "hotels_all.xlsx"
HOTEL_DATA = DATA_DIR / "hotel_data.xlsx"

# Colonnes identité / équipement qu'on (re)prend du scrape
SCRAPE_IDENTITY = [
    "hotel_code",
    "hotel_name",
    "hotel_brand",
    "hotel_adresse_postale_1",
    "hotel_adresse_postale_2",
    "hotel_code_postal",
    "hotel_city",
    "hotel_country",
    "hotel_lat",
    "hotel_lon",
]

# Mapping canonique scrape → hotel_data (pas de doublon de sens)
# Les has_* du scrape peuvent être faux (ex. fitness toujours 0) :
# on recalcule aussi depuis services_raw.
SCRAPE_BOOL_MAP = {
    # scrape has_* → hotel_data (existants métier)
    "has_restaurant": "hotel_f_b_restaurant",
    "has_bar": "hotel_f_b_bar",
    "has_room_service": "hotel_f_b_room_service",
    "has_piscine": "hotel_non_f_b_piscine",
    "has_fitness": "hotel_non_f_b_salle_de_sport",
    "has_spa": "hotel_non_f_b_spa",
    # nouveaux (pas d'équivalent métier déjà rempli globalement)
    "has_parking": "hotel_has_parking",
    "has_wifi": "hotel_has_wifi",
    "has_clim": "hotel_has_clim",
    "has_petit_dejeuner": "hotel_has_petit_dejeuner",
    "has_accessible": "hotel_has_accessible",
    "has_animaux": "hotel_has_animaux",
    "has_non_fumeur": "hotel_has_non_fumeur",
    "has_navette": "hotel_has_navette",
    "has_reunion": "hotel_has_reunion",
}

# Nouvelles colonnes binaires (hors champs pilotes lobby/corner)
NEW_BOOL_COLS = [
    "hotel_has_parking",
    "hotel_has_wifi",
    "hotel_has_clim",
    "hotel_has_petit_dejeuner",
    "hotel_has_accessible",
    "hotel_has_animaux",
    "hotel_has_non_fumeur",
    "hotel_has_navette",
    "hotel_has_reunion",
]

# Mots-clés services_raw (FR Accor) → même clés que has_*
_SERVICES_KEYWORDS: dict[str, tuple[str, ...]] = {
    "has_restaurant": ("restaurant",),
    "has_bar": ("bar",),
    "has_petit_dejeuner": ("petit-déjeuner", "petit dejeuner", "breakfast"),
    "has_room_service": ("service en chambre", "room service"),
    "has_piscine": ("piscine", "pool"),
    "has_parking": ("parking",),
    "has_wifi": ("wifi", "wi-fi"),
    "has_clim": ("air conditionné", "air conditionne", "climatisation"),
    "has_spa": ("spa", "wellness", "hammam", "sauna"),
    "has_fitness": (
        "centre de remise en forme",
        "remise en forme",
        "salle de sport",
        "fitness",
        "gym",
        "musculation",
    ),
    "has_accessible": (
        "fauteuil roulant",
        "accessible en fauteuil",
        "pmr",
        "wheelchair",
    ),
    "has_animaux": ("animaux acceptés", "animaux acceptes", "pets"),
    "has_non_fumeur": (
        "non-fumeurs",
        "non fumeurs",
        "entièrement non-fumeurs",
        "non-smoking",
    ),
    "has_navette": ("navette", "shuttle"),
    "has_reunion": ("réunion", "reunion", "meeting", "salles de réunion", "salle de réunion"),
}


def _norm_code_key(code: Any) -> str:
    """Clé de jointure : H2075 / 2075 / 02075 → 2075 ; HB6A3 → B6A3."""
    s = str(code or "").strip().upper()
    if s.endswith(".0") and s[:-2].replace("-", "").isdigit():
        s = s[:-2]
    s = re.sub(r"^H", "", s)
    if s.isdigit():
        return str(int(s))
    return s


def format_hotel_code(code: Any) -> str:
    """
    Code stocké dans hotel_data : préfixe H (cohérent pilotes / sales).

    ``0339`` → ``H0339``, ``A7L5`` → ``HA7L5``, ``H2075`` → ``H2075``.
    """
    s = str(code or "").strip().upper()
    if s.endswith(".0") and s[:-2].replace("-", "").isdigit():
        s = s[:-2]
    if not s or s in {"NAN", "NONE"}:
        return ""
    if s.startswith("H") and len(s) > 1:
        return s
    return f"H{s}"


def _upper_brand(name: Any) -> str:
    text = str(name or "").strip()
    text = re.sub(r"\s+", " ", text)
    return text.upper() if text and text.lower() not in {"nan", "none"} else ""


def _as_float(v: Any) -> float | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    try:
        x = float(v)
        if pd.isna(x):
            return None
        return x
    except (TypeError, ValueError):
        return None


def _as_int01(v: Any) -> int | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    try:
        return 1 if int(float(v)) else 0
    except (TypeError, ValueError):
        s = str(v).strip().lower()
        if s in {"1", "true", "oui", "yes"}:
            return 1
        if s in {"0", "false", "non", "no", ""}:
            return 0
        return None


def _services_flags(services_raw: Any) -> dict[str, int]:
    """Dérive tous les has_* depuis services_raw (source de vérité Accor)."""
    text = str(services_raw or "").strip().lower()
    if not text or text in {"nan", "none"}:
        return {}
    out: dict[str, int] = {}
    for key, kws in _SERVICES_KEYWORDS.items():
        out[key] = int(any(k in text for k in kws))
    return out


def load_scrape(path: Path | None = None) -> pd.DataFrame:
    path = path or HOTELS_ALL
    if not path.exists():
        raise FileNotFoundError(f"hotels_all introuvable: {path}")
    df = pd.read_excel(path, dtype=str)
    if df.empty:
        return df
    # status ok si présent
    if "status" in df.columns:
        df = df[df["status"].astype(str).str.lower().isin({"ok", "nan", ""}) | df["status"].isna()]
    # drop test évidents
    if "hotel_brand" in df.columns:
        df = df[~df["hotel_brand"].astype(str).str.upper().str.contains("HOTEL DE TEST", na=False)]
    if "hotel_name" in df.columns:
        df = df[~df["hotel_name"].astype(str).str.lower().str.contains("hôtel test", na=False)]
        df = df[~df["hotel_name"].astype(str).str.lower().str.contains("hotel test", na=False)]
    return df.reset_index(drop=True)


def scrape_row_to_hotel(row: pd.Series) -> dict[str, Any]:
    code_raw = row.get("hotel_code_accor") or row.get("hotel_code")
    rec: dict[str, Any] = {
        "hotel_code": format_hotel_code(code_raw),
        "hotel_name": str(row.get("hotel_name") or "").strip() or None,
        "hotel_brand": _upper_brand(row.get("hotel_brand")),
        "hotel_adresse_postale_1": str(row.get("hotel_adresse") or "").strip() or None,
        "hotel_adresse_postale_2": str(row.get("hotel_adresse_complement") or "").strip()
        or None,
        "hotel_code_postal": str(row.get("hotel_code_postal") or "").strip() or None,
        "hotel_city": str(row.get("hotel_city") or "").strip().upper() or None,
        "hotel_country": str(row.get("hotel_country") or "").strip().upper() or None,
        "hotel_lat": _as_float(row.get("hotel_lat")),
        "hotel_lon": _as_float(row.get("hotel_lon")),
    }
    # clean nan strings
    for k, v in list(rec.items()):
        if isinstance(v, str) and v.lower() in {"nan", "none", "nat"}:
            rec[k] = None

    # 1) flags depuis services_raw (prioritaire — corrige has_fitness/spa vides)
    flags = _services_flags(row.get("services_raw"))
    # 2) compléter avec colonnes has_* du scrape si services_raw absents
    for src in SCRAPE_BOOL_MAP:
        if src not in flags and src in row.index:
            v = _as_int01(row.get(src))
            if v is not None:
                flags[src] = v
        elif src in flags and src in row.index:
            # OR logique : si has_* dit 1 et services 0, garder 1
            v = _as_int01(row.get(src))
            if v == 1:
                flags[src] = 1

    for src, dst in SCRAPE_BOOL_MAP.items():
        if src in flags:
            rec[dst] = flags[src]

    # salles de réunion : binaire dédié + colonne métier (0/1 si non déjà un compte pilote)
    if "has_reunion" in flags:
        rec["hotel_has_reunion"] = flags["has_reunion"]
        # ne pas écraser un compte pilote (>1) plus bas à la fusion
        rec["hotel_non_f_b_salles_de_reunion"] = flags["has_reunion"]

    return rec


def empty_hotel_template(cols: list[str]) -> dict[str, Any]:
    return {c: None for c in cols}


def build_hotel_data(
    *,
    force_identity: bool = False,
    hotels_all_path: Path | None = None,
    hotel_data_path: Path | None = None,
) -> pd.DataFrame:
    scrape = load_scrape(hotels_all_path)
    existing_path = hotel_data_path or HOTEL_DATA
    if existing_path.exists():
        existing = pd.read_excel(existing_path)
    else:
        existing = pd.DataFrame()

    # colonnes cibles = schéma + country + nouvelles bool
    cols = list(_HOTEL_EDITABLE)
    if "hotel_country" not in cols:
        # après city
        if "hotel_city" in cols:
            i = cols.index("hotel_city") + 1
            cols = cols[:i] + ["hotel_country"] + cols[i:]
        else:
            cols.append("hotel_country")
    for c in NEW_BOOL_COLS:
        if c not in cols:
            cols.append(c)

    # index existing by norm code
    existing_by_key: dict[str, dict[str, Any]] = {}
    if not existing.empty and "hotel_code" in existing.columns:
        for _, row in existing.iterrows():
            key = _norm_code_key(row.get("hotel_code"))
            if not key:
                continue
            rec = {c: (None if pd.isna(row.get(c)) else row.get(c)) for c in cols if c in existing.columns}
            # garder code original pilote (H2075)
            rec["hotel_code"] = str(row.get("hotel_code")).strip()
            existing_by_key[key] = rec

    seen: set[str] = set()
    rows: list[dict[str, Any]] = []

    for _, srow in scrape.iterrows():
        scraped = scrape_row_to_hotel(srow)
        code = scraped.get("hotel_code") or ""
        key = _norm_code_key(code)
        if not key or not code:
            continue
        if key in seen:
            continue
        seen.add(key)

        base = empty_hotel_template(cols)
        prev = existing_by_key.get(key)

        if prev:
            # partir de la fiche pilote
            base.update({c: prev.get(c) for c in cols if c in prev})
            # code pilote prioritaire
            base["hotel_code"] = prev.get("hotel_code") or code
            if force_identity:
                for c in SCRAPE_IDENTITY:
                    if scraped.get(c) is not None and scraped.get(c) != "":
                        base[c] = scraped[c]
            else:
                # remplir identité seulement si vide
                for c in SCRAPE_IDENTITY:
                    cur = base.get(c)
                    empty = cur is None or (isinstance(cur, float) and pd.isna(cur)) or str(cur).strip() in {"", "nan"}
                    if empty and scraped.get(c) is not None and scraped.get(c) != "":
                        base[c] = scraped[c]
            # binaires équipements : toujours reprendre le scrape (services_raw),
            # sauf compte pilote métier > 1 (ex. 3 restos, 13 salles de réunion)
            amenity_cols = list(dict.fromkeys(
                list(SCRAPE_BOOL_MAP.values()) + ["hotel_non_f_b_salles_de_reunion"]
            ))
            for c in amenity_cols:
                if scraped.get(c) is None:
                    continue
                cur = base.get(c)
                try:
                    if cur is not None and float(cur) > 1:
                        continue  # compte pilote
                except (TypeError, ValueError):
                    pass
                base[c] = scraped[c]
        else:
            base.update(scraped)
            base["hotel_code"] = code

        # brand always upper if present
        if base.get("hotel_brand"):
            base["hotel_brand"] = _upper_brand(base["hotel_brand"])

        rows.append({c: base.get(c) for c in cols})

    # pilotes absents du scrape (garder)
    for key, prev in existing_by_key.items():
        if key in seen:
            continue
        rec = empty_hotel_template(cols)
        rec.update({c: prev.get(c) for c in cols if c in prev})
        if rec.get("hotel_brand"):
            rec["hotel_brand"] = _upper_brand(rec["hotel_brand"])
        rows.append(rec)
        seen.add(key)

    frame = pd.DataFrame(rows)
    # ordre colonnes
    for c in cols:
        if c not in frame.columns:
            frame[c] = None
    frame = frame[cols]
    # tri brand puis code
    frame["_b"] = frame["hotel_brand"].fillna("").astype(str)
    frame["_c"] = frame["hotel_code"].fillna("").astype(str)
    frame = frame.sort_values(["_b", "_c"], kind="mergesort").drop(columns=["_b", "_c"])
    frame = frame.reset_index(drop=True)
    return frame


def sync_hotel_data(
    *,
    force_identity: bool = False,
    out_path: Path | None = None,
) -> dict[str, Any]:
    out_path = out_path or HOTEL_DATA
    frame = build_hotel_data(force_identity=force_identity)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_excel(out_path, index=False, sheet_name="Sheet1")
    n_brand = int(frame["hotel_brand"].notna().sum()) if "hotel_brand" in frame.columns else 0
    n_coords = int(
        frame["hotel_lat"].notna().sum()
    ) if "hotel_lat" in frame.columns else 0
    summary = {
        "ok": True,
        "path": str(out_path),
        "n_hotels": int(len(frame)),
        "n_with_brand": n_brand,
        "n_with_coords": n_coords,
        "n_with_country": int(frame["hotel_country"].notna().sum())
        if "hotel_country" in frame.columns
        else 0,
        "sample": frame[
            [c for c in ("hotel_code", "hotel_name", "hotel_brand", "hotel_city", "hotel_country") if c in frame.columns]
        ]
        .head(5)
        .to_dict(orient="records"),
    }
    return summary


def main() -> None:
    p = argparse.ArgumentParser(description="Sync hotels_all → hotel_data.xlsx")
    p.add_argument(
        "--force-identity",
        action="store_true",
        help="Écrase code/nom/adresse/GPS des pilotes avec le scrape",
    )
    args = p.parse_args()
    print(json.dumps(sync_hotel_data(force_identity=args.force_identity), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
