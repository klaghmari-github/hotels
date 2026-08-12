"""
Assortiment optimal par metres lineaires.

Principe :
1. densite moyenne produits / m_lin sur les hotels de la meme solution
2. N = round(m_lin_cible * densite)
3. rang moyen de chaque nom_produit (par marge) sur les hotels de la solution
4. top N produits (filtres type F&B / NON F&B et gammes optionnels)
5. mix type + gammes = parts de representativite dans le top N
"""

from __future__ import annotations

import logging
import math
from typing import Any

import pandas as pd

from src.pipeline.engine import ConnectionPipeline

logger = logging.getLogger(__name__)

VIEWS = (
    "v_hotel_product_exposure",
    "v_solution_produits_par_m_lin",
    "v_product_margin_by_hotel",
    "v_product_mean_rank_by_solution",
)


def ensure_optimal_mix_views(cp: ConnectionPipeline) -> None:
    """Materialise les vues assortiment (create_or_replace)."""
    for name in VIEWS:
        cp.process_with_requires(name)


def _norm_type_key(raw: str) -> str:
    k = str(raw or "").strip().upper().replace(" ", "_").replace("&", "")
    if "NON" in k:
        return "NON_F_B"
    if "F" in k and "B" in k:
        return "F_B"
    return k or "UNKNOWN"


def _ui_type_label(key: str) -> str:
    if key == "NON_F_B":
        return "NON F&B"
    if key == "F_B":
        return "F&B"
    return key


def _allowed_type_set(allowed_types: list[str] | None) -> set[str] | None:
    if not allowed_types:
        return None
    out: set[str] = set()
    for t in allowed_types:
        out.add(_norm_type_key(t))
    return out or None


def _allowed_gamme_set(allowed_gammes: list[str] | None) -> set[str] | None:
    if not allowed_gammes:
        return None
    out = {str(g).strip().upper() for g in allowed_gammes if str(g).strip()}
    return out or None


def _share_dict(series: pd.Series) -> dict[str, float]:
    counts = series.value_counts(dropna=True)
    total = float(counts.sum())
    if total <= 0:
        return {}
    return {str(k): round(float(v) / total, 6) for k, v in counts.items()}


def recommend_optimal_mix(
    cp: ConnectionPipeline,
    *,
    solution: str,
    metres_lineaires: float,
    allowed_types: list[str] | None = None,
    allowed_gammes: list[str] | None = None,
    ensure_views: bool = True,
) -> dict[str, Any]:
    """
    Calcule le top N produits et les mix type / gamme proposes.

    Returns
    -------
    dict avec :
      - solution, metres_lineaires, produits_par_m_lin, n_products
      - top_products (liste)
      - type_mix (labels UI F&B / NON F&B)
      - gamme_mix (parts globales, format sim_v2)
      - gamme_mix_fb / gamme_mix_nfb (parts dans la famille, somme 1)
    """
    sol = str(solution or "").strip().upper()
    m_lin = max(float(metres_lineaires or 0.0), 0.1)
    if ensure_views:
        ensure_optimal_mix_views(cp)

    dens = cp.con.execute(
        """
        SELECT
          produits_par_m_lin,
          nombre_produits_distincts_moyen,
          nombre_hotels
        FROM v_solution_produits_par_m_lin
        WHERE solution = ?
        """,
        [sol],
    ).df()
    if dens.empty or dens.iloc[0]["produits_par_m_lin"] is None:
        raise ValueError(
            f"Pas de densite produits/m_lin pour la solution {sol}. "
            "Verifiez t_sales / t_hotel_params."
        )

    produits_par_m_lin = float(dens.iloc[0]["produits_par_m_lin"])
    n_products = max(1, int(round(m_lin * produits_par_m_lin)))

    ranks = cp.con.execute(
        """
        SELECT
          nom_produit,
          type_produit,
          gamme,
          rang_moyen,
          nombre_hotels_rang,
          marge_par_mois_moyenne
        FROM v_product_mean_rank_by_solution
        WHERE solution = ?
        ORDER BY rang_moyen ASC, nom_produit
        """,
        [sol],
    ).df()
    if ranks.empty:
        raise ValueError(f"Aucun produit classe pour la solution {sol}.")

    type_ok = _allowed_type_set(allowed_types)
    gamme_ok = _allowed_gamme_set(allowed_gammes)

    ranks = ranks.copy()
    ranks["type_norm"] = ranks["type_produit"].map(_norm_type_key)
    ranks["gamme_norm"] = ranks["gamme"].astype(str).str.strip().str.upper()

    if type_ok is not None:
        ranks = ranks[ranks["type_norm"].isin(type_ok)]
    if gamme_ok is not None:
        ranks = ranks[ranks["gamme_norm"].isin(gamme_ok)]

    if ranks.empty:
        raise ValueError(
            "Aucun produit apres filtres type/gamme. "
            "Elargissez la selection F&B / Non F&B / gammes."
        )

    top = ranks.head(n_products).reset_index(drop=True)
    n_sel = len(top)

    # Mix type (labels UI)
    type_counts = top["type_norm"].value_counts()
    type_mix = {
        _ui_type_label(str(k)): round(float(v) / n_sel, 6)
        for k, v in type_counts.items()
    }
    # garantir cles usuelles si absentes
    for lab in ("F&B", "NON F&B"):
        type_mix.setdefault(lab, 0.0)

    # Mix gammes global (parts du total = representativite top N)
    gamme_mix_global = _share_dict(top["gamme_norm"])

    # Mix gammes dans chaque famille (somme 1)
    def _family_mix(type_key: str) -> dict[str, float]:
        sub = top[top["type_norm"] == type_key]
        if sub.empty:
            return {}
        return _share_dict(sub["gamme_norm"])

    gamme_mix_fb = _family_mix("F_B")
    gamme_mix_nfb = _family_mix("NON_F_B")

    # Parts globales sim_v2 = weight(type) * part_famille
    w_fb = float(type_mix.get("F&B", 0.0))
    w_nfb = float(type_mix.get("NON F&B", 0.0))
    gamme_mix_sim: dict[str, float] = {}
    for g, p in gamme_mix_fb.items():
        gamme_mix_sim[g] = round(w_fb * float(p), 6)
    for g, p in gamme_mix_nfb.items():
        gamme_mix_sim[g] = round(gamme_mix_sim.get(g, 0.0) + w_nfb * float(p), 6)
    # renormalise si besoin
    s_g = sum(gamme_mix_sim.values())
    if s_g > 1e-12 and abs(s_g - 1.0) > 1e-6:
        gamme_mix_sim = {k: round(v / s_g, 6) for k, v in gamme_mix_sim.items()}

    products = []
    for i, row in top.iterrows():
        products.append(
            {
                "rank": int(i) + 1,
                "nom_produit": row["nom_produit"],
                "type": _ui_type_label(str(row["type_norm"])),
                "type_raw": row["type_produit"],
                "gamme": row["gamme_norm"],
                "rang_moyen": float(row["rang_moyen"]),
                "nombre_hotels_rang": int(row["nombre_hotels_rang"]),
                "marge_par_mois_moyenne": float(row["marge_par_mois_moyenne"] or 0.0),
            }
        )

    return {
        "ok": True,
        "method": "optimal_product_rank",
        "solution": sol,
        "metres_lineaires": m_lin,
        "produits_par_m_lin": produits_par_m_lin,
        "nombre_produits_distincts_moyen": float(
            dens.iloc[0]["nombre_produits_distincts_moyen"] or 0.0
        ),
        "nombre_hotels_densite": int(dens.iloc[0]["nombre_hotels"] or 0),
        "n_products_target": n_products,
        "n_products_selected": n_sel,
        "filters": {
            "allowed_types": list(type_ok) if type_ok else None,
            "allowed_gammes": list(gamme_ok) if gamme_ok else None,
        },
        "type_mix": type_mix,
        "gamme_mix": gamme_mix_sim,
        "gamme_mix_global_count": gamme_mix_global,
        "gamme_mix_fb": gamme_mix_fb,
        "gamme_mix_nfb": gamme_mix_nfb,
        "top_products": products,
    }


def hotel_exposure_frame(cp: ConnectionPipeline) -> pd.DataFrame:
    """Table d'exposition produits / m_lin par hotel (debug / admin)."""
    ensure_optimal_mix_views(cp)
    return cp.con.execute(
        """
        SELECT *
        FROM v_hotel_product_exposure
        ORDER BY solution, hotel_code
        """
    ).df()
