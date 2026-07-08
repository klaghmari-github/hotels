"""Chargement et normalisation du fichier ventes."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

FB_LABEL = "F_B"
NFB_LABEL = "N_F_B"


def normalize_category(type_value: str) -> str:
    text = str(type_value).upper().strip()
    if "NON" in text:
        return NFB_LABEL
    if "F&B" in text or "F_B" in text or text == "FB":
        return FB_LABEL
    return sanitize_fallback(text)


def sanitize_fallback(text: str) -> str:
    return text.replace("&", "_").replace(" ", "_").replace("-", "_")


def load_sales_frame(sales_path: Path, *, exclude_year: int | None = None) -> pd.DataFrame:
    """Charge les ventes et applique les règles de base du fichier consignes."""
    if sales_path.suffix.lower() in {".xlsx", ".xlsm"}:
        frame = pd.read_excel(sales_path)
    else:
        frame = pd.read_csv(sales_path)

    hotel_col = "NOM BOUTIQUE" if "NOM BOUTIQUE" in frame.columns else "HOTEL_NAME"
    date_col = "DATE" if "DATE" in frame.columns else "DATETIME"
    qty_col = "QUANTITE" if "QUANTITE" in frame.columns else "QTE"
    price_col = "PRIX TTC" if "PRIX TTC" in frame.columns else "PRIX HT"
    ticket_col = "ORDER ID (TICKET DE CAISSE)"
    product_col = "CODE EAN" if "CODE EAN" in frame.columns else "NOM DU PRODUIT"
    hour_col = "HEURE" if "HEURE" in frame.columns else None

    frame[date_col] = pd.to_datetime(frame[date_col], errors="coerce")
    frame = frame.dropna(subset=[date_col])
    frame["annee"] = frame[date_col].dt.year.astype(int)
    frame["mois"] = frame[date_col].dt.month.astype(int)

    if exclude_year is not None:
        frame = frame[frame["annee"] < exclude_year].copy()

    qty = pd.to_numeric(frame[qty_col], errors="coerce").fillna(0)
    price = pd.to_numeric(frame[price_col], errors="coerce").fillna(0)
    frame["montant_ventes"] = qty * price
    frame["nombre_ventes"] = qty
    frame["nombre_paniers"] = frame[ticket_col] if ticket_col in frame.columns else frame.index
    frame["nombre_produits"] = frame[product_col]
    frame["nom_hotel"] = frame[hotel_col].astype(str)
    frame["categorie"] = frame["TYPE"].map(normalize_category)
    frame["sous_categorie"] = frame["GAMME"].astype(str)

    if hour_col and hour_col in frame.columns:
        frame["heure_vente"] = frame[hour_col].astype(str).str.slice(0, 2).astype(int, errors="ignore")
    else:
        frame["heure_vente"] = frame[date_col].dt.hour

    frame["is_weekend"] = frame[date_col].dt.dayofweek.isin([5, 6]).astype(int)
    frame["is_holiday"] = _french_holiday_flag(frame[date_col])

    return frame


def _french_holiday_flag(dates: pd.Series) -> pd.Series:
    """Jours fériés fixes France (approximation pour is_holiday)."""
    fixed = {(1, 1), (5, 1), (5, 8), (7, 14), (8, 15), (11, 1), (11, 11), (12, 25)}
    return dates.apply(lambda d: int((d.month, d.day) in fixed)).astype(int)


def detect_holdout_year(sales_path: Path) -> int:
    if sales_path.suffix.lower() in {".xlsx", ".xlsm"}:
        years = pd.read_excel(sales_path, usecols=["DATE"] if "DATE" in pd.read_excel(sales_path, nrows=0).columns else [0])
    else:
        sample = pd.read_csv(sales_path, usecols=["DATE"], nrows=1000)
        years = sample
    date_col = "DATE" if "DATE" in years.columns else years.columns[0]
    parsed = pd.to_datetime(years[date_col], errors="coerce")
    return int(parsed.dt.year.max())