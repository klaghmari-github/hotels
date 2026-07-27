"""
Simulateur Excel ROD — référence par **solution** (SIMPLY / LIBERTY / CONNECTED).

Calqué sur ``ROD - Simulateurs + détail des coûts.xlsx`` :
* colonne gauche = moyenne des pilotes de la solution ;
* colonne droite = projection sur l'hôtel désigné ;
* 3 feuilles / onglets identiques (seuls les chiffres changent).

Ne remplace pas ``rod_admin`` (référence par catégorie + éval temporelle).
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

import numpy as np

from accor.data_io import DATA_DIR
from accor.rod_admin import (
    JOURS_MOIS,
    _load_hotels,
    _load_sales,
    _round,
    _years_split,
    hotel_reference_over_years,
)
from accor.user.models import (
    ClientProfile,
    HotelIdentity,
    HotelOperating,
    SimulationRequest,
    StoreConfig,
)
from accor.user.reference import RodReference
from accor.user.rules.coeffs import (
    CLIENT_NEED_LABELS,
    LIBERTY_NFB_NEEDS,
    RULE3_BASELINE_FB,
    RULE3_BASELINE_NF,
    RULE3_FB_COEFFS,
    RULE3_NFB_COEFFS,
)
from accor.user.rules.costs import CostRules
from accor.user.rules.revenue import RevenueRules
from accor.user.services.hotel_context import HotelContextBuilder

CONCEPTS = ("SIMPLY", "LIBERTY", "CONNECTED")
PILOT_MAP_PATH = DATA_DIR / "rod_pilot_concepts.json"
NOT_PROFITABLE = "Not profitable"

# Alias courts audit HTML → clés client_needs
_LIFESTYLE_NFB_ALIASES: dict[str, str] = {
    "cosmetics": "nfb_cosmetics",
    "kids": "nfb_kids",
    "kids items": "nfb_kids",
    "apparel": "nfb_apparel",
    "ready-to-wear": "nfb_apparel",
    "accessories": "nfb_accessories",
    "souvenirs": "nfb_souvenirs",
}

# Commentaires métier extraits de l'Excel (SIMULATEUR *)
EXCEL_COMMENTS: dict[str, str] = {
    "params": (
        "PARAMETRES HOTEL — Nb. de chambres, guests / chambre, TO (YTD), "
        "mètres linéaires, mix F&B / N-F&B et coefficients de marge produits."
    ),
    "derived": (
        "Moyennes dérivées : chambres occupées, clients hébergés / jour, "
        "clients hébergés / mois (× 30,5), nb. ventes mensuelles, "
        "taux de clients acheteurs."
    ),
    "r1_title": "REGLE N°1 — REVENUS CALCULES EN FONCTION DU NB. DE CLIENTS ACHETEURS",
    "r1": (
        "REGLE 1 = Chaque client acheteur génère du CA.\n"
        "Les montants de CA ci-dessous sont basés sur le résultat des pilotes "
        "de cette solution (SIMPLY / LIBERTY / CONNECTED)."
    ),
    "r2_title": "REGLE N°2 — REVENUS POUR 10% (DE PLUS OU DE MOINS) DE MIX PRODUITS",
    "r2": (
        "REGLE 2 = Chaque 10% de MIX PDT en plus ou en moins impacte le CA.\n"
        "Cette règle impacte le CA F&B et le CA N-F&B, aussi bien en « bonus » "
        "qu'en « malus » pour chaque 10% de plus ou de moins par rapport au "
        "MIX PDT DE REFERENCE de la solution."
    ),
    "r3_title": "REGLE N°3 — INFLUENCE DES CATEGORIES DE PRODUITS SELECTIONNEES",
    "r3": (
        "REGLE 3 = Si la catégorie est cochée +X% sur le CA ; "
        "si la catégorie n'est pas cochée −X% sur le CA.\n"
        "Pour les hôtels de + de 50 ch. : si minimum 1 des 5 catégories "
        "lifestyle N-F&B est cochée, alors solution recommandée = LIBERTY.\n"
        "Attention : si le CA de l'étape précédente est négatif, sélectionner "
        "de nombreuses catégories permet de « réduire » la perte de CA."
    ),
    "r4_title": "REGLE N°4 — REVENUS POUR 1 METRE LINEAIRE (DE PLUS OU DE MOINS)",
    "r4": (
        "REGLE 4 = Chaque mètre linéaire en plus ou en moins impacte le CA.\n"
        "Si le nb. de mètres lin. est supérieur à la référence, la formule "
        "ajoute du CA (dans le cas inverse elle retire du CA).\n"
        ">> Plus l'hôtel augmente le nb. de ML de sa boutique, plus le CA augmente."
    ),
    "revenus": "REVENUS — CA HT F&B + N-F&B après application des règles 1 à 4.",
    "marge_produit": (
        "MARGE PRODUITS MENSUELLE — Formule Excel : marge = CA − CA/coef "
        "(coefs de marge F&B et N-F&B de la solution)."
    ),
    "couts": (
        "COUTS MENSUELS — Technos + annexes + agencement (∝ m_lin), "
        "mensualisés selon barèmes Excel (COUTS - TECHNOS / ANNEXES / AGENCEMENT)."
    ),
    "marge_nette": (
        "MARGE NETTE MENSUELLE — Formule = (marge produits mensuelle − coûts mensuels)."
    ),
    "amort": (
        "AMORTISSEMENT — Formule = (coût total capex / marge nette mensuelle) "
        "→ mois (et ans)."
    ),
}


def _r(x: Any, nd: int = 2) -> float | None:
    return _round(x, nd)


def _pilot_map_mtime() -> float:
    try:
        return float(PILOT_MAP_PATH.stat().st_mtime) if PILOT_MAP_PATH.exists() else 0.0
    except OSError:
        return 0.0


@lru_cache(maxsize=4)
def _load_pilot_concept_map_cached(mtime: float) -> dict[str, list[dict[str, str]]]:
    del mtime  # key only — invalide le cache si le fichier change
    if not PILOT_MAP_PATH.exists():
        return {c: [] for c in CONCEPTS}
    raw = json.loads(PILOT_MAP_PATH.read_text(encoding="utf-8"))
    out: dict[str, list[dict[str, str]]] = {}
    for c in CONCEPTS:
        items = (raw.get("concepts") or {}).get(c) or []
        out[c] = [
            {
                "hotel_code": str(it.get("hotel_code") or "").strip(),
                "label": str(it.get("label") or it.get("hotel_code") or "").strip(),
            }
            for it in items
            if str(it.get("hotel_code") or "").strip()
        ]
    return out


def load_pilot_concept_map() -> dict[str, list[dict[str, str]]]:
    """Mapping solution → pilotes. Cache invalidé sur mtime du JSON."""
    return _load_pilot_concept_map_cached(_pilot_map_mtime())


def clear_pilot_concept_map_cache() -> None:
    _load_pilot_concept_map_cached.cache_clear()


def all_needs_open() -> dict[str, bool]:
    return {**{k: True for k in RULE3_FB_COEFFS}, **{k: True for k in RULE3_NFB_COEFFS}}


def _has_lifestyle_nfb(client_needs: dict[str, bool] | None) -> bool:
    """Au moins un besoin lifestyle N-F&B ON (audit : cosmetics, kids, apparel…)."""
    needs = client_needs or {}
    if any(bool(needs.get(k, False)) for k in LIBERTY_NFB_NEEDS):
        return True
    return any(bool(needs.get(alias, False)) for alias in _LIFESTYLE_NFB_ALIASES)


def recommend_display_order(
    nb_chambres: float | int,
    mix_fb: float,
    m_lin: float,
    client_needs: dict[str, bool] | None,
    has_vitrine: bool,
    to: float,
    nb_frigos: float | int | None = None,
) -> tuple[str, list[str], list[str]]:
    """
    Arbre de reco audit HTML (ordre d'affichage, pas d'exclusion).

    IF rooms <= 49 → SIMPLY first
    ELIF any lifestyle NFB need ON → LIBERTY first
    ELIF m_lin > 4 → LIBERTY first
    ELIF has_vitrine → LIBERTY first
    ELIF TO < 0.70 → LIBERTY first
    ELSE → CONNECTED first

    Returns
    -------
    (recommended, ordered_list_of_3, reasons)
    """
    del mix_fb, nb_frigos  # signature stable / futurs critères audit
    rooms = float(nb_chambres or 0)
    ml = float(m_lin or 0)
    to_rate = float(to or 0)
    if to_rate > 1.0:
        to_rate /= 100.0
    needs = client_needs or {}
    reasons: list[str] = []

    if rooms <= 49:
        recommended = "SIMPLY"
        reasons.append(
            f"Nb. chambres ≤ 49 ({int(round(rooms))}) → SIMPLY en premier."
        )
    elif _has_lifestyle_nfb(needs):
        recommended = "LIBERTY"
        active = [
            CLIENT_NEED_LABELS.get(k, k)
            for k in LIBERTY_NFB_NEEDS
            if bool(needs.get(k, False))
        ]
        reasons.append(
            "Catégorie(s) lifestyle N-F&B active(s) "
            f"({', '.join(active) or '—'}) → LIBERTY en premier."
        )
    elif ml > 4:
        recommended = "LIBERTY"
        reasons.append(f"Mètres linéaires > 4 ({_r(ml, 2)}) → LIBERTY en premier.")
    elif bool(has_vitrine):
        recommended = "LIBERTY"
        reasons.append("Vitrine réfrigérée déjà présente → LIBERTY en premier.")
    elif to_rate < 0.70:
        recommended = "LIBERTY"
        reasons.append(
            f"TO moyen < 70 % ({_r(to_rate * 100, 1)} %) → LIBERTY en premier."
        )
    else:
        recommended = "CONNECTED"
        reasons.append(
            "Hôtel ≥ 50 ch., sans lifestyle N-F&B, ML ≤ 4, sans vitrine, "
            f"TO ≥ 70 % ({_r(to_rate * 100, 1)} %) → CONNECTED en premier."
        )

    ordered = [recommended] + [c for c in CONCEPTS if c != recommended]
    return recommended, ordered, reasons


def _merge_dual_rows(
    left_rows: list[dict[str, Any]] | None,
    right_rows: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Fusionne left_rows / right_rows → rows[{label, left, right, hint?, fmt?}].

    Préserve les doublons de label (ex. deux lignes « Amortissement ») via un
    index d'occurrence (label, n).
    """
    left_rows = left_rows or []
    right_rows = right_rows or []

    def _index(rows: list[dict[str, Any]]) -> dict[tuple[str, int], dict[str, Any]]:
        counts: dict[str, int] = {}
        out: dict[tuple[str, int], dict[str, Any]] = {}
        for r in rows:
            lab = str(r.get("label") or "")
            n = counts.get(lab, 0)
            counts[lab] = n + 1
            out[(lab, n)] = r
        return out

    left_by = _index(left_rows)
    right_by = _index(right_rows)
    # Clés ordonnées : gauche d'abord, puis lignes droite absentes à gauche
    keys: list[tuple[str, int]] = []
    seen: set[tuple[str, int]] = set()
    lcounts: dict[str, int] = {}
    for r in left_rows:
        lab = str(r.get("label") or "")
        n = lcounts.get(lab, 0)
        lcounts[lab] = n + 1
        k = (lab, n)
        if k not in seen:
            keys.append(k)
            seen.add(k)
    rcounts: dict[str, int] = {}
    for r in right_rows:
        lab = str(r.get("label") or "")
        n = rcounts.get(lab, 0)
        rcounts[lab] = n + 1
        k = (lab, n)
        if k not in seen:
            keys.append(k)
            seen.add(k)

    out: list[dict[str, Any]] = []
    for k in keys:
        lab, _n = k
        lr = left_by.get(k) or {}
        rr = right_by.get(k) or {}
        row: dict[str, Any] = {
            "label": lab,
            "left": lr.get("value") if lr else None,
            "right": rr.get("value") if rr else None,
        }
        hint = None
        if rr.get("hint") is not None:
            hint = rr.get("hint")
        elif lr.get("hint") is not None:
            hint = lr.get("hint")
        if hint is not None:
            row["hint"] = hint
        fmt = None
        if rr.get("fmt") is not None:
            fmt = rr.get("fmt")
        elif lr.get("fmt") is not None:
            fmt = lr.get("fmt")
        if fmt is not None:
            row["fmt"] = fmt
        # conserver numériques si affichage « Not profitable »
        if rr.get("value_num") is not None:
            row["right_num"] = rr.get("value_num")
        if lr.get("value_num") is not None:
            row["left_num"] = lr.get("value_num")
        out.append(row)
    return out


def _apply_not_profitable_to_steps(
    steps: list[dict[str, Any]],
    *,
    not_profitable: bool,
) -> list[dict[str, Any]]:
    """Remplace CA TOTAL / Marge nette affichés par « Not profitable » si besoin."""
    if not not_profitable:
        return steps
    kpi_labels = {
        "CA HT TOTAL",
        "Marge nette HT / mois",
        "Marge nette",
        "CA TOTAL",
    }
    out: list[dict[str, Any]] = []
    for st in steps:
        st2 = dict(st)
        rows = []
        for r in st.get("rows") or []:
            r2 = dict(r)
            lab = str(r2.get("label") or "")
            if lab in kpi_labels or (
                "CA HT TOTAL" in lab or lab.startswith("Marge nette")
            ):
                if r2.get("value") is not None and not isinstance(r2.get("value"), str):
                    r2["value_num"] = r2.get("value")
                r2["value"] = NOT_PROFITABLE
            rows.append(r2)
        st2["rows"] = rows
        out.append(st2)
    return out


def collect_validation_warnings(
    *,
    m_lin: float,
    client_needs: dict[str, bool] | None,
) -> list[str]:
    """Avertissements audit (m_lin < 2, toutes catégories OFF)."""
    warnings: list[str] = []
    if float(m_lin or 0) < 2:
        warnings.append(
            "Minimum 2 mètres linéaires requis (m_lin < 2)."
        )
    needs = client_needs or {}
    known = list(RULE3_FB_COEFFS) + list(RULE3_NFB_COEFFS)
    if known and not any(bool(needs.get(k, False)) for k in known):
        warnings.append(
            "Toutes les catégories de produits sont désactivées."
        )
    return warnings


def excel_ui_meta() -> dict[str, Any]:
    """Meta UI : besoins, défauts, mapping, commentaires."""
    mapping = load_pilot_concept_map()
    return {
        "ok": True,
        "concepts": list(CONCEPTS),
        "comments": EXCEL_COMMENTS,
        "pilot_map": mapping,
        "client_needs_fb": [
            {"id": k, "label": CLIENT_NEED_LABELS.get(k, k), "coef": v, "default": True}
            for k, v in RULE3_FB_COEFFS.items()
        ],
        "client_needs_nfb": [
            {"id": k, "label": CLIENT_NEED_LABELS.get(k, k), "coef": v, "default": True}
            for k, v in RULE3_NFB_COEFFS.items()
        ],
        "defaults": {
            "mix_fb": 0.70,
            "m_lin": 6.0,
            "client_needs": all_needs_open(),
        },
        "layout": {
            "left": "MOYENNE RESULTATS PILOTES (solution)",
            "right": "SIMULATEUR (hôtel désigné)",
        },
    }


def build_concept_reference(
    concept: str,
    *,
    eval_year: int | None = None,
    train_years: list[int] | None = None,
) -> dict[str, Any]:
    """
    Moyenne des pilotes de la **solution** ``concept``.

    - Paramètres hôtel : moyenne live (ventes train + fiche) si dispo.
    - CA F&B / N-F&B / ventes / mix / marges : pivots Excel ``rod_reference``
      (déjà moyennes multi-pilotes extraites de l'Excel).
    """
    concept = concept.upper()
    if concept not in CONCEPTS:
        return {"ok": False, "error": f"Concept inconnu : {concept}", "concept": concept}

    ref = RodReference()
    key = f"concepts.{concept}"
    excel = {
        "nb_chambres": float(ref.get(f"{key}.pivot_nb_chambres", 100) or 100),
        "guests_per_chambre": float(ref.get(f"{key}.pivot_guests_per_chambre", 1.7) or 1.7),
        "taux_occupation": float(ref.get(f"{key}.pivot_to", 0.75) or 0.75),
        "m_lin": float(ref.get(f"{key}.pivot_m_lin", 6) or 6),
        "mix_fb": float(ref.get(f"{key}.mix_fb", 0.7) or 0.7),
        "mix_nf": float(ref.get(f"{key}.mix_nf", 0.3) or 0.3),
        "margin_fb": float(ref.get(f"{key}.margin_fb_pct", 2.6) or 2.6),
        "margin_nf": float(ref.get(f"{key}.margin_nf_pct", 1.45) or 1.45),
        "ca_fb": float(ref.get(f"{key}.base_monthly_ca_fb", 0) or 0),
        "ca_nf": float(ref.get(f"{key}.base_monthly_ca_nf", 0) or 0),
        "nb_ventes": float(ref.get(f"{key}.base_monthly_sales", 0) or 0),
    }
    excel["ca_ht"] = excel["ca_fb"] + excel["ca_nf"]
    excel["clients_jour"] = (
        excel["nb_chambres"] * excel["taux_occupation"] * excel["guests_per_chambre"]
    )
    excel["clients_mois"] = excel["clients_jour"] * JOURS_MOIS
    excel["taux_acheteur"] = (
        excel["nb_ventes"] / excel["clients_mois"] if excel["clients_mois"] else 0.0
    )

    mapping = load_pilot_concept_map().get(concept) or []
    sales = _load_sales()
    hotels = _load_hotels()

    if sales is not None and not sales.empty:
        ey, ty = _years_split(sales)
        if eval_year is not None:
            ey = int(eval_year)
            ty = [
                int(y)
                for y in sorted(sales["annee"].dropna().unique())
                if int(y) < ey
            ]
        eval_year = ey
        train_years = train_years if train_years is not None else ty
    else:
        eval_year = eval_year or 2026
        train_years = train_years or []

    hotel_refs: list[dict[str, Any]] = []
    rooms: list[float] = []
    tos: list[float] = []
    guests: list[float] = []
    clients: list[float] = []
    ca_live: list[float] = []

    from accor.user.services.hotel_context import (
        BRAND_GUESTS_DEFAULT,
        BRAND_TO_DEFAULT,
        _as_int,
        _as_rate,
        _norm_brand,
    )

    for item in mapping:
        code = item["hotel_code"]
        label = item["label"]
        href = (
            hotel_reference_over_years(sales, code, train_years or [])
            if sales is not None and not sales.empty and train_years
            else {
                "hotel_code": code,
                "by_year": {},
                "reference_monthly": None,
                "n_years": 0,
            }
        )
        row = None
        if hotels is not None and not hotels.empty:
            m = hotels[hotels["hotel_code"] == code]
            if not m.empty:
                row = m.iloc[0]

        name = ""
        brand = ""
        n = 0
        to = None
        g = None
        if row is not None:
            name = str(row.get("hotel_name") or "")
            brand = str(row.get("hotel_brand") or "")
            bk = _norm_brand(brand)
            n = _as_int(row.get("hotel_nb_chambres"), 0)
            to = _as_rate(row.get("hotel_to_annuel"), BRAND_TO_DEFAULT.get(bk, 0.70))
            g = BRAND_GUESTS_DEFAULT.get(bk, 1.7)
            if n > 0 and to is not None and g is not None:
                rooms.append(float(n))
                tos.append(float(to))
                guests.append(float(g))
                clients.append(float(n) * float(to) * float(g) * JOURS_MOIS)

        if href.get("reference_monthly") is not None:
            ca_live.append(float(href["reference_monthly"]))

        hotel_refs.append(
            {
                "hotel_code": code,
                "label": label,
                "hotel_name": name,
                "hotel_brand": brand,
                "nb_chambres": n or None,
                "taux_occupation": _r(to, 4) if to is not None else None,
                "guests_per_chambre": _r(g, 3) if g is not None else None,
                "ca_monthly_ref": _r(href.get("reference_monthly"), 2),
                "by_year": href.get("by_year") or {},
                "n_years": href.get("n_years") or 0,
            }
        )

    def _mean(xs: list[float]) -> float | None:
        return float(np.mean(xs)) if xs else None

    # Params live si dispo, sinon Excel
    live_nb = _mean(rooms)
    live_to = _mean(tos)
    live_g = _mean(guests)
    live_clients = _mean(clients)
    live_ca = _mean(ca_live)

    left_params = {
        "nb_chambres": live_nb if live_nb is not None else excel["nb_chambres"],
        "guests_per_chambre": live_g if live_g is not None else excel["guests_per_chambre"],
        "taux_occupation": live_to if live_to is not None else excel["taux_occupation"],
        "m_lin": excel["m_lin"],
        "mix_fb": excel["mix_fb"],
        "mix_nf": excel["mix_nf"],
        "margin_fb": excel["margin_fb"],
        "margin_nf": excel["margin_nf"],
    }
    left_params["ch_occ"] = (
        left_params["nb_chambres"] * left_params["taux_occupation"]
    )
    left_params["clients_jour"] = (
        left_params["nb_chambres"]
        * left_params["taux_occupation"]
        * left_params["guests_per_chambre"]
    )
    left_params["clients_mois"] = left_params["clients_jour"] * JOURS_MOIS

    # CA base = toujours Excel (split F&B/N-F&B de la solution)
    source = "excel_rod_reference"
    if live_clients is not None and live_ca is not None:
        source = "excel_ca_fb_nf + live_params_moyenne_pilotes"

    return {
        "ok": True,
        "concept": concept,
        "source": source,
        "eval_year": eval_year,
        "train_years": train_years or [],
        "n_pilots": len(hotel_refs),
        "pilots": hotel_refs,
        "excel_fallback": {
            k: _r(v, 4) if isinstance(v, float) else v for k, v in excel.items()
        },
        "left": {
            "params": {k: _r(v, 4) if isinstance(v, float) else v for k, v in left_params.items()},
            "nb_ventes": _r(excel["nb_ventes"], 2),
            "taux_acheteur": _r(excel["taux_acheteur"], 6),
            "ca_fb": _r(excel["ca_fb"], 2),
            "ca_nf": _r(excel["ca_nf"], 2),
            "ca_ht": _r(excel["ca_ht"], 2),
            "ca_monthly_live_avg": _r(live_ca, 2),
            "clients_mois_live_avg": _r(live_clients, 1),
        },
        "method": (
            f"Pilotes = hôtels de la solution {concept} "
            f"({', '.join(p['hotel_code'] for p in hotel_refs) or '—'}). "
            f"Moyenne multi-années train {train_years or '—'} pour params live ; "
            f"CA F&B/N-F&B = pivots Excel rod_reference (moyenne solution)."
        ),
    }


def _build_request(
    *,
    hotel_code: str,
    hotel_name: str,
    hotel_brand: str,
    nb_chambres: float,
    taux_occupation: float,
    guests_per_chambre: float,
    m_lin: float,
    mix_fb: float,
    client_needs: dict[str, bool],
    concept: str,
) -> SimulationRequest:
    mix_fb = float(mix_fb)
    if mix_fb > 1.0:
        mix_fb /= 100.0
    mix_fb = min(max(mix_fb, 0.0), 1.0)
    mix_nf = 1.0 - mix_fb
    return SimulationRequest(
        identity=HotelIdentity(
            hotel_code=hotel_code,
            hotel_name=hotel_name or "",
            hotel_brand=hotel_brand or "",
        ),
        operating=HotelOperating(
            nb_chambres=int(round(nb_chambres)),
            taux_occupation=float(taux_occupation),
            guests_per_chambre=float(guests_per_chambre),
        ),
        client_profile=ClientProfile(client_needs=dict(client_needs)),
        store=StoreConfig(
            concept=concept.upper(),
            m_lin=float(m_lin),
            mix_fb=mix_fb,
            mix_nf=mix_nf,
        ),
    )


def _build_steps(
    *,
    concept: str,
    op: HotelOperating,
    store: StoreConfig,
    ca_fb: float,
    ca_nf: float,
    ca_ht: float,
    nbr_ventes: float,
    taux_acheteur: float,
    marge_prod: float,
    cout: float,
    capex: float,
    cost_res: Any,
    bd: dict[str, Any],
    is_left: bool,
) -> list[dict[str, Any]]:
    """Étapes duales (même structure Excel)."""
    concept = concept.upper()
    marge_nette = marge_prod - cout
    amort_mois = (capex / marge_nette) if marge_nette > 0 else None
    amort_ans = (amort_mois / 12.0) if amort_mois is not None else None
    pivot_m = float(bd.get("pivot_m_lin") or store.m_lin or 0)
    ca_fb_ref = float(bd.get("ca_fb_ref_pilote") or ca_fb)
    ca_nf_ref = float(bd.get("ca_nf_ref_pilote") or ca_nf)
    clients_hotel = float(bd.get("clients_hotel") or op.clients_mois)
    factor = float(bd.get("client_factor") or 1.0)

    r1_rows = [
        {
            "label": "Clients acheteurs / mois",
            "value": _r(clients_hotel * taux_acheteur, 1),
        },
        {"label": "CA HT F&B", "value": _r(ca_fb_ref if is_left else ca_fb_ref * factor, 2)},
        {"label": "CA HT N-F&B", "value": _r(ca_nf_ref if is_left else ca_nf_ref * factor, 2)},
    ]
    if not is_left:
        r1_rows.append(
            {
                "label": "Facteur clients",
                "value": _r(factor, 4),
                "hint": "clients_hôtel / clients_pilote",
            }
        )

    if is_left:
        r2_rows = [
            {"label": "Réf. mix F&B", "value": _r(store.mix_fb, 4)},
            {"label": "Réf. mix N-F&B", "value": _r(store.mix_nf, 4)},
            {"label": "Unité CA / 10% F&B", "value": _r((ca_fb_ref * 0.10) / store.mix_fb if store.mix_fb else 0, 2)},
            {"label": "Unité CA / 10% N-F&B", "value": _r((ca_nf_ref * 0.10) / store.mix_nf if store.mix_nf else 0, 2)},
        ]
        r3_rows = [
            {"label": "Baseline F&B", "value": _r(RULE3_BASELINE_FB, 4)},
            {"label": "Baseline N-F&B", "value": _r(RULE3_BASELINE_NF, 4)},
            {"label": "Note", "value": "—", "hint": "réf. pilote = CA base (pas de R3)"},
        ]
        r4_rows = [
            {"label": "M. lin. ref solution", "value": _r(pivot_m, 2)},
            {"label": "CA HT / m F&B", "value": _r(ca_fb_ref / pivot_m if pivot_m else 0, 2)},
            {"label": "CA HT / m N-F&B", "value": _r(ca_nf_ref / pivot_m if pivot_m else 0, 2)},
        ]
    else:
        r2_rows = [
            {"label": "Steps ×10% F&B", "value": _r(bd.get("mix_steps_fb"), 3)},
            {"label": "Steps ×10% N-F&B", "value": _r(bd.get("mix_steps_nf"), 3)},
        ]
        r3_rows = [
            {"label": "Cumul F&B", "value": _r(bd.get("cumul_rule3_fb"), 4)},
            {"label": "Cumul N-F&B", "value": _r(bd.get("cumul_rule3_nf"), 4)},
            {"label": "Δ F&B vs baseline", "value": _r(bd.get("rule3_delta_fb"), 4)},
            {"label": "Δ N-F&B vs baseline", "value": _r(bd.get("rule3_delta_nf"), 4)},
        ]
        r4_rows = [
            {"label": "M. lin. hôtel", "value": _r(store.m_lin, 2)},
            {"label": "M. lin. ref solution", "value": _r(pivot_m, 2)},
            {"label": "Diff. ML", "value": _r(bd.get("m_lin_diff"), 2)},
        ]

    return [
        {
            "id": "params",
            "title": "PARAMETRES HOTEL",
            "comment": EXCEL_COMMENTS["params"],
            "rows": [
                {"label": "Nb. de ch.", "value": _r(op.nb_chambres, 1)},
                {"label": "Nb. gu / ch", "value": _r(op.guests_per_chambre, 3)},
                {"label": "TO (YTD)", "value": _r(op.taux_occupation, 4)},
                {"label": "M. lin.", "value": _r(store.m_lin, 2)},
                {"label": "Mix F&B", "value": _r(store.mix_fb, 4)},
                {"label": "Mix N-F&B", "value": _r(store.mix_nf, 4)},
            ],
        },
        {
            "id": "derived",
            "title": "MOYENNE (dérivées)",
            "comment": EXCEL_COMMENTS["derived"],
            "rows": [
                {
                    "label": "Ch. occ.",
                    "value": _r(op.nb_chambres * op.taux_occupation, 2),
                    "hint": "chambres occupées",
                },
                {
                    "label": "Cl. héb. / jour",
                    "value": _r(op.clients_jour, 2),
                    "hint": "clients hébergés / jour",
                },
                {
                    "label": "Cl. héb. / mois",
                    "value": _r(op.clients_mois, 2),
                    "hint": "clients hébergés / mois",
                },
                {
                    "label": "Nb. ventes",
                    "value": _r(nbr_ventes, 1),
                    "hint": "ventes mensuelles",
                },
                {
                    "label": "Taux acheteurs",
                    "value": _r(taux_acheteur, 6),
                    "hint": "de clients acheteurs / mois",
                },
            ],
        },
        {
            "id": "r1",
            "title": EXCEL_COMMENTS["r1_title"],
            "comment": EXCEL_COMMENTS["r1"].replace(
                "cette solution (SIMPLY / LIBERTY / CONNECTED)",
                f"des pilotes {concept}.",
            ),
            "rows": r1_rows,
        },
        {
            "id": "r2",
            "title": EXCEL_COMMENTS["r2_title"],
            "comment": EXCEL_COMMENTS["r2"],
            "rows": r2_rows,
        },
        {
            "id": "r3",
            "title": EXCEL_COMMENTS["r3_title"],
            "comment": EXCEL_COMMENTS["r3"],
            "rows": r3_rows,
        },
        {
            "id": "r4",
            "title": EXCEL_COMMENTS["r4_title"],
            "comment": EXCEL_COMMENTS["r4"],
            "rows": r4_rows,
        },
        {
            "id": "revenus",
            "title": "REVENUS",
            "comment": EXCEL_COMMENTS["revenus"],
            "rows": [
                {"label": "CA HT F&B", "value": _r(ca_fb, 2)},
                {"label": "CA HT N-F&B", "value": _r(ca_nf, 2)},
                {"label": "CA HT TOTAL", "value": _r(ca_ht, 2)},
            ],
            "highlight": True,
        },
        {
            "id": "marge_produit",
            "title": "MARGE PRODUITS MENSUELLE",
            "comment": EXCEL_COMMENTS["marge_produit"],
            "rows": [{"label": "Marge produit / mois", "value": _r(marge_prod, 2)}],
            "highlight": True,
        },
        {
            "id": "couts",
            "title": "COUTS MENSUELS",
            "comment": EXCEL_COMMENTS["couts"],
            "rows": [
                {"label": "Techno / mois", "value": _r(cost_res.techno_monthly, 2)},
                {"label": "Annexes / mois", "value": _r(cost_res.annexes_monthly, 2)},
                {"label": "Agencement / mois", "value": _r(cost_res.agencement_monthly, 2)},
                {"label": "TOTAL coûts / mois", "value": _r(cout, 2)},
                {"label": "Capex total", "value": _r(capex, 2)},
            ],
        },
        {
            "id": "marge_nette",
            "title": "MARGE NETTE MENSUELLE",
            "comment": EXCEL_COMMENTS["marge_nette"],
            "rows": [
                {"label": "Marge nette HT / mois", "value": _r(marge_nette, 2)},
                {
                    "label": "Taux",
                    "value": (
                        _r(marge_nette / ca_ht, 4)
                        if ca_ht > 0 and marge_nette > 0
                        else None
                    ),
                    "hint": "N/A si marge < 0",
                },
            ],
            "highlight": True,
        },
        {
            "id": "amort",
            "title": "AMORTISSEMENT",
            "comment": EXCEL_COMMENTS["amort"],
            "rows": [
                {"label": "Amortissement", "value": _r(amort_mois, 1), "hint": "mois"},
                {"label": "Amortissement", "value": _r(amort_ans, 2), "hint": "ans"},
            ],
        },
    ]


def _left_snapshot(
    cost: CostRules,
    request: SimulationRequest,
    concept: str,
    *,
    ca_fb: float,
    ca_nf: float,
    nb_ventes: float,
    margin_fb: float,
    margin_nf: float,
) -> dict[str, Any]:
    """
    Colonne gauche Excel = **référence pilote** (CA base solution),
    sans ré-appliquer R2–R4 (comme E120=E34 dans l'Excel).
    """
    concept = concept.upper()
    store = request.store
    op = request.operating
    assert store is not None
    cost_res = cost.compute(request, concept)
    ca_ht = ca_fb + ca_nf
    marge_prod = RevenueRules.marge_produit(ca_fb, ca_nf, margin_fb, margin_nf)
    cout = float(cost_res.monthly_cost)
    capex = float(cost_res.capex)
    marge_nette = marge_prod - cout
    amort_mois = (capex / marge_nette) if marge_nette > 0 else None
    clients_mois = float(op.clients_mois)
    taux_acheteur = nb_ventes / clients_mois if clients_mois else 0.0
    bd = {
        "pivot_m_lin": store.m_lin,
        "ca_fb_ref_pilote": ca_fb,
        "ca_nf_ref_pilote": ca_nf,
        "clients_hotel": clients_mois,
        "client_factor": 1.0,
    }
    steps = _build_steps(
        concept=concept,
        op=op,
        store=store,
        ca_fb=ca_fb,
        ca_nf=ca_nf,
        ca_ht=ca_ht,
        nbr_ventes=nb_ventes,
        taux_acheteur=taux_acheteur,
        marge_prod=marge_prod,
        cout=cout,
        capex=capex,
        cost_res=cost_res,
        bd=bd,
        is_left=True,
    )
    return {
        "is_pilot_avg": True,
        "params": {
            "nb_chambres": op.nb_chambres,
            "guests_per_chambre": _r(op.guests_per_chambre, 3),
            "taux_occupation": _r(op.taux_occupation, 4),
            "m_lin": _r(store.m_lin, 2),
            "mix_fb": _r(store.mix_fb, 4),
            "mix_nf": _r(store.mix_nf, 4),
            "clients_jour": _r(op.clients_jour, 2),
            "clients_mois": _r(op.clients_mois, 2),
        },
        "ca_fb": _r(ca_fb, 2),
        "ca_nf": _r(ca_nf, 2),
        "ca_ht": _r(ca_ht, 2),
        "nbr_ventes": _r(nb_ventes, 1),
        "marge_produit": _r(marge_prod, 2),
        "cout_mensuel": _r(cout, 2),
        "marge_nette": _r(marge_nette, 2),
        "capex": _r(capex, 2),
        "amort_mois": _r(amort_mois, 1),
        "amort_ans": _r((amort_mois / 12.0) if amort_mois else None, 2),
        "cost_lines": cost_res.cost_lines,
        "steps": steps,
        "warnings": list(cost_res.warnings or []),
    }


def _right_snapshot(
    rev: RevenueRules,
    cost: CostRules,
    request: SimulationRequest,
    concept: str,
) -> dict[str, Any]:
    """Colonne droite = projection hôtel désigné (toutes les règles)."""
    concept = concept.upper()
    rev_res = rev.compute(request, concept)
    cost_res = cost.compute(request, concept)
    bd = rev_res.breakdown or {}
    op = request.operating
    store = request.store
    assert store is not None

    ca_fb = float(rev_res.ca_fb_mensuel)
    ca_nf = float(rev_res.ca_nf_mensuel)
    ca_ht = float(rev_res.ca_ht_mensuel)
    marge_prod = float(rev_res.marge_produit_mensuelle)
    cout = float(cost_res.monthly_cost)
    capex = float(cost_res.capex)
    marge_nette = marge_prod - cout
    amort_mois = (capex / marge_nette) if marge_nette > 0 else None
    taux_acheteur = float(bd.get("taux_acheteur") or 0)

    steps = _build_steps(
        concept=concept,
        op=op,
        store=store,
        ca_fb=ca_fb,
        ca_nf=ca_nf,
        ca_ht=ca_ht,
        nbr_ventes=float(rev_res.nbr_ventes_mensuel),
        taux_acheteur=taux_acheteur,
        marge_prod=marge_prod,
        cout=cout,
        capex=capex,
        cost_res=cost_res,
        bd=bd,
        is_left=False,
    )

    ca_ht_num = _r(ca_ht, 2)
    marge_nette_num = _r(marge_nette, 2)
    # Audit : CA ou marge nette négatifs → affichage « Not profitable »
    not_profitable = bool(
        (ca_ht is not None and ca_ht < 0)
        or (marge_nette is not None and marge_nette < 0)
    )
    if not_profitable:
        steps = _apply_not_profitable_to_steps(steps, not_profitable=True)

    return {
        "is_pilot_avg": False,
        "params": {
            "nb_chambres": op.nb_chambres,
            "guests_per_chambre": _r(op.guests_per_chambre, 3),
            "taux_occupation": _r(op.taux_occupation, 4),
            "m_lin": _r(store.m_lin, 2),
            "mix_fb": _r(store.mix_fb, 4),
            "mix_nf": _r(store.mix_nf, 4),
            "clients_jour": _r(op.clients_jour, 2),
            "clients_mois": _r(op.clients_mois, 2),
        },
        "ref_pilote": {
            "nb_chambres": _r(bd.get("pivot_nb_chambres"), 1),
            "to": _r(bd.get("pivot_to"), 4),
            "guests": _r(bd.get("pivot_guests"), 3),
            "m_lin": _r(bd.get("pivot_m_lin"), 2),
            "ca_fb": _r(bd.get("ca_fb_ref_pilote"), 2),
            "ca_nf": _r(bd.get("ca_nf_ref_pilote"), 2),
            "nb_ventes": _r(bd.get("ventes_ref_pilote"), 1),
            "clients_mois": _r(bd.get("clients_pilote"), 1),
        },
        "ca_fb": _r(ca_fb, 2),
        "ca_nf": _r(ca_nf, 2),
        "ca_ht": NOT_PROFITABLE if not_profitable else ca_ht_num,
        "ca_ht_num": ca_ht_num,
        "nbr_ventes": _r(rev_res.nbr_ventes_mensuel, 1),
        "marge_produit": _r(marge_prod, 2),
        "cout_mensuel": _r(cout, 2),
        "marge_nette": NOT_PROFITABLE if not_profitable else marge_nette_num,
        "marge_nette_num": marge_nette_num,
        "not_profitable": not_profitable,
        "capex": _r(capex, 2),
        "amort_mois": _r(amort_mois, 1),
        "amort_ans": _r((amort_mois / 12.0) if amort_mois else None, 2),
        "cost_lines": cost_res.cost_lines,
        "steps": steps,
        "warnings": list(rev_res.warnings or []) + list(cost_res.warnings or []),
    }


def simulate_excel_dual(
    hotel_code: str,
    *,
    m_lin: float | None = None,
    mix_fb: float | None = None,
    client_needs: dict[str, bool] | None = None,
    nb_chambres: float | None = None,
    taux_occupation: float | None = None,
    guests_per_chambre: float | None = None,
    year: int | None = None,
    has_vitrine: bool | None = None,
    nb_frigos: float | int | None = None,
) -> dict[str, Any]:
    """
    Pour l'hôtel désigné : produit les 3 onglets SIMPLY / LIBERTY / CONNECTED
    avec colonne gauche (moyenne pilotes solution) et droite (projection).

    Colonne gauche = CA base pilote (sans R2–R4, fidélité Excel).
    Recommandation = arbre audit (ordre d'affichage, 3 solutions toujours calculées).
    """
    code = str(hotel_code or "").strip()
    if not code:
        return {"ok": False, "error": "hotel_code requis"}

    builder = HotelContextBuilder()
    try:
        ctx = builder.build(code, fetch_if_missing=False)
    except Exception as exc:
        return {"ok": False, "error": f"Contexte hôtel : {exc}", "hotel_code": code}

    ident = ctx.identity or {}
    hotel_name = str(ident.get("hotel_name") or "")
    hotel_brand = str(ident.get("hotel_brand") or "")

    # Defaults from hotel context
    op0 = ctx.operating if hasattr(ctx, "operating") else None
    if isinstance(op0, dict):
        def_n = float(op0.get("nb_chambres") or 100)
        def_to = float(op0.get("taux_occupation") or 0.7)
        def_g = float(op0.get("guests_per_chambre") or 1.7)
    else:
        def_n = float(getattr(op0, "nb_chambres", 100) or 100)
        def_to = float(getattr(op0, "taux_occupation", 0.7) or 0.7)
        def_g = float(getattr(op0, "guests_per_chambre", 1.7) or 1.7)

    n = float(nb_chambres) if nb_chambres is not None else def_n
    to = float(taux_occupation) if taux_occupation is not None else def_to
    if to > 1.0:
        to /= 100.0
    g = float(guests_per_chambre) if guests_per_chambre is not None else def_g
    ml = float(m_lin) if m_lin is not None else 6.0
    mx = float(mix_fb) if mix_fb is not None else 0.70
    if mx > 1.0:
        mx /= 100.0
    needs = client_needs if isinstance(client_needs, dict) else all_needs_open()
    # normalize needs
    needs = {str(k): bool(v) for k, v in needs.items()}
    for k in list(RULE3_FB_COEFFS) + list(RULE3_NFB_COEFFS):
        needs.setdefault(k, True)

    # Vitrine / frigos : param explicite ou fiche hôtel (lobby fridge)
    if has_vitrine is None:
        services = getattr(ctx, "services", None) or {}
        has_vitrine = bool(
            isinstance(services, dict)
            and (
                services.get("lobby_fridge")
                or services.get("has_vitrine")
                or services.get("vitrine_refrigeree")
            )
        )
    else:
        has_vitrine = bool(has_vitrine)

    validation_warnings = collect_validation_warnings(m_lin=ml, client_needs=needs)
    recommended, concept_order, reco_reasons = recommend_display_order(
        n,
        mx,
        ml,
        needs,
        has_vitrine,
        to,
        nb_frigos=nb_frigos,
    )

    ref = RodReference()
    rev = RevenueRules(ref)
    cost = CostRules(ref)

    sales = _load_sales()
    eval_year, train_years = (None, [])
    if sales is not None and not sales.empty:
        eval_year, train_years = _years_split(sales)
        if year is not None:
            eval_year = int(year)
            train_years = [
                int(y)
                for y in sorted(sales["annee"].dropna().unique())
                if int(y) < eval_year
            ]

    by_concept: dict[str, Any] = {}
    for concept in CONCEPTS:
        concept_ref = build_concept_reference(
            concept, eval_year=eval_year, train_years=train_years
        )
        left_p = (concept_ref.get("left") or {}).get("params") or {}
        excel_fb = float((concept_ref.get("left") or {}).get("ca_fb") or 0)
        excel_nf = float((concept_ref.get("left") or {}).get("ca_nf") or 0)
        excel_ventes = float((concept_ref.get("left") or {}).get("nb_ventes") or 0)
        excel_mix_fb = float(left_p.get("mix_fb") or 0.7)
        excel_ml = float(left_p.get("m_lin") or 6)
        excel_n = float(left_p.get("nb_chambres") or 100)
        excel_to = float(left_p.get("taux_occupation") or 0.75)
        excel_g = float(left_p.get("guests_per_chambre") or 1.7)

        # Colonne gauche = moyenne pilotes solution (CA base Excel, sans R2–R4)
        left_req = _build_request(
            hotel_code=f"PILOT_AVG_{concept}",
            hotel_name=f"Moyenne pilotes {concept}",
            hotel_brand="",
            nb_chambres=excel_n,
            taux_occupation=excel_to,
            guests_per_chambre=excel_g,
            m_lin=excel_ml,
            mix_fb=excel_mix_fb,
            client_needs=all_needs_open(),
            concept=concept,
        )
        excel_fb_m = float(
            (concept_ref.get("excel_fallback") or {}).get("margin_fb")
            or left_p.get("margin_fb")
            or 2.6
        )
        excel_nf_m = float(
            (concept_ref.get("excel_fallback") or {}).get("margin_nf")
            or left_p.get("margin_nf")
            or 1.45
        )
        left = _left_snapshot(
            cost,
            left_req,
            concept,
            ca_fb=excel_fb,
            ca_nf=excel_nf,
            nb_ventes=excel_ventes,
            margin_fb=excel_fb_m,
            margin_nf=excel_nf_m,
        )

        # Colonne droite = hôtel désigné projeté avec référence de CETTE solution
        right_req = _build_request(
            hotel_code=code,
            hotel_name=hotel_name,
            hotel_brand=hotel_brand,
            nb_chambres=n,
            taux_occupation=to,
            guests_per_chambre=g,
            m_lin=ml,
            mix_fb=mx,
            client_needs=needs,
            concept=concept,
        )
        right = _right_snapshot(rev, cost, right_req, concept)

        # Fusionner steps left/right pour l'UI (même id)
        dual_steps: list[dict[str, Any]] = []
        left_by_id = {s["id"]: s for s in left.get("steps") or []}
        right_by_id = {s["id"]: s for s in right.get("steps") or []}
        order = [s["id"] for s in (right.get("steps") or [])]
        for sid in order:
            ls = left_by_id.get(sid) or {}
            rs = right_by_id.get(sid) or {}
            left_rows = ls.get("rows") or []
            right_rows = rs.get("rows") or []
            dual_steps.append(
                {
                    "id": sid,
                    "title": rs.get("title") or ls.get("title") or sid,
                    "comment": rs.get("comment") or ls.get("comment") or "",
                    "highlight": bool(rs.get("highlight") or ls.get("highlight")),
                    "left_rows": left_rows,
                    "right_rows": right_rows,
                    # Frontend unifié : label + left/right
                    "rows": _merge_dual_rows(left_rows, right_rows),
                }
            )

        right_ca_display = right.get("ca_ht")
        right_marge_display = right.get("marge_nette")
        by_concept[concept] = {
            "concept": concept,
            "label": f"{concept} STORE",
            "pilots": concept_ref.get("pilots") or [],
            "n_pilots": concept_ref.get("n_pilots") or 0,
            "method": concept_ref.get("method"),
            "source": concept_ref.get("source"),
            "left": left,
            "right": right,
            "steps": dual_steps,
            "kpi": {
                "left_ca_ht": left.get("ca_ht"),
                "right_ca_ht": right_ca_display,
                "right_ca_ht_num": right.get("ca_ht_num", right.get("ca_ht")),
                "left_marge_nette": left.get("marge_nette"),
                "right_marge_nette": right_marge_display,
                "right_marge_nette_num": right.get(
                    "marge_nette_num", right.get("marge_nette")
                ),
                "right_not_profitable": bool(right.get("not_profitable")),
                "left_amort_mois": left.get("amort_mois"),
                "right_amort_mois": right.get("amort_mois"),
            },
            # contexte Excel brut (debug / chips)
            "excel_base": {
                "ca_fb": _r(excel_fb, 2),
                "ca_nf": _r(excel_nf, 2),
                "nb_ventes": _r(excel_ventes, 1),
                "m_lin": _r(excel_ml, 2),
                "mix_fb": _r(excel_mix_fb, 4),
            },
        }

    return {
        "ok": True,
        "hotel_code": code,
        "hotel_name": hotel_name,
        "hotel_brand": hotel_brand,
        "eval_year": eval_year,
        "train_years": train_years,
        "params": {
            "nb_chambres": int(round(n)),
            "taux_occupation": _r(to, 4),
            "guests_per_chambre": _r(g, 3),
            "m_lin": _r(ml, 2),
            "mix_fb": _r(mx, 4),
            "mix_nf": _r(1.0 - mx, 4),
            "client_needs": needs,
            "has_vitrine": bool(has_vitrine),
            "nb_frigos": nb_frigos,
        },
        "concepts": by_concept,
        "recommended_concept": recommended,
        "concept_order": concept_order,
        "recommendation_reasons": reco_reasons,
        "validation_warnings": validation_warnings,
        "comments": EXCEL_COMMENTS,
    }



def list_excel_pilots(year: int | None = None) -> dict[str, Any]:
    """Liste pilotes par solution avec moyennes calculées."""
    sales = _load_sales()
    eval_year, train_years = (2026, [])
    if sales is not None and not sales.empty:
        eval_year, train_years = _years_split(sales)
        if year is not None:
            eval_year = int(year)
            train_years = [
                int(y)
                for y in sorted(sales["annee"].dropna().unique())
                if int(y) < eval_year
            ]

    by: dict[str, Any] = {}
    for c in CONCEPTS:
        by[c] = build_concept_reference(
            c, eval_year=eval_year, train_years=train_years
        )
    return {
        "ok": True,
        "eval_year": eval_year,
        "train_years": train_years,
        "by_concept": by,
        "map": load_pilot_concept_map(),
    }
