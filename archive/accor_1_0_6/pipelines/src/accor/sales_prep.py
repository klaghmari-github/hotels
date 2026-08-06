#!/usr/bin/env python3
"""
Pipeline ventes : hotel_sales_raw_data → hotel_sales_data.

Étapes (SalesPrepPipeline) :
  1. charge le raw (lignes de ticket / caisse)
  2. prepare_lines — normalise TYPE, GAMME, boutique → hotel_code
  3. build_monthly_sales — agrégats mensuels + mix % catégories
  4. attach_holiday_sales — jointure éventuelle calendrier
  5. écrit hotel_sales_data.xlsx

API publique : rebuild_hotel_sales_data, prepare_lines, et helpers.
Utilisé par l'onglet sales (rebuild) et en amont de all_data / concept_pilote.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Any

import pandas as pd

from archive.accor_1_0_6.pipelines.src.accor.data_io import DATA_DIR, PROJECT_ROOT, read_excel

RAW_FILENAME = "hotel_sales_raw_data.xlsx"
# Prefer extended (avec MARGE / SOLUTION / METRES_LINEAIRES) si présent
RAW_EXTENDED_FILENAME = "hotel_sales_raw_extended_data.xlsx"
RAW_SHEET = "sales_raw"
SALES_FILENAME = "hotel_sales_data.xlsx"
SALES_SHEET = "hotel_sales"

RAW_COLUMN_MAP = {
    "nom boutique": "nom_boutique",
    "nom_boutique": "nom_boutique",
    "operateur": "operateur",
    "machine": "machine",
    "date": "date",
    "heure": "heure",
    "statut": "statut",
    "code ean": "code_ean",
    "nom du produit": "nom_produit",
    "nom_produit": "nom_produit",
    "quantite": "quantite",
    "prix ht": "prix_ht",
    "vat": "vat",
    "prix ttc": "prix_ttc",
    "type": "type_raw",
    "type_raw": "type_raw",
    "gamme": "gamme_raw",
    "gamme_raw": "gamme_raw",
    "marque": "marque_produit",
    "fournisseur": "fournisseur",
    "order id (ticket de caisse)": "order_id",
    "order_id": "order_id",
    "marge": "marge",
    "prix_ttc_marche": "prix_ttc_marche",
    "prix ttc marche": "prix_ttc_marche",
    "solution": "solution",
    "hotel_code": "hotel_code_src",
    "hotel name": "hotel_name_src",
    "hotel_name": "hotel_name_src",
    "metres_lineaires": "metres_lineaires",
}

TYPE_MAP = {
    "f&b": "f_b",
    "f_b": "f_b",
    "f-b": "f_b",
    "fb": "f_b",
    "food": "f_b",
    "non-f&b": "n_f_b",
    "non_f&b": "n_f_b",
    "non-f_b": "n_f_b",
    "non_f_b": "n_f_b",
    "n-f&b": "n_f_b",
    "n_f_b": "n_f_b",
    "n-f_b": "n_f_b",
    "non fb": "n_f_b",
    "non_fb": "n_f_b",
}

GAMME_MAP = {
    "sans alcool": "sans_alcool",
    "sans-alcool": "sans_alcool",
    "sans_alcool": "sans_alcool",
    "food sucree": "food_sucree",
    "food sucrée": "food_sucree",
    "food_sucree": "food_sucree",
    "sugary food": "food_sucree",
    "sugary-food": "food_sucree",
    "sugary_food": "food_sucree",
    "food salee": "food_salee",
    "food salée": "food_salee",
    "food_salee": "food_salee",
    "salty food": "food_salee",
    "salty-food": "food_salee",
    "salty_food": "food_salee",
    "sos": "sos",
    "alcool": "alcool",
    "accessoires": "accessoires",
    "jeux / enfants": "jeux_enfants",
    "jeux enfants": "jeux_enfants",
    "jeu_enfants": "jeux_enfants",
    "jeux_enfants": "jeux_enfants",
    "cosmetique": "cosmetique",
    "cosmétique": "cosmetique",
    "pap": "pap",
    "souvenirs": "souvenirs",
    "formule": "formule",
    "ref": "ref",
}

MEASURES = (
    "nombre_ventes",
    "montant_ventes",
    "montant_marge",
    "nombre_paniers",
    "nombre_produits",
)
SOUS_CAT_SLUGS = (
    "ref",
    "accessoires",
    "alcool",
    "cosmetique",
    "food_salee",
    "food_sucree",
    "jeux_enfants",
    "pap",
    "sans_alcool",
    "sos",
    "souvenirs",
)

HOLIDAY_SALES_COLS = (
    "nombre_ventes_holidays",
    "montant_ventes_holidays",
    "nombre_ventes_hors_holidays",
    "montant_ventes_hors_holidays",
    "pct_nombre_ventes_holidays",
    "pct_montant_ventes_holidays",
    "pct_nombre_ventes_hors_holidays",
    "pct_montant_ventes_hors_holidays",
)


# ---------------------------------------------------------------------------
# Normalisations de libelles (reutilisees hors pipeline)
# ---------------------------------------------------------------------------


def _strip_accents(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normalize_label(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).strip()
    if not text or text.upper() in {"#REF!", "#N/A", "N/A", "NAN", "NONE", "?", "NULL"}:
        return ""
    if text.upper().startswith("#"):
        return ""
    text = _strip_accents(text).lower()
    text = re.sub(r"\s+", " ", text)
    return text


def slugify(value: str) -> str:
    text = normalize_label(value)
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return text or "autre"


def normalize_type(value: Any) -> str:
    key = normalize_label(value).replace(" ", "_")
    key2 = normalize_label(value)
    if key in TYPE_MAP:
        return TYPE_MAP[key]
    if key2 in TYPE_MAP:
        return TYPE_MAP[key2]
    if "non" in key2 and "f" in key2:
        return "n_f_b"
    if "f&b" in key2 or key2 in {"fb", "f_b"}:
        return "f_b"
    return "n_f_b"


def normalize_gamme(value: Any) -> str:
    key = normalize_label(value)
    if key in GAMME_MAP:
        return GAMME_MAP[key]
    return slugify(value) if key else "autre"


def sales_path() -> Path:
    return DATA_DIR / SALES_FILENAME


def load_hotel_lookup() -> pd.DataFrame:
    path = DATA_DIR / "hotel_data.xlsx"
    hotels = read_excel(path, sheet=0)
    if hotels.empty or "hotel_code" not in hotels.columns or "hotel_name" not in hotels.columns:
        return pd.DataFrame(columns=["hotel_code", "hotel_name", "nom_key"])
    out = hotels[["hotel_code", "hotel_name"]].drop_duplicates().copy()
    out["nom_key"] = out["hotel_name"].map(normalize_label)
    return out


class HotelBoutiqueMatcher:
    """Associe NOM BOUTIQUE → hotel_code (exact, containment, tokens)."""

    def __init__(self, lookup: pd.DataFrame | None = None) -> None:
        self.lookup = lookup if lookup is not None else load_hotel_lookup()
        self._cache: dict[str, tuple[str | None, str | None]] = {}

    def match(self, nom_boutique: str) -> tuple[str | None, str | None]:
        if nom_boutique in self._cache:
            return self._cache[nom_boutique]
        result = match_hotel_code(nom_boutique, self.lookup)
        self._cache[nom_boutique] = result
        return result


def match_hotel_code(
    nom_boutique: str, lookup: pd.DataFrame
) -> tuple[str | None, str | None]:
    key = normalize_label(nom_boutique)
    if not key or lookup.empty:
        return None, None
    hit = lookup.loc[lookup["nom_key"] == key]
    if len(hit):
        row = hit.iloc[0]
        return str(row["hotel_code"]), str(row["hotel_name"])
    for _, row in lookup.iterrows():
        nk = row["nom_key"]
        if not nk:
            continue
        if key in nk or nk in key:
            return str(row["hotel_code"]), str(row["hotel_name"])
    tokens = set(key.split())
    best_score, best = 0, None
    for _, row in lookup.iterrows():
        nk = row["nom_key"]
        if not nk:
            continue
        score = len(tokens & set(nk.split()))
        if tokens and nk.split() and list(tokens)[0] == nk.split()[0]:
            score += 0.5
        if score > best_score:
            best_score = score
            best = row
    if best is not None and best_score >= 2:
        return str(best["hotel_code"]), str(best["hotel_name"])
    return None, None


def _normalize_raw_columns(frame: pd.DataFrame) -> pd.DataFrame:
    rename = {}
    for c in frame.columns:
        key = normalize_label(c)
        if key in RAW_COLUMN_MAP:
            rename[c] = RAW_COLUMN_MAP[key]
        else:
            slug = slugify(c)
            if slug in RAW_COLUMN_MAP.values():
                rename[c] = slug
    out = frame.rename(columns=rename)
    # Extended export has TYPE + TYPE_RAW (both → type_raw) and GAMME + GAMME_RAW.
    # Keep the first occurrence (cleaned TYPE/GAMME columns come first).
    if out.columns.duplicated().any():
        out = out.loc[:, ~out.columns.duplicated()].copy()
    return out


def raw_path() -> Path:
    """Préfère le fichier extended (marge / solution) s'il existe."""
    ext = DATA_DIR / RAW_EXTENDED_FILENAME
    if ext.exists():
        return ext
    return DATA_DIR / RAW_FILENAME


def load_raw_sales(path: Path | None = None) -> pd.DataFrame:
    path = path or raw_path()
    if not path.exists():
        legacy = (
            PROJECT_ROOT.parent
            / "archive"
            / "sources"
            / "raw"
            / "001.queryVentes.csv"
        )
        if legacy.exists():
            frame = pd.read_csv(legacy, dtype=str, low_memory=False)
            return _normalize_raw_columns(frame)
        return pd.DataFrame()
    # extended n'a souvent pas de sheet sales_raw
    try:
        frame = read_excel(path, sheet=RAW_SHEET, dtype=str)
    except Exception:
        frame = pd.DataFrame()
    if frame is None or frame.empty:
        frame = read_excel(path, sheet=0, dtype=str)
    return _normalize_raw_columns(frame)


def import_raw_from_csv(csv_path: Path, dest: Path | None = None) -> Path:
    dest = dest or raw_path()
    frame = pd.read_csv(csv_path, low_memory=False)
    frame = _normalize_raw_columns(frame)
    dest.parent.mkdir(parents=True, exist_ok=True)
    frame.to_excel(dest, index=False, sheet_name=RAW_SHEET)
    return dest


def prepare_lines(
    raw: pd.DataFrame,
    lookup: pd.DataFrame,
    *,
    matcher: HotelBoutiqueMatcher | None = None,
) -> pd.DataFrame:
    """Normalise les lignes brutes + attache hotel_code."""
    if raw is None or raw.empty:
        return pd.DataFrame()
    df = raw.copy()
    if "statut" in df.columns:
        st = df["statut"].astype(str).str.strip().str.upper()
        keep = (
            st.eq("DONE")
            | st.isin(["", "NAN", "NONE", "NAT"])
            | df["statut"].isna()
        )
        df = df.loc[keep].copy()
    if "date" not in df.columns:
        raise ValueError("Colonne DATE / date manquante dans les ventes brutes.")
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"])
    df["annee"] = df["date"].dt.year.astype(int)
    df["mois"] = df["date"].dt.month.astype(int)

    q = (
        pd.to_numeric(df["quantite"] if "quantite" in df.columns else 1, errors="coerce")
        .fillna(1.0)
        .clip(lower=0)
    )
    ht = (
        pd.to_numeric(df["prix_ht"], errors="coerce")
        if "prix_ht" in df.columns
        else pd.Series(pd.NA, index=df.index)
    )
    ttc = (
        pd.to_numeric(df["prix_ttc"], errors="coerce")
        if "prix_ttc" in df.columns
        else pd.Series(pd.NA, index=df.index)
    )
    unit = ht.fillna(ttc).fillna(0.0)
    df["nombre_ventes"] = q
    # PRIX_TTC extended = total ligne (ne pas re-multiplier) ; sinon unit × qty
    if "prix_ttc" in df.columns and ttc.notna().any():
        # Heuristique : si médiane TTC ≈ HT*(1+TVA) pour q>1 → unitaire
        # Sinon (fichier extended) TTC est déjà le total de ligne.
        df["montant_ventes"] = ttc.fillna(unit * q).astype(float)
    else:
        df["montant_ventes"] = (unit * q).astype(float)

    # Marge (cible finale ML) — colonne MARGE du extended, sinon TTC − marché
    if "marge" in df.columns:
        df["montant_marge"] = pd.to_numeric(df["marge"], errors="coerce").fillna(0.0)
    elif "prix_ttc_marche" in df.columns:
        marche = pd.to_numeric(df["prix_ttc_marche"], errors="coerce").fillna(0.0)
        df["montant_marge"] = (df["montant_ventes"] - marche).astype(float)
    else:
        df["montant_marge"] = 0.0

    if "order_id" in df.columns:
        df["order_id"] = df["order_id"].astype(str)
    else:
        df["order_id"] = [f"row_{i}" for i in range(len(df))]
    if "code_ean" in df.columns:
        df["code_ean"] = df["code_ean"].astype(str)
    else:
        df["code_ean"] = (
            df["nom_produit"].astype(str) if "nom_produit" in df.columns else ""
        )
    type_src = df["type_raw"] if "type_raw" in df.columns else pd.Series("", index=df.index)
    gamme_src = (
        df["gamme_raw"] if "gamme_raw" in df.columns else pd.Series("", index=df.index)
    )
    df["categorie"] = type_src.map(normalize_type)
    df["sous_categorie"] = gamme_src.map(normalize_gamme)

    if "nom_boutique" not in df.columns and "hotel_code_src" not in df.columns:
        raise ValueError(
            "Colonne NOM BOUTIQUE / nom_boutique (ou HOTEL_CODE) manquante."
        )
    matcher = matcher or HotelBoutiqueMatcher(lookup)
    boutique_series = (
        df["nom_boutique"].astype(str)
        if "nom_boutique" in df.columns
        else pd.Series([""] * len(df), index=df.index)
    )

    # Prefer HOTEL_CODE from extended export (vectorized)
    codes: pd.Series
    if "hotel_code_src" in df.columns:
        src = df["hotel_code_src"].astype(str).str.strip()
        bad = src.isin(("", "nan", "None", "NaT", "<NA>")) | df["hotel_code_src"].isna()
        codes = src.mask(bad, other=pd.NA)
    else:
        codes = pd.Series(pd.NA, index=df.index, dtype=object)

    # Fallback: boutique name → hotel_code (unique names only)
    need = codes.isna()
    if need.any() and boutique_series.notna().any():
        unique_noms = boutique_series.loc[need].dropna().unique()
        mapping: dict[str, tuple[str | None, str | None]] = {}
        for nom in unique_noms:
            mapping[str(nom)] = matcher.match(str(nom))
        matched = boutique_series.loc[need].map(
            lambda n: mapping.get(str(n), (None, None))[0]
        )
        codes.loc[need] = matched.values

    # Display names from lookup / extended / boutique
    lookup_names = {}
    if not lookup.empty and "hotel_code" in lookup.columns:
        lu = lookup.drop_duplicates("hotel_code", keep="first")
        lookup_names = dict(
            zip(
                lu["hotel_code"].astype(str).str.strip(),
                lu["hotel_name"].astype(str),
            )
        )
    name_ref = codes.map(lambda c: lookup_names.get(str(c)) if pd.notna(c) else None)
    if "hotel_name_src" in df.columns:
        hn = df["hotel_name_src"].astype(str)
        df["nom_hotel"] = boutique_series.where(
            boutique_series.ne("") & boutique_series.notna(), hn
        ).astype(str)
    else:
        df["nom_hotel"] = boutique_series.astype(str)
    df["hotel_code"] = codes
    df["hotel_name_ref"] = name_ref.fillna(df["nom_hotel"])
    return df


def build_monthly_sales(lines: pd.DataFrame) -> pd.DataFrame:
    """Agrege hotel x annee x mois + mix cat / sous-cat (pct)."""
    if lines is None or lines.empty:
        return pd.DataFrame()

    keys = ["hotel_code", "nom_hotel", "annee", "mois"]
    agg_map = {
        "nombre_ventes": ("nombre_ventes", "sum"),
        "montant_ventes": ("montant_ventes", "sum"),
        "nombre_paniers": ("order_id", "nunique"),
        "nombre_produits": ("code_ean", "nunique"),
    }
    if "montant_marge" in lines.columns:
        agg_map["montant_marge"] = ("montant_marge", "sum")
    base = (
        lines.groupby(keys, dropna=False)
        .agg(**{k: v for k, v in agg_map.items()})
        .reset_index()
    )
    if "montant_marge" not in base.columns:
        base["montant_marge"] = 0.0

    cat_counts = (
        lines.groupby(keys + ["categorie"], dropna=False)["sous_categorie"]
        .nunique()
        .reset_index(name="n_sous")
    )
    n_fb = cat_counts[cat_counts["categorie"] == "f_b"][keys + ["n_sous"]].rename(
        columns={"n_sous": "nombre_categories_mois_f_b"}
    )
    n_nfb = cat_counts[cat_counts["categorie"] == "n_f_b"][keys + ["n_sous"]].rename(
        columns={"n_sous": "nombre_categories_mois_n_f_b"}
    )
    base = base.merge(n_fb, on=keys, how="left").merge(n_nfb, on=keys, how="left")
    base["nombre_categories_mois_f_b"] = base["nombre_categories_mois_f_b"].fillna(0)
    base["nombre_categories_mois_n_f_b"] = base["nombre_categories_mois_n_f_b"].fillna(0)
    tot_n = base["nombre_categories_mois_f_b"] + base["nombre_categories_mois_n_f_b"]
    base["pct_categories_mois_f_b"] = (
        base["nombre_categories_mois_f_b"] / tot_n.replace(0, pd.NA)
    ).fillna(0.0)
    base["pct_categories_mois_n_f_b"] = (
        base["nombre_categories_mois_n_f_b"] / tot_n.replace(0, pd.NA)
    ).fillna(0.0)

    cat_agg = {
        "nombre_ventes": ("nombre_ventes", "sum"),
        "montant_ventes": ("montant_ventes", "sum"),
        "nombre_paniers": ("order_id", "nunique"),
        "nombre_produits": ("code_ean", "nunique"),
    }
    if "montant_marge" in lines.columns:
        cat_agg["montant_marge"] = ("montant_marge", "sum")
    by_cat = (
        lines.groupby(keys + ["categorie"], dropna=False)
        .agg(**{k: v for k, v in cat_agg.items()})
        .reset_index()
    )
    for measure in MEASURES:
        if measure not in by_cat.columns:
            by_cat[measure] = 0.0
    for measure in MEASURES:
        for cat in ("f_b", "n_f_b"):
            col = f"pct_cat_{cat}_{measure}"
            sub = by_cat.loc[by_cat["categorie"] == cat, keys + [measure]].rename(
                columns={measure: "_v"}
            )
            base = base.merge(sub, on=keys, how="left")
            base["_v"] = base["_v"].fillna(0.0)
            base[col] = (base["_v"] / base[measure].replace(0, pd.NA)).fillna(0.0)
            base = base.drop(columns=["_v"])

    sub_agg = {
        "nombre_ventes": ("nombre_ventes", "sum"),
        "montant_ventes": ("montant_ventes", "sum"),
        "nombre_paniers": ("order_id", "nunique"),
        "nombre_produits": ("code_ean", "nunique"),
    }
    if "montant_marge" in lines.columns:
        sub_agg["montant_marge"] = ("montant_marge", "sum")
    by_sub = (
        lines.groupby(keys + ["categorie", "sous_categorie"], dropna=False)
        .agg(**{k: v for k, v in sub_agg.items()})
        .reset_index()
    )
    for measure in MEASURES:
        if measure not in by_sub.columns:
            by_sub[measure] = 0.0
    cat_tot = by_sub.groupby(keys + ["categorie"], dropna=False)[list(MEASURES)].transform(
        "sum"
    )
    for measure in MEASURES:
        by_sub[f"_pct_{measure}"] = (
            by_sub[measure] / cat_tot[measure].replace(0, pd.NA)
        ).fillna(0.0)

    for measure in MEASURES:
        for slug in SOUS_CAT_SLUGS:
            col = f"pct_sous_cat_{slug}_{measure}"
            sub = (
                by_sub.loc[by_sub["sous_categorie"] == slug, keys + [f"_pct_{measure}"]]
                .groupby(keys, dropna=False)[f"_pct_{measure}"]
                .sum()
                .reset_index()
                .rename(columns={f"_pct_{measure}": col})
            )
            base = base.merge(sub, on=keys, how="left")
            base[col] = base[col].fillna(0.0)

    base["hotel_code"] = base["hotel_code"].astype(str)
    sort_cols = [c for c in ("hotel_code", "annee", "mois") if c in base.columns]
    if sort_cols:
        base = base.sort_values(sort_cols).reset_index(drop=True)
    return base


def attach_holiday_sales(
    lines: pd.DataFrame,
    monthly: pd.DataFrame,
    holidays: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Split ventes holidays / hors holidays sur le grain mensuel."""
    from archive.accor_1_0_6.pipelines.src.accor.geo_holidays import holidays_day_sets, load_holidays_frame

    out = monthly.copy()
    for c in HOLIDAY_SALES_COLS:
        out[c] = 0.0
    if lines is None or lines.empty:
        return out
    if holidays is None:
        holidays = load_holidays_frame()
    day_sets = holidays_day_sets(holidays)

    work = lines.copy()
    if "date" not in work.columns:
        return out
    work["date"] = pd.to_datetime(work["date"], errors="coerce")
    work = work.dropna(subset=["date"])
    work["_iso"] = work["date"].dt.strftime("%Y-%m-%d")
    work["annee"] = work["date"].dt.year.astype(int)
    work["mois"] = work["date"].dt.month.astype(int)

    def _is_hol(row: pd.Series) -> bool:
        code = str(row.get("hotel_code") or "").strip()
        key = (code, int(row["annee"]), int(row["mois"]))
        days = day_sets.get(key)
        if not days:
            return False
        return str(row["_iso"]) in days

    work["is_holiday_day"] = work.apply(_is_hol, axis=1)
    keys = ["hotel_code", "annee", "mois"]
    hol = (
        work.loc[work["is_holiday_day"]]
        .groupby(keys, dropna=False)
        .agg(
            nombre_ventes_holidays=("nombre_ventes", "sum"),
            montant_ventes_holidays=("montant_ventes", "sum"),
        )
        .reset_index()
    )
    nhol = (
        work.loc[~work["is_holiday_day"]]
        .groupby(keys, dropna=False)
        .agg(
            nombre_ventes_hors_holidays=("nombre_ventes", "sum"),
            montant_ventes_hors_holidays=("montant_ventes", "sum"),
        )
        .reset_index()
    )
    out = out.merge(hol, on=keys, how="left", suffixes=("", "_h"))
    out = out.merge(nhol, on=keys, how="left", suffixes=("", "_n"))
    for c in (
        "nombre_ventes_holidays",
        "montant_ventes_holidays",
        "nombre_ventes_hors_holidays",
        "montant_ventes_hors_holidays",
    ):
        if f"{c}_h" in out.columns:
            out[c] = out[f"{c}_h"].fillna(out.get(c, 0)).fillna(0)
            out = out.drop(columns=[f"{c}_h"])
        if f"{c}_n" in out.columns:
            out[c] = out[f"{c}_n"].fillna(out.get(c, 0)).fillna(0)
            out = out.drop(columns=[f"{c}_n"])
        if c not in out.columns:
            out[c] = 0.0
        else:
            out[c] = pd.to_numeric(out[c], errors="coerce").fillna(0.0)

    nv = out["nombre_ventes"].replace(0, pd.NA)
    mv = out["montant_ventes"].replace(0, pd.NA)
    out["pct_nombre_ventes_holidays"] = (out["nombre_ventes_holidays"] / nv).fillna(0.0)
    out["pct_montant_ventes_holidays"] = (out["montant_ventes_holidays"] / mv).fillna(0.0)
    out["pct_nombre_ventes_hors_holidays"] = (
        out["nombre_ventes_hors_holidays"] / nv
    ).fillna(0.0)
    out["pct_montant_ventes_hors_holidays"] = (
        out["montant_ventes_hors_holidays"] / mv
    ).fillna(0.0)

    miss_n = out["nombre_ventes_hors_holidays"].eq(0) & out["nombre_ventes"].gt(0)
    out.loc[miss_n, "nombre_ventes_hors_holidays"] = (
        out.loc[miss_n, "nombre_ventes"] - out.loc[miss_n, "nombre_ventes_holidays"]
    ).clip(lower=0)
    miss_m = out["montant_ventes_hors_holidays"].eq(0) & out["montant_ventes"].gt(0)
    out.loc[miss_m, "montant_ventes_hors_holidays"] = (
        out.loc[miss_m, "montant_ventes"] - out.loc[miss_m, "montant_ventes_holidays"]
    ).clip(lower=0)
    out["pct_nombre_ventes_hors_holidays"] = (
        out["nombre_ventes_hors_holidays"] / nv
    ).fillna(0.0)
    out["pct_montant_ventes_hors_holidays"] = (
        out["montant_ventes_hors_holidays"] / mv
    ).fillna(0.0)
    return out


class SalesPrepPipeline:
    """
    Pipeline raw → hotel_sales_data (etapes reutilisables).

        SalesPrepPipeline().run()
        SalesPrepPipeline(raw=df, drop_unmatched=False).run()
    """

    def __init__(
        self,
        *,
        raw: pd.DataFrame | None = None,
        drop_unmatched: bool = True,
        lookup: pd.DataFrame | None = None,
    ) -> None:
        self.raw = raw
        self.drop_unmatched = drop_unmatched
        self.lookup = lookup if lookup is not None else load_hotel_lookup()
        self.lines = pd.DataFrame()
        self.monthly = pd.DataFrame()
        self.n_raw = 0
        self.n_unmatched = 0
        self.holidays_joined = False

    def load_raw(self) -> "SalesPrepPipeline":
        if self.raw is None:
            self.raw = load_raw_sales()
        if self.raw is None or self.raw.empty:
            raise ValueError(
                "Ventes brutes introuvables. Placez hotel_sales_raw_data.xlsx "
                "ou importez archive/sources/raw/001.queryVentes.csv."
            )
        return self

    def prepare(self) -> "SalesPrepPipeline":
        matcher = HotelBoutiqueMatcher(self.lookup)
        self.lines = prepare_lines(self.raw, self.lookup, matcher=matcher)
        self.n_raw = len(self.lines)
        self.n_unmatched = (
            int(self.lines["hotel_code"].isna().sum())
            if "hotel_code" in self.lines.columns
            else self.n_raw
        )
        if self.drop_unmatched and "hotel_code" in self.lines.columns:
            self.lines = self.lines.loc[self.lines["hotel_code"].notna()].copy()
        if self.lines.empty:
            raise ValueError(
                f"Aucune ligne matchee sur hotel_data "
                f"({self.n_unmatched}/{self.n_raw} non liees)."
            )
        return self

    def aggregate(self) -> "SalesPrepPipeline":
        self.monthly = build_monthly_sales(self.lines)
        return self

    def join_holidays(self) -> "SalesPrepPipeline":
        from archive.accor_1_0_6.pipelines.src.accor.geo_holidays import load_holidays_frame

        holidays = load_holidays_frame()
        self.monthly = attach_holiday_sales(
            self.lines, self.monthly, holidays=holidays
        )
        self.holidays_joined = not holidays.empty if holidays is not None else False
        return self

    def write(self, path: Path | None = None) -> Path:
        path = path or sales_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        self.monthly.to_excel(path, index=False, sheet_name=SALES_SHEET)
        return path

    def run(self) -> dict[str, Any]:
        self.load_raw().prepare().aggregate().join_holidays()
        path = self.write()
        monthly = self.monthly
        return {
            "ok": True,
            "path": str(path),
            "rows": len(monthly),
            "columns": list(monthly.columns),
            "n_columns": len(monthly.columns),
            "n_raw_lines": self.n_raw,
            "n_unmatched": self.n_unmatched,
            "n_hotels": int(monthly["hotel_code"].nunique())
            if "hotel_code" in monthly.columns
            else 0,
            "years": sorted(monthly["annee"].dropna().unique().tolist())
            if "annee" in monthly.columns
            else [],
            "holidays_joined": self.holidays_joined,
        }


def rebuild_hotel_sales_data(
    *,
    raw: pd.DataFrame | None = None,
    drop_unmatched: bool = True,
) -> dict[str, Any]:
    """Facade stable : pipeline complet raw → hotel_sales_data.xlsx."""
    return SalesPrepPipeline(raw=raw, drop_unmatched=drop_unmatched).run()


def ensure_raw_sales_from_archive() -> Path | None:
    dest = raw_path()
    if dest.exists():
        return dest
    legacy = (
        PROJECT_ROOT.parent
        / "archive"
        / "sources"
        / "raw"
        / "001.queryVentes.csv"
    )
    if legacy.exists():
        return import_raw_from_csv(legacy, dest)
    return None
