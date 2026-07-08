"""Agrégations SalesPrep — étapes 1.a à 6.c."""

from __future__ import annotations

import pandas as pd

from prepare._shared.columns import sanitize_column_name
from prepare._shared.months import compute_year_month_stats, missing_boundary_months

MEASURES = ("nombre_ventes", "montant_ventes", "nombre_paniers", "nombre_produits")
FB_YEAR_COLS = (
    "nombre_categories_annee_f_b",
    "nombre_categories_annee_n_f_b",
    "pct_categories_annee_f_b",
    "pct_categories_annee_n_f_b",
)
MOIS_FB_COLS = (
    "nombre_categories_mois_f_b",
    "nombre_categories_mois_n_f_b",
    "pct_categories_mois_f_b",
    "pct_categories_mois_n_f_b",
)


def _agg_measures(frame: pd.DataFrame) -> pd.Series:
    return pd.Series(
        {
            "nombre_ventes": frame["nombre_ventes"].sum(),
            "montant_ventes": frame["montant_ventes"].sum(),
            "nombre_paniers": frame["nombre_paniers"].nunique(),
            "nombre_produits": frame["nombre_produits"].nunique(),
        }
    )


def _category_counts(frame: pd.DataFrame, suffix: str) -> pd.Series:
    fb = frame.loc[frame["categorie"] == "F_B", "sous_categorie"].nunique()
    nfb = frame.loc[frame["categorie"] == "N_F_B", "sous_categorie"].nunique()
    total = fb + nfb
    return pd.Series(
        {
            f"nombre_categories_{suffix}_f_b": fb,
            f"nombre_categories_{suffix}_n_f_b": nfb,
            f"pct_categories_{suffix}_f_b": (fb / total) if total else 0.0,
            f"pct_categories_{suffix}_n_f_b": (nfb / total) if total else 0.0,
        }
    )


def step_1a_annual_raw(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    for (hotel, year), group in frame.groupby(["nom_hotel", "annee"], dropna=False):
        months = set(group["mois"].unique())
        stats = compute_year_month_stats(months)
        row = {
            "nom_hotel": hotel,
            "annee": int(year),
            **_agg_measures(group).to_dict(),
            **_category_counts(group, "annee").to_dict(),
            "nombre_mois": stats.nombre_mois,
            "premier_mois": stats.premier_mois,
            "dernier_mois": stats.dernier_mois,
            "mois_actifs": stats.mois_actifs,
            "mois_manquants": stats.mois_manquants,
        }
        rows.append(row)
    return pd.DataFrame(rows)


def step_1b_annual_normalized(step_1a: pd.DataFrame) -> pd.DataFrame:
    out = step_1a.copy()
    for col in MEASURES:
        out[col] = out.apply(
            lambda r: (r[col] / r["mois_actifs"] * 12) if r["mois_actifs"] else 0.0,
            axis=1,
        )
    return out


def step_1c_annual_divided_by_12(step_1a: pd.DataFrame) -> pd.DataFrame:
    out = step_1a[["nom_hotel", "annee", *MEASURES]].copy()
    for col in MEASURES:
        out[col] = out[col] / 12.0
    return out


def step_2a_monthly_raw(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    for (hotel, year), year_group in frame.groupby(["nom_hotel", "annee"], dropna=False):
        months = set(year_group["mois"].unique())
        ystats = compute_year_month_stats(months)
        for month, group in year_group.groupby("mois", dropna=False):
            row = {
                "nom_hotel": hotel,
                "annee": int(year),
                "mois": int(month),
                **_agg_measures(group).to_dict(),
                **_category_counts(group, "mois").to_dict(),
                "nombre_mois": ystats.nombre_mois,
                "premier_mois": ystats.premier_mois,
                "dernier_mois": ystats.dernier_mois,
                "mois_actifs": ystats.mois_actifs,
                "mois_manquants": ystats.mois_manquants,
            }
            rows.append(row)
    return pd.DataFrame(rows)


def _impute_monthly_rows(step_2a: pd.DataFrame) -> pd.DataFrame:
    """2.b — complète les mois hors plage [premier, dernier]."""
    parts = [step_2a]
    for (hotel, year), group in step_2a.groupby(["nom_hotel", "annee"], dropna=False):
        premier = int(group["premier_mois"].iloc[0])
        dernier = int(group["dernier_mois"].iloc[0])
        actifs = int(group["mois_actifs"].iloc[0])
        existing = set(group["mois"].astype(int))
        to_add = [m for m in missing_boundary_months(premier, dernier) if m not in existing]
        if not to_add:
            continue
        avg = {
            col: group[col].sum() / actifs if actifs else 0.0
            for col in MEASURES
        }
        fb_avg = {
            col: group[col].mean()
            for col in MOIS_FB_COLS
        }
        meta = group.iloc[0][
            ["nombre_mois", "premier_mois", "dernier_mois", "mois_actifs", "mois_manquants"]
        ].to_dict()
        for month in to_add:
            parts.append(
                pd.DataFrame(
                    [
                        {
                            "nom_hotel": hotel,
                            "annee": int(year),
                            "mois": month,
                            **avg,
                            **fb_avg,
                            **meta,
                        }
                    ]
                )
            )
    return pd.concat(parts, ignore_index=True).drop_duplicates(
        subset=["nom_hotel", "annee", "mois"], keep="first"
    )


def step_2b_monthly_imputed(step_2a: pd.DataFrame) -> pd.DataFrame:
    return _impute_monthly_rows(step_2a)


def step_3a_category_monthly(frame: pd.DataFrame) -> pd.DataFrame:
    keys = ["nom_hotel", "annee", "mois", "categorie", "sous_categorie"]
    return (
        frame.groupby(keys, dropna=False)
        .agg(
            nombre_ventes=("nombre_ventes", "sum"),
            montant_ventes=("montant_ventes", "sum"),
            nombre_paniers=("nombre_paniers", "nunique"),
            nombre_produits=("nombre_produits", "nunique"),
        )
        .reset_index()
    )


def step_3b_category_imputed(step_3a: pd.DataFrame, monthly_keys: pd.DataFrame) -> pd.DataFrame:
    """Complète chaque combinaison catégorie avec les mois manquants (moyenne annuelle)."""
    parts = [step_3a]
    for keys, group in step_3a.groupby(
        ["nom_hotel", "annee", "categorie", "sous_categorie"], dropna=False
    ):
        hotel, year, cat, sub = keys
        hotel_year = monthly_keys[
            (monthly_keys["nom_hotel"] == hotel) & (monthly_keys["annee"] == year)
        ]
        if hotel_year.empty:
            continue
        premier = int(hotel_year["premier_mois"].iloc[0])
        dernier = int(hotel_year["dernier_mois"].iloc[0])
        actifs = int(hotel_year["mois_actifs"].iloc[0])
        existing = set(group["mois"].astype(int))
        for month in missing_boundary_months(premier, dernier):
            if month in existing:
                continue
            avg = {col: group[col].sum() / actifs if actifs else 0.0 for col in MEASURES}
            parts.append(
                pd.DataFrame(
                    [
                        {
                            "nom_hotel": hotel,
                            "annee": int(year),
                            "mois": month,
                            "categorie": cat,
                            "sous_categorie": sub,
                            **avg,
                        }
                    ]
                )
            )
    return pd.concat(parts, ignore_index=True)


def _pivot_measures(
    frame: pd.DataFrame,
    key_cols: list[str],
    category_col: str,
    prefix: str,
) -> pd.DataFrame:
    wide_parts = []
    for measure in MEASURES:
        pivot = frame.pivot_table(
            index=key_cols,
            columns=category_col,
            values=measure,
            aggfunc="sum",
            fill_value=0.0,
        )
        pivot.columns = [
            sanitize_column_name(f"{prefix}_{col}_{measure}") for col in pivot.columns
        ]
        wide_parts.append(pivot)
    if not wide_parts:
        return pd.DataFrame(columns=key_cols)
    merged = wide_parts[0]
    for part in wide_parts[1:]:
        merged = merged.join(part, how="outer")
    return merged.reset_index()


def step_3c_category_wide(step_3b: pd.DataFrame) -> pd.DataFrame:
    keys = ["nom_hotel", "annee", "mois"]
    by_cat = _pivot_measures(step_3b, keys, "categorie", "cat")
    by_sub = _pivot_measures(step_3b, keys, "sous_categorie", "sous_cat")
    if by_cat.empty:
        return by_sub
    if by_sub.empty:
        return by_cat
    return by_cat.merge(by_sub, on=keys, how="outer")


def _grouped_step(frame: pd.DataFrame, extra_keys: list[str]) -> pd.DataFrame:
    keys = ["nom_hotel", "annee", "mois", "categorie", "sous_categorie", *extra_keys]
    return (
        frame.groupby(keys, dropna=False)
        .agg(
            nombre_ventes=("nombre_ventes", "sum"),
            montant_ventes=("montant_ventes", "sum"),
            nombre_paniers=("nombre_paniers", "nunique"),
            nombre_produits=("nombre_produits", "nunique"),
        )
        .reset_index()
    )


def step_4a_hourly(_step_3b_base: pd.DataFrame, raw: pd.DataFrame) -> pd.DataFrame:
    return _grouped_step(raw, ["heure_vente"])


def step_4b_hourly_imputed(step_4a: pd.DataFrame, monthly_keys: pd.DataFrame) -> pd.DataFrame:
    return _impute_grouped(step_4a, monthly_keys, ["heure_vente"])


def step_4c_hourly_wide(step_4b: pd.DataFrame) -> pd.DataFrame:
    return _pivot_extra_wide(step_4b, "heure_vente", "heure")


def step_5a_weekend(raw: pd.DataFrame) -> pd.DataFrame:
    return _grouped_step(raw, ["is_weekend"])


def step_5b_weekend_imputed(step_5a: pd.DataFrame, monthly_keys: pd.DataFrame) -> pd.DataFrame:
    return _impute_grouped(step_5a, monthly_keys, ["is_weekend"])


def step_5c_weekend_wide(step_5b: pd.DataFrame) -> pd.DataFrame:
    return _pivot_extra_wide(step_5b, "is_weekend", "weekend")


def step_6a_holiday(raw: pd.DataFrame) -> pd.DataFrame:
    return _grouped_step(raw, ["is_holiday"])


def step_6b_holiday_imputed(step_6a: pd.DataFrame, monthly_keys: pd.DataFrame) -> pd.DataFrame:
    return _impute_grouped(step_6a, monthly_keys, ["is_holiday"])


def step_6c_holiday_wide(step_6b: pd.DataFrame) -> pd.DataFrame:
    return _pivot_extra_wide(step_6b, "is_holiday", "holiday")


def _impute_grouped(
    grouped: pd.DataFrame,
    monthly_keys: pd.DataFrame,
    dim_cols: list[str],
) -> pd.DataFrame:
    parts = [grouped]
    meta_keys = ["nom_hotel", "annee", *dim_cols]
    for keys, group in grouped.groupby(meta_keys, dropna=False):
        hotel, year, *dims = keys
        hotel_year = monthly_keys[
            (monthly_keys["nom_hotel"] == hotel) & (monthly_keys["annee"] == year)
        ]
        if hotel_year.empty:
            continue
        premier = int(hotel_year["premier_mois"].iloc[0])
        dernier = int(hotel_year["dernier_mois"].iloc[0])
        actifs = int(hotel_year["mois_actifs"].iloc[0])
        existing = set(group["mois"].astype(int))
        for month in missing_boundary_months(premier, dernier):
            if month in existing:
                continue
            avg = {col: group[col].sum() / actifs if actifs else 0.0 for col in MEASURES}
            row = {"nom_hotel": hotel, "annee": int(year), "mois": month, **avg}
            for dim_col, dim_val in zip(dim_cols, dims):
                row[dim_col] = dim_val
            parts.append(pd.DataFrame([row]))
    return pd.concat(parts, ignore_index=True)


def _pivot_extra_wide(frame: pd.DataFrame, dim_col: str, prefix: str) -> pd.DataFrame:
    keys = ["nom_hotel", "annee", "mois"]
    wide_parts = []
    for measure in MEASURES:
        pivot = frame.pivot_table(
            index=keys,
            columns=dim_col,
            values=measure,
            aggfunc="sum",
            fill_value=0.0,
        )
        pivot.columns = [
            sanitize_column_name(f"{prefix}_{col}_{measure}") for col in pivot.columns
        ]
        wide_parts.append(pivot)
    merged = wide_parts[0]
    for part in wide_parts[1:]:
        merged = merged.join(part, how="outer")
    return merged.reset_index()