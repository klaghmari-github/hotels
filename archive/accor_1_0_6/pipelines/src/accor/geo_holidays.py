#!/usr/bin/env python3
"""
Calendrier FR par hôtel × mois — hotel_holidays_data.xlsx.

  ensure_hotel_holidays_data   charge si présent, sinon grille minimale
  rebuild_hotel_holidays_data  hotels × années sales × mois terminés

Calcul
------
  jours fériés FR (fixe + Pâques)
  vacances scolaires zones A/B/C (binaires + compteurs)
  weekends, nb jours mois, % holidays
  département / commune repris du fichier existant si dispo

Pas d'appel réseau. Doc : docs/DATA.md.
"""

from __future__ import annotations

import json
from calendar import monthrange
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from archive.accor_1_0_6.pipelines.src.accor.data_io import DATA_DIR
HOLIDAYS_FILENAME = "hotel_holidays_data.xlsx"
HOLIDAYS_SHEET = "hotel_holidays"

# Colonnes calendrier (listes ISO + compteurs exclusifs)
# zone_scolaire (A/B/C texte) retirée : les binaires a/b/c suffisent
HOLIDAY_FEATURE_COLS = [
    "zone_scolaire_a",
    "zone_scolaire_b",
    "zone_scolaire_c",
    "departement",
    "commune",
    "nb_jours_dans_mois",
    "nb_jours_feries",
    "nb_jours_weekend",
    "nb_jours_vacances_scolaires",
    "nb_jours_vacances_hors_feries",
    "nb_jours_holidays",  # union exclusive weekend ∪ fériés ∪ vacances scolaires
    "pct_jours_holidays",  # nb_jours_holidays / nb_jours_dans_mois
    "jours_feries",
    "jours_weekend",
    "jours_vacances_scolaires",
    "jours_vacances_hors_feries",
    "jours_holidays",  # liste sans doublons
]


def holidays_path() -> Path:
    return DATA_DIR / HOLIDAYS_FILENAME


def load_holidays_frame(path: Path | None = None) -> pd.DataFrame:
    path = path or holidays_path()
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_excel(path, sheet_name=HOLIDAYS_SHEET)
    except ValueError:
        try:
            return pd.read_excel(path, sheet_name="holidays_monthly")
        except ValueError:
            return pd.read_excel(path, sheet_name=0)


def save_holidays_frame(frame: pd.DataFrame, path: Path | None = None) -> Path:
    path = path or holidays_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    other: dict[str, pd.DataFrame] = {}
    if path.exists():
        try:
            xl = pd.ExcelFile(path)
            for name in xl.sheet_names:
                if name not in (HOLIDAYS_SHEET, "holidays_monthly"):
                    other[name] = pd.read_excel(path, sheet_name=name)
        except Exception:
            pass
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        frame.to_excel(writer, index=False, sheet_name=HOLIDAYS_SHEET)
        for name, df in other.items():
            df.to_excel(writer, index=False, sheet_name=str(name)[:31])
    return path


# ---------------------------------------------------------------------------
# Jours fériés France
# ---------------------------------------------------------------------------

def _easter_sunday(year: int) -> date:
    """Dimanche de Pâques (algorithme de Meeus/Jones/Butcher)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    ll = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * ll) // 451
    month, day = divmod(h + ll - 7 * m + 114, 31)
    return date(year, month, day + 1)


def french_public_holidays(year: int) -> set[date]:
    """Jours fériés légaux métropole (hors Alsace-Moselle spécifiques)."""
    easter = _easter_sunday(year)
    fixed = {
        date(year, 1, 1),   # Jour de l'an
        date(year, 5, 1),   # Fête du travail
        date(year, 5, 8),   # Victoire 1945
        date(year, 7, 14),  # Fête nationale
        date(year, 8, 15),  # Assomption
        date(year, 11, 1),  # Toussaint
        date(year, 11, 11), # Armistice
        date(year, 12, 25), # Noël
    }
    movable = {
        easter + timedelta(days=1),   # Lundi de Pâques
        easter + timedelta(days=39),  # Ascension
        easter + timedelta(days=50),  # Lundi de Pentecôte
    }
    return fixed | movable


# ---------------------------------------------------------------------------
# Vacances scolaires (périodes zones A/B/C — repères officiels récents)
# ---------------------------------------------------------------------------

# Périodes approximatives (début inclus, fin exclus) par zone et année scolaire.
# Format: year_mois_cible -> liste (zone, start, end) pour les jours dans year.
# On stocke par année civile les plages connues.

def _school_periods_for_year(year: int) -> dict[str, list[tuple[date, date]]]:
    """
    Retourne pour chaque zone (A/B/C) les intervalles [start, end) de vacances
    chevauchant l'année civile ``year``.

    Sources : calendriers MEN (repères 2022–2026). Si année inconnue → {}.
    """
    # Année scolaire Y-1 / Y couvre jan–août de Y et sept–déc de Y-1
    # On encode les grandes périodes pour 2023–2026.
    table: dict[int, dict[str, list[tuple[date, date]]]] = {
        2023: {
            "A": [
                (date(2023, 2, 4), date(2023, 2, 20)),
                (date(2023, 4, 15), date(2023, 5, 2)),
                (date(2023, 7, 8), date(2023, 9, 4)),
                (date(2023, 10, 21), date(2023, 11, 6)),
                (date(2023, 12, 23), date(2024, 1, 8)),
            ],
            "B": [
                (date(2023, 2, 11), date(2023, 2, 27)),
                (date(2023, 4, 8), date(2023, 4, 24)),
                (date(2023, 7, 8), date(2023, 9, 4)),
                (date(2023, 10, 21), date(2023, 11, 6)),
                (date(2023, 12, 23), date(2024, 1, 8)),
            ],
            "C": [
                (date(2023, 2, 18), date(2023, 3, 6)),
                (date(2023, 4, 22), date(2023, 5, 9)),
                (date(2023, 7, 8), date(2023, 9, 4)),
                (date(2023, 10, 21), date(2023, 11, 6)),
                (date(2023, 12, 23), date(2024, 1, 8)),
            ],
        },
        2024: {
            "A": [
                (date(2023, 12, 23), date(2024, 1, 8)),
                (date(2024, 2, 10), date(2024, 2, 26)),
                (date(2024, 4, 6), date(2024, 4, 22)),
                (date(2024, 7, 6), date(2024, 9, 2)),
                (date(2024, 10, 19), date(2024, 11, 4)),
                (date(2024, 12, 21), date(2025, 1, 6)),
            ],
            "B": [
                (date(2023, 12, 23), date(2024, 1, 8)),
                (date(2024, 2, 17), date(2024, 3, 4)),
                (date(2024, 4, 13), date(2024, 4, 29)),
                (date(2024, 7, 6), date(2024, 9, 2)),
                (date(2024, 10, 19), date(2024, 11, 4)),
                (date(2024, 12, 21), date(2025, 1, 6)),
            ],
            "C": [
                (date(2023, 12, 23), date(2024, 1, 8)),
                (date(2024, 2, 24), date(2024, 3, 11)),
                (date(2024, 4, 20), date(2024, 5, 6)),
                (date(2024, 7, 6), date(2024, 9, 2)),
                (date(2024, 10, 19), date(2024, 11, 4)),
                (date(2024, 12, 21), date(2025, 1, 6)),
            ],
        },
        2025: {
            "A": [
                (date(2024, 12, 21), date(2025, 1, 6)),
                (date(2025, 2, 8), date(2025, 2, 24)),
                (date(2025, 4, 5), date(2025, 4, 22)),
                (date(2025, 7, 5), date(2025, 9, 1)),
                (date(2025, 10, 18), date(2025, 11, 3)),
                (date(2025, 12, 20), date(2026, 1, 5)),
            ],
            "B": [
                (date(2024, 12, 21), date(2025, 1, 6)),
                (date(2025, 2, 15), date(2025, 3, 3)),
                (date(2025, 4, 12), date(2025, 4, 28)),
                (date(2025, 7, 5), date(2025, 9, 1)),
                (date(2025, 10, 18), date(2025, 11, 3)),
                (date(2025, 12, 20), date(2026, 1, 5)),
            ],
            "C": [
                (date(2024, 12, 21), date(2025, 1, 6)),
                (date(2025, 2, 22), date(2025, 3, 10)),
                (date(2025, 4, 19), date(2025, 5, 5)),
                (date(2025, 7, 5), date(2025, 9, 1)),
                (date(2025, 10, 18), date(2025, 11, 3)),
                (date(2025, 12, 20), date(2026, 1, 5)),
            ],
        },
        2026: {
            "A": [
                (date(2025, 12, 20), date(2026, 1, 5)),
                (date(2026, 2, 7), date(2026, 2, 23)),
                (date(2026, 4, 4), date(2026, 4, 20)),
                (date(2026, 7, 4), date(2026, 9, 1)),
            ],
            "B": [
                (date(2025, 12, 20), date(2026, 1, 5)),
                (date(2026, 2, 14), date(2026, 3, 2)),
                (date(2026, 4, 11), date(2026, 4, 27)),
                (date(2026, 7, 4), date(2026, 9, 1)),
            ],
            "C": [
                (date(2025, 12, 20), date(2026, 1, 5)),
                (date(2026, 2, 21), date(2026, 3, 9)),
                (date(2026, 4, 18), date(2026, 5, 4)),
                (date(2026, 7, 4), date(2026, 9, 1)),
            ],
        },
    }
    return table.get(year, {"A": [], "B": [], "C": []})


def _days_in_month(year: int, month: int) -> list[date]:
    _, n = monthrange(year, month)
    return [date(year, month, d) for d in range(1, n + 1)]


def _days_in_ranges(days: list[date], ranges: list[tuple[date, date]]) -> list[date]:
    out = []
    for d in days:
        for start, end in ranges:
            if start <= d < end:
                out.append(d)
                break
    return out


def _iso_list(days: list[date]) -> str:
    return json.dumps([d.isoformat() for d in sorted(set(days))], ensure_ascii=False)


def _zone_letter_from_row(row: pd.Series | dict[str, Any]) -> str:
    """Reconstitue A/B/C depuis la colonne texte (legacy) ou les binaires."""
    z = str(row.get("zone_scolaire") or "").strip().upper()
    if z in {"A", "B", "C"}:
        return z
    try:
        if int(row.get("zone_scolaire_a") or 0) == 1:
            return "A"
        if int(row.get("zone_scolaire_b") or 0) == 1:
            return "B"
        if int(row.get("zone_scolaire_c") or 0) == 1:
            return "C"
    except (TypeError, ValueError):
        pass
    return ""


def _hotel_meta_lookup(existing: pd.DataFrame) -> dict[str, dict[str, Any]]:
    """hotel_code → {zone, departement, commune} depuis fichier existant."""
    lookup: dict[str, dict[str, Any]] = {}
    if existing is None or existing.empty or "hotel_code" not in existing.columns:
        return lookup
    for code, group in existing.groupby("hotel_code"):
        row = group.iloc[0]
        lookup[str(code)] = {
            "zone_scolaire": _zone_letter_from_row(row),
            "departement": row.get("departement") or "",
            "commune": row.get("commune") or "",
        }
    return lookup


def _zone_from_lat_lon(lat: Any, lon: Any) -> str:
    """Heuristique grossière zone A/B/C via lon (fallback)."""
    try:
        lo = float(lon)
    except (TypeError, ValueError):
        return "C"
    # Est → A, Ouest → B, IdF/centre → C (approximatif)
    if lo > 4.5:
        return "A"
    if lo < 1.5:
        return "B"
    return "C"


# Départements → zone scolaire (académies MEN, repère 2023+)
_ZONE_A_DEPTS = {
    "01", "03", "07", "15", "16", "17", "19", "21", "23", "24", "25", "26",
    "33", "38", "39", "40", "42", "43", "47", "58", "63", "64", "69", "70",
    "71", "73", "74", "79", "86", "87", "89", "90",
}
_ZONE_B_DEPTS = {
    "02", "04", "05", "06", "08", "10", "13", "14", "18", "22", "27", "28",
    "29", "35", "36", "37", "41", "44", "45", "49", "50", "51", "52", "53",
    "54", "55", "56", "57", "59", "60", "61", "62", "67", "68", "72", "76",
    "80", "84", "85", "88",
    "2A", "2B",  # Corse rattachée zone B (académies)
}
_ZONE_C_DEPTS = {
    "09", "11", "12", "30", "31", "32", "34", "46", "48", "65", "66", "75",
    "77", "78", "81", "82", "91", "92", "93", "94", "95",
}


def _dept_from_postal(postal: Any) -> str:
    """Extrait le code département (2 car. ou 2A/2B) depuis un CP français."""
    s = str(postal or "").strip().upper().replace(" ", "")
    if not s:
        return ""
    # Corse : 20000–20199 → 2A, 20200–20999 → 2B (approx)
    if s.startswith("20") and len(s) >= 3:
        try:
            n = int(s[:3])
            return "2A" if n < 202 else "2B"
        except ValueError:
            return "20"
    if s[:2].isdigit():
        return s[:2]
    return ""


def _zone_from_department(dept: str) -> str:
    d = str(dept or "").strip().upper()
    if d in _ZONE_A_DEPTS:
        return "A"
    if d in _ZONE_B_DEPTS:
        return "B"
    if d in _ZONE_C_DEPTS:
        return "C"
    return ""


def resolve_hotel_zone(
    hotel_row: pd.Series | dict[str, Any],
    *,
    meta: dict[str, Any] | None = None,
) -> tuple[str, str, str]:
    """
    Détermine (zone A/B/C, departement, commune) pour un hôtel.

    Priorité zone : méta existante → département (CP) → lat/lon.
    """
    meta = meta or {}
    zone = str(meta.get("zone_scolaire") or "").strip().upper()
    dep = str(meta.get("departement") or "").strip()
    commune = str(meta.get("commune") or hotel_row.get("hotel_city") or "").strip()

    if not dep:
        dep = _dept_from_postal(hotel_row.get("hotel_code_postal"))
    if zone not in {"A", "B", "C"}:
        zone = _zone_from_department(dep)
    if zone not in {"A", "B", "C"}:
        zone = _zone_from_lat_lon(hotel_row.get("hotel_lat"), hotel_row.get("hotel_lon"))
    if zone not in {"A", "B", "C"}:
        zone = "C"
    return zone, dep, commune


def _weekends_in_month(days: list[date]) -> list[date]:
    """Samedi (5) + dimanche (6)."""
    return [d for d in days if d.weekday() >= 5]


def compute_holidays_rows(
    hotels: pd.DataFrame,
    pairs: list[tuple[int, int]],
    *,
    meta: dict[str, dict[str, Any]] | None = None,
    school_cache: dict[int, dict[str, list[tuple[date, date]]]] | None = None,
) -> list[dict[str, Any]]:
    """
    Calcule les lignes holidays (hôtel × année × mois) pour un sous-ensemble d'hôtels.

    Utilisé par :func:`rebuild_hotel_holidays_data` et ``parallel_holidays``.
    """
    meta = meta or {}
    school_cache = school_cache if school_cache is not None else {}
    rows: list[dict[str, Any]] = []

    for _, h in hotels.iterrows():
        code = str(h.get("hotel_code") or "").strip()
        if not code:
            continue
        name = h.get("hotel_name")
        info = meta.get(code, {})
        zone, dep, commune = resolve_hotel_zone(h, meta=info)

        for year, month in pairs:
            if year not in school_cache:
                school_cache[year] = _school_periods_for_year(year)
            days = _days_in_month(year, month)
            n_mois = len(days)

            feries = sorted({d for d in days if d in french_public_holidays(year)})
            weekends = sorted({d for d in _weekends_in_month(days)})
            vac_ranges = school_cache[year].get(zone, [])
            vac_all = sorted(set(_days_in_ranges(days, vac_ranges)))
            vac_hors = sorted(set(vac_all) - set(feries))

            holidays_set = sorted(set(feries) | set(weekends) | set(vac_all))
            nb_holidays = len(holidays_set)
            pct_holidays = (nb_holidays / n_mois) if n_mois else 0.0

            rows.append(
                {
                    "hotel_code": code,
                    "hotel_name": name,
                    "annee": int(year),
                    "mois": int(month),
                    "zone_scolaire_a": 1 if zone == "A" else 0,
                    "zone_scolaire_b": 1 if zone == "B" else 0,
                    "zone_scolaire_c": 1 if zone == "C" else 0,
                    "departement": dep,
                    "commune": commune,
                    "nb_jours_dans_mois": n_mois,
                    "nb_jours_feries": len(feries),
                    "nb_jours_weekend": len(weekends),
                    "nb_jours_vacances_scolaires": len(vac_all),
                    "nb_jours_vacances_hors_feries": len(vac_hors),
                    "nb_jours_holidays": nb_holidays,
                    "pct_jours_holidays": round(pct_holidays, 6),
                    "jours_feries": _iso_list(feries),
                    "jours_weekend": _iso_list(weekends),
                    "jours_vacances_scolaires": _iso_list(vac_all),
                    "jours_vacances_hors_feries": _iso_list(vac_hors),
                    "jours_holidays": _iso_list(holidays_set),
                }
            )
    return rows


def rebuild_hotel_holidays_data() -> dict[str, Any]:
    """
    Recalcule ``hotel_holidays_data.xlsx``.

    * Hôtels = hotel_data
    * Années = années de hotel_sales_data (ou sales_raw via sales_years)
    * Mois = mois terminés (mois en cours exclu)

    Pour chaque mois on produit les **listes de jours** (ISO) :
    fériés, weekend, vacances scolaires, puis ``jours_holidays`` =
    union exclusive (sans doublon) weekend ∪ fériés ∪ vacances scolaires.

    Compteurs :
    * nb_jours_feries / weekend / vacances_scolaires (bruts)
    * nb_jours_vacances_hors_feries (vacances hors fériés)
    * nb_jours_holidays (taille de l'union exclusive)
    * pct_jours_holidays = nb_jours_holidays / nb_jours_dans_mois
    * zone_scolaire_a/b/c en 0/1 (la lettre A/B/C n'est plus exportée)
    """
    from archive.accor_1_0_6.pipelines.src.accor.geo_common import load_hotels, sales_years, year_month_pairs

    hotels = load_hotels()
    if hotels.empty:
        raise ValueError("hotel_data.xlsx vide ou introuvable.")

    years = sales_years()
    pairs = year_month_pairs(years)
    if not pairs:
        raise ValueError("Aucun mois terminé à générer.")

    existing = load_holidays_frame()
    meta = _hotel_meta_lookup(existing)

    rows = compute_holidays_rows(hotels, pairs, meta=meta)
    frame = pd.DataFrame(rows)
    sort_cols = [c for c in ("hotel_code", "annee", "mois") if c in frame.columns]
    if sort_cols:
        frame = frame.sort_values(sort_cols).reset_index(drop=True)

    path = save_holidays_frame(frame)
    return {
        "ok": True,
        "path": str(path),
        "rows": len(frame),
        "columns": list(frame.columns),
        "n_columns": len(frame.columns),
        "years": years,
        "n_hotels": int(hotels["hotel_code"].nunique())
        if "hotel_code" in hotels.columns
        else len(hotels),
    }


def holidays_day_sets(holidays: pd.DataFrame) -> dict[tuple[str, int, int], set[str]]:
    """
    Index (hotel_code, annee, mois) → set de dates ISO « holidays »
    (union exclusive weekend ∪ fériés ∪ vacances).

    Utilisé par ``sales_prep`` pour tagger chaque ticket raw.
    """
    out: dict[tuple[str, int, int], set[str]] = {}
    if holidays is None or holidays.empty:
        return out
    col = "jours_holidays" if "jours_holidays" in holidays.columns else None
    for _, row in holidays.iterrows():
        code = str(row.get("hotel_code") or "").strip()
        try:
            y, m = int(row["annee"]), int(row["mois"])
        except Exception:
            continue
        days: set[str] = set()
        if col and pd.notna(row.get(col)):
            val = row[col]
            if isinstance(val, str) and val.strip().startswith("["):
                try:
                    days = set(json.loads(val.replace("'", '"')))
                except json.JSONDecodeError:
                    days = set()
            elif isinstance(val, (list, tuple)):
                days = set(str(x) for x in val)
        else:
            # fallback union des listes séparées
            for c in ("jours_feries", "jours_weekend", "jours_vacances_scolaires"):
                if c not in holidays.columns:
                    continue
                val = row.get(c)
                if isinstance(val, str) and val.strip().startswith("["):
                    try:
                        days |= set(json.loads(val.replace("'", '"')))
                    except json.JSONDecodeError:
                        pass
        out[(code, y, m)] = days
    return out



def ensure_hotel_holidays_data(
    *,
    force_refresh: bool = False,
    hotels: pd.DataFrame | None = None,
    years: tuple[int, ...] | None = None,
) -> pd.DataFrame:
    """
    Garantit le fichier holidays.

    Si force_refresh ou fichier absent → :func:`rebuild_hotel_holidays_data`.
    """
    path = holidays_path()
    if path.exists() and not force_refresh:
        frame = load_holidays_frame(path)
        if not frame.empty:
            return frame
    result = rebuild_hotel_holidays_data()
    return load_holidays_frame(path)
