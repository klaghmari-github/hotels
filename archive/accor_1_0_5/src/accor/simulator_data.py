#!/usr/bin/env python3
"""
Simulateur Data — mesures ventes pour SIMPLY / LIBERTY / CONNECTED.

À partir de ``hotel_sales_raw_data.xlsx`` (+ mapping pilotes solution) :
  1. normalise les lignes tickets (TYPE F&B / N-F&B, boutique → hotel_code)
  2. agrège les mesures utiles au simulateur Excel (CA HT/TTC, mix, ventes…)
  3. écrit ``data/simulateur_data.xlsx`` (feuilles détail + moyennes)

UI admin : onglet « Simulateur Data » + bouton Reconstruire.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from archive.accor_1_0_5.src.accor.data_io import DATA_DIR, read_excel

FILENAME = "simulateur_data.xlsx"
SHEET_MAIN = "simulateur_data"
SHEET_MENSUEL = "mensuel"
SHEET_MOYENNES = "moyennes_solution"
SHEET_META = "meta"

CONCEPTS = ("SIMPLY", "LIBERTY", "CONNECTED")

# Marges produit par défaut (réf. Excel rod_reference) si absentes
DEFAULT_MARGINS = {
    "SIMPLY": {"margin_fb": 2.6, "margin_nf": 1.45},
    "LIBERTY": {"margin_fb": 2.6, "margin_nf": 2.0},
    "CONNECTED": {"margin_fb": 2.6, "margin_nf": 1.8},
}

# Colonnes affichées (ordre table admin)
SIMULATEUR_DATA_COLUMNS = [
    "solution",
    "hotel_code",
    "hotel_label",
    "hotel_name",
    "annee",
    "n_mois",
    "ca_ht_fb_mensuel",
    "ca_ht_nf_mensuel",
    "ca_ht_total_mensuel",
    "ca_ttc_fb_mensuel",
    "ca_ttc_nf_mensuel",
    "ca_ttc_total_mensuel",
    "nb_ventes_mensuel",
    "nb_paniers_mensuel",
    "mix_fb",
    "mix_nf",
    "ticket_moyen_ht",
    "panier_moyen_ht",
    "margin_fb",
    "margin_nf",
    "margin_ponderee",
    "taux_occupation",
    "nb_chambres",
    "clients_mois_estimes",
    "taux_acheteur",
    "ca_ht_par_1pct_to",
]


def simulateur_data_path() -> Path:
    return DATA_DIR / FILENAME


def _load_pilot_map() -> dict[str, list[dict[str, str]]]:
    path = DATA_DIR / "rod_pilot_concepts.json"
    if not path.exists():
        return {c: [] for c in CONCEPTS}
    import json

    raw = json.loads(path.read_text(encoding="utf-8"))
    concepts = raw.get("concepts") or {}
    out: dict[str, list[dict[str, str]]] = {}
    for c in CONCEPTS:
        items = concepts.get(c) or []
        out[c] = [
            {
                "hotel_code": str(it.get("hotel_code") or "").strip(),
                "label": str(it.get("label") or "").strip(),
            }
            for it in items
            if it.get("hotel_code")
        ]
    return out


def _code_to_solution(mapping: dict[str, list[dict[str, str]]]) -> dict[str, tuple[str, str]]:
    """hotel_code → (solution, label)."""
    out: dict[str, tuple[str, str]] = {}
    for sol, items in mapping.items():
        for it in items:
            out[it["hotel_code"]] = (sol, it["label"])
    return out


def _margins_from_ref() -> dict[str, dict[str, float]]:
    path = DATA_DIR / "rod_reference.json"
    out = {c: dict(DEFAULT_MARGINS[c]) for c in CONCEPTS}
    if not path.exists():
        return out
    import json

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        concepts = data.get("concepts") or {}
        for c in CONCEPTS:
            node = concepts.get(c) or {}
            if node.get("margin_fb_pct") is not None:
                out[c]["margin_fb"] = float(node["margin_fb_pct"])
            if node.get("margin_nf_pct") is not None:
                out[c]["margin_nf"] = float(node["margin_nf_pct"])
    except Exception:
        pass
    return out


def _hotel_operating() -> pd.DataFrame:
    """nb_chambres + TO depuis hotel_data (si dispo)."""
    path = DATA_DIR / "hotel_data.xlsx"
    if not path.exists():
        return pd.DataFrame(columns=["hotel_code", "nb_chambres", "taux_occupation"])
    try:
        hotels = read_excel(path, sheet=0)
    except Exception:
        return pd.DataFrame(columns=["hotel_code", "nb_chambres", "taux_occupation"])
    if hotels.empty or "hotel_code" not in hotels.columns:
        return pd.DataFrame(columns=["hotel_code", "nb_chambres", "taux_occupation"])
    out = hotels[["hotel_code"]].copy()
    out["hotel_code"] = out["hotel_code"].astype(str).str.strip()
    n_col = next(
        (c for c in hotels.columns if str(c).lower() in ("hotel_nb_chambres", "nb_chambres")),
        None,
    )
    to_col = next(
        (c for c in hotels.columns if str(c).lower() in ("hotel_to_annuel", "taux_occupation", "to")),
        None,
    )
    out["nb_chambres"] = (
        pd.to_numeric(hotels[n_col], errors="coerce") if n_col else pd.NA
    )
    to = pd.to_numeric(hotels[to_col], errors="coerce") if to_col else pd.Series(pd.NA, index=hotels.index)
    # TO parfois en % (70) parfois en ratio (0.7)
    to = to.where(to.isna() | (to <= 1.5), to / 100.0)
    out["taux_occupation"] = to
    return out.drop_duplicates("hotel_code")


def _load_prepared_lines() -> pd.DataFrame:
    from archive.accor_1_0_5.src.accor.sales_prep import load_hotel_lookup, load_raw_sales, prepare_lines

    raw = load_raw_sales()
    if raw is None or raw.empty:
        raise ValueError(
            "hotel_sales_raw_data.xlsx vide ou introuvable — placez le fichier dans data/."
        )
    lines = prepare_lines(raw, load_hotel_lookup())
    if lines is None or lines.empty:
        raise ValueError("Aucune ligne de vente après préparation.")
    # HT / TTC unitaires pour CA TTC
    lines = lines.copy()
    ht = (
        pd.to_numeric(lines["prix_ht"], errors="coerce")
        if "prix_ht" in lines.columns
        else pd.Series(0.0, index=lines.index)
    )
    ttc = (
        pd.to_numeric(lines["prix_ttc"], errors="coerce")
        if "prix_ttc" in lines.columns
        else pd.Series(pd.NA, index=lines.index)
    )
    q = pd.to_numeric(lines["nombre_ventes"], errors="coerce").fillna(0.0)
    # Si prix_ttc manquant : approx TVA 10% F&B / 20% N-F&B
    tva = lines["categorie"].map({"f_b": 1.10, "n_f_b": 1.20}).fillna(1.15)
    ttc = ttc.fillna(ht.fillna(0.0) * tva)
    lines["montant_ttc"] = (ttc.fillna(0.0) * q).astype(float)
    if "montant_ventes" not in lines.columns:
        lines["montant_ventes"] = (ht.fillna(0.0) * q).astype(float)
    return lines


def _monthly_by_hotel(lines: pd.DataFrame, pilots: dict[str, tuple[str, str]]) -> pd.DataFrame:
    """Agrégat hotel × an × mois pour les pilotes solution uniquement."""
    df = lines.loc[lines["hotel_code"].notna()].copy()
    df["hotel_code"] = df["hotel_code"].astype(str).str.strip()
    df = df.loc[df["hotel_code"].isin(pilots.keys())].copy()
    if df.empty:
        return pd.DataFrame()

    keys = ["hotel_code", "annee", "mois"]
    # Totaux
    base = (
        df.groupby(keys, dropna=False)
        .agg(
            ca_ht_total=("montant_ventes", "sum"),
            ca_ttc_total=("montant_ttc", "sum"),
            nb_ventes=("nombre_ventes", "sum"),
            nb_paniers=("order_id", "nunique"),
            hotel_name=("nom_hotel", "first"),
        )
        .reset_index()
    )
    # F&B / N-F&B
    by_cat = (
        df.groupby(keys + ["categorie"], dropna=False)
        .agg(
            ca_ht=("montant_ventes", "sum"),
            ca_ttc=("montant_ttc", "sum"),
            nb_ventes=("nombre_ventes", "sum"),
        )
        .reset_index()
    )
    for cat, prefix in (("f_b", "fb"), ("n_f_b", "nf")):
        sub = by_cat.loc[by_cat["categorie"] == cat, keys + ["ca_ht", "ca_ttc", "nb_ventes"]].rename(
            columns={
                "ca_ht": f"ca_ht_{prefix}",
                "ca_ttc": f"ca_ttc_{prefix}",
                "nb_ventes": f"nb_ventes_{prefix}",
            }
        )
        base = base.merge(sub, on=keys, how="left")
    for c in (
        "ca_ht_fb",
        "ca_ht_nf",
        "ca_ttc_fb",
        "ca_ttc_nf",
        "nb_ventes_fb",
        "nb_ventes_nf",
    ):
        if c not in base.columns:
            base[c] = 0.0
        base[c] = pd.to_numeric(base[c], errors="coerce").fillna(0.0)

    # solution / label
    base["solution"] = base["hotel_code"].map(lambda c: pilots[c][0])
    base["hotel_label"] = base["hotel_code"].map(lambda c: pilots[c][1])
    # Mix F&B / N-F&B = part du **nombre de ventes total** (période de modélisation)
    # — même technique que les sous-catégories ; somme = 100 % (ε toléré).
    tot_v = base["nb_ventes_fb"] + base["nb_ventes_nf"]
    base["mix_fb"] = (base["nb_ventes_fb"] / tot_v.replace(0, pd.NA)).fillna(0.0)
    base["mix_nf"] = (base["nb_ventes_nf"] / tot_v.replace(0, pd.NA)).fillna(0.0)
    # Normalise ε (somme doit être 1)
    s_mix = base["mix_fb"] + base["mix_nf"]
    base.loc[s_mix > 0, "mix_fb"] = base.loc[s_mix > 0, "mix_fb"] / s_mix[s_mix > 0]
    base.loc[s_mix > 0, "mix_nf"] = base.loc[s_mix > 0, "mix_nf"] / s_mix[s_mix > 0]
    return base


def _annual_from_monthly(monthly: pd.DataFrame, margins: dict[str, dict[str, float]], op: pd.DataFrame) -> pd.DataFrame:
    """Moyennes mensuelles par hotel × année (mois avec activité)."""
    if monthly is None or monthly.empty:
        return pd.DataFrame(columns=SIMULATEUR_DATA_COLUMNS)

    keys = ["solution", "hotel_code", "hotel_label", "hotel_name", "annee"]
    g = monthly.groupby(keys, dropna=False)
    ann = g.agg(
        n_mois=("mois", "nunique"),
        ca_ht_fb_mensuel=("ca_ht_fb", "mean"),
        ca_ht_nf_mensuel=("ca_ht_nf", "mean"),
        ca_ht_total_mensuel=("ca_ht_total", "mean"),
        ca_ttc_fb_mensuel=("ca_ttc_fb", "mean"),
        ca_ttc_nf_mensuel=("ca_ttc_nf", "mean"),
        ca_ttc_total_mensuel=("ca_ttc_total", "mean"),
        nb_ventes_mensuel=("nb_ventes", "mean"),
        nb_paniers_mensuel=("nb_paniers", "mean"),
        mix_fb=("mix_fb", "mean"),
        mix_nf=("mix_nf", "mean"),
    ).reset_index()

    # ticket / panier moyen
    ann["ticket_moyen_ht"] = (
        ann["ca_ht_total_mensuel"] / ann["nb_ventes_mensuel"].replace(0, pd.NA)
    ).fillna(0.0)
    ann["panier_moyen_ht"] = (
        ann["ca_ht_total_mensuel"] / ann["nb_paniers_mensuel"].replace(0, pd.NA)
    ).fillna(0.0)

    # marges réf. solution
    ann["margin_fb"] = ann["solution"].map(lambda s: margins.get(s, {}).get("margin_fb", 2.6))
    ann["margin_nf"] = ann["solution"].map(lambda s: margins.get(s, {}).get("margin_nf", 1.45))
    ann["margin_ponderee"] = (
        ann["margin_fb"] * ann["mix_fb"] + ann["margin_nf"] * ann["mix_nf"]
    )

    # operating (fiche hôtel)
    if op is not None and not op.empty:
        ann = ann.merge(op, on="hotel_code", how="left")
    else:
        ann["nb_chambres"] = pd.NA
        ann["taux_occupation"] = pd.NA

    # Fallback pivots Excel rod_reference si TO / chambres manquants
    try:
        from archive.accor_1_0_5.src.accor.user.reference import RodReference

        ref = RodReference()
        pivot_to = {
            c: float(ref.get(f"concepts.{c}.pivot_to", 0.75) or 0.75) for c in CONCEPTS
        }
        pivot_n = {
            c: float(ref.get(f"concepts.{c}.pivot_nb_chambres", 100) or 100)
            for c in CONCEPTS
        }
        pivot_g = {
            c: float(ref.get(f"concepts.{c}.pivot_guests_per_chambre", 1.7) or 1.7)
            for c in CONCEPTS
        }
    except Exception:
        pivot_to = {c: 0.75 for c in CONCEPTS}
        pivot_n = {c: 100.0 for c in CONCEPTS}
        pivot_g = {c: 1.7 for c in CONCEPTS}

    n = pd.to_numeric(ann["nb_chambres"], errors="coerce")
    to = pd.to_numeric(ann["taux_occupation"], errors="coerce")
    n = n.fillna(ann["solution"].map(pivot_n))
    to = to.fillna(ann["solution"].map(pivot_to))
    ann["nb_chambres"] = n
    ann["taux_occupation"] = to
    guests = ann["solution"].map(pivot_g).fillna(1.7)

    # clients mois estimés (30.5 j) + taux acheteur
    JOURS = 30.5
    ann["clients_mois_estimes"] = (n * to * guests * JOURS).round(1)
    ann["taux_acheteur"] = (
        ann["nb_ventes_mensuel"] / ann["clients_mois_estimes"].replace(0, pd.NA)
    ).fillna(0.0)
    # Impact +1 pt TO ≈ CA_mensuel / (TO*100)
    ann["ca_ht_par_1pct_to"] = (
        ann["ca_ht_total_mensuel"] / (to * 100.0).replace(0, pd.NA)
    ).fillna(0.0)

    # arrondis
    money = [
        "ca_ht_fb_mensuel",
        "ca_ht_nf_mensuel",
        "ca_ht_total_mensuel",
        "ca_ttc_fb_mensuel",
        "ca_ttc_nf_mensuel",
        "ca_ttc_total_mensuel",
        "ticket_moyen_ht",
        "panier_moyen_ht",
        "ca_ht_par_1pct_to",
    ]
    for c in money:
        ann[c] = pd.to_numeric(ann[c], errors="coerce").round(2)
    for c in ("nb_ventes_mensuel", "nb_paniers_mensuel"):
        ann[c] = pd.to_numeric(ann[c], errors="coerce").round(1)
    for c in ("mix_fb", "mix_nf", "taux_acheteur", "margin_ponderee"):
        ann[c] = pd.to_numeric(ann[c], errors="coerce").round(4)
    for c in ("margin_fb", "margin_nf"):
        ann[c] = pd.to_numeric(ann[c], errors="coerce").round(2)

    cols = [c for c in SIMULATEUR_DATA_COLUMNS if c in ann.columns]
    extra = [c for c in ann.columns if c not in cols]
    ann = ann[cols + extra]
    return ann.sort_values(["solution", "hotel_code", "annee"]).reset_index(drop=True)


def _per_hotel_train_means(
    annual: pd.DataFrame, train_years: list[int] | None = None
) -> pd.DataFrame:
    """
    Une ligne par hôtel pilote = moyenne des années train.

    Règle Excel / audit : d'abord stabiliser chaque pilote, puis moyenne
    multi-pilotes à **poids égaux** (pas de biais si un hôtel a plus d'années).
    """
    if annual is None or annual.empty:
        return pd.DataFrame()
    df = annual.copy()
    if train_years:
        filt = df.loc[df["annee"].isin(train_years)].copy()
        if not filt.empty:
            df = filt
    num_cols = [
        c
        for c in (
            "n_mois",
            "ca_ht_fb_mensuel",
            "ca_ht_nf_mensuel",
            "ca_ht_total_mensuel",
            "ca_ttc_fb_mensuel",
            "ca_ttc_nf_mensuel",
            "ca_ttc_total_mensuel",
            "nb_ventes_mensuel",
            "nb_paniers_mensuel",
            "mix_fb",
            "mix_nf",
            "ticket_moyen_ht",
            "panier_moyen_ht",
            "margin_fb",
            "margin_nf",
            "margin_ponderee",
            "taux_occupation",
            "nb_chambres",
            "clients_mois_estimes",
            "taux_acheteur",
            "ca_ht_par_1pct_to",
        )
        if c in df.columns
    ]
    keys = ["solution", "hotel_code"]
    label_cols = [c for c in ("hotel_label", "hotel_name") if c in df.columns]
    g = df.groupby(keys, dropna=False)
    out = g[num_cols].mean().reset_index()
    for lc in label_cols:
        out[lc] = g[lc].first().values
    out["n_annees_train"] = g["annee"].nunique().values
    out["annees_train"] = g["annee"].apply(
        lambda s: ", ".join(str(int(y)) for y in sorted(s.unique()))
    ).values
    # Mix = moyenne des mix (déjà en part du nb de ventes total) ;
    # renormalise pour somme = 1 (ε virgules).
    if "mix_fb" in out.columns and "mix_nf" in out.columns:
        s_mix = out["mix_fb"].fillna(0) + out["mix_nf"].fillna(0)
        out.loc[s_mix > 0, "mix_fb"] = out.loc[s_mix > 0, "mix_fb"] / s_mix[s_mix > 0]
        out.loc[s_mix > 0, "mix_nf"] = out.loc[s_mix > 0, "mix_nf"] / s_mix[s_mix > 0]
    if "margin_fb" in out.columns and "margin_nf" in out.columns:
        out["margin_ponderee"] = (
            out["margin_fb"] * out["mix_fb"] + out["margin_nf"] * out["mix_nf"]
        )
    return out.sort_values(["solution", "hotel_code"]).reset_index(drop=True)


def _solution_averages(annual: pd.DataFrame, train_years: list[int] | None = None) -> pd.DataFrame:
    """
    Moyenne multi-pilotes par solution.

    Règle métier (audit + rod_pilot_concepts) :
      * plusieurs hôtels pour une solution → **moyenne à poids égaux par hôtel**
      * chaque hôtel = moyenne de ses années train (mensuel déjà agrégé)
      * mix F&B/N-F&B recalculé depuis CA moyens (cohérent R2)
    """
    per_hotel = _per_hotel_train_means(annual, train_years=train_years)
    if per_hotel is None or per_hotel.empty:
        return pd.DataFrame()

    num_cols = [
        c
        for c in (
            "n_mois",
            "ca_ht_fb_mensuel",
            "ca_ht_nf_mensuel",
            "ca_ht_total_mensuel",
            "ca_ttc_fb_mensuel",
            "ca_ttc_nf_mensuel",
            "ca_ttc_total_mensuel",
            "nb_ventes_mensuel",
            "nb_paniers_mensuel",
            "mix_fb",
            "mix_nf",
            "ticket_moyen_ht",
            "panier_moyen_ht",
            "margin_fb",
            "margin_nf",
            "margin_ponderee",
            "taux_occupation",
            "nb_chambres",
            "clients_mois_estimes",
            "taux_acheteur",
            "ca_ht_par_1pct_to",
        )
        if c in per_hotel.columns
    ]
    rows = []
    for sol in CONCEPTS:
        sub = per_hotel.loc[per_hotel["solution"] == sol]
        if sub.empty:
            continue
        labels = []
        for r in sub.itertuples():
            lab = getattr(r, "hotel_label", None) or r.hotel_code
            labels.append(f"{lab} ({r.hotel_code})")
        years_set: set[int] = set()
        for a in sub.get("annees_train", pd.Series(dtype=str)).fillna(""):
            for part in str(a).split(","):
                part = part.strip()
                if part.isdigit():
                    years_set.add(int(part))
        row: dict[str, Any] = {
            "solution": sol,
            "n_pilotes": int(sub["hotel_code"].nunique()),
            "pilotes": ", ".join(sorted(labels)),
            "annees": ", ".join(str(y) for y in sorted(years_set)),
            "n_lignes_hotel_an": int(sub["n_annees_train"].sum())
            if "n_annees_train" in sub.columns
            else len(sub),
            "aggregation": "mean_equal_weight_per_hotel",
        }
        for c in num_cols:
            row[c] = round(float(pd.to_numeric(sub[c], errors="coerce").mean()), 4)
        # CA total depuis canaux ; mix déjà en part nb_ventes (renormalisé)
        ca_fb = float(row.get("ca_ht_fb_mensuel") or 0)
        ca_nf = float(row.get("ca_ht_nf_mensuel") or 0)
        row["ca_ht_total_mensuel"] = round(ca_fb + ca_nf, 4)
        mf = float(row.get("mix_fb") or 0)
        mn = float(row.get("mix_nf") or 0)
        sm = mf + mn
        if sm > 0:
            row["mix_fb"] = round(mf / sm, 4)
            row["mix_nf"] = round(mn / sm, 4)
        m_fb = float(row.get("margin_fb") or 2.6)
        m_nf = float(row.get("margin_nf") or 1.45)
        row["margin_ponderee"] = round(
            m_fb * float(row.get("mix_fb") or 0) + m_nf * float(row.get("mix_nf") or 0),
            4,
        )
        rows.append(row)
    return pd.DataFrame(rows)


def build_live_excel_annex_sheets(
    per_hotel: pd.DataFrame, moyennes: pd.DataFrame
) -> dict[str, Any]:
    """
    Feuilles annexes type Excel MIX + IMPACT TO, **tous les pilotes** de chaque solution.
    """
    mix_products: dict[str, Any] = {"title": "REVENUS ► MIX PRODUITS (live ventes)"}
    impact_to: dict[str, Any] = {"title": "REVENUS ► TAUX D'OCCUPATION (live ventes)"}

    for sol in CONCEPTS:
        ph = (
            per_hotel.loc[per_hotel["solution"] == sol]
            if per_hotel is not None and not per_hotel.empty
            else pd.DataFrame()
        )
        moy_row = None
        if moyennes is not None and not moyennes.empty:
            m = moyennes.loc[moyennes["solution"] == sol]
            if not m.empty:
                moy_row = m.iloc[0]

        pilots_mix = []
        pilots_imp = []
        for _, d in ph.iterrows():
            lab = str(d.get("hotel_label") or d.get("hotel_code") or "")
            code = str(d.get("hotel_code") or "")
            mix_fb = float(d.get("mix_fb") or 0)
            mix_nf = float(d.get("mix_nf") or max(0.0, 1.0 - mix_fb))
            m_fb = float(d.get("margin_fb") or 2.6)
            m_nf = d.get("margin_nf")
            m_nf_f = float(m_nf) if pd.notna(m_nf) else None
            pond = float(d.get("margin_ponderee") or 0)
            pilots_mix.append(
                {
                    "label": lab,
                    "hotel_code": code,
                    "mix_fb": round(mix_fb, 4),
                    "mix_nf": round(mix_nf, 4),
                    "margin_fb": m_fb,
                    "margin_nf": m_nf_f,
                    "margin_ponderee": round(pond, 4),
                    "margin_affichee": round(pond, 4),
                }
            )
            ca_fb = float(d.get("ca_ht_fb_mensuel") or 0)
            ca_nf = float(d.get("ca_ht_nf_mensuel") or 0)
            ca_ttc_fb = float(d.get("ca_ttc_fb_mensuel") or 0)
            ca_ttc_nf = float(d.get("ca_ttc_nf_mensuel") or 0)
            to = d.get("taux_occupation")
            pilots_imp.append(
                {
                    "label": lab,
                    "hotel_code": code,
                    "to": float(to) if pd.notna(to) else None,
                    "ca_ht_fb": round(ca_fb, 2),
                    "ca_ht_nf": round(ca_nf, 2),
                    "ca_ht_total": round(ca_fb + ca_nf, 2),
                    "ca_ttc_fb": round(ca_ttc_fb, 2),
                    "ca_ttc_nf": round(ca_ttc_nf, 2),
                    "ca_ttc_total": round(ca_ttc_fb + ca_ttc_nf, 2),
                }
            )

        mix_products[sol] = {
            "pilots": pilots_mix,
            "moyenne": {
                "mix_fb": float(moy_row["mix_fb"]) if moy_row is not None else None,
                "mix_nf": float(moy_row["mix_nf"]) if moy_row is not None else None,
                "margin_fb": float(moy_row["margin_fb"]) if moy_row is not None else None,
                "margin_nf": float(moy_row["margin_nf"]) if moy_row is not None else None,
                "margin_ponderee": float(moy_row["margin_ponderee"])
                if moy_row is not None
                else None,
            }
            if moy_row is not None
            else {},
        }
        impact_to[sol] = {
            "pilots": pilots_imp,
            "moyenne": {
                "to": float(moy_row["taux_occupation"])
                if moy_row is not None and pd.notna(moy_row.get("taux_occupation"))
                else None,
                "ca_ht_fb": float(moy_row["ca_ht_fb_mensuel"])
                if moy_row is not None
                else None,
                "ca_ht_nf": float(moy_row["ca_ht_nf_mensuel"])
                if moy_row is not None
                else None,
                "ca_ht_total": float(moy_row["ca_ht_total_mensuel"])
                if moy_row is not None
                else None,
                "ca_ttc_fb": float(moy_row["ca_ttc_fb_mensuel"])
                if moy_row is not None
                else None,
                "ca_ttc_nf": float(moy_row["ca_ttc_nf_mensuel"])
                if moy_row is not None
                else None,
                "ca_ttc_total": float(moy_row["ca_ttc_total_mensuel"])
                if moy_row is not None
                else None,
            }
            if moy_row is not None
            else {},
            "impact_1pct": {
                "ca_ht_fb": None,
                "ca_ht_nf": None,
                "ca_ht_total": float(moy_row["ca_ht_par_1pct_to"])
                if moy_row is not None and pd.notna(moy_row.get("ca_ht_par_1pct_to"))
                else None,
                "ca_ttc_fb": None,
                "ca_ttc_nf": None,
                "ca_ttc_total": None,
            }
            if moy_row is not None
            else {},
        }

    return {
        "_source": "simulateur_data.xlsx (rebuild ventes live)",
        "_note": (
            "Tous les hôtels pilotes de chaque solution, moyenne train "
            "à poids égaux par hôtel (règle multi-pilotes)."
        ),
        "mix_products": mix_products,
        "impact_to": impact_to,
    }


def rebuild_simulateur_data() -> dict[str, Any]:
    """
    Recalcule et écrit ``data/simulateur_data.xlsx``.

    Synchronise aussi les flags solution 0/1 sur ``hotel_data``
    (``hotel_solution_simply|liberty|connected``) pour all_data / model_data.

    Returns
    -------
    dict ok, path, rows, columns, n_hotels, years, solutions…
    """
    # Flags hotel_data (pilotes = 1, reste = 0) — même mapping que simulateur
    hotel_flags: dict[str, Any] = {}
    try:
        from archive.accor_1_0_5.src.accor.hotel_solutions import sync_hotel_data_solution_flags

        hotel_flags = sync_hotel_data_solution_flags()
    except Exception as exc:
        hotel_flags = {"ok": False, "error": str(exc)}

    mapping = _load_pilot_map()
    pilots = _code_to_solution(mapping)
    if not pilots:
        raise ValueError(
            "Aucun pilote dans rod_pilot_concepts.json (SIMPLY / LIBERTY / CONNECTED)."
        )

    lines = _load_prepared_lines()
    monthly = _monthly_by_hotel(lines, pilots)
    if monthly.empty:
        raise ValueError(
            "Aucune vente pour les hôtels pilotes solution "
            f"({', '.join(pilots.keys())}). Vérifiez le matching boutique → hotel_code."
        )

    margins = _margins_from_ref()
    op = _hotel_operating()
    annual = _annual_from_monthly(monthly, margins, op)

    years = sorted(int(y) for y in annual["annee"].unique())
    # Période de modélisation = toutes sauf max année (hold-out type 2026)
    eval_year = max(years) if years else None
    train_years = [y for y in years if eval_year is None or y < eval_year]
    # 1) moyenne par hôtel (années de modélisation)
    # 2) moyenne solution poids égaux
    per_hotel = _per_hotel_train_means(annual, train_years=train_years or None)
    moyennes = _solution_averages(annual, train_years=train_years or None)
    annex = build_live_excel_annex_sheets(per_hotel, moyennes)

    # Feuille mensuelle enrichie solution
    mensuel = monthly.copy()
    mensuel = mensuel.sort_values(
        ["solution", "hotel_code", "annee", "mois"]
    ).reset_index(drop=True)
    # arrondi
    for c in mensuel.select_dtypes(include="number").columns:
        if c in ("annee", "mois"):
            continue
        mensuel[c] = pd.to_numeric(mensuel[c], errors="coerce").round(2)

    # Vérif mapping : tous les pilotes déclarés doivent apparaître
    missing_pilots: list[str] = []
    for sol, items in mapping.items():
        present = set(
            annual.loc[annual["solution"] == sol, "hotel_code"].astype(str).unique()
        )
        for it in items:
            code = it["hotel_code"]
            if code not in present:
                missing_pilots.append(f"{sol}:{code}")

    meta = pd.DataFrame(
        [
            {"key": "built_at", "value": datetime.now(timezone.utc).isoformat()},
            {"key": "source", "value": "hotel_sales_raw_data.xlsx"},
            {"key": "pilot_map", "value": "rod_pilot_concepts.json"},
            {
                "key": "aggregation_rule",
                "value": "equal_weight_per_hotel (mean years modélisation then mean hotels)",
            },
            {
                "key": "mix_definition",
                "value": "mix_fb/nf = nb_ventes(canal) / nb_ventes(total) — somme ≈ 100%",
            },
            {"key": "n_raw_lines_prepared", "value": str(len(lines))},
            {"key": "n_monthly_rows", "value": str(len(mensuel))},
            {"key": "n_annual_rows", "value": str(len(annual))},
            {
                "key": "n_per_hotel_rows",
                "value": str(len(per_hotel) if per_hotel is not None else 0),
            },
            {"key": "years", "value": ",".join(str(y) for y in years)},
            {"key": "train_years", "value": ",".join(str(y) for y in train_years)},
            {"key": "eval_year", "value": str(eval_year or "")},
            {
                "key": "pilot_codes",
                "value": ",".join(sorted(pilots.keys())),
            },
            {
                "key": "solutions",
                "value": ",".join(
                    f"{s}:{len(mapping.get(s) or [])}" for s in CONCEPTS
                ),
            },
            {
                "key": "missing_pilots",
                "value": ",".join(missing_pilots) if missing_pilots else "",
            },
        ]
    )

    path = simulateur_data_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet_pilotes = "pilotes_train"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        annual.to_excel(writer, index=False, sheet_name=SHEET_MAIN)
        mensuel.to_excel(writer, index=False, sheet_name=SHEET_MENSUEL)
        if per_hotel is not None and not per_hotel.empty:
            per_hotel.to_excel(writer, index=False, sheet_name=sheet_pilotes)
        moyennes.to_excel(writer, index=False, sheet_name=SHEET_MOYENNES)
        meta.to_excel(writer, index=False, sheet_name=SHEET_META)

    # Annexes live pour le simulateur Excel (tous les pilotes par solution)
    annex_path = DATA_DIR / "rod_excel_sheets_live.json"
    try:
        import json

        annex_path.write_text(
            json.dumps(annex, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        annex_path = None

    return {
        "ok": True,
        "path": str(path),
        "filename": FILENAME,
        "rows": len(annual),
        "columns": list(annual.columns),
        "n_columns": len(annual.columns),
        "n_hotels": int(annual["hotel_code"].nunique()) if len(annual) else 0,
        "n_monthly_rows": len(mensuel),
        "n_per_hotel": int(len(per_hotel)) if per_hotel is not None else 0,
        "years": years,
        "train_years": train_years,
        "eval_year": eval_year,
        "aggregation": "equal_weight_per_hotel",
        "missing_pilots": missing_pilots,
        "annex_path": str(annex_path) if annex_path else None,
        "solutions": {
            s: int(annual.loc[annual["solution"] == s, "hotel_code"].nunique())
            if len(annual)
            else 0
            for s in CONCEPTS
        },
        "hotel_solution_flags": hotel_flags,
        "sheets": [
            SHEET_MAIN,
            SHEET_MENSUEL,
            sheet_pilotes,
            SHEET_MOYENNES,
            SHEET_META,
        ],
    }


def ensure_simulateur_data() -> Path:
    path = simulateur_data_path()
    if not path.exists():
        rebuild_simulateur_data()
    return path


def load_simulateur_data() -> pd.DataFrame:
    path = simulateur_data_path()
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_excel(path, sheet_name=SHEET_MAIN)
    except Exception:
        return pd.read_excel(path, sheet_name=0)


def load_moyennes_solution() -> pd.DataFrame:
    """Feuille moyennes multi-pilotes (années train)."""
    path = simulateur_data_path()
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_excel(path, sheet_name=SHEET_MOYENNES)
    except Exception:
        return pd.DataFrame()


def load_solution_baselines(
    *,
    train_years: list[int] | None = None,
) -> dict[str, dict[str, Any]]:
    """
    Baselines pilote par solution pour le simulateur Excel.

    Priorité :
      1. feuille ``moyennes_solution`` (poids égaux par hôtel)
      2. recalcul equal-weight depuis feuille annuelle
      3. {} si fichier absent
    """
    path = simulateur_data_path()
    if not path.exists():
        return {}

    def _row_to_baseline(row: pd.Series | dict, *, src: str) -> dict[str, Any]:
        def g(key, default=None):
            if isinstance(row, dict):
                return row.get(key, default)
            return row.get(key, default) if key in row.index else default

        mix_fb = float(g("mix_fb") or 0)
        if mix_fb > 1.0:
            mix_fb /= 100.0
        mix_nf_raw = g("mix_nf")
        mix_nf = float(mix_nf_raw) if mix_nf_raw is not None and pd.notna(mix_nf_raw) else (1.0 - mix_fb)
        if mix_nf > 1.0:
            mix_nf /= 100.0
        ca_fb = float(g("ca_ht_fb_mensuel") or 0)
        ca_nf = float(g("ca_ht_nf_mensuel") or 0)
        # mix depuis CA si cohérent
        if ca_fb + ca_nf > 0:
            mix_fb = ca_fb / (ca_fb + ca_nf)
            mix_nf = ca_nf / (ca_fb + ca_nf)
        to = g("taux_occupation")
        to_f = float(to) if to is not None and pd.notna(to) else None
        if to_f is not None and to_f > 1.5:
            to_f /= 100.0
        n = g("nb_chambres")
        n_f = float(n) if n is not None and pd.notna(n) else None
        cm = g("clients_mois_estimes")
        cm_f = float(cm) if cm is not None and pd.notna(cm) else None
        impact = g("ca_ht_par_1pct_to")
        impact_f = float(impact) if impact is not None and pd.notna(impact) else None
        n_pil = g("n_pilotes")
        return {
            "ca_fb": ca_fb,
            "ca_nf": ca_nf,
            "ca_ht": ca_fb + ca_nf,
            "nb_ventes": float(g("nb_ventes_mensuel") or 0),
            "mix_fb": mix_fb,
            "mix_nf": mix_nf,
            "margin_fb": float(g("margin_fb") or 2.6),
            "margin_nf": float(g("margin_nf") or 1.45),
            "nb_chambres": n_f,
            "taux_occupation": to_f,
            "clients_mois": cm_f,
            "ca_ht_par_1pct_to": impact_f,
            "n_pilotes": int(n_pil) if n_pil is not None and pd.notna(n_pil) else None,
            "source": src,
            "pilotes": str(g("pilotes") or ""),
            "annees": str(g("annees") or ""),
            "aggregation": str(g("aggregation") or "mean_equal_weight_per_hotel"),
        }

    out: dict[str, dict[str, Any]] = {}

    # 1) moyennes_solution (déjà equal-weight si rebuild récent)
    moy = load_moyennes_solution()
    if moy is not None and not moy.empty and "solution" in moy.columns:
        for _, row in moy.iterrows():
            sol = str(row.get("solution") or "").upper()
            if sol in CONCEPTS:
                out[sol] = _row_to_baseline(row, src="simulateur_data.moyennes_solution")

    # 2) recalcul equal-weight si manquant ou fichier ancien
    annual = load_simulateur_data()
    if annual is not None and not annual.empty and "solution" in annual.columns:
        recomputed = _solution_averages(annual, train_years=train_years)
        if recomputed is not None and not recomputed.empty:
            for _, row in recomputed.iterrows():
                sol = str(row.get("solution") or "").upper()
                if sol not in CONCEPTS:
                    continue
                # Préférer recalcul si n_pilotes plus complet ou agrégation correcte
                prev = out.get(sol)
                nb = int(row.get("n_pilotes") or 0)
                if (
                    prev is None
                    or (prev.get("n_pilotes") or 0) < nb
                    or prev.get("aggregation") != "mean_equal_weight_per_hotel"
                ):
                    out[sol] = _row_to_baseline(
                        row, src="simulateur_data.equal_weight_per_hotel"
                    )

    return out


def solution_baseline_as_pilot_overrides(
    baseline: dict[str, Any] | None,
) -> dict[str, float]:
    """Convertit une baseline en dict pilot_overrides pour RevenueRules / UI."""
    if not baseline:
        return {}
    keys = (
        "ca_fb",
        "ca_nf",
        "nb_ventes",
        "mix_fb",
        "mix_nf",
        "margin_fb",
        "margin_nf",
        "nb_chambres",
        "taux_occupation",
    )
    out: dict[str, float] = {}
    for k in keys:
        v = baseline.get(k)
        if v is None or (isinstance(v, float) and pd.isna(v)):
            continue
        try:
            out[k] = float(v)
        except (TypeError, ValueError):
            continue
    return out
