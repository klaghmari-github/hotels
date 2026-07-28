#!/usr/bin/env python3
"""
Flags binaires de solution ROD sur hotel_data.

Colonnes (0/1) :
  hotel_solution_simply
  hotel_solution_liberty
  hotel_solution_connected

Par défaut 0 partout ; 1 uniquement pour les hôtels pilotes de la solution
(mapping ``data/rod_pilot_concepts.json``).

Ces colonnes passent ensuite dans all_data (join hotel) et model_data.
``simulateur_data`` s'appuie déjà sur le même mapping pilotes → solution.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from accor.data_io import DATA_DIR

SOLUTION_FLAG_COLS = (
    "hotel_solution_simply",
    "hotel_solution_liberty",
    "hotel_solution_connected",
)

_SOLUTION_TO_COL = {
    "SIMPLY": "hotel_solution_simply",
    "LIBERTY": "hotel_solution_liberty",
    "CONNECTED": "hotel_solution_connected",
}

PILOT_MAP_PATH = DATA_DIR / "rod_pilot_concepts.json"
HOTEL_PATH = DATA_DIR / "hotel_data.xlsx"
HOTEL_SHEET = "Sheet1"


def load_pilot_solution_codes() -> dict[str, str]:
    """hotel_code → SIMPLY | LIBERTY | CONNECTED."""
    if not PILOT_MAP_PATH.exists():
        return {}
    raw = json.loads(PILOT_MAP_PATH.read_text(encoding="utf-8"))
    out: dict[str, str] = {}
    for sol, items in (raw.get("concepts") or {}).items():
        sol_u = str(sol).upper()
        if sol_u not in _SOLUTION_TO_COL:
            continue
        for it in items or []:
            code = str(it.get("hotel_code") or "").strip()
            if code:
                out[code] = sol_u
    return out


def ensure_solution_flag_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """Ajoute les 3 colonnes (0) si absentes."""
    out = frame.copy()
    for col in SOLUTION_FLAG_COLS:
        if col not in out.columns:
            out[col] = 0
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0).astype(int).clip(0, 1)
    return out


def apply_solution_flags(
    frame: pd.DataFrame,
    *,
    pilot_map: dict[str, str] | None = None,
    reset_non_pilots: bool = True,
) -> pd.DataFrame:
    """
    Pose les flags 0/1 selon le mapping pilotes.

    Si ``reset_non_pilots`` : tous à 0 puis 1 sur les pilotes
    (évite des 1 orphelins si le mapping change).
    """
    out = ensure_solution_flag_columns(frame)
    if "hotel_code" not in out.columns:
        return out
    codes = out["hotel_code"].astype(str).str.strip()
    mapping = pilot_map if pilot_map is not None else load_pilot_solution_codes()

    if reset_non_pilots:
        for col in SOLUTION_FLAG_COLS:
            out[col] = 0

    for code, sol in mapping.items():
        col = _SOLUTION_TO_COL.get(sol)
        if not col:
            continue
        mask = codes == code
        if mask.any():
            out.loc[mask, col] = 1
            # Un hôtel = une solution pilote : zéro les autres flags
            for other in SOLUTION_FLAG_COLS:
                if other != col:
                    out.loc[mask, other] = 0
    return out


def sync_hotel_data_solution_flags(
    path: Path | None = None,
    *,
    sheet: str = HOTEL_SHEET,
) -> dict[str, Any]:
    """
    Met à jour ``hotel_data.xlsx`` avec les 3 flags solution.

    Returns
    -------
    dict ok, path, n_hotels, n_pilots_flagged, by_solution
    """
    path = path or HOTEL_PATH
    if not path.exists():
        raise FileNotFoundError(f"hotel_data introuvable : {path}")

    frame = pd.read_excel(path, sheet_name=sheet)
    before_cols = list(frame.columns)
    mapping = load_pilot_solution_codes()
    updated = apply_solution_flags(frame, pilot_map=mapping, reset_non_pilots=True)

    # Place les colonnes après hotel_brand si possible
    cols = list(updated.columns)
    for c in SOLUTION_FLAG_COLS:
        if c in cols:
            cols.remove(c)
    insert_at = cols.index("hotel_brand") + 1 if "hotel_brand" in cols else min(3, len(cols))
    for i, c in enumerate(SOLUTION_FLAG_COLS):
        cols.insert(insert_at + i, c)
    updated = updated[cols]

    path.parent.mkdir(parents=True, exist_ok=True)
    updated.to_excel(path, index=False, sheet_name=sheet)

    by_sol: dict[str, list[str]] = {s: [] for s in _SOLUTION_TO_COL}
    codes = updated["hotel_code"].astype(str).str.strip()
    for sol, col in _SOLUTION_TO_COL.items():
        flagged = codes[updated[col] == 1].tolist()
        by_sol[sol] = flagged

    return {
        "ok": True,
        "path": str(path),
        "filename": path.name,
        "n_hotels": len(updated),
        "n_pilots_flagged": int(sum(len(v) for v in by_sol.values())),
        "by_solution": by_sol,
        "columns_added": [c for c in SOLUTION_FLAG_COLS if c not in before_cols],
        "columns": list(SOLUTION_FLAG_COLS),
    }
