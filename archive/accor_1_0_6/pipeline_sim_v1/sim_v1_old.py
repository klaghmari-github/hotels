"""
LOO sim_v1 « old » — via RevenueRules (package pipelines).

- Filtre 6 hotels (excl. H5586)
- Reference = moyenne pairs meme solution
- Export data / predictions / metrics
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pandas as pd

from .constants import EXCEL_OLD, PIPELINES_SRC, PROJECT_ROOT
from .features import (
    build_data_table,
    build_pilot_overrides,
    load_hotels,
    load_pilot_map,
    load_sales,
    load_simulateur_per_hotel,
    metrics_from_predictions,
    peers_for,
)


def _ensure_pipelines_path() -> None:
    """Ajoute project_root et pipelines/src au sys.path pour importer accor.*."""
    for p in (str(PROJECT_ROOT), str(PIPELINES_SRC)):
        if p not in sys.path:
            sys.path.insert(0, p)


def _all_needs_open() -> dict[str, bool]:
    from accor.user.models import DEFAULT_CLIENT_NEEDS

    return {k: True for k in DEFAULT_CLIENT_NEEDS}


def predict_one(hotel_row: pd.Series, *, peers: list[str], data: pd.DataFrame) -> dict[str, Any]:
    """Prediction CA/marge via RevenueRules + pilot_overrides LOO."""
    _ensure_pipelines_path()
    from accor.user.models import (
        ClientProfile,
        HotelIdentity,
        HotelOperating,
        SimulationRequest,
        StoreConfig,
    )
    from accor.user.rules.revenue import RevenueRules

    code = str(hotel_row["hotel_code"])
    concept = str(hotel_row["solution"])
    overrides = build_pilot_overrides(peers, concept=concept, data=data)
    # RevenueRules attend des floats ; frigo_ref None ok pour S/L
    ov = {k: v for k, v in overrides.items() if v is not None}

    op = HotelOperating(
        nb_chambres=int(float(hotel_row["nb_chambres"])),
        taux_occupation=float(hotel_row["taux_occupation"]),
        guests_per_chambre=float(hotel_row["guests_per_chambre"]),
    )
    mix = float(hotel_row["mix_fb"])
    if mix > 1:
        mix /= 100.0
    mix = min(max(mix, 0.0), 1.0)

    req = SimulationRequest(
        identity=HotelIdentity(
            hotel_code=code,
            hotel_name=str(hotel_row.get("hotel_name") or ""),
            hotel_brand=str(hotel_row.get("hotel_brand") or ""),
        ),
        operating=op,
        client_profile=ClientProfile(client_needs=_all_needs_open()),
        store=StoreConfig(
            concept=concept,
            m_lin=float(hotel_row["m_lin"]),
            mix_fb=mix,
            mix_nf=1.0 - mix,
            nb_frigos_froid=3,
        ),
    )
    rev = RevenueRules().compute(req, concept, pilot_overrides=ov)

    true_ca = float(hotel_row["ca_ht_mensuel"])
    true_marge = float(hotel_row["marge_mensuel"])
    pred_ca = float(rev.ca_ht_mensuel or 0.0)
    pred_marge = float(rev.marge_produit_mensuelle or 0.0)

    return {
        "hotel_code": code,
        "solution": concept,
        "peers": ", ".join(peers),
        "ca_reel": round(true_ca, 2),
        "ca_pred": round(pred_ca, 2),
        "ca_err_abs": round(abs(pred_ca - true_ca), 2),
        "marge_reel": round(true_marge, 2),
        "marge_pred": round(pred_marge, 2),
        "marge_err_abs": round(abs(pred_marge - true_marge), 2),
        "n_mois": int(hotel_row.get("n_mois") or 0),
        "hotel_name": str(hotel_row.get("hotel_name") or ""),
        "hotel_brand": str(hotel_row.get("hotel_brand") or ""),
    }


def evaluate_loo() -> dict[str, Any]:
    """Leave-one-out sur les 6 hotels."""
    _ensure_pipelines_path()
    pilot_map = load_pilot_map()
    sales = load_sales()
    hotels = load_hotels()
    sim = load_simulateur_per_hotel()
    data = build_data_table(sales, hotels, sim, pilot_map)

    pred_rows: list[dict[str, Any]] = []
    for _, row in data.iterrows():
        code = str(row["hotel_code"])
        concept = str(row["solution"])
        peers = peers_for(code, concept, pilot_map)
        pred_rows.append(predict_one(row, peers=peers, data=data))

    predictions = pd.DataFrame(pred_rows)
    # ordre colonnes export
    cols = [
        "hotel_code",
        "solution",
        "peers",
        "ca_reel",
        "ca_pred",
        "ca_err_abs",
        "marge_reel",
        "marge_pred",
        "marge_err_abs",
        "n_mois",
    ]
    predictions = predictions[[c for c in cols if c in predictions.columns]]
    metrics = metrics_from_predictions(predictions)
    return {
        "ok": True,
        "engine": "sim_v1_old",
        "data": data,
        "predictions": predictions,
        "metrics": metrics,
    }


def write_excel(result: dict[str, Any] | None = None, path: Path | None = None) -> Path:
    path = path or EXCEL_OLD
    result = result or evaluate_loo()
    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path, engine="openpyxl") as w:
        result["data"].to_excel(w, index=False, sheet_name="data")
        result["predictions"].to_excel(w, index=False, sheet_name="predictions")
        result["metrics"].to_excel(w, index=False, sheet_name="metrics")
    return path


def run(path: Path | None = None) -> dict[str, Any]:
    result = evaluate_loo()
    out = write_excel(result, path=path)
    result["excel_path"] = str(out)
    return result


if __name__ == "__main__":
    r = run()
    print(r["metrics"].to_string(index=False))
    print(f"Excel → {r['excel_path']}")
