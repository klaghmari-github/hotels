#!/usr/bin/env python3
"""
Enrichit ``data/hotel_brand_data.xlsx`` depuis ``data/marques/marques.xlsx``.

Colonnes identité / marque (remplies) :
* ``Marque`` — nom UPPERCASE
* ``logo_path`` — chemin relatif sous ``data/marques/`` (ex. ``economy/ibis.png``)
* ``cat_<slug>`` — dummies 0/1 (ECONOMY, MIDSCALE, PREMIUM, …)

Colonnes parc hôtelier (vides à remplir, sauf valeurs déjà saisies) :
* ``Nb_Hotels``, ``Nb_Ch_*``, ``Nb_Resto_*``, ``Nb_Bar_*``

Usage
-----
    cd accord
    python -m sync_brand_data
    python -m sync_brand_data --force-empty-counts  # remet les Nb_* à vide
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
MARQUES_XLSX = DATA / "marques" / "marques.xlsx"
BRAND_XLSX = DATA / "hotel_brand_data.xlsx"

# Effectifs parc — saisie admin (restent vides si absents de l'ancien fichier)
COUNT_COLS = [
    "Nb_Hotels",
    "Nb_Ch_0_49",
    "Nb_Ch_50_99",
    "Nb_Ch_100_149",
    "Nb_Ch_150_199",
    "Nb_Ch_200_249",
    "Nb_Ch_250_299",
    "Nb_Ch_300_Plus",
    "Nb_Resto_0",
    "Nb_Resto_1",
    "Nb_Resto_2",
    "Nb_Resto_3",
    "Nb_Bar_0",
    "Nb_Bar_1",
    "Nb_Bar_2",
    "Nb_Bar_3",
]


def cat_col_name(categorie_slug: str) -> str:
    """``lifestyle_by_ennismore`` → ``cat_lifestyle_by_ennismore``."""
    slug = re.sub(r"[^a-z0-9]+", "_", str(categorie_slug or "").lower()).strip("_")
    return f"cat_{slug or 'autres'}"


def category_columns(slugs: list[str]) -> list[str]:
    return [cat_col_name(s) for s in sorted(set(slugs))]


def _norm_brand(name: Any) -> str:
    s = str(name or "").strip().upper()
    s = re.sub(r"\s+", " ", s)
    return s


def load_marques(path: Path | None = None) -> pd.DataFrame:
    path = path or MARQUES_XLSX
    if not path.exists():
        raise FileNotFoundError(f"marques.xlsx introuvable: {path}")
    df = pd.read_excel(path)
    if df.empty:
        return df
    out = df.copy()
    if "marque_nom" not in out.columns:
        raise ValueError("marques.xlsx: colonne marque_nom manquante")
    out["Marque"] = out["marque_nom"].map(_norm_brand)
    if "categorie_slug" not in out.columns:
        out["categorie_slug"] = "autres"
    if "logo_path" not in out.columns:
        out["logo_path"] = ""
    # garder une ligne par marque
    out = out.drop_duplicates(subset=["Marque"], keep="first")
    return out.reset_index(drop=True)


def load_existing_brand(path: Path | None = None) -> pd.DataFrame:
    path = path or BRAND_XLSX
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_excel(path, sheet_name="Sheet1")
    except ValueError:
        return pd.read_excel(path, sheet_name=0)


def build_brand_frame(
    *,
    force_empty_counts: bool = False,
    marques_path: Path | None = None,
    existing_path: Path | None = None,
) -> pd.DataFrame:
    """Construit le DataFrame hotel_brand_data enrichi."""
    marques = load_marques(marques_path)
    existing = load_existing_brand(existing_path)

    cat_slugs = (
        marques["categorie_slug"].fillna("autres").astype(str).str.strip().tolist()
    )
    cat_cols = category_columns(cat_slugs)

    # Index des effectifs existants par marque
    existing_map: dict[str, dict[str, Any]] = {}
    if not existing.empty and "Marque" in existing.columns and not force_empty_counts:
        for _, row in existing.iterrows():
            key = _norm_brand(row.get("Marque"))
            if not key:
                continue
            existing_map[key] = {
                c: row.get(c) for c in COUNT_COLS if c in existing.columns
            }

    rows: list[dict[str, Any]] = []
    for _, m in marques.iterrows():
        name = _norm_brand(m.get("Marque") or m.get("marque_nom"))
        if not name:
            continue
        logo = str(m.get("logo_path") or "").strip().replace("\\", "/")
        if logo.lower() in {"nan", "none", "null"}:
            logo = ""
        # Toujours relatif à data/marques/ (servi par run_admin via /api/marques/logos/)
        for prefix in ("data/marques/", "marques/", "./data/marques/", "./marques/"):
            if logo.lower().startswith(prefix):
                logo = logo[len(prefix) :]
                break
        logo = logo.lstrip("/")
        # vérifie que le fichier existe bien sous data/marques/
        if logo:
            abs_logo = (DATA / "marques" / logo).resolve()
            try:
                abs_logo.relative_to((DATA / "marques").resolve())
            except ValueError:
                logo = ""
            else:
                if not abs_logo.is_file():
                    # fallback logo_file + categorie_slug
                    cat = str(m.get("categorie_slug") or "").strip()
                    fname = str(m.get("logo_file") or "").strip()
                    if cat and fname:
                        alt = f"{cat}/{fname}"
                        if (DATA / "marques" / alt).is_file():
                            logo = alt
                        else:
                            logo = ""
                    else:
                        logo = ""
        slug = str(m.get("categorie_slug") or "autres").strip() or "autres"
        rec: dict[str, Any] = {
            "Marque": name,
            "logo_path": logo,
        }
        # dummies catégorie
        for c in cat_cols:
            rec[c] = 0
        rec[cat_col_name(slug)] = 1

        # effectifs : conserver si déjà saisis, sinon None (vide)
        prev = existing_map.get(name, {})
        for c in COUNT_COLS:
            val = prev.get(c) if prev else None
            if val is None or (isinstance(val, float) and pd.isna(val)):
                rec[c] = None
            else:
                # garder nombres
                try:
                    rec[c] = int(val) if float(val) == int(float(val)) else float(val)
                except (TypeError, ValueError):
                    rec[c] = val
        rows.append(rec)

    # Marques présentes dans l'ancien fichier mais absentes de marques.xlsx
    known = {_norm_brand(r["Marque"]) for r in rows}
    if not existing.empty and "Marque" in existing.columns:
        for _, row in existing.iterrows():
            name = _norm_brand(row.get("Marque"))
            if not name or name in known:
                continue
            rec = {"Marque": name, "logo_path": ""}
            for c in cat_cols:
                rec[c] = int(row[c]) if c in existing.columns and pd.notna(row.get(c)) else 0
            for c in COUNT_COLS:
                val = row.get(c) if c in existing.columns else None
                rec[c] = None if val is None or (isinstance(val, float) and pd.isna(val)) else val
            rows.append(rec)

    cols = ["Marque", "logo_path", *cat_cols, *COUNT_COLS]
    frame = pd.DataFrame(rows)
    for c in cols:
        if c not in frame.columns:
            frame[c] = None if c in COUNT_COLS else (0 if c.startswith("cat_") else "")
    frame = frame[cols]
    frame = frame.sort_values("Marque").reset_index(drop=True)
    # dummies en int 0/1
    for c in cat_cols:
        frame[c] = pd.to_numeric(frame[c], errors="coerce").fillna(0).astype(int)
    return frame


def sync_hotel_brand_data(
    *,
    force_empty_counts: bool = False,
    out_path: Path | None = None,
) -> dict[str, Any]:
    out_path = out_path or BRAND_XLSX
    frame = build_brand_frame(force_empty_counts=force_empty_counts)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_excel(out_path, index=False, sheet_name="Sheet1")
    cat_cols = [c for c in frame.columns if c.startswith("cat_")]
    summary = {
        "ok": True,
        "path": str(out_path),
        "n_brands": int(len(frame)),
        "category_columns": cat_cols,
        "n_with_logo": int((frame["logo_path"].astype(str).str.len() > 0).sum()),
        "n_with_nb_hotels": int(frame["Nb_Hotels"].notna().sum())
        if "Nb_Hotels" in frame.columns
        else 0,
        "sample": frame[["Marque", "logo_path", *cat_cols[:3]]].head(5).to_dict(
            orient="records"
        ),
    }
    return summary


def main() -> None:
    import json

    p = argparse.ArgumentParser(description="Sync marques → hotel_brand_data.xlsx")
    p.add_argument(
        "--force-empty-counts",
        action="store_true",
        help="Ignore les Nb_* déjà saisis (tout à vide)",
    )
    args = p.parse_args()
    result = sync_hotel_brand_data(force_empty_counts=args.force_empty_counts)
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
