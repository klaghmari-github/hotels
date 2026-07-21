"""Jointures sans doublons de colonnes."""

from __future__ import annotations

from typing import Sequence

import pandas as pd


def coerce_join_keys(frame: pd.DataFrame, keys: Sequence[str]) -> pd.DataFrame:
    """Homogénéise les types des clés de jointure (code, année, mois)."""
    out = frame.copy()
    if "hotel_code" in keys and "hotel_code" in out.columns:
        out["hotel_code"] = out["hotel_code"].astype(str)
        out.loc[out["hotel_code"].isin(["nan", "None", "<NA>", ""]), "hotel_code"] = pd.NA
    for col in ("annee", "mois"):
        if col in keys and col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").astype("Int64")
    return out


def merge_no_duplicate_columns(
    left: pd.DataFrame,
    right: pd.DataFrame,
    *,
    on: Sequence[str],
    how: str = "left",
) -> pd.DataFrame:
    """LEFT/INNER merge en n'ajoutant que les colonnes absentes de ``left``.

    - Les clés ``on`` sont conservées une seule fois.
    - Si une colonne non-clé existe déjà à gauche, la version droite est **ignorée**
      (pas de suffixes ``_x`` / ``_y`` / ``_prox``).
    - Déduplique les lignes de ``right`` sur les clés.
    """
    if left is None or left.empty:
        return left if left is not None else pd.DataFrame()
    if right is None or right.empty:
        return left

    keys = [k for k in on if k in left.columns and k in right.columns]
    if not keys:
        return left

    left_c = coerce_join_keys(left, keys)
    right_c = coerce_join_keys(right, keys)

    new_cols = [c for c in right_c.columns if c not in left_c.columns and c not in keys]
    # Toujours garder les clés + nouvelles features uniquement
    right_slim = right_c[keys + new_cols].drop_duplicates(subset=keys, keep="first")

    if not new_cols:
        # Rien à ajouter (toutes les colonnes déjà présentes)
        return left_c

    try:
        merged = left_c.merge(
            right_slim,
            on=list(keys),
            how=how,
            validate="m:1" if how == "left" else None,
        )
    except pd.errors.MergeError:
        # Clés non uniques à droite malgré drop_duplicates — fallback sans validate
        merged = left_c.merge(right_slim, on=list(keys), how=how)

    # Nettoie uniquement les paires de suffixes pandas (col_x + col_y)
    # Ne pas toucher aux noms légitimes comme commerce_fb_100m ou meteo_x.
    cols = set(merged.columns)
    for col in list(merged.columns):
        if col.endswith("_x"):
            base = col[:-2]
            ycol = f"{base}_y"
            if ycol in cols:
                # Conflit pandas : garder _x (gauche) sous le nom de base
                merged = merged.drop(columns=[ycol])
                if base not in merged.columns:
                    merged = merged.rename(columns={col: base})
                else:
                    merged = merged.drop(columns=[col])
    return merged



def drop_duplicate_named_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """Si des noms de colonnes sont strictement en double, garde la 1ʳe occurrence."""
    if frame is None or frame.empty:
        return frame
    return frame.loc[:, ~frame.columns.duplicated(keep="first")].copy()
