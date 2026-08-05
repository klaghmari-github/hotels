#!/usr/bin/env python3
"""
Évaluation leave-one-out du **simulateur ROD v1** (règles Excel).

Méthode
-------
* **Toutes** les années de ventes (pas de split 2023–25 / 2026).
* Indicateurs = moyennes mensuelles par hôtel (Σ / n_mois renseignés).
* Pour chaque hôtel pilote H de solution S :
    1. exclure H de la référence
    2. reconstruire la baseline pilote = moyenne des **autres** pilotes de S
       (ventes live si dispo, sinon pivots Excel)
    3. projeter CA HT et marge produit via ``RevenueRules`` (R1→R4)
    4. comparer au vrai mensuel de H
* Métrique : **MAE** par hôtel puis moyenne sur les hôtels.

Ne modifie aucun fichier de données ni le comportement de run_admin / run_user.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from accor.data_io import DATA_DIR
from accor.user.models import (
    ClientProfile,
    HotelIdentity,
    HotelOperating,
    SimulationRequest,
    StoreConfig,
)
from accor.user.rules.pilot_table import JOURS_MOIS, get_pilot
from accor.user.rules.revenue import RevenueRules
from accor.user.services.hotel_context import (
    BRAND_GUESTS_DEFAULT,
    BRAND_TO_DEFAULT,
    _as_rate,
    _norm_brand,
)

CONCEPTS = ("SIMPLY", "LIBERTY", "CONNECTED")
PILOT_MAP_PATH = DATA_DIR / "rod_pilot_concepts.json"
SALES_PATH = DATA_DIR / "hotel_sales_data.xlsx"
HOTEL_PATH = DATA_DIR / "hotel_data.xlsx"
SIM_DATA_PATH = DATA_DIR / "simulateur_data.xlsx"


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


def load_pilot_map() -> dict[str, list[dict[str, str]]]:
    if not PILOT_MAP_PATH.exists():
        return {c: [] for c in CONCEPTS}
    raw = json.loads(PILOT_MAP_PATH.read_text(encoding="utf-8"))
    concepts = raw.get("concepts") or {}
    out: dict[str, list[dict[str, str]]] = {}
    for c in CONCEPTS:
        items = concepts.get(c) or []
        out[c] = [
            {
                "hotel_code": str(it.get("hotel_code") or "").strip(),
                "label": str(it.get("label") or it.get("hotel_label") or "").strip(),
                "name": str(
                    it.get("name_display")
                    or it.get("name_ventes")
                    or it.get("hotel_name")
                    or ""
                ).strip(),
            }
            for it in items
            if it.get("hotel_code")
        ]
    return out


def code_to_solution(mapping: dict[str, list[dict[str, str]]] | None = None) -> dict[str, str]:
    mapping = mapping or load_pilot_map()
    out: dict[str, str] = {}
    for sol, items in mapping.items():
        for it in items:
            out[it["hotel_code"]] = sol
    return out


def load_sales() -> pd.DataFrame:
    if not SALES_PATH.exists():
        return pd.DataFrame()
    try:
        df = pd.read_excel(SALES_PATH, sheet_name="hotel_sales")
    except Exception:
        df = pd.read_excel(SALES_PATH, sheet_name=0)
    if df.empty:
        return df
    df = df.copy()
    df["hotel_code"] = df["hotel_code"].astype(str).str.strip()
    df["annee"] = pd.to_numeric(df.get("annee"), errors="coerce")
    df["mois"] = pd.to_numeric(df.get("mois"), errors="coerce")
    df["montant_ventes"] = pd.to_numeric(df.get("montant_ventes"), errors="coerce").fillna(0.0)
    if "montant_marge" in df.columns:
        df["montant_marge"] = pd.to_numeric(df["montant_marge"], errors="coerce").fillna(0.0)
    else:
        df["montant_marge"] = 0.0
    if "nombre_ventes" in df.columns:
        df["nombre_ventes"] = pd.to_numeric(df["nombre_ventes"], errors="coerce").fillna(0.0)
    else:
        df["nombre_ventes"] = 0.0
    return df


def load_hotels() -> pd.DataFrame:
    if not HOTEL_PATH.exists():
        return pd.DataFrame()
    df = pd.read_excel(HOTEL_PATH, sheet_name=0)
    if df.empty or "hotel_code" not in df.columns:
        return pd.DataFrame()
    df = df.copy()
    df["hotel_code"] = df["hotel_code"].astype(str).str.strip()
    return df


def load_simulateur_per_hotel() -> pd.DataFrame:
    """Lignes hôtel×année de simulateur_data si présent."""
    if not SIM_DATA_PATH.exists():
        return pd.DataFrame()
    try:
        df = pd.read_excel(SIM_DATA_PATH, sheet_name="simulateur_data")
    except Exception:
        try:
            df = pd.read_excel(SIM_DATA_PATH, sheet_name=0)
        except Exception:
            return pd.DataFrame()
    if df.empty or "hotel_code" not in df.columns:
        return pd.DataFrame()
    df = df.copy()
    df["hotel_code"] = df["hotel_code"].astype(str).str.strip()
    return df


# ---------------------------------------------------------------------------
# Monthly indicators (all years)
# ---------------------------------------------------------------------------


def compute_monthly_indicators(sales: pd.DataFrame | None = None) -> pd.DataFrame:
    """
    Une ligne par hôtel : moyennes mensuelles sur **toutes** les périodes disponibles.

    ca_mensuel   = sum(montant_ventes) / n_mois
    marge_mensuel = sum(montant_marge) / n_mois
    nb_ventes_mensuel = sum(nombre_ventes) / n_mois
    """
    sales = load_sales() if sales is None else sales
    if sales is None or sales.empty:
        return pd.DataFrame(
            columns=[
                "hotel_code",
                "n_mois",
                "years",
                "ca_mensuel",
                "marge_mensuel",
                "nb_ventes_mensuel",
                "mix_fb",
                "mix_nf",
            ]
        )

    rows: list[dict[str, Any]] = []
    for code, g in sales.groupby("hotel_code"):
        n = int(len(g))
        if n <= 0:
            continue
        ca = float(g["montant_ventes"].sum())
        marge = float(g["montant_marge"].sum())
        nv = float(g["nombre_ventes"].sum()) if "nombre_ventes" in g.columns else 0.0
        years = sorted(
            int(y) for y in pd.to_numeric(g["annee"], errors="coerce").dropna().unique()
        )
        mix_fb = None
        mix_nf = None
        for col_fb, col_nf in (
            ("pct_cat_f_b_montant_ventes", "pct_cat_n_f_b_montant_ventes"),
            ("pct_cat_f_b_nombre_ventes", "pct_cat_n_f_b_nombre_ventes"),
        ):
            if col_fb in g.columns and col_nf in g.columns:
                mf = pd.to_numeric(g[col_fb], errors="coerce").mean()
                mn = pd.to_numeric(g[col_nf], errors="coerce").mean()
                if pd.notna(mf):
                    mix_fb = float(mf)
                    if mix_fb > 1.0:
                        mix_fb /= 100.0
                if pd.notna(mn):
                    mix_nf = float(mn)
                    if mix_nf > 1.0:
                        mix_nf /= 100.0
                break
        if mix_fb is None:
            mix_fb = 0.5
        if mix_nf is None:
            mix_nf = 1.0 - mix_fb
        rows.append(
            {
                "hotel_code": str(code),
                "n_mois": n,
                "years": years,
                "years_label": ",".join(str(y) for y in years),
                "ca_mensuel": ca / n,
                "marge_mensuel": marge / n,
                "nb_ventes_mensuel": nv / n,
                "mix_fb": mix_fb,
                "mix_nf": mix_nf,
            }
        )
    return pd.DataFrame(rows)


def _hotel_params(hotels: pd.DataFrame, code: str) -> dict[str, Any]:
    empty = {
        "hotel_code": code,
        "hotel_name": "",
        "hotel_brand": "",
        "nb_chambres": 100.0,
        "taux_occupation": 0.70,
        "guests_per_chambre": 1.7,
        "m_lin": 6.0,
    }
    if hotels is None or hotels.empty:
        return empty
    m = hotels[hotels["hotel_code"] == code]
    if m.empty:
        return empty
    row = m.iloc[0]
    brand = str(row.get("hotel_brand") or "")
    bk = _norm_brand(brand)
    n = pd.to_numeric(row.get("hotel_nb_chambres"), errors="coerce")
    n = float(n) if pd.notna(n) and float(n) > 0 else 100.0
    to = _as_rate(row.get("hotel_to_annuel"), BRAND_TO_DEFAULT.get(bk, 0.70))
    guests = BRAND_GUESTS_DEFAULT.get(bk, 1.7)
    m_lin = None
    for col in (
        "hotel_corner_de_vente_actuel_metres_lineaires",
        "hotel_metres_lineaires_dedies_corner",
        "metres_lineaires",
        "m_lin",
    ):
        if col in row.index:
            v = pd.to_numeric(row.get(col), errors="coerce")
            if pd.notna(v) and float(v) > 0:
                m_lin = float(v)
                break
    if m_lin is None:
        m_lin = 6.0
    return {
        "hotel_code": code,
        "hotel_name": str(row.get("hotel_name") or ""),
        "hotel_brand": brand,
        "nb_chambres": n,
        "taux_occupation": to,
        "guests_per_chambre": guests,
        "m_lin": m_lin,
    }


def _sim_hotel_means(sim: pd.DataFrame, code: str) -> dict[str, float] | None:
    """Moyenne multi-années d'un hôtel dans simulateur_data."""
    if sim is None or sim.empty:
        return None
    g = sim[sim["hotel_code"] == code]
    if g.empty:
        return None

    def _m(col: str) -> float | None:
        if col not in g.columns:
            return None
        s = pd.to_numeric(g[col], errors="coerce").dropna()
        return float(s.mean()) if len(s) else None

    out: dict[str, float] = {}
    mapping = {
        "ca_fb": "ca_ht_fb_mensuel",
        "ca_nf": "ca_ht_nf_mensuel",
        "ca_ht": "ca_ht_total_mensuel",
        "nb_ventes": "nb_ventes_mensuel",
        "mix_fb": "mix_fb",
        "mix_nf": "mix_nf",
        "margin_fb": "margin_fb",
        "margin_nf": "margin_nf",
        "nb_chambres": "nb_chambres",
        "taux_occupation": "taux_occupation",
        "clients_heb": "clients_mois_estimes",
    }
    for k, col in mapping.items():
        v = _m(col)
        if v is not None:
            out[k] = v
    if "mix_fb" in out and out["mix_fb"] > 1.0:
        out["mix_fb"] /= 100.0
    if "mix_nf" in out and out["mix_nf"] > 1.0:
        out["mix_nf"] /= 100.0
    return out or None


def build_pilot_overrides(
    peer_codes: list[str],
    *,
    concept: str,
    indicators: pd.DataFrame,
    sim: pd.DataFrame | None,
    hotels: pd.DataFrame,
) -> dict[str, float]:
    """
    Baseline pilote = moyenne des hôtels ``peer_codes`` (sans le left-out).
    Fallback : pivots Excel ``get_pilot(concept)``.
    """
    concept = concept.upper()
    pilot = dict(get_pilot(concept))
    ca_fbs: list[float] = []
    ca_nfs: list[float] = []
    ventes: list[float] = []
    mixes: list[float] = []
    clients: list[float] = []
    rooms: list[float] = []
    tos: list[float] = []
    guests: list[float] = []
    mlins: list[float] = []
    m_fb: list[float] = []
    m_nf: list[float] = []

    ind_by = (
        indicators.set_index("hotel_code")
        if indicators is not None and not indicators.empty
        else None
    )

    for code in peer_codes:
        params = _hotel_params(hotels, code)
        rooms.append(float(params["nb_chambres"]))
        tos.append(float(params["taux_occupation"]))
        guests.append(float(params["guests_per_chambre"]))
        mlins.append(float(params["m_lin"]))
        clients.append(
            float(params["nb_chambres"])
            * float(params["taux_occupation"])
            * float(params["guests_per_chambre"])
            * JOURS_MOIS
        )

        sm = _sim_hotel_means(sim, code) if sim is not None else None
        if sm:
            if "ca_fb" in sm:
                ca_fbs.append(sm["ca_fb"])
            if "ca_nf" in sm:
                ca_nfs.append(sm["ca_nf"])
            if "nb_ventes" in sm:
                ventes.append(sm["nb_ventes"])
            if "mix_fb" in sm:
                mixes.append(sm["mix_fb"])
            if "margin_fb" in sm:
                m_fb.append(sm["margin_fb"])
            if "margin_nf" in sm:
                m_nf.append(sm["margin_nf"])
            if "clients_heb" in sm and sm["clients_heb"] > 0:
                clients[-1] = sm["clients_heb"]
            continue

        # fallback ventes agrégées (pas de split F&B) → mix 50/50 ou mix sales
        if ind_by is not None and code in ind_by.index:
            r = ind_by.loc[code]
            ca = float(r["ca_mensuel"] or 0)
            mix = float(r["mix_fb"] if pd.notna(r.get("mix_fb")) else 0.5)
            mix = mix if mix <= 1.0 else mix / 100.0
            ca_fbs.append(ca * mix)
            ca_nfs.append(ca * (1.0 - mix))
            ventes.append(float(r["nb_ventes_mensuel"] or 0))
            mixes.append(mix)

    def _mean(xs: list[float], default: float) -> float:
        return float(np.mean(xs)) if xs else float(default)

    ca_fb = _mean(ca_fbs, float(pilot["ca_fb"]))
    ca_nf = _mean(ca_nfs, float(pilot["ca_nfb"]))
    nb_ventes = _mean(ventes, float(pilot["ventes"]))
    mix_fb = _mean(mixes, float(pilot["mix_fb"]))
    if mix_fb > 1.0:
        mix_fb /= 100.0
    ml_ref = _mean(mlins, float(pilot.get("ml_ref") or 6.0))
    clients_heb = _mean(
        clients,
        float(
            pilot.get("clients_heb")
            or pilot["nb_chambres"] * pilot["guests"] * pilot["to"] * JOURS_MOIS
        ),
    )
    margin_fb = _mean(m_fb, float(pilot["coeff_fb"]))
    margin_nf = _mean(m_nf, float(pilot["coeff_nfb"]))

    # dérivés R2 / R4 cohérents avec la baseline
    ca_10_fb = ca_fb / 10.0 if ca_fb else float(pilot["ca_10_fb"])
    ca_10_nfb = ca_nf / 10.0 if ca_nf else float(pilot["ca_10_nfb"])
    ca_1ml_fb = ca_fb / ml_ref if ml_ref else float(pilot.get("ca_1ml_fb") or 0)
    ca_1ml_nfb = ca_nf / ml_ref if ml_ref else float(pilot.get("ca_1ml_nfb") or 0)

    return {
        "ca_fb": ca_fb,
        "ca_nf": ca_nf,
        "nb_ventes": nb_ventes,
        "mix_fb": mix_fb,
        "m_lin": ml_ref,
        "clients_heb": clients_heb,
        "nb_chambres": _mean(rooms, float(pilot["nb_chambres"])),
        "taux_occupation": _mean(tos, float(pilot["to"])),
        "guests_per_chambre": _mean(guests, float(pilot["guests"])),
        "margin_fb": margin_fb,
        "margin_nf": margin_nf,
        "ca_10_fb": ca_10_fb,
        "ca_10_nfb": ca_10_nfb,
        "ca_1ml_fb": ca_1ml_fb,
        "ca_1ml_nfb": ca_1ml_nfb,
        "n_peers": float(len(peer_codes)),
    }


def all_needs_open() -> dict[str, bool]:
    from accor.user.models import DEFAULT_CLIENT_NEEDS

    return {k: True for k in DEFAULT_CLIENT_NEEDS}


def build_request(
    params: dict[str, Any], mix_fb: float, *, concept: str = "SIMPLY"
) -> SimulationRequest:
    mix = float(mix_fb)
    if mix > 1.0:
        mix /= 100.0
    mix = min(max(mix, 0.0), 1.0)
    op = HotelOperating(
        nb_chambres=int(params["nb_chambres"]),
        taux_occupation=float(params["taux_occupation"]),
        guests_per_chambre=float(params["guests_per_chambre"]),
    )
    return SimulationRequest(
        identity=HotelIdentity(
            hotel_code=str(params.get("hotel_code") or ""),
            hotel_name=str(params.get("hotel_name") or ""),
            hotel_brand=str(params.get("hotel_brand") or ""),
        ),
        operating=op,
        client_profile=ClientProfile(client_needs=all_needs_open()),
        store=StoreConfig(
            concept=concept.upper(),
            m_lin=float(params.get("m_lin") or 6.0),
            mix_fb=mix,
            mix_nf=1.0 - mix,
            nb_frigos_froid=3,
        ),
    )


def predict_hotel_loo(
    hotel_code: str,
    *,
    concept: str | None = None,
    indicators: pd.DataFrame | None = None,
    sales: pd.DataFrame | None = None,
    hotels: pd.DataFrame | None = None,
    sim: pd.DataFrame | None = None,
    pilot_map: dict[str, list[dict[str, str]]] | None = None,
) -> dict[str, Any]:
    """
    Exclut ``hotel_code`` de la référence solution, projette CA + marge produit.

    Si ``concept`` est None → solution installée (rod_pilot_concepts).
    """
    pilot_map = pilot_map or load_pilot_map()
    c2s = code_to_solution(pilot_map)
    hotels = load_hotels() if hotels is None else hotels
    sales = load_sales() if sales is None else sales
    indicators = compute_monthly_indicators(sales) if indicators is None else indicators
    sim = load_simulateur_per_hotel() if sim is None else sim

    code = str(hotel_code).strip()
    concept = (concept or c2s.get(code) or "SIMPLY").upper()
    peers = [
        it["hotel_code"]
        for it in (pilot_map.get(concept) or [])
        if it["hotel_code"] != code
    ]
    # si solution mono-pilote : peers = tous les autres pilotes toutes solutions
    if not peers:
        peers = [c for c in c2s if c != code]

    overrides = build_pilot_overrides(
        peers,
        concept=concept,
        indicators=indicators,
        sim=sim,
        hotels=hotels,
    )
    params = _hotel_params(hotels, code)
    # mix cible = mix historique de l'hôtel (indicateurs)
    mix_fb = 0.5
    if indicators is not None and not indicators.empty:
        row = indicators[indicators["hotel_code"] == code]
        if not row.empty and pd.notna(row.iloc[0].get("mix_fb")):
            mix_fb = float(row.iloc[0]["mix_fb"])

    req = build_request(params, mix_fb, concept=concept)
    rev = RevenueRules().compute(req, concept, pilot_overrides=overrides)

    true_ca = true_marge = true_ventes = None
    n_mois = 0
    years: list[int] = []
    if indicators is not None and not indicators.empty:
        row = indicators[indicators["hotel_code"] == code]
        if not row.empty:
            r0 = row.iloc[0]
            true_ca = float(r0["ca_mensuel"])
            true_marge = float(r0["marge_mensuel"])
            true_ventes = float(r0["nb_ventes_mensuel"])
            n_mois = int(r0["n_mois"])
            years = list(r0.get("years") or [])

    pred_ca = float(rev.ca_ht_mensuel or 0.0)
    pred_marge = float(rev.marge_produit_mensuelle or 0.0)
    pred_ventes = float(rev.nbr_ventes_mensuel or 0.0)

    err_ca = abs(pred_ca - true_ca) if true_ca is not None else None
    err_marge = abs(pred_marge - true_marge) if true_marge is not None else None

    return {
        "hotel_code": code,
        "hotel_name": params.get("hotel_name") or "",
        "hotel_brand": params.get("hotel_brand") or "",
        "concept": concept,
        "peers": peers,
        "n_peers": len(peers),
        "n_mois": n_mois,
        "years": years,
        "params": {
            "nb_chambres": params["nb_chambres"],
            "taux_occupation": params["taux_occupation"],
            "guests_per_chambre": params["guests_per_chambre"],
            "m_lin": params["m_lin"],
            "mix_fb": mix_fb,
            "clients_mois": float(req.operating.clients_mois),
        },
        "pilot_overrides": {k: round(float(v), 4) for k, v in overrides.items()},
        "true": {
            "ca_mensuel": round(true_ca, 2) if true_ca is not None else None,
            "marge_mensuel": round(true_marge, 2) if true_marge is not None else None,
            "nb_ventes_mensuel": round(true_ventes, 2) if true_ventes is not None else None,
        },
        "pred": {
            "ca_mensuel": round(pred_ca, 2),
            "marge_mensuel": round(pred_marge, 2),
            "nb_ventes_mensuel": round(pred_ventes, 2),
            "ca_fb": round(float(rev.ca_fb_mensuel or 0), 2),
            "ca_nf": round(float(rev.ca_nf_mensuel or 0), 2),
        },
        "abs_error": {
            "ca": round(err_ca, 2) if err_ca is not None else None,
            "marge": round(err_marge, 2) if err_marge is not None else None,
        },
        "warnings": list(rev.warnings or []),
    }


def _mae(values: list[float]) -> float | None:
    if not values:
        return None
    return float(np.mean(values))


def evaluate_loo_sim_v1(
    *,
    sales: pd.DataFrame | None = None,
    hotels: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """
    Leave-one-out sur tous les hôtels pilotes.

    Returns JSON-serializable dict with per-hotel rows + aggregate MAE.
    """
    pilot_map = load_pilot_map()
    c2s = code_to_solution(pilot_map)
    sales = load_sales() if sales is None else sales
    hotels = load_hotels() if hotels is None else hotels
    indicators = compute_monthly_indicators(sales)
    sim = load_simulateur_per_hotel()

    hotels_eval = sorted(c2s.keys())
    # restreindre à ceux qui ont des ventes
    if indicators is not None and not indicators.empty:
        with_sales = set(indicators["hotel_code"].astype(str))
        hotels_eval = [h for h in hotels_eval if h in with_sales]

    rows: list[dict[str, Any]] = []
    for code in hotels_eval:
        try:
            rows.append(
                predict_hotel_loo(
                    code,
                    indicators=indicators,
                    sales=sales,
                    hotels=hotels,
                    sim=sim,
                    pilot_map=pilot_map,
                )
            )
        except Exception as exc:  # noqa: BLE001 — on isole un hôtel raté
            rows.append(
                {
                    "hotel_code": code,
                    "concept": c2s.get(code),
                    "error": str(exc),
                    "abs_error": {"ca": None, "marge": None},
                }
            )

    ae_ca = [r["abs_error"]["ca"] for r in rows if r.get("abs_error", {}).get("ca") is not None]
    ae_marge = [
        r["abs_error"]["marge"] for r in rows if r.get("abs_error", {}).get("marge") is not None
    ]

    # MAE par solution
    by_sol: dict[str, dict[str, Any]] = {}
    for sol in CONCEPTS:
        sub = [r for r in rows if r.get("concept") == sol]
        by_sol[sol] = {
            "n": len(sub),
            "mae_ca": _mae(
                [r["abs_error"]["ca"] for r in sub if r.get("abs_error", {}).get("ca") is not None]
            ),
            "mae_marge": _mae(
                [
                    r["abs_error"]["marge"]
                    for r in sub
                    if r.get("abs_error", {}).get("marge") is not None
                ]
            ),
        }

    mae_ca = _mae(ae_ca)
    mae_marge = _mae(ae_marge)

    # MAPE optionnel (info)
    mape_ca_vals: list[float] = []
    for r in rows:
        t = (r.get("true") or {}).get("ca_mensuel")
        e = (r.get("abs_error") or {}).get("ca")
        if t and e is not None and abs(t) > 1e-6:
            mape_ca_vals.append(100.0 * e / abs(t))

    return {
        "ok": True,
        "method": "leave-one-out",
        "simulator": "v1_excel_rules",
        "description": (
            "Toutes les années de ventes → moyenne mensuelle par hôtel. "
            "Pour chaque pilote, la référence solution exclut l'hôtel (peers restants), "
            "puis RevenueRules R1→R4 projette CA HT et marge produit. "
            "MAE = moyenne des |pred − true| sur les hôtels."
        ),
        "n_hotels": len(rows),
        "years_all": sorted(
            {
                int(y)
                for ys in indicators["years"]
                for y in (ys if isinstance(ys, list) else [])
            }
        )
        if indicators is not None and not indicators.empty
        else [],
        "metrics": {
            "mae_ca_mensuel": round(mae_ca, 2) if mae_ca is not None else None,
            "mae_marge_mensuel": round(mae_marge, 2) if mae_marge is not None else None,
            "mape_ca_pct": round(float(np.mean(mape_ca_vals)), 1) if mape_ca_vals else None,
            "n_with_ca": len(ae_ca),
            "n_with_marge": len(ae_marge),
        },
        "by_solution": {
            k: {
                "n": v["n"],
                "mae_ca_mensuel": round(v["mae_ca"], 2) if v["mae_ca"] is not None else None,
                "mae_marge_mensuel": round(v["mae_marge"], 2)
                if v["mae_marge"] is not None
                else None,
            }
            for k, v in by_sol.items()
        },
        "hotels": rows,
        "indicators": indicators.to_dict(orient="records")
        if indicators is not None and not indicators.empty
        else [],
    }


def metrics_summary(result: dict[str, Any]) -> str:
    m = result.get("metrics") or {}
    lines = [
        f"Simulateur v1 — leave-one-out sur {result.get('n_hotels')} hôtels",
        f"  MAE CA mensuel    : {m.get('mae_ca_mensuel')} €",
        f"  MAE marge mensuel : {m.get('mae_marge_mensuel')} €",
        f"  MAPE CA          : {m.get('mape_ca_pct')} %",
    ]
    for sol, v in (result.get("by_solution") or {}).items():
        lines.append(
            f"  [{sol}] n={v.get('n')}  MAE_CA={v.get('mae_ca_mensuel')}  "
            f"MAE_marge={v.get('mae_marge_mensuel')}"
        )
    return "\n".join(lines)
