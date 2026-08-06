"""
Prepare les fichiers plats attendus par les YAML ConnectionPipeline.

- data/rod_pilot_concepts_flat.xlsx
- data/v1_pilot_defaults.xlsx
- data/v1_hotel_params.xlsx  (features + actuals des 6 hotels)
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .constants import (
    DATA_DIR,
    EVAL_HOTELS,
    PILOT_FALLBACK,
)
from .features import build_data_table, load_pilot_map


def write_pilot_concepts_flat(path: Path | None = None) -> Path:
    path = path or (DATA_DIR / "rod_pilot_concepts_flat.xlsx")
    pilot_map = load_pilot_map()
    rows = []
    for solution, items in pilot_map.items():
        for it in items:
            rows.append(
                {
                    "hotel_code": it["hotel_code"],
                    "solution": solution,
                    "label": it.get("label") or "",
                    "name": it.get("name") or "",
                }
            )
    # Completer avec EVAL si besoin
    present = {r["hotel_code"] for r in rows}
    for code, sol in EVAL_HOTELS.items():
        if code not in present:
            rows.append(
                {
                    "hotel_code": code,
                    "solution": sol,
                    "label": "",
                    "name": "",
                }
            )
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_excel(path, index=False)
    return path


def write_pilot_defaults(path: Path | None = None) -> Path:
    path = path or (DATA_DIR / "v1_pilot_defaults.xlsx")
    rows = []
    for solution, pilot in PILOT_FALLBACK.items():
        row = {"solution": solution, **pilot}
        # Simply / Liberty : pas de frigo (NULL metier)
        if solution != "CONNECTED":
            row["frigo_ref"] = None
        rows.append(row)
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_excel(path, index=False)
    return path


def write_hotel_params(path: Path | None = None) -> Path:
    """Table features + actuals (meme logique que sim_v1_new Python)."""
    path = path or (DATA_DIR / "v1_hotel_params.xlsx")
    data = build_data_table()
    # Colonnes stables pour le SQL
    out = data.rename(
        columns={
            "ca_ht_mensuel": "ca_reel_mensuel",
            "marge_mensuel": "marge_reelle_mensuelle",
            "hotel_label": "label",
        }
    ).copy()
    out["nb_frigos_froid"] = 3.0
    keep = [
        "hotel_code",
        "solution",
        "label",
        "hotel_name",
        "hotel_brand",
        "nb_chambres",
        "taux_occupation",
        "guests_per_chambre",
        "m_lin",
        "nb_frigos_froid",
        "clients_mois",
        "mix_fb",
        "ca_reel_mensuel",
        "ca_fb_mensuel",
        "ca_nf_mensuel",
        "marge_reelle_mensuelle",
        "nb_ventes_mensuel",
        "nb_paniers_mensuel",
        "n_mois",
    ]
    for col in keep:
        if col not in out.columns:
            out[col] = None
    path.parent.mkdir(parents=True, exist_ok=True)
    out[keep].to_excel(path, index=False)
    return path


def prepare_all() -> dict[str, Path]:
    return {
        "pilot_concepts": write_pilot_concepts_flat(),
        "pilot_defaults": write_pilot_defaults(),
        "hotel_params": write_hotel_params(),
    }


if __name__ == "__main__":
    for name, path in prepare_all().items():
        print(f"{name}: {path}")
