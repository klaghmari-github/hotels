#!/usr/bin/env python3
"""
Aligne les Excel de ``accord/data/`` sur les colonnes affichées dans l'UI.

Pour chaque dataset (hors All Data) :
  - lit le xlsx actuel (ou une source archive de secours)
  - ne conserve que ``schema.editable_columns``
  - réécrit le fichier (feuille nommée comme dans le schéma)

Holidays : privilégie ``archive/prepare/HolidaysPrep/Output`` (arrays de jours).
Sales : reprend les indicateurs ventes de l'xlsx courant (sans fériés).
Puis reconstruit ``all_data.xlsx`` (jointure).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
ARCHIVE = ROOT.parent / "archive"
sys.path.insert(0, str(ROOT))

from schemas import DATASETS, DATA_DIR, get_schema  # noqa: E402
from store import _project_to_schema, _save_excel  # noqa: E402


def _read_any(path: Path, sheet: str | int | None = None) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        if sheet is not None:
            return pd.read_excel(path, sheet_name=sheet)
    except ValueError:
        pass
    try:
        return pd.read_excel(path, sheet_name=0)
    except Exception:
        return pd.DataFrame()


def sync_brand() -> dict:
    schema = get_schema("brand")
    frame = _read_any(schema.path, schema.sheet)
    projected = _project_to_schema(frame, schema)
    _save_excel("brand", projected, schema)
    return {"id": "brand", "rows": len(projected), "cols": list(projected.columns)}


def sync_hotel() -> dict:
    schema = get_schema("hotel")
    frame = _read_any(schema.path, schema.sheet)
    projected = _project_to_schema(frame, schema)
    _save_excel("hotel", projected, schema)
    return {"id": "hotel", "rows": len(projected), "cols": list(projected.columns)}


def sync_weather() -> dict:
    schema = get_schema("weather")
    frame = _read_any(schema.path, schema.sheet)
    projected = _project_to_schema(frame, schema)
    _save_excel("weather", projected, schema)
    return {"id": "weather", "rows": len(projected), "cols": list(projected.columns)}


def sync_sales() -> dict:
    """Indicateurs ventes uniquement (pas de colonnes holidays / heure / weekend)."""
    schema = get_schema("sales")
    frame = _read_any(schema.path, schema.sheet)
    if frame.empty:
        # Fallback archive SalesPrep
        alt = ARCHIVE / "prepare" / "SalesPrep" / "Output" / "hotel_sales_data.xlsx"
        frame = _read_any(alt, "hotel_sales")
    # Drop holiday-like columns if present before project
    drop = [
        c
        for c in frame.columns
        if any(
            k in c
            for k in (
                "ferie",
                "vacance",
                "zone_scolaire",
                "departement",
                "jours_feries",
                "jours_vacances",
            )
        )
    ]
    if drop:
        frame = frame.drop(columns=drop, errors="ignore")
    projected = _project_to_schema(frame, schema)
    _save_excel("sales", projected, schema)
    return {"id": "sales", "rows": len(projected), "cols": list(projected.columns)}


def sync_holidays() -> dict:
    """Source de vérité : HolidaysPrep (arrays de jours inclus)."""
    schema = get_schema("holidays")
    candidates = [
        ARCHIVE / "prepare" / "HolidaysPrep" / "Output" / "hotel_holidays_data.xlsx",
        schema.path,
    ]
    frame = pd.DataFrame()
    extra_sheets: dict[str, pd.DataFrame] = {}
    for path in candidates:
        if not path.exists():
            continue
        xl = pd.ExcelFile(path)
        # feuille principale
        for name in ("hotel_holidays", "holidays_monthly", 0):
            try:
                frame = pd.read_excel(path, sheet_name=name)
                break
            except ValueError:
                continue
        for name in xl.sheet_names:
            if name in ("hotel_holidays", "holidays_monthly"):
                continue
            extra_sheets[name] = pd.read_excel(path, sheet_name=name)
        if not frame.empty:
            break

    projected = _project_to_schema(frame, schema)
    # Écrire feuille principale + secondaires
    path = schema.path
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet_name = schema.sheet if isinstance(schema.sheet, str) else "hotel_holidays"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        projected.to_excel(writer, index=False, sheet_name=sheet_name)
        for name, df in extra_sheets.items():
            df.to_excel(writer, index=False, sheet_name=str(name)[:31])
    return {"id": "holidays", "rows": len(projected), "cols": list(projected.columns)}


def sync_all_data(*, fill_weather: bool = False, fill_proximity: bool = False) -> dict:
    from join_data import build_joined_dataframe, save_joined_excel
    from store import _cache, JOINED_DATASET_ID

    frame = build_joined_dataframe(
        fill_weather=fill_weather, fill_proximity=fill_proximity
    )
    path = save_joined_excel(frame)
    _cache.pop(JOINED_DATASET_ID, None)
    return {
        "id": "data",
        "path": str(path),
        "rows": len(frame),
        "cols": len(frame.columns),
    }


def main() -> int:
    print(f"DATA_DIR = {DATA_DIR}")
    results = []
    for fn in (sync_brand, sync_hotel, sync_weather, sync_sales, sync_holidays):
        r = fn()
        results.append(r)
        print(f"  [{r['id']}] rows={r['rows']} cols={len(r['cols'])}")
        # clear store cache if imported later
    # Invalide tout le cache store
    try:
        from store import _cache

        _cache.clear()
    except Exception:
        pass

    print("  [all_data] rebuild join…")
    r = sync_all_data(fill_weather=False, fill_proximity=False)
    results.append(r)
    print(f"  [all_data] rows={r['rows']} cols={r['cols']} → {r['path']}")

    # Vérification : colonnes fichier == schéma pour chaque dataset éditable
    print("\nVérification fichier ↔ schéma :")
    ok = True
    for did, schema in DATASETS.items():
        if did == "data" or not schema.editable_columns:
            continue
        frame = _read_any(schema.path, schema.sheet)
        file_cols = list(frame.columns)
        want = list(schema.editable_columns)
        if file_cols != want:
            ok = False
            missing = [c for c in want if c not in file_cols]
            extra = [c for c in file_cols if c not in want]
            print(f"  ✗ {did}: missing={missing[:5]} extra={extra[:5]} "
                  f"(n_file={len(file_cols)} n_schema={len(want)})")
        else:
            print(f"  ✓ {did}: {len(want)} colonnes, {len(frame)} lignes")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
