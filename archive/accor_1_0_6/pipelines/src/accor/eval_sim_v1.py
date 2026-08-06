#!/usr/bin/env python3
"""
Evaluation leave-one-out du simulateur ROD v1 (regles Excel).

- Indicateurs mensuels par hotel (TO, chambres, clients, mix, panier, conversion)
- Prediction CA / marge en excluant l'hotel de la reference solution
- Export Excel : data + eval_<code> + eval
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from archive.accor_1_0_6.pipelines.src.accor.data_io import DATA_DIR
from archive.accor_1_0_6.pipelines.src.accor.user.models import (
    ClientProfile,
    HotelIdentity,
    HotelOperating,
    SimulationRequest,
    StoreConfig,
)
from archive.accor_1_0_6.pipelines.src.accor.user.rules.pilot_table import JOURS_MOIS, get_pilot
from archive.accor_1_0_6.pipelines.src.accor.user.rules.revenue import RevenueRules
from archive.accor_1_0_6.pipelines.src.accor.user.services.hotel_context import (
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
EXCEL_OUT = DATA_DIR / "eval_sim_v1_loo.xlsx"


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
                "label": str(it.get("label") or "").strip(),
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
    df["montant_ventes"] = pd.to_numeric(df.get("montant_ventes"), errors="coerce").fillna(0.0)
    df["montant_marge"] = pd.to_numeric(df.get("montant_marge"), errors="coerce").fillna(0.0)
    df["nombre_ventes"] = pd.to_numeric(df.get("nombre_ventes"), errors="coerce").fillna(0.0)
    if "nombre_paniers" in df.columns:
        df["nombre_paniers"] = pd.to_numeric(df["nombre_paniers"], errors="coerce").fillna(0.0)
    else:
        df["nombre_paniers"] = df["nombre_ventes"]
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
    m_lin = 6.0
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
    return {
        "hotel_code": code,
        "hotel_name": str(row.get("hotel_name") or ""),
        "hotel_brand": brand,
        "nb_chambres": n,
        "taux_occupation": to,
        "guests_per_chambre": guests,
        "m_lin": m_lin,
    }


def _sim_means(sim: pd.DataFrame, code: str) -> dict[str, float]:
    if sim is None or sim.empty:
        return {}
    g = sim[sim["hotel_code"] == code]
    if g.empty:
        return {}
    out: dict[str, float] = {}
    for k, col in {
        "ca_fb": "ca_ht_fb_mensuel",
        "ca_nf": "ca_ht_nf_mensuel",
        "ca_ht": "ca_ht_total_mensuel",
        "nb_ventes": "nb_ventes_mensuel",
        "nb_paniers": "nb_paniers_mensuel",
        "mix_fb": "mix_fb",
        "mix_nf": "mix_nf",
        "margin_fb": "margin_fb",
        "margin_nf": "margin_nf",
        "ticket_moyen_ht": "ticket_moyen_ht",
        "panier_moyen_ht": "panier_moyen_ht",
        "clients_mois": "clients_mois_estimes",
        "taux_acheteur": "taux_acheteur",
    }.items():
        if col not in g.columns:
            continue
        s = pd.to_numeric(g[col], errors="coerce").dropna()
        if len(s):
            out[k] = float(s.mean())
    if "mix_fb" in out and out["mix_fb"] > 1:
        out["mix_fb"] /= 100.0
    if "mix_nf" in out and out["mix_nf"] > 1:
        out["mix_nf"] /= 100.0
    return out


def build_data_table(
    sales: pd.DataFrame,
    hotels: pd.DataFrame,
    sim: pd.DataFrame,
    pilot_map: dict[str, list[dict[str, str]]],
) -> pd.DataFrame:
    """
    Onglet data : un hotel = une ligne d'indicateurs utilises par les regles ROD.
    """
    c2s = code_to_solution(pilot_map)
    codes = sorted(c2s.keys())
    rows: list[dict[str, Any]] = []

    for code in codes:
        params = _hotel_params(hotels, code)
        concept = c2s[code]
        g = sales[sales["hotel_code"] == code] if not sales.empty else pd.DataFrame()
        n_mois = int(len(g)) if not g.empty else 0
        ca_sum = float(g["montant_ventes"].sum()) if n_mois else 0.0
        marge_sum = float(g["montant_marge"].sum()) if n_mois else 0.0
        ventes_sum = float(g["nombre_ventes"].sum()) if n_mois else 0.0
        paniers_sum = float(g["nombre_paniers"].sum()) if n_mois else 0.0

        ca_m = ca_sum / n_mois if n_mois else 0.0
        marge_m = marge_sum / n_mois if n_mois else 0.0
        ventes_m = ventes_sum / n_mois if n_mois else 0.0
        paniers_m = paniers_sum / n_mois if n_mois else 0.0

        mix_fb = 0.5
        if n_mois and "pct_cat_f_b_montant_ventes" in g.columns:
            mf = pd.to_numeric(g["pct_cat_f_b_montant_ventes"], errors="coerce").mean()
            if pd.notna(mf):
                mix_fb = float(mf)
                if mix_fb > 1:
                    mix_fb /= 100.0
        mix_nf = 1.0 - mix_fb

        sm = _sim_means(sim, code)
        if sm.get("mix_fb") is not None:
            mix_fb = float(sm["mix_fb"])
            mix_nf = float(sm.get("mix_nf", 1.0 - mix_fb))
        if sm.get("ca_ht") is not None:
            ca_m = float(sm["ca_ht"])
        if sm.get("nb_ventes") is not None:
            ventes_m = float(sm["nb_ventes"])
        if sm.get("nb_paniers") is not None:
            paniers_m = float(sm["nb_paniers"])

        clients_jour = (
            params["nb_chambres"] * params["taux_occupation"] * params["guests_per_chambre"]
        )
        clients_mois = clients_jour * JOURS_MOIS
        # Taux conversion clients heberges -> acheteurs (R1)
        taux_conversion = (ventes_m / clients_mois) if clients_mois > 0 else 0.0
        # Panier moyen HT par vente / par client heberge
        panier_moyen_ht = (ca_m / ventes_m) if ventes_m > 0 else 0.0
        ca_par_client = (ca_m / clients_mois) if clients_mois > 0 else 0.0
        ca_fb_m = ca_m * mix_fb
        ca_nf_m = ca_m * mix_nf

        years = sorted(
            int(y)
            for y in pd.to_numeric(g.get("annee"), errors="coerce").dropna().unique()
        ) if n_mois else []

        label = ""
        for it in pilot_map.get(concept) or []:
            if it["hotel_code"] == code:
                label = it.get("label") or ""
                break

        rows.append(
            {
                "hotel_code": code,
                "hotel_label": label,
                "hotel_name": params["hotel_name"],
                "hotel_brand": params["hotel_brand"],
                "solution": concept,
                "nb_chambres": round(params["nb_chambres"], 1),
                "taux_occupation": round(params["taux_occupation"], 4),
                "guests_per_chambre": round(params["guests_per_chambre"], 3),
                "m_lin": round(params["m_lin"], 2),
                "clients_jour": round(clients_jour, 2),
                "clients_mois": round(clients_mois, 2),
                "n_mois": n_mois,
                "annees": ",".join(str(y) for y in years),
                "ca_ht_mensuel": round(ca_m, 2),
                "ca_fb_mensuel": round(ca_fb_m, 2),
                "ca_nf_mensuel": round(ca_nf_m, 2),
                "marge_mensuel": round(marge_m, 2),
                "nb_ventes_mensuel": round(ventes_m, 2),
                "nb_paniers_mensuel": round(paniers_m, 2),
                "mix_fb": round(mix_fb, 4),
                "mix_nf": round(mix_nf, 4),
                "taux_conversion_acheteur": round(taux_conversion, 6),
                "panier_moyen_ht": round(panier_moyen_ht, 4),
                "ca_par_client_heberge": round(ca_par_client, 4),
            }
        )
    return pd.DataFrame(rows)


def build_pilot_overrides(
    peer_codes: list[str],
    *,
    concept: str,
    data: pd.DataFrame,
) -> dict[str, float]:
    pilot = dict(get_pilot(concept))
    if data is None or data.empty or not peer_codes:
        return {
            "ca_fb": float(pilot["ca_fb"]),
            "ca_nf": float(pilot["ca_nfb"]),
            "nb_ventes": float(pilot["ventes"]),
            "mix_fb": float(pilot["mix_fb"]),
            "m_lin": float(pilot.get("ml_ref") or 6.0),
            "clients_heb": float(
                pilot.get("clients_heb")
                or pilot["nb_chambres"] * pilot["guests"] * pilot["to"] * JOURS_MOIS
            ),
            "margin_fb": float(pilot["coeff_fb"]),
            "margin_nf": float(pilot["coeff_nfb"]),
            "ca_10_fb": float(pilot["ca_10_fb"]),
            "ca_10_nfb": float(pilot["ca_10_nfb"]),
            "ca_1ml_fb": float(pilot.get("ca_1ml_fb") or 0),
            "ca_1ml_nfb": float(pilot.get("ca_1ml_nfb") or 0),
            "n_peers": 0.0,
        }

    sub = data[data["hotel_code"].isin(peer_codes)]
    if sub.empty:
        return build_pilot_overrides([], concept=concept, data=data)

    def mean(col: str, default: float) -> float:
        s = pd.to_numeric(sub[col], errors="coerce").dropna()
        return float(s.mean()) if len(s) else float(default)

    ca_fb = mean("ca_fb_mensuel", float(pilot["ca_fb"]))
    ca_nf = mean("ca_nf_mensuel", float(pilot["ca_nfb"]))
    nb_ventes = mean("nb_ventes_mensuel", float(pilot["ventes"]))
    mix_fb = mean("mix_fb", float(pilot["mix_fb"]))
    ml_ref = mean("m_lin", float(pilot.get("ml_ref") or 6.0))
    clients_heb = mean("clients_mois", float(pilot.get("clients_heb") or 5000))
    if ml_ref <= 0:
        ml_ref = 6.0

    return {
        "ca_fb": ca_fb,
        "ca_nf": ca_nf,
        "nb_ventes": nb_ventes,
        "mix_fb": mix_fb,
        "m_lin": ml_ref,
        "clients_heb": clients_heb,
        "nb_chambres": mean("nb_chambres", float(pilot["nb_chambres"])),
        "taux_occupation": mean("taux_occupation", float(pilot["to"])),
        "guests_per_chambre": mean("guests_per_chambre", float(pilot["guests"])),
        "margin_fb": float(pilot["coeff_fb"]),
        "margin_nf": float(pilot["coeff_nfb"]),
        "ca_10_fb": ca_fb / 10.0 if ca_fb else float(pilot["ca_10_fb"]),
        "ca_10_nfb": ca_nf / 10.0 if ca_nf else float(pilot["ca_10_nfb"]),
        "ca_1ml_fb": ca_fb / ml_ref,
        "ca_1ml_nfb": ca_nf / ml_ref,
        "n_peers": float(len(peer_codes)),
        "taux_conversion_ref": (nb_ventes / clients_heb) if clients_heb else 0.0,
        "panier_moyen_ref": ((ca_fb + ca_nf) / nb_ventes) if nb_ventes else 0.0,
    }


def all_needs_open() -> dict[str, bool]:
    from archive.accor_1_0_6.pipelines.src.accor.user.models import DEFAULT_CLIENT_NEEDS

    return {k: True for k in DEFAULT_CLIENT_NEEDS}


def predict_one(
    hotel_row: pd.Series,
    *,
    peers: list[str],
    data: pd.DataFrame,
) -> dict[str, Any]:
    code = str(hotel_row["hotel_code"])
    concept = str(hotel_row["solution"])
    overrides = build_pilot_overrides(peers, concept=concept, data=data)

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
        client_profile=ClientProfile(client_needs=all_needs_open()),
        store=StoreConfig(
            concept=concept,
            m_lin=float(hotel_row["m_lin"]),
            mix_fb=mix,
            mix_nf=1.0 - mix,
            nb_frigos_froid=3,
        ),
    )
    rev = RevenueRules().compute(req, concept, pilot_overrides=overrides)
    bd = rev.breakdown or {}

    true_ca = float(hotel_row["ca_ht_mensuel"])
    true_marge = float(hotel_row["marge_mensuel"])
    pred_ca = float(rev.ca_ht_mensuel or 0.0)
    pred_marge = float(rev.marge_produit_mensuelle or 0.0)

    # Table des entrees utilisees pour la prediction (lisibles metier)
    inputs = [
        {"etape": "Hotel evalue", "variable": "hotel_code", "valeur": code, "source": "pilote"},
        {"etape": "Hotel evalue", "variable": "solution", "valeur": concept, "source": "rod_pilot_concepts"},
        {"etape": "Hotel evalue", "variable": "nb_chambres", "valeur": round(float(hotel_row["nb_chambres"]), 2), "source": "hotel_data"},
        {"etape": "Hotel evalue", "variable": "taux_occupation", "valeur": round(float(hotel_row["taux_occupation"]), 4), "source": "hotel_data"},
        {"etape": "Hotel evalue", "variable": "guests_per_chambre", "valeur": round(float(hotel_row["guests_per_chambre"]), 3), "source": "defaut marque"},
        {"etape": "Hotel evalue", "variable": "clients_mois", "valeur": round(float(op.clients_mois), 2), "source": "n x TO x guests x 30.5"},
        {"etape": "Hotel evalue", "variable": "m_lin", "valeur": round(float(hotel_row["m_lin"]), 2), "source": "hotel_data corner"},
        {"etape": "Hotel evalue", "variable": "mix_fb", "valeur": round(mix, 4), "source": "ventes / simulateur_data"},
        {"etape": "Hotel evalue", "variable": "mix_nf", "valeur": round(1.0 - mix, 4), "source": "1 - mix_fb"},
        {"etape": "Reference pairs (leave-one-out)", "variable": "pairs_exclus", "valeur": code, "source": "exclu de la moyenne"},
        {"etape": "Reference pairs (leave-one-out)", "variable": "pairs_utilises", "valeur": ", ".join(peers) if peers else "(aucun)", "source": "meme solution"},
        {"etape": "Reference pairs (leave-one-out)", "variable": "ca_fb_ref", "valeur": round(overrides["ca_fb"], 2), "source": "moyenne pairs"},
        {"etape": "Reference pairs (leave-one-out)", "variable": "ca_nf_ref", "valeur": round(overrides["ca_nf"], 2), "source": "moyenne pairs"},
        {"etape": "Reference pairs (leave-one-out)", "variable": "nb_ventes_ref", "valeur": round(overrides["nb_ventes"], 2), "source": "moyenne pairs"},
        {"etape": "Reference pairs (leave-one-out)", "variable": "clients_ref", "valeur": round(overrides["clients_heb"], 2), "source": "moyenne pairs"},
        {"etape": "Reference pairs (leave-one-out)", "variable": "mix_fb_ref", "valeur": round(overrides["mix_fb"], 4), "source": "moyenne pairs"},
        {"etape": "Reference pairs (leave-one-out)", "variable": "m_lin_ref", "valeur": round(overrides["m_lin"], 2), "source": "moyenne pairs"},
        {"etape": "Reference pairs (leave-one-out)", "variable": "taux_conversion_ref", "valeur": round(float(overrides.get("taux_conversion_ref") or 0), 6), "source": "ventes_ref / clients_ref"},
        {"etape": "Reference pairs (leave-one-out)", "variable": "panier_moyen_ref", "valeur": round(float(overrides.get("panier_moyen_ref") or 0), 4), "source": "CA_ref / ventes_ref"},
        {"etape": "R1 clients acheteurs", "variable": "taux_acheteur", "valeur": round(float(bd.get("taux_acheteur") or 0), 6), "source": "ventes_ref / clients_ref"},
        {"etape": "R1 clients acheteurs", "variable": "nb_acheteurs", "valeur": round(float(bd.get("nb_acheteurs") or 0), 2), "source": "clients_hotel x taux"},
        {"etape": "R1 clients acheteurs", "variable": "facteur_clients", "valeur": round(float(bd.get("client_factor") or 0), 4), "source": "clients_hotel / clients_ref"},
        {"etape": "R1 clients acheteurs", "variable": "ca_r1_fb", "valeur": round(float(bd.get("ca_r1_fb") or 0), 2), "source": "regle 1"},
        {"etape": "R1 clients acheteurs", "variable": "ca_r1_nf", "valeur": round(float(bd.get("ca_r1_nfb") or 0), 2), "source": "regle 1"},
        {"etape": "R2 mix", "variable": "mix_steps", "valeur": round(float(bd.get("mix_steps_fb") or 0), 4), "source": "(mix_hotel - mix_ref) x 10"},
        {"etape": "R2 mix", "variable": "ca_r2_fb", "valeur": round(float(bd.get("ca_r2_fb") or 0), 2), "source": "regle 2"},
        {"etape": "R2 mix", "variable": "ca_r2_nf", "valeur": round(float(bd.get("ca_r2_nfb") or 0), 2), "source": "regle 2"},
        {"etape": "R3 categories", "variable": "mult_fb", "valeur": round(float(bd.get("mult_rule3_fb") or 0), 4), "source": "besoins clients"},
        {"etape": "R3 categories", "variable": "mult_nf", "valeur": round(float(bd.get("mult_rule3_nfb") or 0), 4), "source": "besoins clients"},
        {"etape": "R3 categories", "variable": "ca_r3_fb", "valeur": round(float(bd.get("ca_r3_fb") or 0), 2), "source": "regle 3"},
        {"etape": "R3 categories", "variable": "ca_r3_nf", "valeur": round(float(bd.get("ca_r3_nfb") or 0), 2), "source": "regle 3"},
        {"etape": "R4 surface", "variable": "mode", "valeur": str(bd.get("r4_mode") or ""), "source": "m_lin ou frigos"},
        {"etape": "R4 surface", "variable": "diff", "valeur": round(float(bd.get("r4_diff") or 0), 4), "source": "hotel - ref"},
        {"etape": "Sortie", "variable": "ca_fb_pred", "valeur": round(float(rev.ca_fb_mensuel or 0), 2), "source": "apres R1-R4"},
        {"etape": "Sortie", "variable": "ca_nf_pred", "valeur": round(float(rev.ca_nf_mensuel or 0), 2), "source": "apres R1-R4"},
        {"etape": "Sortie", "variable": "ca_ht_pred", "valeur": round(pred_ca, 2), "source": "CA FB + CA NF"},
        {"etape": "Sortie", "variable": "marge_pred", "valeur": round(pred_marge, 2), "source": "CA - CA/coef"},
        {"etape": "Controle", "variable": "ca_ht_reel", "valeur": round(true_ca, 2), "source": "ventes (moy. mensuelle)"},
        {"etape": "Controle", "variable": "marge_reel", "valeur": round(true_marge, 2), "source": "ventes (moy. mensuelle)"},
        {"etape": "Controle", "variable": "erreur_abs_ca", "valeur": round(abs(pred_ca - true_ca), 2), "source": "|pred - reel|"},
        {"etape": "Controle", "variable": "erreur_abs_marge", "valeur": round(abs(pred_marge - true_marge), 2), "source": "|pred - reel|"},
    ]

    return {
        "hotel_code": code,
        "hotel_name": str(hotel_row.get("hotel_name") or ""),
        "hotel_brand": str(hotel_row.get("hotel_brand") or ""),
        "hotel_label": str(hotel_row.get("hotel_label") or ""),
        "concept": concept,
        "peers": peers,
        "inputs": inputs,
        "true_ca": true_ca,
        "pred_ca": pred_ca,
        "err_ca": abs(pred_ca - true_ca),
        "true_marge": true_marge,
        "pred_marge": pred_marge,
        "err_marge": abs(pred_marge - true_marge),
        "n_mois": int(hotel_row.get("n_mois") or 0),
        "summary": {
            "nb_chambres": float(hotel_row["nb_chambres"]),
            "taux_occupation": float(hotel_row["taux_occupation"]),
            "guests_per_chambre": float(hotel_row["guests_per_chambre"]),
            "clients_mois": float(op.clients_mois),
            "m_lin": float(hotel_row["m_lin"]),
            "mix_fb": mix,
            "taux_conversion_hotel": float(hotel_row.get("taux_conversion_acheteur") or 0),
            "panier_moyen_hotel": float(hotel_row.get("panier_moyen_ht") or 0),
            "ca_par_client_hotel": float(hotel_row.get("ca_par_client_heberge") or 0),
            "taux_conversion_ref": float(overrides.get("taux_conversion_ref") or 0),
            "panier_moyen_ref": float(overrides.get("panier_moyen_ref") or 0),
        },
    }


def evaluate_loo_sim_v1() -> dict[str, Any]:
    pilot_map = load_pilot_map()
    c2s = code_to_solution(pilot_map)
    sales = load_sales()
    hotels = load_hotels()
    sim = load_simulateur_per_hotel()
    data = build_data_table(sales, hotels, sim, pilot_map)

    per_hotel: list[dict[str, Any]] = []
    for _, row in data.iterrows():
        code = str(row["hotel_code"])
        concept = str(row["solution"])
        peers = [
            it["hotel_code"]
            for it in (pilot_map.get(concept) or [])
            if it["hotel_code"] != code
        ]
        if not peers:
            peers = [c for c in c2s if c != code]
        per_hotel.append(predict_one(row, peers=peers, data=data))

    err_ca = [h["err_ca"] for h in per_hotel]
    err_marge = [h["err_marge"] for h in per_hotel]
    mae_ca = float(np.mean(err_ca)) if err_ca else None
    mae_marge = float(np.mean(err_marge)) if err_marge else None

    by_sol: dict[str, dict[str, Any]] = {}
    for sol in CONCEPTS:
        sub = [h for h in per_hotel if h["concept"] == sol]
        by_sol[sol] = {
            "n": len(sub),
            "mae_ca": float(np.mean([h["err_ca"] for h in sub])) if sub else None,
            "mae_marge": float(np.mean([h["err_marge"] for h in sub])) if sub else None,
        }

    mape_vals = [
        100.0 * h["err_ca"] / abs(h["true_ca"])
        for h in per_hotel
        if h["true_ca"] and abs(h["true_ca"]) > 1e-6
    ]

    return {
        "ok": True,
        "data": data,
        "per_hotel": per_hotel,
        "metrics": {
            "mae_ca_mensuel": round(mae_ca, 2) if mae_ca is not None else None,
            "mae_marge_mensuel": round(mae_marge, 2) if mae_marge is not None else None,
            "mape_ca_pct": round(float(np.mean(mape_vals)), 1) if mape_vals else None,
            "n_hotels": len(per_hotel),
        },
        "by_solution": by_sol,
    }


def write_eval_excel(result: dict[str, Any] | None = None, path: Path | None = None) -> Path:
    """Ecrit data + eval_<code> + eval dans un classeur unique."""
    path = path or EXCEL_OUT
    result = result or evaluate_loo_sim_v1()
    data: pd.DataFrame = result["data"]
    per_hotel: list[dict[str, Any]] = result["per_hotel"]
    metrics = result["metrics"]
    by_sol = result["by_solution"]

    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path, engine="openpyxl") as w:
        data.to_excel(w, index=False, sheet_name="data")

        for h in per_hotel:
            code = h["hotel_code"]
            sheet = f"eval_{code}"[:31]
            # resume prediction
            resume = pd.DataFrame(
                [
                    {"indicateur": "hotel_code", "valeur": h["hotel_code"]},
                    {"indicateur": "hotel_name", "valeur": h["hotel_name"]},
                    {"indicateur": "solution", "valeur": h["concept"]},
                    {"indicateur": "pairs", "valeur": ", ".join(h["peers"])},
                    {"indicateur": "ca_ht_reel_mensuel", "valeur": round(h["true_ca"], 2)},
                    {"indicateur": "ca_ht_pred_mensuel", "valeur": round(h["pred_ca"], 2)},
                    {"indicateur": "erreur_abs_ca", "valeur": round(h["err_ca"], 2)},
                    {"indicateur": "marge_reel_mensuel", "valeur": round(h["true_marge"], 2)},
                    {"indicateur": "marge_pred_mensuel", "valeur": round(h["pred_marge"], 2)},
                    {"indicateur": "erreur_abs_marge", "valeur": round(h["err_marge"], 2)},
                    {"indicateur": "n_mois", "valeur": h["n_mois"]},
                ]
            )
            detail = pd.DataFrame(h["inputs"])
            # two blocks on same sheet: write resume then detail with blank row via concat
            block = pd.concat(
                [
                    pd.DataFrame([{"etape": "RESUME", "variable": "", "valeur": "", "source": ""}]),
                    resume.rename(
                        columns={
                            "indicateur": "variable",
                            "valeur": "valeur",
                        }
                    ).assign(etape="RESUME", source=""),
                    pd.DataFrame([{"etape": "", "variable": "", "valeur": "", "source": ""}]),
                    pd.DataFrame(
                        [{"etape": "DETAIL REGLES", "variable": "", "valeur": "", "source": ""}]
                    ),
                    detail,
                ],
                ignore_index=True,
            )
            # simpler: two sheets is cleaner but user asked eval_HCODE one tab
            # Put resume cols + detail
            out_sheet = pd.DataFrame(h["inputs"])
            # prepend summary as first rows with etape RESUME
            head = pd.DataFrame(
                [
                    {"etape": "RESUME", "variable": k, "valeur": v, "source": ""}
                    for k, v in {
                        "hotel_code": h["hotel_code"],
                        "hotel_name": h["hotel_name"],
                        "solution": h["concept"],
                        "pairs": ", ".join(h["peers"]),
                        "ca_ht_reel": round(h["true_ca"], 2),
                        "ca_ht_pred": round(h["pred_ca"], 2),
                        "erreur_abs_ca": round(h["err_ca"], 2),
                        "marge_reel": round(h["true_marge"], 2),
                        "marge_pred": round(h["pred_marge"], 2),
                        "erreur_abs_marge": round(h["err_marge"], 2),
                    }.items()
                ]
            )
            pd.concat([head, out_sheet], ignore_index=True).to_excel(
                w, index=False, sheet_name=sheet
            )

        # eval global
        eval_rows = []
        for h in per_hotel:
            eval_rows.append(
                {
                    "hotel_code": h["hotel_code"],
                    "hotel_name": h["hotel_name"],
                    "solution": h["concept"],
                    "pairs": ", ".join(h["peers"]),
                    "ca_ht_reel": round(h["true_ca"], 2),
                    "ca_ht_pred": round(h["pred_ca"], 2),
                    "erreur_abs_ca": round(h["err_ca"], 2),
                    "marge_reel": round(h["true_marge"], 2),
                    "marge_pred": round(h["pred_marge"], 2),
                    "erreur_abs_marge": round(h["err_marge"], 2),
                    "n_mois": h["n_mois"],
                }
            )
        df_eval = pd.DataFrame(eval_rows)
        # metrics footer
        metrics_df = pd.DataFrame(
            [
                {"hotel_code": "MAE_GLOBAL", "erreur_abs_ca": metrics.get("mae_ca_mensuel"), "erreur_abs_marge": metrics.get("mae_marge_mensuel")},
                {"hotel_code": "MAPE_CA_PCT", "erreur_abs_ca": metrics.get("mape_ca_pct"), "erreur_abs_marge": None},
            ]
        )
        for sol, v in by_sol.items():
            metrics_df = pd.concat(
                [
                    metrics_df,
                    pd.DataFrame(
                        [
                            {
                                "hotel_code": f"MAE_{sol}",
                                "erreur_abs_ca": None
                                if v.get("mae_ca") is None
                                else round(v["mae_ca"], 2),
                                "erreur_abs_marge": None
                                if v.get("mae_marge") is None
                                else round(v["mae_marge"], 2),
                                "solution": sol,
                                "n_mois": v.get("n"),
                            }
                        ]
                    ),
                ],
                ignore_index=True,
            )
        pd.concat([df_eval, metrics_df], ignore_index=True).to_excel(
            w, index=False, sheet_name="eval"
        )

    return path


def metrics_summary(result: dict[str, Any]) -> str:
    m = result.get("metrics") or {}
    lines = [
        f"Simulateur v1 leave-one-out — {m.get('n_hotels')} hotels",
        f"  MAE CA mensuel    : {m.get('mae_ca_mensuel')} EUR",
        f"  MAE marge mensuel : {m.get('mae_marge_mensuel')} EUR",
        f"  MAPE CA           : {m.get('mape_ca_pct')} %",
    ]
    for sol, v in (result.get("by_solution") or {}).items():
        lines.append(
            f"  [{sol}] n={v.get('n')} MAE_CA={None if v.get('mae_ca') is None else round(v['mae_ca'], 2)} "
            f"MAE_marge={None if v.get('mae_marge') is None else round(v['mae_marge'], 2)}"
        )
    return "\n".join(lines)
