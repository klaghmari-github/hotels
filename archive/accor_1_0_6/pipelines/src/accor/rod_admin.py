"""
Simulateur ROD — côté **admin** (pilotes + éval temporelle).

Rôles des apps
--------------
* ``run_user``  : simuler **n'importe quel** hôtel (souvent sans ventes).
* ``run_admin`` : valider les règles sur les hôtels **pilotes** (ventes connues).

Split = **temporel**, pas par hôtel
-----------------------------------
* **Apprentissage / référence** : années **hors 2026** (ex. 2023–2025).
  Tous les hôtels avec ventes sur ces années entrent dans les moyennes
  de catégorie — **aucune exclusion d'hôtel**.
* **Évaluation** : année **2026** (ex. mois partiels). On estime 2026
  avec la ref train, puis on compare au réel 2026 (Σ/12).

On a peu d'hôtels en apprentissage : c'est normal ; le hold-out est
l'année, pas un sous-ensemble d'hôtels.

API admin : /api/rod/*
UI admin  : static/js/admin/rod-sim-panel.js
Doc       : docs/ROD_ADMIN.md
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import numpy as np
import pandas as pd

from archive.accor_1_0_6.pipelines.src.accor.brand_category import (
    brand_to_category_map,
    category_from_dummies,
    normalize_brand_name,
)
from archive.accor_1_0_6.pipelines.src.accor.data_io import DATA_DIR, read_excel
from archive.accor_1_0_6.pipelines.src.accor.user.models import SimulationRequest
from archive.accor_1_0_6.pipelines.src.accor.user.reference import RodReference
from archive.accor_1_0_6.pipelines.src.accor.user.rules.coeffs import RULE3_BASELINE_FB, RULE3_BASELINE_NF
from archive.accor_1_0_6.pipelines.src.accor.user.rules.costs import CostRules
from archive.accor_1_0_6.pipelines.src.accor.user.rules.recommendation import RecommendationRules
from archive.accor_1_0_6.pipelines.src.accor.user.rules.revenue import RevenueRules
from archive.accor_1_0_6.pipelines.src.accor.user.services.hotel_context import HotelContextBuilder
from archive.accor_1_0_6.pipelines.src.accor.user.services.orchestrator import SimulationOrchestrator

CONCEPTS = ("SIMPLY", "LIBERTY", "CONNECTED")
DIVISOR_MONTHS = 12.0
JOURS_MOIS = 30.5


def _round(x: Any, nd: int = 2) -> float | None:
    try:
        v = float(x)
        if v != v:
            return None
        return round(v, nd)
    except (TypeError, ValueError):
        return None


def _load_sales() -> pd.DataFrame:
    path = DATA_DIR / "hotel_sales_data.xlsx"
    sales = read_excel(path, sheet="hotel_sales")
    if sales.empty:
        sales = read_excel(path, sheet=0)
    if sales.empty:
        return sales
    out = sales.copy()
    out["hotel_code"] = out["hotel_code"].astype(str).str.strip()
    out["annee"] = pd.to_numeric(out.get("annee"), errors="coerce")
    out["mois"] = pd.to_numeric(out.get("mois"), errors="coerce")
    out["montant_ventes"] = pd.to_numeric(out.get("montant_ventes"), errors="coerce")
    if "nombre_ventes" in out.columns:
        out["nombre_ventes"] = pd.to_numeric(out["nombre_ventes"], errors="coerce")
    return out


def _load_hotels() -> pd.DataFrame:
    path = DATA_DIR / "hotel_data.xlsx"
    hd = read_excel(path, sheet=0)
    if hd.empty:
        return hd
    out = hd.copy()
    out["hotel_code"] = out["hotel_code"].astype(str).str.strip()
    return out


def _hotel_category(row: pd.Series | dict[str, Any], brand: str | None = None) -> str | None:
    cat = category_from_dummies(row)
    if cat:
        return cat
    bmap = brand_to_category_map()
    b = normalize_brand_name(brand or (row.get("hotel_brand") if hasattr(row, "get") else ""))
    return bmap.get(b)


def _years_split(sales: pd.DataFrame) -> tuple[int | None, list[int]]:
    """Retourne (eval_year, train_years). eval = max année dispo."""
    years = sorted(int(y) for y in sales["annee"].dropna().unique())
    if not years:
        return None, []
    eval_year = years[-1]
    train_years = [y for y in years if y < eval_year]
    return eval_year, train_years


def yearly_monthly_avg(frame: pd.DataFrame, value_col: str = "montant_ventes") -> float | None:
    """
    Pour un sous-ensemble hôtel×année (plusieurs mois) :
    moyenne mensuelle métier = somme(valeurs mois) / 12.
    """
    if frame is None or frame.empty or value_col not in frame.columns:
        return None
    s = float(pd.to_numeric(frame[value_col], errors="coerce").fillna(0).sum())
    return s / DIVISOR_MONTHS


def hotel_reference_over_years(
    sales: pd.DataFrame,
    hotel_code: str,
    train_years: list[int],
    value_col: str = "montant_ventes",
) -> dict[str, Any]:
    """
    Pour un hôtel : avg mensuelle par année train, puis moyenne de ces moyennes.
    """
    code = str(hotel_code).strip()
    sub = sales[(sales["hotel_code"] == code) & (sales["annee"].isin(train_years))]
    by_year: dict[int, float] = {}
    for y, g in sub.groupby("annee"):
        avg = yearly_monthly_avg(g, value_col)
        if avg is not None:
            by_year[int(y)] = avg
    if not by_year:
        return {
            "hotel_code": code,
            "by_year": {},
            "reference_monthly": None,
            "n_years": 0,
        }
    ref = float(np.mean(list(by_year.values())))
    return {
        "hotel_code": code,
        "by_year": {str(k): _round(v, 4) for k, v in sorted(by_year.items())},
        "reference_monthly": ref,
        "n_years": len(by_year),
    }


@lru_cache(maxsize=4)
def _pilot_hotel_codes_cached(eval_year: int) -> tuple[str, ...]:
    """Codes ayant au moins une vente sur une année < eval_year."""
    sales = _load_sales()
    if sales.empty:
        return ()
    train = sales[sales["annee"] < int(eval_year)]
    return tuple(sorted(train["hotel_code"].dropna().unique().astype(str)))


def build_category_reference(
    category: str,
    *,
    eval_year: int,
    train_years: list[int] | None = None,
) -> dict[str, Any]:
    """
    Référence pilote pour une catégorie de marque (années de modélisation).

    Tous les pilotes de la catégorie avec ventes sur les années train
    (ex. 2023–2025) entrent dans la moyenne — **pas d'exclusion** d'hôtel.
    L'année eval (ex. 2026) n'entre jamais dans la référence.
    """
    sales = _load_sales()
    hotels = _load_hotels()
    if sales.empty:
        return {"ok": False, "error": "Pas de ventes", "category": category}

    if train_years is None:
        _, train_years = _years_split(sales)
    train_years = [int(y) for y in train_years if y < eval_year]

    # Map code → category
    code_cat: dict[str, str] = {}
    if not hotels.empty:
        for _, row in hotels.iterrows():
            code = str(row.get("hotel_code") or "").strip()
            if not code:
                continue
            cat = _hotel_category(row)
            if cat:
                code_cat[code] = cat

    pilot_codes = set(_pilot_hotel_codes_cached(eval_year))
    cat_hotels = [c for c in pilot_codes if code_cat.get(c) == category]

    hotel_refs: list[dict[str, Any]] = []
    ca_list: list[float] = []
    clients_list: list[float] = []
    to_list: list[float] = []
    rooms_list: list[float] = []
    guests_list: list[float] = []

    from archive.accor_1_0_6.pipelines.src.accor.user.services.hotel_context import (
        BRAND_GUESTS_DEFAULT,
        BRAND_TO_DEFAULT,
        _as_rate,
        _as_int,
        _norm_brand,
    )

    for code in cat_hotels:
        href = hotel_reference_over_years(sales, code, train_years)
        if href["reference_monthly"] is None:
            continue
        ca_list.append(float(href["reference_monthly"]))

        row = None
        if not hotels.empty:
            m = hotels[hotels["hotel_code"] == code]
            if not m.empty:
                row = m.iloc[0]

        name = ""
        brand = ""
        n = 0
        to = None
        g = None
        clients_mois = None
        if row is not None:
            name = str(row.get("hotel_name") or "")
            brand = str(row.get("hotel_brand") or "")
            bk = _norm_brand(brand)
            n = _as_int(row.get("hotel_nb_chambres"), 0)
            to = _as_rate(row.get("hotel_to_annuel"), BRAND_TO_DEFAULT.get(bk, 0.70))
            g = BRAND_GUESTS_DEFAULT.get(bk, 1.7)
            if n > 0 and to is not None and g is not None:
                clients_mois = float(n) * float(to) * float(g) * JOURS_MOIS
                rooms_list.append(float(n))
                to_list.append(float(to))
                guests_list.append(float(g))
                clients_list.append(clients_mois)

        # nom depuis ventes train si fiche absente
        if not name and not sales.empty and "nom_hotel" in sales.columns:
            sub_n = sales[
                (sales["hotel_code"] == code) & (sales["annee"].isin(train_years))
            ]
            nn = sub_n["nom_hotel"].dropna()
            if len(nn):
                name = str(nn.iloc[0] or "")

        hotel_refs.append(
            {
                **href,
                "hotel_name": name,
                "hotel_brand": brand,
                "nb_chambres": n or None,
                "taux_occupation": _round(to, 4) if to is not None else None,
                "clients_mois": _round(clients_mois, 1) if clients_mois is not None else None,
                "ca_monthly_ref": _round(float(href["reference_monthly"]), 2),
                "train_years": sorted(int(y) for y in (href.get("by_year") or {}).keys()),
            }
        )

    if not ca_list:
        return {
            "ok": False,
            "error": f"Aucune référence pour la catégorie {category} sur {train_years}",
            "category": category,
            "train_years": train_years,
            "eval_year": eval_year,
            "n_hotels": 0,
        }

    def _mean(xs: list[float]) -> float | None:
        return float(np.mean(xs)) if xs else None

    return {
        "ok": True,
        "category": category,
        "train_years": train_years,
        "eval_year": eval_year,
        "n_hotels": len(ca_list),
        "hotel_codes": [h["hotel_code"] for h in hotel_refs],
        "hotel_refs": hotel_refs,
        "ca_monthly_ref": _mean(ca_list),
        "clients_mois_ref": _mean(clients_list),
        "nb_chambres_ref": _mean(rooms_list),
        "taux_occupation_ref": _mean(to_list),
        "guests_per_chambre_ref": _mean(guests_list),
        "method": (
            f"Pilotes = hôtels avec ventes sur {train_years} (modélisation). "
            f"Catégorie={category} — tous les pilotes de la catégorie, sans exclusion. "
            f"avg_mensuelle(année)=Σ mois/{int(DIVISOR_MONTHS)} ; "
            f"moyenne multi-années puis entre pilotes. "
            f"Année {eval_year} = hold-out (absente de la ref)."
        ),
    }


def list_pilot_hotels(year: int | None = None) -> dict[str, Any]:
    """
    Hôtels pilotes pour l'admin : codes avec ventes sur les années **train**
    (toutes les années < ``eval_year``, ex. 2023–2025).

    Split **temporel** uniquement : la ref catégorie utilise le train ;
    l'évaluation compare à l'année hold-out (ex. 2026) quand le réel
    existe. **Aucun hôtel n'est exclu** de la ref catégorie.
    """
    sales = _load_sales()
    hotels_df = _load_hotels()
    if sales.empty:
        return {"ok": False, "error": "hotel_sales_data indisponible", "hotels": []}

    eval_year, train_years = _years_split(sales)
    if year is not None:
        eval_year = int(year)
        train_years = [
            int(y)
            for y in sorted(sales["annee"].dropna().unique())
            if int(y) < eval_year
        ]

    if eval_year is None:
        return {"ok": False, "error": "Aucune année dans les ventes", "hotels": []}

    if not train_years:
        return {
            "ok": False,
            "error": f"Pas d'années train avant {eval_year}",
            "eval_year": eval_year,
            "hotels": [],
        }

    pilot_codes = list(_pilot_hotel_codes_cached(int(eval_year)))
    if not pilot_codes:
        # fallback si cache vide : codes avec ventes train
        train_sales = sales[sales["annee"].isin(train_years)]
        pilot_codes = sorted(
            train_sales["hotel_code"].dropna().unique().astype(str).tolist()
        )

    # brand/cat map
    info: dict[str, dict[str, Any]] = {}
    if not hotels_df.empty:
        for _, row in hotels_df.iterrows():
            code = str(row.get("hotel_code") or "").strip()
            if not code:
                continue
            info[code] = {
                "hotel_name": str(row.get("hotel_name") or ""),
                "hotel_brand": str(row.get("hotel_brand") or ""),
                "category": _hotel_category(row),
            }

    # réel hold-out optionnel par code
    hold = sales[sales["annee"] == eval_year]
    hold_by: dict[str, pd.DataFrame] = {}
    if not hold.empty:
        for code, g in hold.groupby("hotel_code"):
            hold_by[str(code).strip()] = g

    # noms depuis ventes train si manquants
    train = sales[sales["annee"].isin(train_years)]
    name_from_sales: dict[str, str] = {}
    if not train.empty and "nom_hotel" in train.columns:
        for code, g in train.groupby("hotel_code"):
            n = str(g["nom_hotel"].dropna().iloc[0] or "") if len(g["nom_hotel"].dropna()) else ""
            if n:
                name_from_sales[str(code).strip()] = n

    hotels: list[dict[str, Any]] = []
    for code in pilot_codes:
        code = str(code).strip()
        meta = info.get(code, {})
        name = meta.get("hotel_name") or name_from_sales.get(code) or ""
        g_hold = hold_by.get(code)
        has_holdout = g_hold is not None and not g_hold.empty
        if has_holdout:
            months = sorted(
                int(m)
                for m in g_hold["mois"].dropna().unique().tolist()
                if 1 <= int(m) <= 12
            )
            sum_true = float(g_hold["montant_ventes"].fillna(0).sum())
            avg_true = _round(sum_true / DIVISOR_MONTHS, 2)
            sum_true_r = _round(sum_true, 2)
            if not name and "nom_hotel" in g_hold.columns:
                name = str(g_hold["nom_hotel"].iloc[0] or "") or name
        else:
            months = []
            sum_true_r = None
            avg_true = None

        # années train présentes pour cet hôtel
        train_years_h = sorted(
            int(y)
            for y in train.loc[train["hotel_code"] == code, "annee"]
            .dropna()
            .unique()
            .tolist()
        )
        # CA réel moyen / mois sur période de modélisation (train)
        href = hotel_reference_over_years(sales, code, train_years)
        avg_train = href.get("reference_monthly")
        if avg_train is not None:
            avg_train = _round(avg_train, 2)

        hotels.append(
            {
                "hotel_code": code,
                "hotel_name": name,
                "hotel_brand": meta.get("hotel_brand") or "",
                "category": meta.get("category"),
                "train_years": train_years_h,
                "has_holdout": has_holdout,
                "n_months": len(months) if has_holdout else 0,
                "months": months,
                "sum_montant_ventes": sum_true_r,
                "avg_monthly_true": avg_true,
                "avg_monthly_train": avg_train,
                "reference_monthly": avg_train,
            }
        )
    hotels.sort(key=lambda h: (not h.get("has_holdout"), h["hotel_code"]))

    n_holdout = sum(1 for h in hotels if h.get("has_holdout"))
    return {
        "ok": True,
        "eval_year": eval_year,
        "train_years": train_years,
        "divisor_months": int(DIVISOR_MONTHS),
        "n": len(hotels),
        "n_with_holdout": n_holdout,
        "n_predict_only": len(hotels) - n_holdout,
        "split": "temporal",
        "hotels": hotels,
        "roles": {
            "admin": (
                f"Apprendre sur {train_years} (tous les pilotes, sans exclusion "
                f"d'hôtel) ; évaluer sur {eval_year} (réel Σ/12 quand dispo)."
            ),
            "user": (
                "run_user : simuler n'importe quel hôtel (souvent sans ventes) ; "
                "pas d'évaluation chiffrée tant qu'il n'y a pas de réel."
            ),
            "pilot_definition": (
                "Hôtel pilote = a des ventes sur des années passées ; entre dans "
                "la référence catégorie (années train) et peut être évalué sur "
                "l'année hold-out."
            ),
        },
        "method": (
            f"Split **temporel** (pas par hôtel) : ref catégorie = années "
            f"{train_years} pour **tous** les pilotes de la catégorie ; "
            f"année {eval_year} exclue de la ref. Évaluation = estimer puis "
            f"comparer au réel {eval_year} (Σ/{int(DIVISOR_MONTHS)}). "
            f"n_pilotes={len(hotels)} (peu d'hôtels en apprentissage = normal)."
        ),
    }


def _sales_steps_category_pilot(
    rev: RevenueRules,
    request: SimulationRequest,
    concept: str,
    cat_ref: dict[str, Any],
) -> dict[str, Any]:
    """
    Chaîne revenus ROD en utilisant la référence **catégorie** comme pilote
    (CA mensuel + clients), et les pivots concept pour mix / m_lin / coefs.
    """
    concept = concept.upper()
    if request.store is None:
        raise ValueError("store requis")

    ref = rev._ref
    key = f"concepts.{concept}"
    # Pivots concept (store / mix / m_lin) — structure Excel
    pivot_m_lin = float(ref.get(f"{key}.pivot_m_lin", 6) or 6)
    margin_fb = float(ref.get(f"{key}.margin_fb_pct", 2.6) or 2.6)
    margin_nf = float(ref.get(f"{key}.margin_nf_pct", 1.45) or 1.45)
    ref_mix_fb = float(ref.get(f"{key}.mix_fb", 0.7) or 0.7)
    ref_mix_nf = float(ref.get(f"{key}.mix_nf", 0.3) or 0.3)
    impact_to = float(ref.get("impact_to.ht_per_0_01_to", 9.233974) or 9.233974)

    # Référence catégorie (années train) — remplace le CA/clients pilote concept
    ca_ht_ref = float(cat_ref.get("ca_monthly_ref") or 0.0)
    ca_fb_ref = ca_ht_ref * ref_mix_fb
    ca_nf_ref = ca_ht_ref * ref_mix_nf
    clients_pilote = float(cat_ref.get("clients_mois_ref") or 0.0)
    if clients_pilote <= 0:
        # fallback pivots concept
        pivot_nb = float(ref.get(f"{key}.pivot_nb_chambres", 129) or 129)
        pivot_guests = float(ref.get(f"{key}.pivot_guests_per_chambre", 1.7) or 1.7)
        pivot_to = float(ref.get(f"{key}.pivot_to", 0.75) or 0.75)
        clients_pilote = pivot_nb * pivot_to * pivot_guests * JOURS_MOIS
    pivot_to_cat = float(cat_ref.get("taux_occupation_ref") or ref.get(f"{key}.pivot_to", 0.75) or 0.75)
    pivot_nb_cat = float(cat_ref.get("nb_chambres_ref") or 0)
    pivot_g_cat = float(cat_ref.get("guests_per_chambre_ref") or 1.7)

    store = request.store
    user_mix_fb = float(store.mix_fb)
    user_mix_nf = float(store.mix_nf)
    total_mix = user_mix_fb + user_mix_nf
    if total_mix > 0:
        user_mix_fb /= total_mix
        user_mix_nf /= total_mix
    mix_customized = (
        abs(user_mix_fb - ref_mix_fb) > 0.02 or abs(user_mix_nf - ref_mix_nf) > 0.02
    )
    effective_fb = user_mix_fb if mix_customized else ref_mix_fb
    effective_nf = user_mix_nf if mix_customized else ref_mix_nf

    op = request.operating
    clients_hotel = op.clients_mois
    to_delta = op.taux_occupation - pivot_to_cat

    steps: list[dict[str, Any]] = []

    steps.append(
        {
            "id": "hotel_cible",
            "title": "Hôtel désigné pour simulation",
            "rule": "Caractéristiques de l'hôtel désigné (hotel_data) — pas ses ventes train",
            "formula": "clients_mois = n × TO × guests × 30,5",
            "values": {
                "nb_chambres": op.nb_chambres,
                "taux_occupation": _round(op.taux_occupation, 4),
                "guests_per_chambre": _round(op.guests_per_chambre, 3),
                "clients_jour": _round(op.clients_jour, 2),
                "clients_mois": _round(clients_hotel, 2),
                "m_lin": _round(store.m_lin, 2),
                "mix_fb": _round(user_mix_fb, 4),
            },
            "ca_fb": None,
            "ca_nf": None,
            "ca_ht": None,
        }
    )

    steps.append(
        {
            "id": "category_pilot",
            "title": f"Référence pilote catégorie « {cat_ref.get('category')} »",
            "rule": "Moyennes hôtels pilotes même catégorie, années train uniquement",
            "formula": (
                "avg_mensuelle(année)=Σ mois/12 ; moyenne multi-années par hôtel ; "
                "moyenne entre hôtels de la catégorie"
            ),
            "values": {
                "category": cat_ref.get("category"),
                "train_years": cat_ref.get("train_years"),
                "eval_year_exclue": cat_ref.get("eval_year"),
                "n_hotels_ref": cat_ref.get("n_hotels"),
                "ca_monthly_ref": _round(ca_ht_ref, 2),
                "clients_mois_ref": _round(clients_pilote, 2),
                "nb_chambres_ref": _round(pivot_nb_cat, 1),
                "taux_occupation_ref": _round(pivot_to_cat, 4),
                "guests_ref": _round(pivot_g_cat, 3),
                "ca_fb_ref_via_mix_concept": _round(ca_fb_ref, 2),
                "ca_nf_ref_via_mix_concept": _round(ca_nf_ref, 2),
                "mix_fb_concept": ref_mix_fb,
                "mix_nf_concept": ref_mix_nf,
            },
            "ca_fb": ca_fb_ref,
            "ca_nf": ca_nf_ref,
            "ca_ht": ca_ht_ref,
        }
    )

    ca_fb, ca_nf = RevenueRules.apply_to_impact(
        ca_fb_ref, ca_nf_ref, to_delta, impact_to
    )
    to_impact = (to_delta / 0.01) * impact_to
    steps.append(
        {
            "id": "impact_to",
            "title": "Impact taux d’occupation",
            "rule": "ΔTO (hôtel − TO moyen catégorie) × impact € / point",
            "formula": "impact = (ΔTO / 0,01) × 9,233974 € réparti F&B / N-F&B",
            "values": {
                "to_hotel": _round(op.taux_occupation, 4),
                "to_ref_categorie": _round(pivot_to_cat, 4),
                "to_delta": _round(to_delta, 4),
                "impact_ht": _round(to_impact, 2),
            },
            "ca_fb": ca_fb,
            "ca_nf": ca_nf,
            "ca_ht": ca_fb + ca_nf,
        }
    )

    ca_fb, ca_nf, client_factor = RevenueRules.rule1_clients(
        ca_fb, ca_nf, clients_hotel, clients_pilote
    )
    steps.append(
        {
            "id": "r1_clients",
            "title": "Règle 1 — scaling clients",
            "rule": "CA × (clients hôtel désigné / clients référence catégorie)",
            "formula": "facteur = clients_mois_cible / clients_mois_catégorie",
            "values": {
                "clients_hotel_cible": _round(clients_hotel, 2),
                "clients_categorie": _round(clients_pilote, 2),
                "client_factor": _round(client_factor, 4),
            },
            "ca_fb": ca_fb,
            "ca_nf": ca_nf,
            "ca_ht": ca_fb + ca_nf,
        }
    )

    ca_fb, ca_nf, steps_fb, steps_nf = RevenueRules.rule2_mix(
        ca_fb,
        ca_nf,
        user_mix_fb=effective_fb,
        user_mix_nf=effective_nf,
        ref_mix_fb=ref_mix_fb,
        ref_mix_nf=ref_mix_nf,
        ca_fb_ref=ca_fb_ref,
        ca_nf_ref=ca_nf_ref,
    )
    ca_fb, ca_nf = max(ca_fb, 0.0), max(ca_nf, 0.0)
    steps.append(
        {
            "id": "r2_mix",
            "title": "Règle 2 — mix F&B / N-F&B",
            "rule": "Ajustement vs mix du concept (pas de 10 %)",
            "formula": "steps = (mix_user − mix_concept) × 10",
            "values": {
                "mix_fb_effectif": _round(effective_fb, 4),
                "mix_fb_concept": ref_mix_fb,
                "steps_fb": _round(steps_fb, 3),
                "steps_nf": _round(steps_nf, 3),
            },
            "ca_fb": ca_fb,
            "ca_nf": ca_nf,
            "ca_ht": ca_fb + ca_nf,
        }
    )

    cumul_fb, cumul_nf = RevenueRules.cumul_rule3(request.client_profile.client_needs)
    ca_fb, ca_nf, delta_fb, delta_nf = RevenueRules.rule3_categories(
        ca_fb, ca_nf, cumul_fb, cumul_nf
    )
    ca_fb, ca_nf = max(ca_fb, 0.0), max(ca_nf, 0.0)
    steps.append(
        {
            "id": "r3_categories",
            "title": "Règle 3 — catégories besoins clients",
            "rule": "Δ cumul coefs besoins vs baseline",
            "formula": "CA_canal × (1 + (cumul − baseline))",
            "values": {
                "cumul_fb": _round(cumul_fb, 4),
                "cumul_nf": _round(cumul_nf, 4),
                "baseline_fb": RULE3_BASELINE_FB,
                "baseline_nf": RULE3_BASELINE_NF,
                "delta_fb": _round(delta_fb, 4),
                "delta_nf": _round(delta_nf, 4),
            },
            "ca_fb": ca_fb,
            "ca_nf": ca_nf,
            "ca_ht": ca_fb + ca_nf,
        }
    )

    ca_fb, ca_nf, m_lin_diff = RevenueRules.rule4_m_lin(
        ca_fb,
        ca_nf,
        m_lin=store.m_lin,
        pivot_m_lin=pivot_m_lin,
        ca_fb_ref=ca_fb_ref,
        ca_nf_ref=ca_nf_ref,
    )
    ca_fb, ca_nf = max(ca_fb, 0.0), max(ca_nf, 0.0)
    steps.append(
        {
            "id": "r4_mlin",
            "title": "Règle 4 — mètres linéaires",
            "rule": "Écart m_lin client vs pivot concept",
            "formula": "Δm = m_lin − pivot_m_lin concept",
            "values": {
                "m_lin": _round(store.m_lin, 2),
                "pivot_m_lin": pivot_m_lin,
                "m_lin_diff": _round(m_lin_diff, 2),
            },
            "ca_fb": ca_fb,
            "ca_nf": ca_nf,
            "ca_ht": ca_fb + ca_nf,
        }
    )

    ca_ht = ca_fb + ca_nf
    # ventes : taux acheteur = ventes_ref concept / clients_pilote_concept
    # ici on approxime via CA : garder ratio concept si dispo
    ventes_ref = float(rev._ref.get(f"{key}.base_monthly_sales", 0) or 0)
    # si CA category >> CA concept, scale ventes_ref proportionnellement
    ca_concept = float(rev._ref.get(f"{key}.base_monthly_ca_fb", 0) or 0) + float(
        rev._ref.get(f"{key}.base_monthly_ca_nf", 0) or 0
    )
    if ca_concept > 0 and ca_ht_ref > 0 and ventes_ref > 0:
        ventes_ref_adj = ventes_ref * (ca_ht_ref / ca_concept)
    else:
        ventes_ref_adj = ventes_ref
    taux_acheteur = ventes_ref_adj / clients_pilote if clients_pilote else 0.0
    nbr_ventes = taux_acheteur * clients_hotel
    marge = RevenueRules.marge_produit(ca_fb, ca_nf, margin_fb, margin_nf)
    steps.append(
        {
            "id": "marge_produit",
            "title": "Marge produit",
            "rule": "marge = CA − CA/coef (F&B et N-F&B concept)",
            "formula": f"coefs {margin_fb} / {margin_nf}",
            "values": {
                "ca_ht_mensuel": _round(ca_ht, 2),
                "nbr_ventes_mensuel": _round(nbr_ventes, 2),
                "marge_produit_mensuelle": _round(marge, 2),
            },
            "ca_fb": ca_fb,
            "ca_nf": ca_nf,
            "ca_ht": ca_ht,
        }
    )

    for s in steps:
        if s.get("ca_fb") is not None:
            s["ca_fb"] = _round(s["ca_fb"], 2)
        if s.get("ca_nf") is not None:
            s["ca_nf"] = _round(s["ca_nf"], 2)
        if s.get("ca_ht") is not None:
            s["ca_ht"] = _round(s["ca_ht"], 2)

    return {
        "concept": concept,
        "ca_ht_mensuel": _round(ca_ht, 2),
        "ca_fb_mensuel": _round(ca_fb, 2),
        "ca_nf_mensuel": _round(ca_nf, 2),
        "nbr_ventes_mensuel": _round(nbr_ventes, 2),
        "marge_produit_mensuelle": _round(marge, 2),
        "steps": steps,
    }


def all_needs_open() -> dict[str, bool]:
    """Défaut directeur : aucune sous-catégorie filtrée (toutes autorisées)."""
    from archive.accor_1_0_6.pipelines.src.accor.user.rules.coeffs import RULE3_FB_COEFFS, RULE3_NFB_COEFFS

    return {**{k: True for k in RULE3_FB_COEFFS}, **{k: True for k in RULE3_NFB_COEFFS}}


def rod_ui_meta() -> dict[str, Any]:
    """Labels et défauts pour l'UI simulateur (mix, m_lin, sous-catégories)."""
    from archive.accor_1_0_6.pipelines.src.accor.user.rules.coeffs import (
        CLIENT_NEED_LABELS,
        RULE3_FB_COEFFS,
        RULE3_NFB_COEFFS,
    )

    return {
        "ok": True,
        "client_needs_fb": [
            {
                "id": k,
                "label": CLIENT_NEED_LABELS.get(k, k),
                "coef": v,
                "default": True,
            }
            for k, v in RULE3_FB_COEFFS.items()
        ],
        "client_needs_nfb": [
            {
                "id": k,
                "label": CLIENT_NEED_LABELS.get(k, k),
                "coef": v,
                "default": True,
            }
            for k, v in RULE3_NFB_COEFFS.items()
        ],
        "defaults": {
            "mix_fb": 0.70,
            "m_lin": 6.0,
            "client_needs": all_needs_open(),
        },
    }


def simulate_hotel_trace(
    hotel_code: str,
    *,
    year: int | None = None,
    m_lin: float | None = None,
    mix_fb: float | None = None,
    client_needs: dict[str, bool] | None = None,
    nb_chambres: float | None = None,
    taux_occupation: float | None = None,
    guests_per_chambre: float | None = None,
    fetch_if_missing: bool = False,
    include_gaps: bool = True,
) -> dict[str, Any]:
    """
    Simule un **hôtel cible** (estimation corner) :

    * référence CA / clients = catégorie de marque (années train) ;
    * paramètres corner éditables : m_lin, mix_fb, sous-catégories (besoins) ;
    * règles ROD → CA, coûts, marge pour les 3 concepts + reco.

    Défauts corner : m_lin hôtel ou 6, mix_fb 70 %, toutes sous-catégories ON.

    ``fetch_if_missing`` : scrape Accor si fiche absente (parcours user).
    ``include_gaps`` : écart vs réel hold-out (admin) ; False côté directeur.
    """
    code = str(hotel_code or "").strip()
    if not code:
        return {"ok": False, "error": "hotel_code requis"}

    sales = _load_sales()
    if sales.empty:
        return {"ok": False, "error": "Pas de ventes"}

    eval_year, train_years = _years_split(sales)
    if year is not None:
        eval_year = int(year)
        train_years = [
            int(y) for y in sorted(sales["annee"].dropna().unique()) if int(y) < eval_year
        ]
    if eval_year is None:
        return {"ok": False, "error": "Aucune année"}

    # Contexte hôtel (identité / exploitation) — sans se baser sur ses ventes train
    builder = HotelContextBuilder()
    try:
        ctx = builder.build(code, fetch_if_missing=bool(fetch_if_missing))
    except Exception as exc:
        return {"ok": False, "error": f"Contexte : {exc}", "hotel_code": code}

    brand = (ctx.identity or {}).get("hotel_brand") or ""
    # catégorie
    hotels = _load_hotels()
    category = None
    if not hotels.empty:
        m = hotels[hotels["hotel_code"] == code]
        if not m.empty:
            category = _hotel_category(m.iloc[0], brand)
    if not category:
        category = brand_to_category_map().get(normalize_brand_name(brand))

    if not category:
        return {
            "ok": False,
            "error": f"Catégorie de marque introuvable pour {code} ({brand})",
            "hotel_code": code,
            "hotel_brand": brand,
        }

    cat_ref = build_category_reference(
        category,
        eval_year=eval_year,
        train_years=train_years,
    )
    if not cat_ref.get("ok"):
        return {
            "ok": False,
            "error": cat_ref.get("error") or "Référence catégorie vide",
            "hotel_code": code,
            "category": category,
            "train_years": train_years,
            "eval_year": eval_year,
        }

    orch = SimulationOrchestrator(auto_enrich=False)
    req = SimulationRequest.from_dict(ctx.to_simulation_payload())
    req, prep = orch.prepare_request(req, hydrate_from_admin=True)

    # --- Paramètres corner du directeur (surcharges) ---
    # m_lin : défaut corner hôtel sinon 6
    default_m = req.corner.m_lin
    if default_m is None or float(default_m) <= 0:
        default_m = 6.0
    use_m = float(m_lin) if m_lin is not None and m_lin != "" else float(default_m)
    if use_m <= 0:
        use_m = 6.0
    req.corner.m_lin = use_m
    req.corner.has_corner = True

    # mix F&B : défaut 70 % si non fourni (allocation corner)
    if mix_fb is not None and mix_fb != "":
        mf = float(mix_fb)
        if mf > 1.0:
            mf = mf / 100.0
        mf = min(max(mf, 0.0), 1.0)
    else:
        mf = 0.70
    req.corner.mix_fb = mf

    # sous-catégories : défaut toutes autorisées
    needs = all_needs_open()
    if client_needs and isinstance(client_needs, dict):
        for k, v in client_needs.items():
            needs[str(k)] = bool(v)
    req.client_profile.client_needs = needs

    # exploitation optionnelle (sinon hotel_data)
    if nb_chambres is not None and float(nb_chambres) > 0:
        req.operating.nb_chambres = int(float(nb_chambres))
    if taux_occupation is not None and taux_occupation != "":
        to = float(taux_occupation)
        if to > 1.0:
            to /= 100.0
        req.operating.taux_occupation = min(max(to, 0.0), 1.0)
    if guests_per_chambre is not None and float(guests_per_chambre) > 0:
        req.operating.guests_per_chambre = float(guests_per_chambre)

    params_used = {
        "m_lin": use_m,
        "mix_fb": mf,
        "mix_nf": 1.0 - mf,
        "client_needs": dict(needs),
        "nb_chambres": req.operating.nb_chambres,
        "taux_occupation": req.operating.taux_occupation,
        "guests_per_chambre": req.operating.guests_per_chambre,
        "clients_mois": req.operating.clients_mois,
    }

    rev = RevenueRules(orch.reference)
    costs = CostRules(orch.reference)
    reco = RecommendationRules()

    by_concept: dict[str, Any] = {}
    sims_for_reco: dict[str, Any] = {}

    for c in CONCEPTS:
        req_c = orch.request_for_concept(req, c)
        try:
            sales_trace = _sales_steps_category_pilot(rev, req_c, c, cat_ref)
            cost = costs.compute(req_c, c)
            marge_prod = float(sales_trace["marge_produit_mensuelle"] or 0)
            cout_m = float(cost.monthly_cost or 0)
            marge_nette = marge_prod - cout_m
            from archive.accor_1_0_6.pipelines.src.accor.user.models import ConceptSimulation

            sim = ConceptSimulation(
                source="ROD_CATEGORY_PILOT",
                concept=c,
                store=req_c.store.to_dict() if req_c.store else {},
                ca_mensuel=float(sales_trace["ca_ht_mensuel"] or 0),
                ca_annuel=float(sales_trace["ca_ht_mensuel"] or 0) * 12,
                ventes_mensuel=float(sales_trace["nbr_ventes_mensuel"] or 0),
                ventes_annuel=float(sales_trace["nbr_ventes_mensuel"] or 0) * 12,
                marge_produit_mensuelle=marge_prod,
                marge_produit_annuelle=marge_prod * 12,
                cout_mensuel=cout_m,
                cout_annuel=cout_m * 12,
                marge_nette_mensuelle=marge_nette,
                marge_nette_annuelle=marge_nette * 12,
                capex=float(cost.capex or 0),
                roi_months=(
                    float(cost.capex) / (marge_nette / 12)
                    if marge_nette > 0 and cost.capex
                    else None
                ),
            )
            sims_for_reco[c] = sim
            by_concept[c] = {
                "ok": True,
                "sales": sales_trace,
                "costs": {
                    "monthly_cost": _round(cout_m, 2),
                    "annual_cost": _round(cost.annual_cost, 2),
                    "capex": _round(cost.capex, 2),
                    "techno_monthly": _round(cost.techno_monthly, 2),
                    "annexes_monthly": _round(cost.annexes_monthly, 2),
                    "agencement_monthly": _round(cost.agencement_monthly, 2),
                    "cost_lines": cost.cost_lines,
                    "warnings": cost.warnings,
                },
                "margin": {
                    "marge_produit_mensuelle": _round(marge_prod, 2),
                    "marge_produit_annuelle": _round(marge_prod * 12, 2),
                    "cout_mensuel": _round(cout_m, 2),
                    "cout_annuel": _round(cout_m * 12, 2),
                    "marge_nette_mensuelle": _round(marge_nette, 2),
                    "marge_nette_annuelle": _round(marge_nette * 12, 2),
                    "formula": "marge_nette = marge_produit − coûts_mensuels",
                },
                "store": req_c.store.to_dict() if req_c.store else {},
            }
        except Exception as exc:
            import traceback

            by_concept[c] = {
                "ok": False,
                "error": str(exc),
                "traceback": traceback.format_exc()[-500:],
            }

    allowed, reco_warnings = reco.allowed_concepts(req)
    if sims_for_reco:
        recommended, best_margin, reason = reco.recommend(sims_for_reco, allowed)
    else:
        recommended, best_margin, reason = "SIMPLY", "SIMPLY", "Aucun concept simulé."

    # Réel hold-out / écarts — réservé à l'admin (include_gaps=True)
    gaps: dict[str, Any] = {}
    has_holdout = False
    months: list[int] = []
    sum_true = None
    avg_true = None
    if include_gaps:
        hold = sales[(sales["hotel_code"] == code) & (sales["annee"] == eval_year)]
        has_holdout = not hold.empty
        if has_holdout:
            sum_true = float(hold["montant_ventes"].fillna(0).sum())
            months = sorted(int(m) for m in hold["mois"].dropna().unique().tolist())
            avg_true = sum_true / DIVISOR_MONTHS
        for c, block in by_concept.items():
            if not block.get("sales"):
                continue
            ca = float(block["sales"].get("ca_ht_mensuel") or 0)
            if has_holdout and avg_true is not None:
                gap = ca - avg_true
                pct = (100.0 * gap / avg_true) if abs(avg_true) > 1e-9 else None
                gaps[c] = {
                    "ca_sim_mensuel": _round(ca, 2),
                    "avg_monthly_true": _round(avg_true, 2),
                    "gap": _round(gap, 2),
                    "gap_pct": _round(pct, 1) if pct is not None else None,
                    "has_holdout": True,
                }
            else:
                gaps[c] = {
                    "ca_sim_mensuel": _round(ca, 2),
                    "avg_monthly_true": None,
                    "gap": None,
                    "gap_pct": None,
                    "has_holdout": False,
                }

    method = (
        f"Ref catégorie {category} sur {train_years} "
        f"(année {eval_year} exclue — split temporel, pas d'exclusion d'hôtel). "
        f"Hôtel désigné pour simulation {code}. Règles ROD → CA / coûts / marge + reco."
    )
    if include_gaps and has_holdout:
        method += f" Éval admin : écart vs réel {eval_year} (Σ/12)."

    out: dict[str, Any] = {
        "ok": True,
        "hotel_code": code,
        "hotel_brand": brand,
        "hotel_name": (ctx.identity or {}).get("hotel_name") or "",
        "category": category,
        "eval_year": eval_year,
        "train_years": train_years,
        "divisor_months": int(DIVISOR_MONTHS),
        "as_target_hotel": True,
        "params": params_used,
        "category_reference": {
            k: v
            for k, v in cat_ref.items()
            if k != "hotel_refs"
        },
        # Pilotes même catégorie (années de modélisation) — toujours exposés
        "category_pilots": cat_ref.get("hotel_refs") or [],
        "identity": req.identity.to_dict(),
        "operating": req.operating.to_dict(),
        "client_needs": dict(req.client_profile.client_needs or {}),
        "prep_warnings": list(prep.get("warnings") or []) + list(ctx.warnings or []),
        "by_concept": by_concept,
        "recommendation": {
            "recommended_concept": recommended,
            "best_margin_concept": best_margin,
            "allowed_concepts": allowed,
            "reason": reason,
            "warnings": reco_warnings,
        },
        "method": method,
        "scraped": bool((ctx.sources or {}).get("scrape")),
    }
    if include_gaps:
        out["has_holdout"] = has_holdout
        # alias rétrocompat
        out["category_reference_hotels"] = out["category_pilots"]
        out["real_holdout"] = {
            "year": eval_year,
            "available": has_holdout,
            "months": months,
            "n_months": len(months),
            "sum_montant_ventes": _round(sum_true, 2) if sum_true is not None else None,
            "avg_monthly_true": _round(avg_true, 2) if avg_true is not None else None,
            "formula": f"avg_monthly_true = somme(mois {eval_year}) / {int(DIVISOR_MONTHS)}",
        }
        out["gaps"] = gaps
    return out


def _concept_economics(tr: dict[str, Any], concept: str) -> dict[str, Any]:
    """CA / coûts / marges pour une solution dans une trace simulateur."""
    block = (tr.get("by_concept") or {}).get(concept) or {}
    sales = block.get("sales") or {}
    costs = block.get("costs") or {}
    margin = block.get("margin") or {}
    ca = sales.get("ca_ht_mensuel")
    cout = margin.get("cout_mensuel")
    if cout is None:
        cout = costs.get("monthly_cost")
    marge_prod = margin.get("marge_produit_mensuelle")
    marge_nette = margin.get("marge_nette_mensuelle")
    if (
        marge_nette is None
        and marge_prod is not None
        and cout is not None
    ):
        try:
            marge_nette = float(marge_prod) - float(cout)
        except (TypeError, ValueError):
            marge_nette = None
    return {
        "ca_sim_mensuel": _round(ca, 2) if ca is not None else None,
        "cout_mensuel": _round(cout, 2) if cout is not None else None,
        "marge_produit_mensuelle": _round(marge_prod, 2)
        if marge_prod is not None
        else None,
        "marge_nette_mensuelle": _round(marge_nette, 2)
        if marge_nette is not None
        else None,
        "capex": _round(costs.get("capex"), 2)
        if costs.get("capex") is not None
        else None,
    }


def evaluate_pilots_year(year: int | None = None) -> dict[str, Any]:
    """
    Batch d'évaluation **temporelle** : ref = années train, vérité = hold-out
    (ex. 2026). Tous les pilotes (peu nombreux) ; pas d'exclusion d'hôtel
    dans la ref. Métriques d'écart si réel hold-out présent.

    Pour chaque pilote, expose aussi **coûts et marge** de la **solution
    installée** (connue via ``rod_pilot_concepts`` / flags hotel_data) :
    ce sont les grandeurs « réalisées » associées au dispositif en place.
    """
    from archive.accor_1_0_6.pipelines.src.accor.hotel_solutions import load_pilot_solution_codes

    pilots = list_pilot_hotels(year)
    if not pilots.get("ok"):
        return pilots

    eval_year = int(pilots["eval_year"])
    pilot_sol = load_pilot_solution_codes()
    rows: list[dict[str, Any]] = []
    for h in pilots.get("hotels") or []:
        code = h["hotel_code"]
        has_holdout = bool(h.get("has_holdout"))
        installed = pilot_sol.get(str(code).strip())
        try:
            tr = simulate_hotel_trace(code, year=eval_year)
            if not tr.get("ok"):
                rows.append(
                    {
                        "hotel_code": code,
                        "hotel_name": h.get("hotel_name"),
                        "error": tr.get("error"),
                        "has_holdout": has_holdout,
                        "avg_monthly_true": h.get("avg_monthly_true"),
                        "installed_solution": installed,
                        "train_years": h.get("train_years") or pilots.get("train_years"),
                    }
                )
                continue
            reco = (tr.get("recommendation") or {}).get("recommended_concept") or "SIMPLY"
            gaps = tr.get("gaps") or {}
            g_reco = gaps.get(reco) or {}
            # CA sim toujours (même sans hold-out)
            ca_sim = g_reco.get("ca_sim_mensuel")
            if ca_sim is None:
                block = (tr.get("by_concept") or {}).get(reco) or {}
                ca_sim = (block.get("sales") or {}).get("ca_ht_mensuel")

            by_c: dict[str, Any] = {}
            for c in CONCEPTS:
                eco = _concept_economics(tr, c)
                g = gaps.get(c) or {}
                by_c[c] = {
                    **eco,
                    "gap": g.get("gap"),
                    "gap_pct": g.get("gap_pct"),
                }

            # Solution installée = vérité métier du pilote (coût / marge connus)
            inst = installed if installed in CONCEPTS else None
            eco_inst = by_c.get(inst) if inst else None
            eco_reco = by_c.get(reco) or {}

            # CA réel période modélisation (train) si dispo dans list_pilot
            train_ca = h.get("avg_monthly_train")
            if train_ca is None:
                # fallback : moyenne multi-années via hotel_reference si présent
                train_ca = h.get("reference_monthly")

            rows.append(
                {
                    "hotel_code": code,
                    "hotel_name": h.get("hotel_name") or "",
                    "hotel_brand": tr.get("hotel_brand") or h.get("hotel_brand"),
                    "category": tr.get("category") or h.get("category"),
                    "has_holdout": bool(tr.get("has_holdout", has_holdout)),
                    "n_months": h.get("n_months"),
                    "months": h.get("months"),
                    "train_years": h.get("train_years") or pilots.get("train_years"),
                    "avg_monthly_true": (
                        h.get("avg_monthly_true")
                        if (tr.get("has_holdout") or has_holdout)
                        else None
                    ),
                    "avg_monthly_train": train_ca,
                    "ca_ref_categorie": _round(
                        (tr.get("category_reference") or {}).get("ca_monthly_ref"), 2
                    ),
                    "installed_solution": inst,
                    "recommended_concept": reco,
                    "ca_sim_reco": ca_sim,
                    "cout_mensuel_reco": eco_reco.get("cout_mensuel"),
                    "marge_produit_reco": eco_reco.get("marge_produit_mensuelle"),
                    "marge_nette_reco": eco_reco.get("marge_nette_mensuelle"),
                    # Grandeurs « réalisées » = solution pilote installée
                    "ca_sim_installee": (eco_inst or {}).get("ca_sim_mensuel"),
                    "cout_mensuel_installee": (eco_inst or {}).get("cout_mensuel"),
                    "marge_produit_installee": (eco_inst or {}).get(
                        "marge_produit_mensuelle"
                    ),
                    "marge_nette_installee": (eco_inst or {}).get(
                        "marge_nette_mensuelle"
                    ),
                    "capex_installee": (eco_inst or {}).get("capex"),
                    "gap_reco": g_reco.get("gap") if tr.get("has_holdout") else None,
                    "gap_pct_reco": g_reco.get("gap_pct") if tr.get("has_holdout") else None,
                    "by_concept": by_c,
                }
            )
        except Exception as exc:
            rows.append(
                {
                    "hotel_code": code,
                    "hotel_name": h.get("hotel_name"),
                    "error": str(exc),
                    "has_holdout": has_holdout,
                    "avg_monthly_true": h.get("avg_monthly_true"),
                    "installed_solution": installed,
                }
            )

    # Métriques uniquement sur hôtels avec réel hold-out + gap
    scored = [
        r
        for r in rows
        if r.get("gap_reco") is not None and r.get("avg_monthly_true") is not None
    ]
    ok_rows = [r for r in rows if not r.get("error")]
    metrics: dict[str, Any] = {
        "n": len(scored),
        "n_predicted": len(ok_rows),
        "n_total": len(rows),
    }
    if scored:
        g = np.array([float(r["gap_reco"]) for r in scored], dtype=float)
        yt = np.array([float(r["avg_monthly_true"] or 0) for r in scored], dtype=float)
        yp = yt + g
        metrics["mae"] = _round(float(np.mean(np.abs(g))), 2)
        metrics["bias"] = _round(float(np.mean(g)), 2)
        metrics["rmse"] = _round(float(np.sqrt(np.mean(g ** 2))), 2)
        nz = np.abs(yt) > 1e-9
        if nz.any():
            metrics["mape"] = _round(float(np.mean(np.abs(g[nz] / yt[nz])) * 100.0), 1)
        metrics["mean_true"] = _round(float(np.mean(yt)), 2)
        metrics["mean_sim"] = _round(float(np.mean(yp)), 2)
        # moyenne sim sur *tous* les prédits (pas seulement scored)
        all_sim = [
            float(r["ca_sim_reco"])
            for r in rows
            if r.get("ca_sim_reco") is not None and not r.get("error")
        ]
        if all_sim:
            metrics["mean_sim_all"] = _round(float(np.mean(all_sim)), 2)

    # Moyennes coûts / marges sur solution **installée** (modélisation pilote)
    couts = [
        float(r["cout_mensuel_installee"])
        for r in ok_rows
        if r.get("cout_mensuel_installee") is not None
    ]
    margs = [
        float(r["marge_nette_installee"])
        for r in ok_rows
        if r.get("marge_nette_installee") is not None
    ]
    mprods = [
        float(r["marge_produit_installee"])
        for r in ok_rows
        if r.get("marge_produit_installee") is not None
    ]
    if couts:
        metrics["mean_cout_installee"] = _round(float(np.mean(couts)), 2)
        metrics["n_with_installed_costs"] = len(couts)
    if margs:
        metrics["mean_marge_nette_installee"] = _round(float(np.mean(margs)), 2)
    if mprods:
        metrics["mean_marge_produit_installee"] = _round(float(np.mean(mprods)), 2)

    return {
        "ok": True,
        "eval_year": eval_year,
        "train_years": pilots.get("train_years"),
        "divisor_months": int(DIVISOR_MONTHS),
        "n_hotels": len(rows),
        "n_with_holdout": pilots.get("n_with_holdout"),
        "n_predict_only": pilots.get("n_predict_only"),
        "method": (
            f"Split temporel : ref = {pilots.get('train_years')} (tous les "
            f"pilotes de la catégorie, sans exclusion d'hôtel) ; "
            f"éval = {eval_year}. n={len(rows)} pilote(s). "
            f"Coût & marge « réalisés » = solution installée du pilote "
            f"(Simply/Liberty/Connected) via barème ROD. "
            f"Écart CA = CA_sim_reco − (Σ réel {eval_year}/12) ; "
            f"MAE sur n={metrics.get('n', 0)} avec réel."
        ),
        "metrics": metrics,
        "hotels": rows,
    }
