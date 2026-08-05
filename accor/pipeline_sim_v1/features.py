"""
Chargement des sources et table d'indicateurs hotel (formules alignes eval_sim_v1).

Filtre obligatoire : 6 hotels EVAL_HOTELS, exclusion H5586.
"""

from __future__ import annotations

import json
from typing import Any

import pandas as pd

from .constants import (
    BRAND_GUESTS_DEFAULT,
    BRAND_TO_DEFAULT,
    EVAL_CODES,
    EVAL_HOTELS,
    EXCLUDED_HOTELS,
    HOTEL_PATH,
    JOURS_MOIS,
    PILOT_FALLBACK,
    PILOT_MAP_PATH,
    SALES_PATH,
    SIM_DATA_PATH,
)


def _norm_brand(brand: Any) -> str:
    return str(brand or "").strip().upper().replace("_", " ")


def _as_rate(value: Any, default: float = 0.70) -> float:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return default
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    if v > 1.0:
        v /= 100.0
    return min(max(v, 0.0), 1.0)


def load_pilot_map() -> dict[str, list[dict[str, str]]]:
    """Mapping solution → hotels pilotes (filtre EXCLUDED + EVAL)."""
    raw_concepts: dict[str, list[dict[str, Any]]] = {}
    if PILOT_MAP_PATH.exists():
        raw = json.loads(PILOT_MAP_PATH.read_text(encoding="utf-8"))
        raw_concepts = raw.get("concepts") or {}

    out: dict[str, list[dict[str, str]]] = {}
    for sol, code_sol in (
        ("SIMPLY", "SIMPLY"),
        ("LIBERTY", "LIBERTY"),
        ("CONNECTED", "CONNECTED"),
    ):
        items = raw_concepts.get(sol) or []
        kept: list[dict[str, str]] = []
        for it in items:
            code = str(it.get("hotel_code") or "").strip()
            if not code or code in EXCLUDED_HOTELS:
                continue
            if code not in EVAL_HOTELS:
                continue
            kept.append(
                {
                    "hotel_code": code,
                    "label": str(it.get("label") or "").strip(),
                    "name": str(
                        it.get("name_display")
                        or it.get("name_ventes")
                        or it.get("hotel_name")
                        or ""
                    ).strip(),
                }
            )
        # Completer si fichier incomplet
        for code, s in EVAL_HOTELS.items():
            if s != code_sol:
                continue
            if any(x["hotel_code"] == code for x in kept):
                continue
            kept.append({"hotel_code": code, "label": "", "name": ""})
        out[sol] = kept
    return out


def code_to_solution(mapping: dict[str, list[dict[str, str]]] | None = None) -> dict[str, str]:
    mapping = mapping or load_pilot_map()
    out: dict[str, str] = {}
    for sol, items in mapping.items():
        for it in items:
            out[it["hotel_code"]] = sol
    # Force mapping EVAL (source de verite)
    for code, sol in EVAL_HOTELS.items():
        out[code] = sol
    for code in EXCLUDED_HOTELS:
        out.pop(code, None)
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
    df = df[~df["hotel_code"].isin(EXCLUDED_HOTELS)]
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
    df = df[~df["hotel_code"].isin(EXCLUDED_HOTELS)]
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
    sales: pd.DataFrame | None = None,
    hotels: pd.DataFrame | None = None,
    sim: pd.DataFrame | None = None,
    pilot_map: dict[str, list[dict[str, str]]] | None = None,
) -> pd.DataFrame:
    """
    Une ligne par hotel evalue : indicateurs utilises par les regles ROD.
    """
    pilot_map = pilot_map or load_pilot_map()
    sales = sales if sales is not None else load_sales()
    hotels = hotels if hotels is not None else load_hotels()
    sim = sim if sim is not None else load_simulateur_per_hotel()
    c2s = code_to_solution(pilot_map)

    # Uniquement les 6 hotels
    codes = [c for c in EVAL_CODES if c in c2s and c not in EXCLUDED_HOTELS]
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
        taux_conversion = (ventes_m / clients_mois) if clients_mois > 0 else 0.0
        panier_moyen_ht = (ca_m / ventes_m) if ventes_m > 0 else 0.0
        ca_par_client = (ca_m / clients_mois) if clients_mois > 0 else 0.0
        ca_fb_m = ca_m * mix_fb
        ca_nf_m = ca_m * mix_nf

        years = (
            sorted(
                int(y)
                for y in pd.to_numeric(g.get("annee"), errors="coerce").dropna().unique()
            )
            if n_mois
            else []
        )

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


def peers_for(code: str, solution: str, pilot_map: dict[str, list[dict[str, str]]] | None = None) -> list[str]:
    """Pairs = autres hotels de la meme solution parmi les 6."""
    pilot_map = pilot_map or load_pilot_map()
    peers = [
        it["hotel_code"]
        for it in (pilot_map.get(solution) or [])
        if it["hotel_code"] != code and it["hotel_code"] not in EXCLUDED_HOTELS
    ]
    if not peers:
        peers = [
            c
            for c, s in EVAL_HOTELS.items()
            if s == solution and c != code and c not in EXCLUDED_HOTELS
        ]
    return peers


def build_pilot_overrides(
    peer_codes: list[str],
    *,
    concept: str,
    data: pd.DataFrame,
) -> dict[str, float]:
    """Reference LOO = moyenne des features des pairs (meme solution)."""
    pilot = dict(PILOT_FALLBACK.get(concept.upper(), PILOT_FALLBACK["SIMPLY"]))
    if data is None or data.empty or not peer_codes:
        ml = float(pilot.get("ml_ref") or 6.0)
        ca_fb = float(pilot["ca_fb"])
        ca_nf = float(pilot["ca_nfb"])
        return {
            "ca_fb": ca_fb,
            "ca_nf": ca_nf,
            "nb_ventes": float(pilot["ventes"]),
            "mix_fb": float(pilot["mix_fb"]),
            "m_lin": ml,
            "clients_heb": float(pilot.get("clients_heb") or 5000),
            "margin_fb": float(pilot["coeff_fb"]),
            "margin_nf": float(pilot["coeff_nfb"]),
            "ca_10_fb": float(pilot["ca_10_fb"]),
            "ca_10_nfb": float(pilot["ca_10_nfb"]),
            "ca_1ml_fb": float(pilot.get("ca_1ml_fb") or (ca_fb / ml if ml else 0)),
            "ca_1ml_nfb": float(pilot.get("ca_1ml_nfb") or (ca_nf / ml if ml else 0)),
            "frigo_ref": float(pilot.get("frigo_ref") or 0) or None,  # type: ignore[dict-item]
            "ca_1frigo_fb": float(pilot.get("ca_1frigo_fb") or (ca_fb / 3.0)),
            "ca_1frigo_nfb": float(pilot.get("ca_1frigo_nfb") or (ca_nf / 3.0)),
            "n_peers": 0.0,
            "taux_conversion_ref": 0.0,
            "panier_moyen_ref": 0.0,
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

    frigo_ref = float(pilot.get("frigo_ref") or 0) or None
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
        "frigo_ref": frigo_ref,  # type: ignore[dict-item]
        "ca_1frigo_fb": ca_fb / 3.0,
        "ca_1frigo_nfb": ca_nf / 3.0,
        "n_peers": float(len(peer_codes)),
        "taux_conversion_ref": (nb_ventes / clients_heb) if clients_heb else 0.0,
        "panier_moyen_ref": ((ca_fb + ca_nf) / nb_ventes) if nb_ventes else 0.0,
    }


def metrics_from_predictions(pred: pd.DataFrame) -> pd.DataFrame:
    """Feuille metrics : global + par solution."""
    rows: list[dict[str, Any]] = []
    if pred is None or pred.empty:
        return pd.DataFrame(rows)

    def _block(label: str, sub: pd.DataFrame) -> None:
        if sub.empty:
            return
        err_ca = sub["ca_err_abs"].astype(float)
        err_m = sub["marge_err_abs"].astype(float)
        mape = []
        for _, r in sub.iterrows():
            t = float(r["ca_reel"])
            if abs(t) > 1e-6:
                mape.append(100.0 * float(r["ca_err_abs"]) / abs(t))
        rows.append(
            {
                "scope": label,
                "n_hotels": int(len(sub)),
                "mae_ca": round(float(err_ca.mean()), 2),
                "mae_marge": round(float(err_m.mean()), 2),
                "mape_ca_pct": round(float(sum(mape) / len(mape)), 1) if mape else None,
            }
        )

    _block("GLOBAL", pred)
    for sol in ("SIMPLY", "LIBERTY", "CONNECTED"):
        _block(sol, pred[pred["solution"] == sol])
    return pd.DataFrame(rows)
