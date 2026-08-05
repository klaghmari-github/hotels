#!/usr/bin/env python3
"""
Étend hotel_sales_raw_clean_data.xlsx avec :

  - SOLUTION            simply | liberty | connected (pilotes ROD)
  - HOTEL_CODE          code hôtel Accor
  - HOTEL_NAME          nom hôtel (hotel_data, sinon NOM_BOUTIQUE)
  - METRES_LINEAIRES    m_lin corner hôtel (même source que le simulateur)
  - HOTEL_NB_CHAMBRES / HOTEL_TO_ANNUEL / HOTEL_GUESTS_PER_CHAMBRE
  - COEF_MARGE          coef marge Excel (solution × catégorie F&B / N-F&B)
  - MONTANT_ACHATS_SELON_COEF   PRIX_HT / COEF_MARGE
  - MARGE_SELON_COEF            PRIX_HT − MONTANT_ACHATS_SELON_COEF
  - PRIX_TTC_MARCHE     prix unitaire marché (médiane) × QUANTITE
  - MARGE               PRIX_TTC − PRIX_TTC_MARCHE
                        (PRIX_TTC est déjà le total ligne)

Ordre des colonnes (aligné notebook main.ipynb) :
  SOLUTION, HOTEL_CODE, HOTEL_NAME, METRES_LINEAIRES,
  HOTEL_NB_CHAMBRES, HOTEL_TO_ANNUEL, HOTEL_GUESTS_PER_CHAMBRE,
  TYPE / GAMME / NOM_PRODUIT (+ raw + CATEGORIE),
  puis le reste, puis COEF_MARGE, MONTANT_ACHATS_SELON_COEF,
  MARGE_SELON_COEF, PRIX_TTC_MARCHE, MARGE

Mètres linéaires (aligné hotel_context / director) :
  hotel_metres_lineaires_dedies_corner
  sinon hotel_corner_de_vente_actuel_metres_lineaires
  (NaN si non renseigné dans hotel_data — le simulateur bascule alors sur 6 m)

Usage :
  python extend_hotel_sales.py
  python extend_hotel_sales.py \\
      --clean data/hotel_sales_raw_clean_data.xlsx \\
      --out   data/hotel_sales_raw_extended_data.xlsx
"""

from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
DEFAULT_CLEAN = ROOT / "data" / "hotel_sales_raw_clean_data.xlsx"
DEFAULT_OUT = ROOT / "data" / "hotel_sales_raw_extended_data.xlsx"
DEFAULT_HOTEL = ROOT / "data" / "hotel_data.xlsx"
DEFAULT_ROD_REF = ROOT / "data" / "rod_reference.json"

# Colonnes hotel_data (même ordre de priorité que HotelContextBuilder)
COL_M_LIN_DEDIE = "hotel_metres_lineaires_dedies_corner"
COL_M_LIN_ACTUEL = "hotel_corner_de_vente_actuel_metres_lineaires"

# Guests / chambre : défauts marque (hotel_data n'a pas ce champ)
# Aligné hotel_context / pilot Excel
BRAND_GUESTS_DEFAULT: dict[str, float] = {
    "IBIS BUDGET": 1.7,
    "IBIS STYLES": 2.0,
    "NOVOTEL": 1.8,
    "MERCURE": 2.0,
    "IBIS": 1.8,
}
SOLUTION_GUESTS_DEFAULT: dict[str, float] = {
    "simply": 1.7,
    "liberty": 2.2,
    "connected": 1.8,
}

# Coef marge Excel (rod_reference) : par solution × canal F&B / N-F&B
# Formule simu : marge = CA_HT − CA_HT / coef  ⇒  achats = CA_HT / coef
DEFAULT_COEF_MARGE: dict[str, dict[str, float]] = {
    "simply": {"fb": 2.6, "nfb": 1.45},
    "liberty": {"fb": 2.6, "nfb": 2.0},
    "connected": {"fb": 2.6, "nfb": 1.8},
}

# Boutique caisse (NOM_BOUTIQUE) → hotel_code Accor
# Source : archive/data/reference/hotel_identity_registry.json + tests + rod_recap
# Attention : "Novotel Paris Tour Eiffel" = H3546 Centre (Quai de Grenelle),
# PAS H1978 Vaugirard Montparnasse (faux positif du matcher fuzzy).
BOUTIQUE_TO_CODE: dict[str, str] = {
    "ibis budget nice": "H2075",
    "ibis budget strasbourg centre republique": "HB6A3",
    "mercure paris boulogne": "H6188",
    "novotel megeve mont blanc": "HB5I0",
    "mercure paris montmartre sacre coeur": "H0373",
    "novotel paris tour eiffel": "H3546",
    "novotel paris centre tour eiffel": "H3546",
    "novotel porte d italie": "H5586",
    "novotel paris 13 porte d italie": "H5586",
}

# Mètres linéaires dédiés — source brute :
# archive/sources/raw/Récapitulatif de l'ensemble des données ROD (2).xlsx
# feuille RECAP DATA ROD, ligne D129 « MÈTRES LINÉAIRES DEDIES A VOTRE CORNER »
# Colonnes K→Q = NICE, STRASBOURG, CDG, MEGEVE, TOUR EIFFEL, MONTMARTRE, BOULOGNE
# Porte d'Italie n'est PAS dans ce fichier source (pas de valeur officielle).
METRES_LINEAIRES_RECAP: dict[str, float] = {
    "H2075": 6.0,  # IBB Nice
    "HB6A3": 2.0,  # IBB Strasbourg
    "H0815": 5.0,  # Ibis Styles Roissy CDG (hors ventes)
    "HB5I0": 8.0,  # Novotel Megève
    "H3546": 7.0,  # Novotel Paris Centre Tour Eiffel
    "H0373": 6.0,  # Mercure Montmartre
    "H6188": 6.0,  # Mercure Boulogne
}


def _norm(s: object) -> str:
    text = str(s).strip().lower()
    # Ligatures / caractères spéciaux FR avant NFKD
    for a, b in (
        ("œ", "oe"),
        ("æ", "ae"),
        ("ß", "ss"),
        ("’", "'"),
        ("‘", "'"),
        ("ʼ", "'"),
    ):
        text = text.replace(a, b)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def boutique_to_code(name: object) -> str | None:
    """Match exact sur nom normalisé uniquement (pas de fuzzy substring)."""
    key = _norm(name)
    return BOUTIQUE_TO_CODE.get(key)


def load_pilot_map() -> dict[str, str]:
    """hotel_code → simply|liberty|connected (rod_pilot_concepts.json)."""
    sys.path.insert(0, str(ROOT / "src"))
    from accor.hotel_solutions import load_pilot_solution_codes

    raw = load_pilot_solution_codes()
    return {code: sol.lower() for code, sol in raw.items()}


def _norm_brand(brand: object) -> str:
    s = str(brand or "").strip().upper().replace("_", " ")
    s = re.sub(r"\s+", " ", s)
    return s


def guests_for_brand(brand: object, solution: object = None) -> float:
    """Guests / chambre : défaut marque, sinon pivot solution, sinon 1.7."""
    g = BRAND_GUESTS_DEFAULT.get(_norm_brand(brand))
    if g is not None:
        return float(g)
    sol = str(solution or "").strip().lower()
    if sol in SOLUTION_GUESTS_DEFAULT:
        return float(SOLUTION_GUESTS_DEFAULT[sol])
    return 1.7


def load_coef_marge_by_solution(rod_ref_path: Path | None = None) -> dict[str, dict[str, float]]:
    """
    Coefs marge Excel par solution et canal (F&B / N-F&B).

    Source : data/rod_reference.json (margin_fb_pct / margin_nf_pct).
    """
    out = {k: dict(v) for k, v in DEFAULT_COEF_MARGE.items()}
    path = rod_ref_path or DEFAULT_ROD_REF
    if not path.exists():
        return out
    import json

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        concepts = data.get("concepts") or {}
        for sol_key, sol_norm in (
            ("SIMPLY", "simply"),
            ("LIBERTY", "liberty"),
            ("CONNECTED", "connected"),
        ):
            node = concepts.get(sol_key) or {}
            if node.get("margin_fb_pct") is not None:
                out[sol_norm]["fb"] = float(node["margin_fb_pct"])
            if node.get("margin_nf_pct") is not None:
                out[sol_norm]["nfb"] = float(node["margin_nf_pct"])
            if node.get("pivot_guests_per_chambre") is not None:
                SOLUTION_GUESTS_DEFAULT[sol_norm] = float(
                    node["pivot_guests_per_chambre"]
                )
    except Exception:
        pass
    return out


def is_fb_row(row_type: object, categorie: object = None) -> bool:
    """True si ligne F&B (TYPE ou CATEGORIE)."""
    for v in (row_type, categorie):
        if v is None or (isinstance(v, float) and pd.isna(v)):
            continue
        s = str(v).strip().upper().replace("&", "_").replace("-", "_")
        s = re.sub(r"\s+", "_", s)
        if "NON_F_B" in s or s in {"NON_FB", "NONFB", "NON F B"}:
            return False
        if s in {"F_B", "FB", "F&B"} or s.startswith("F_B") or "F_B" == s:
            return True
        if s == "F&B" or "F_B" in s and "NON" not in s:
            return True
    return False


def load_hotel_lookup(hotel_path: Path) -> pd.DataFrame:
    """
    Table HOTEL_CODE → HOTEL_NAME + METRES_LINEAIRES + chambres + TO + brand.

    M_lin aligné sur ``HotelContextBuilder`` (hotel_context.py) :
      1. hotel_metres_lineaires_dedies_corner
      2. hotel_corner_de_vente_actuel_metres_lineaires
    """
    if not hotel_path.exists():
        raise FileNotFoundError(f"hotel_data introuvable : {hotel_path}")

    hotels = pd.read_excel(hotel_path)
    if "hotel_code" not in hotels.columns:
        raise ValueError("Colonne hotel_code absente de hotel_data.xlsx")

    frame = pd.DataFrame(
        {"HOTEL_CODE": hotels["hotel_code"].astype(str).str.strip()}
    )
    if "hotel_name" in hotels.columns:
        frame["HOTEL_NAME"] = hotels["hotel_name"].astype(str).str.strip()
    else:
        frame["HOTEL_NAME"] = pd.NA
    if "hotel_brand" in hotels.columns:
        frame["HOTEL_BRAND"] = hotels["hotel_brand"].astype(str).str.strip()
    else:
        frame["HOTEL_BRAND"] = pd.NA
    if "hotel_nb_chambres" in hotels.columns:
        frame["HOTEL_NB_CHAMBRES"] = pd.to_numeric(
            hotels["hotel_nb_chambres"], errors="coerce"
        )
    else:
        frame["HOTEL_NB_CHAMBRES"] = pd.NA
    if "hotel_to_annuel" in hotels.columns:
        to = pd.to_numeric(hotels["hotel_to_annuel"], errors="coerce")
        # parfois en %
        to = to.where(to.isna() | (to <= 1.0), other=to / 100.0)
        frame["HOTEL_TO_ANNUEL"] = to
    else:
        frame["HOTEL_TO_ANNUEL"] = pd.NA

    dedie = (
        pd.to_numeric(hotels[COL_M_LIN_DEDIE], errors="coerce")
        if COL_M_LIN_DEDIE in hotels.columns
        else pd.Series(pd.NA, index=hotels.index)
    )
    actuel = (
        pd.to_numeric(hotels[COL_M_LIN_ACTUEL], errors="coerce")
        if COL_M_LIN_ACTUEL in hotels.columns
        else pd.Series(pd.NA, index=hotels.index)
    )
    # 0 ou négatif = non renseigné utile
    dedie = dedie.where(dedie.notna() & (dedie > 0), other=pd.NA)
    actuel = actuel.where(actuel.notna() & (actuel > 0), other=pd.NA)
    frame["METRES_LINEAIRES"] = dedie.combine_first(actuel)
    # Priorité aux valeurs officielles du Récapitulatif ROD (archive)
    for code, mlin in METRES_LINEAIRES_RECAP.items():
        mask = frame["HOTEL_CODE"] == code
        if mask.any():
            frame.loc[mask, "METRES_LINEAIRES"] = float(mlin)
        else:
            frame = pd.concat(
                [
                    frame,
                    pd.DataFrame(
                        [
                            {
                                "HOTEL_CODE": code,
                                "HOTEL_NAME": pd.NA,
                                "HOTEL_BRAND": pd.NA,
                                "HOTEL_NB_CHAMBRES": pd.NA,
                                "HOTEL_TO_ANNUEL": pd.NA,
                                "METRES_LINEAIRES": float(mlin),
                            }
                        ]
                    ),
                ],
                ignore_index=True,
            )
    return frame.drop_duplicates("HOTEL_CODE", keep="first")


def reorder_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Ordre stable pour analyses / GROUP BY notebook :

      SOLUTION, HOTEL_CODE, HOTEL_NAME, METRES_LINEAIRES,
      HOTEL_NB_CHAMBRES, HOTEL_TO_ANNUEL, HOTEL_GUESTS_PER_CHAMBRE,
      TYPE / RAW, GAMME / RAW, NOM_PRODUIT / RAW, NATURE_PRODUIT, CATEGORIE,
      … reste transactionnel …,
      COEF_MARGE, MONTANT_ACHATS_SELON_COEF, MARGE_SELON_COEF,
      PRIX_TTC_MARCHE, MARGE
    """
    head = [
        "SOLUTION",
        "HOTEL_CODE",
        "HOTEL_NAME",
        "METRES_LINEAIRES",
        "HOTEL_NB_CHAMBRES",
        "HOTEL_TO_ANNUEL",
        "HOTEL_GUESTS_PER_CHAMBRE",
        "NOM_BOUTIQUE",
        "TYPE_RAW",
        "TYPE",
        "GAMME_RAW",
        "GAMME",
        "NOM_PRODUIT_RAW",
        "NOM_PRODUIT",
        "NATURE_PRODUIT",
        "MACHINE_RAW",
        "MACHINE",
        "MARQUE_RAW",
        "MARQUE",
        "FOURNISSEUR_RAW",
        "FOURNISSEUR",
        "CATEGORIE",
    ]
    tail = [
        "COEF_MARGE",
        "MONTANT_ACHATS_SELON_COEF",
        "MARGE_SELON_COEF",
        "PRIX_TTC_MARCHE",
        "MARGE",
    ]
    middle = [c for c in df.columns if c not in head and c not in tail]
    ordered = [c for c in head if c in df.columns] + middle + [
        c for c in tail if c in df.columns
    ]
    rest = [c for c in df.columns if c not in ordered]
    return df[ordered + rest]


def extend(
    df: pd.DataFrame,
    pilot_map: dict[str, str],
    hotel_lookup: pd.DataFrame | None = None,
) -> pd.DataFrame:
    out = df.copy()

    codes = out["NOM_BOUTIQUE"].map(boutique_to_code)
    out["HOTEL_CODE"] = codes
    out["SOLUTION"] = codes.map(
        lambda c: pilot_map.get(c) if isinstance(c, str) else pd.NA
    )

    # Nom hôtel + mètres linéaires + chambres + TO + brand (hotel_data)
    if hotel_lookup is not None and not hotel_lookup.empty:
        # éviter double colonnes si déjà présentes
        for c in (
            "HOTEL_NAME",
            "METRES_LINEAIRES",
            "HOTEL_BRAND",
            "HOTEL_NB_CHAMBRES",
            "HOTEL_TO_ANNUEL",
        ):
            if c in out.columns and c in hotel_lookup.columns:
                out = out.drop(columns=[c])
        out = out.merge(hotel_lookup, on="HOTEL_CODE", how="left")
    else:
        out["HOTEL_NAME"] = pd.NA
        out["METRES_LINEAIRES"] = pd.NA
        out["HOTEL_BRAND"] = pd.NA
        if "HOTEL_NB_CHAMBRES" not in out.columns:
            out["HOTEL_NB_CHAMBRES"] = pd.NA
        if "HOTEL_TO_ANNUEL" not in out.columns:
            out["HOTEL_TO_ANNUEL"] = pd.NA

    # Fallback nom : boutique caisse si pas de match hotel_data
    if "HOTEL_NAME" not in out.columns:
        out["HOTEL_NAME"] = pd.NA
    out["HOTEL_NAME"] = out["HOTEL_NAME"].where(
        out["HOTEL_NAME"].notna()
        & ~out["HOTEL_NAME"].astype(str).isin(["", "nan", "None", "NaN", "<NA>"]),
        other=out["NOM_BOUTIQUE"],
    )

    # Guests / chambre (pas dans les ventes : défaut marque / pivot solution)
    brand_series = out["HOTEL_BRAND"] if "HOTEL_BRAND" in out.columns else pd.Series("", index=out.index)
    out["HOTEL_GUESTS_PER_CHAMBRE"] = [
        guests_for_brand(b, s)
        for b, s in zip(brand_series, out["SOLUTION"])
    ]

    # Coef marge Excel : solution × catégorie (F&B / N-F&B)
    coefs = load_coef_marge_by_solution()
    type_s = out["TYPE"] if "TYPE" in out.columns else pd.Series("", index=out.index)
    cat_s = out["CATEGORIE"] if "CATEGORIE" in out.columns else pd.Series("", index=out.index)
    sol_s = out["SOLUTION"].astype(str).str.strip().str.lower()

    def _coef(sol: object, typ: object, cat: object) -> float:
        key = str(sol or "").strip().lower()
        table = coefs.get(key) or coefs.get("simply") or {"fb": 2.6, "nfb": 1.45}
        return float(table["fb"] if is_fb_row(typ, cat) else table["nfb"])

    out["COEF_MARGE"] = [
        _coef(sol, typ, cat) for sol, typ, cat in zip(sol_s, type_s, cat_s)
    ]

    # Marge selon coef Excel (sur CA HT ligne, comme le simulateur)
    prix_ht = pd.to_numeric(out.get("PRIX_HT"), errors="coerce")
    coef = pd.to_numeric(out["COEF_MARGE"], errors="coerce")
    # achats = CA / coef ; marge = CA - achats = CA × (1 - 1/coef)
    out["MONTANT_ACHATS_SELON_COEF"] = (prix_ht / coef).where(coef > 0)
    out["MARGE_SELON_COEF"] = prix_ht - out["MONTANT_ACHATS_SELON_COEF"]

    q = pd.to_numeric(out["QUANTITE"], errors="coerce").fillna(1.0)
    prix_ttc = pd.to_numeric(out["PRIX_TTC"], errors="coerce")

    ean = out["CODE_EAN"].astype(str).str.strip()
    ean = ean.where(~ean.isin(["", "nan", "None", "NaN", "<NA>"]), other=pd.NA)
    prod_key = ean.fillna(out["NOM_PRODUIT"].astype(str).str.strip())

    # PRIX_TTC = total ligne → unitaire = TTC / |QUANTITE| (ignore qty ≤ 0 pour le barème)
    abs_q = q.abs().where(q != 0, other=pd.NA)
    unit_ttc = prix_ttc / abs_q
    # Uniquement ventes "normales" pour la médiane de référence
    unit_for_ref = unit_ttc.where(q > 0)
    unit_market = unit_for_ref.groupby(prod_key).transform("median")
    unit_market = unit_market.fillna(
        unit_for_ref.groupby(out["NOM_PRODUIT"].astype(str)).transform("median")
    )

    # Marché total ligne = unitaire habituel × QUANTITE (signe conservé si retour)
    out["PRIX_TTC_MARCHE"] = (unit_market * q).astype(float)
    # Marge = total vendu − total marché (PRIX_TTC déjà total, pas de × qty)
    out["MARGE"] = (prix_ttc - out["PRIX_TTC_MARCHE"]).astype(float)

    # brand technique non exportée dans le head métier
    if "HOTEL_BRAND" in out.columns:
        out = out.drop(columns=["HOTEL_BRAND"])

    out = reorder_columns(out)
    # Colonnes non numériques : NaN → "" (jamais de NaN texte)
    non_num = out.select_dtypes(
        exclude=["number", "datetime", "datetimetz", "timedelta"]
    ).columns
    for c in non_num:
        out[c] = out[c].fillna("").map(
            lambda x: ""
            if x is None
            or (isinstance(x, float) and pd.isna(x))
            or str(x).strip().lower() in {"nan", "none", "<na>", "nat"}
            else x
        )
    return out


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Étend les ventes clean avec solution + m_lin + prix marché + marge"
    )
    parser.add_argument("--clean", type=Path, default=DEFAULT_CLEAN)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--hotel", type=Path, default=DEFAULT_HOTEL)
    args = parser.parse_args()

    if not args.clean.exists():
        print(f"❌ Clean introuvable : {args.clean}")
        sys.exit(1)

    print(f"1. Clean    : {args.clean}")
    df = pd.read_excel(args.clean, sheet_name=0)
    print(f"   → {len(df):,} lignes")

    print("2. Pilotes solution (rod_pilot_concepts.json)…")
    pilot_map = load_pilot_map()
    print(f"   → {pilot_map}")

    print(f"3. Lookup hôtel ({args.hotel.name})…")
    hotel_lookup = load_hotel_lookup(args.hotel)
    n_filled = hotel_lookup["METRES_LINEAIRES"].notna().sum()
    print(f"   → {len(hotel_lookup):,} hôtels | {n_filled} avec m_lin renseigné")

    print("4. Extension…")
    extended = extend(df, pilot_map, hotel_lookup=hotel_lookup)
    print("   colonnes :", list(extended.columns))
    print("   SOLUTION :")
    print(extended["SOLUTION"].value_counts(dropna=False).to_string())
    print("   par hôtel :")
    print(
        extended.groupby(
            [
                "SOLUTION",
                "HOTEL_CODE",
                "HOTEL_NAME",
                "METRES_LINEAIRES",
            ],
            dropna=False,
        )
        .size()
        .to_string()
    )
    print(
        f"   MARGE mean={extended['MARGE'].mean():.3f} "
        f"median={extended['MARGE'].median():.3f} "
        f"sum={extended['MARGE'].sum():.2f}"
    )

    print(f"5. Écriture : {args.out}")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    extended.to_excel(args.out, index=False, sheet_name="sales_extended", na_rep="")
    size_mo = args.out.stat().st_size / (1024 * 1024)
    print(f"   → {len(extended):,} lignes | {size_mo:.1f} Mo")
    print("\n✅", args.out.resolve())
    print(
        "\nColonnes (ordre notebook) :\n"
        "  SOLUTION, HOTEL_CODE, HOTEL_NAME, METRES_LINEAIRES,\n"
        "  TYPE / GAMME / NOM_PRODUIT (+ raw + CATEGORIE),\n"
        "  … transaction …, PRIX_TTC_MARCHE, MARGE"
    )


if __name__ == "__main__":
    main()
