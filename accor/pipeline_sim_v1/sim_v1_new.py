"""
LOO sim_v1 « new » — formules R1–R4 pures (sans Flask / RevenueRules).

Meme schema Excel que sim_v1_old.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from .constants import (
    CAT_FB,
    CAT_NFB,
    COEFF_FB,
    COEFF_NFB,
    EXCEL_NEW,
    JOURS_MOIS,
)
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


def rule1_buyers(
    *,
    clients_hotel: float,
    ventes_pilote: float,
    clients_pilote: float,
    ca_fb_pilote: float,
    ca_nfb_pilote: float,
) -> tuple[float, float, float, float, float]:
    """R1 — taux acheteurs, panier moyen pilote."""
    if clients_pilote <= 0 or ventes_pilote <= 0:
        return 0.0, 0.0, 0.0, 0.0, 0.0
    taux = ventes_pilote / clients_pilote
    acheteurs = clients_hotel * taux
    ca_fb = (ca_fb_pilote / ventes_pilote) * acheteurs
    ca_nfb = (ca_nfb_pilote / ventes_pilote) * acheteurs
    return ca_fb, ca_nfb, taux, acheteurs, clients_hotel / clients_pilote


def rule2_mix(
    ca_fb: float,
    ca_nfb: float,
    *,
    mix_fb_user: float,
    mix_fb_ref: float,
    ca_10_fb: float,
    ca_10_nfb: float,
) -> tuple[float, float, float]:
    """R2 — impact mix ±10 %."""
    d_fb = float(mix_fb_user) - float(mix_fb_ref)
    steps = d_fb * 10.0
    ca_fb = ca_fb + ca_10_fb * steps
    ca_nfb = ca_nfb + ca_10_nfb * (-steps)
    return ca_fb, ca_nfb, steps


def rule3_categories_all_on(ca_fb: float, ca_nfb: float) -> tuple[float, float, float, float]:
    """R3 — toutes categories ON (comme all_needs_open de l'ancien eval)."""
    sum_fb = sum(CAT_FB.values())
    sum_nfb = sum(CAT_NFB.values())
    mult_fb = 1.0 + sum_fb
    mult_nfb = 1.0 + sum_nfb
    return ca_fb * mult_fb, ca_nfb * mult_nfb, mult_fb, mult_nfb


def rule4_surface(
    ca_fb: float,
    ca_nfb: float,
    *,
    concept: str,
    m_lin: float,
    ml_ref: float,
    ca_1ml_fb: float,
    ca_1ml_nfb: float,
    nb_frigos_froid: float = 3.0,
    frigo_ref: float | None = None,
    ca_1frigo_fb: float = 0.0,
    ca_1frigo_nfb: float = 0.0,
    mix_fb: float = 0.5,
) -> tuple[float, float, float, str]:
    """
    R4 — Simply/Liberty : m_lin ; Connected : frigos froid (ref=3, hotel=3).
    Aligne l'ancien eval (nb_frigos_froid=3 + frigo_ref pilote).
    """
    concept = concept.upper()
    if concept == "CONNECTED" and frigo_ref is not None:
        nb = float(nb_frigos_froid)
        if mix_fb < 0.10:
            nb = 0.0
        diff = nb - float(frigo_ref)
        abs_d = abs(diff)
        sign = -1.0 if diff < 0 else 1.0
        return (
            ca_fb + sign * ca_1frigo_fb * abs_d,
            ca_nfb + sign * ca_1frigo_nfb * abs_d,
            diff,
            "frigos_froid",
        )
    diff = float(m_lin) - float(ml_ref)
    abs_d = abs(diff)
    if diff < 0:
        return ca_fb - ca_1ml_fb * abs_d, ca_nfb - ca_1ml_nfb * abs_d, diff, "m_lin"
    return ca_fb + ca_1ml_fb * abs_d, ca_nfb + ca_1ml_nfb * abs_d, diff, "m_lin"


def marge_produit(ca_fb: float, ca_nf: float, coef_fb: float = COEFF_FB, coef_nf: float = COEFF_NFB) -> float:
    """marge = CA − CA/coef."""
    m_fb = ca_fb - (ca_fb / coef_fb) if coef_fb else 0.0
    m_nf = ca_nf - (ca_nf / coef_nf) if coef_nf else 0.0
    return m_fb + m_nf


def predict_one(hotel_row: pd.Series, *, peers: list[str], data: pd.DataFrame) -> dict[str, Any]:
    """Pipeline R1→R2→R3→R4→marge pour un hotel LOO."""
    code = str(hotel_row["hotel_code"])
    concept = str(hotel_row["solution"])
    ov = build_pilot_overrides(peers, concept=concept, data=data)

    clients_hotel = (
        float(hotel_row["nb_chambres"])
        * float(hotel_row["taux_occupation"])
        * float(hotel_row["guests_per_chambre"])
        * JOURS_MOIS
    )
    mix = float(hotel_row["mix_fb"])
    if mix > 1:
        mix /= 100.0
    mix = min(max(mix, 0.0), 1.0)
    m_lin = float(hotel_row["m_lin"])
    if concept != "CONNECTED" and m_lin < 2.0:
        m_lin = 2.0

    ventes = float(ov["nb_ventes"])
    ca_fb_p = float(ov["ca_fb"])
    ca_nfb_p = float(ov["ca_nf"])
    mix_ref = float(ov["mix_fb"])
    if mix_ref > 1.0:
        mix_ref /= 100.0
    ml_ref = float(ov["m_lin"])
    clients_pilote = float(ov["clients_heb"])
    ca_10_fb = float(ov["ca_10_fb"])
    ca_10_nfb = float(ov["ca_10_nfb"])
    ca_1ml_fb = float(ov["ca_1ml_fb"])
    ca_1ml_nfb = float(ov["ca_1ml_nfb"])
    frigo_ref = ov.get("frigo_ref")
    if frigo_ref is not None:
        frigo_ref = float(frigo_ref)
    ca_1frigo_fb = float(ov.get("ca_1frigo_fb") or (ca_fb_p / 3.0))
    ca_1frigo_nfb = float(ov.get("ca_1frigo_nfb") or (ca_nfb_p / 3.0))
    coeff_fb = float(ov.get("margin_fb") or COEFF_FB)
    coeff_nfb = float(ov.get("margin_nf") or COEFF_NFB)

    # R1
    ca_fb, ca_nfb, _taux, _ach, _fac = rule1_buyers(
        clients_hotel=clients_hotel,
        ventes_pilote=ventes,
        clients_pilote=clients_pilote,
        ca_fb_pilote=ca_fb_p,
        ca_nfb_pilote=ca_nfb_p,
    )
    # R2
    ca_fb, ca_nfb, _steps = rule2_mix(
        ca_fb,
        ca_nfb,
        mix_fb_user=mix,
        mix_fb_ref=mix_ref,
        ca_10_fb=ca_10_fb,
        ca_10_nfb=ca_10_nfb,
    )
    # R3 all ON
    ca_fb, ca_nfb, _mf, _mn = rule3_categories_all_on(ca_fb, ca_nfb)
    # R4
    ca_fb, ca_nfb, _d, _mode = rule4_surface(
        ca_fb,
        ca_nfb,
        concept=concept,
        m_lin=m_lin,
        ml_ref=ml_ref,
        ca_1ml_fb=ca_1ml_fb,
        ca_1ml_nfb=ca_1ml_nfb,
        nb_frigos_froid=3.0,
        frigo_ref=frigo_ref if concept == "CONNECTED" else None,
        ca_1frigo_fb=ca_1frigo_fb,
        ca_1frigo_nfb=ca_1frigo_nfb,
        mix_fb=mix,
    )

    pred_ca = ca_fb + ca_nfb
    pred_marge = marge_produit(ca_fb, ca_nfb, coeff_fb, coeff_nfb)
    true_ca = float(hotel_row["ca_ht_mensuel"])
    true_marge = float(hotel_row["marge_mensuel"])

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
    }


def evaluate_loo() -> dict[str, Any]:
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
        "engine": "sim_v1_new",
        "data": data,
        "predictions": predictions,
        "metrics": metrics,
    }


def write_excel(result: dict[str, Any] | None = None, path: Path | None = None) -> Path:
    path = path or EXCEL_NEW
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
