#!/usr/bin/env python3
"""
Nettoyage du fichier de ventes hôtels Accor.

Entrées :
  - hotel_sales_raw_data.xlsx          (fichier brut ~130k lignes)
  - hotels_produits_nettoyes.xlsx      (mapping de référence, cas par cas)

Sortie :
  - hotel_sales_raw_clean_data.xlsx

Usage :
  python clean_hotel_sales.py
  python clean_hotel_sales.py \\
      --raw  data/hotel_sales_raw_data.xlsx \\
      --map  data/hotels_produits_nettoyes.xlsx \\
      --out  data/hotel_sales_raw_clean_data.xlsx

  # Reconstruit / améliore le mapping avant application
  python clean_hotel_sales.py --improve-map
"""

from __future__ import annotations

import argparse
import html
import re
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

DEFAULT_RAW = Path("data/hotel_sales_raw_data.xlsx")
DEFAULT_MAP = Path("data/hotels_produits_nettoyes.xlsx")
DEFAULT_MAP_FALLBACK = Path("hotels_produits_nettoyes.xlsx")
DEFAULT_OUT = Path("data/hotel_sales_raw_clean_data.xlsx")

GAMME_MAP = {
    "FOOD SALEE": "SALTY FOOD",
    "FOOD SUCREE": "SUGARY FOOD",
    "SALTY FOOD (Fresh)": "SALTY FOOD",
    "SALTY FOOD (Dry)": "SALTY FOOD",
    "SUGARY FOOD (Fresh)": "SUGARY FOOD",
    "SUGARY FOOD (Dry)": "SUGARY FOOD",
    "FORMULE": "FORMULE",
    "SANS ALCOOL": "SANS ALCOOL",
    "ALCOOL": "ALCOOL",
    "ACCESSOIRES": "ACCESSOIRES",
    "PAP": "PAP",
    "SOS": "SOS",
    "JEUX / ENFANTS": "JEU_ENFANTS",
    "JEU_ENFANTS": "JEU_ENFANTS",
    "COSMETIQUE": "COSMETIQUE",
    "SOUVENIRS": "SOUVENIRS",
}

CANON_GAMMES = set(GAMME_MAP.values()) | {"JEU_ENFANTS"}

BRAND_MAP = {
    "coca cola": "Coca-Cola",
    "coca-cola": "Coca-Cola",
    "coca/cola": "Coca-Cola",
    "coca - cola": "Coca-Cola",
    "coca / cola": "Coca-Cola",
    "red bull": "Red Bull",
    "m&m's": "M&M's",
    "m&ms": "M&M's",
    "kinder bueno": "Kinder Bueno",
    "kinder maxi": "Kinder Maxi",
    "san bendetto": "San Benedetto",
    "san benedetto": "San Benedetto",
    "san pellegrino": "San Pellegrino",
    "michel&augustin": "Michel & Augustin",
    "michel & augustin": "Michel & Augustin",
    "nuxe": "Nuxe",
    "perrier": "Perrier",
    "evian": "Evian",
    "vittel": "Vittel",
    "orangina": "Orangina",
    "fuze tea": "Fuze Tea",
    "fuzetea": "Fuze Tea",
    "kit kat": "Kit Kat",
    "kitkat": "Kit Kat",
    "toblerone": "Toblerone",
    "tobleron": "Toblerone",
    "lay's": "Lay's",
    "lays": "Lay's",
    "novotel": "Novotel",
    "heineken": "Heineken",
    "doritos": "Doritos",
    "pringles": "Pringles",
    "snickers": "Snickers",
    "twix": "Twix",
    "bounty": "Bounty",
    "dragibus": "Dragibus",
    "minute maid": "Minute Maid",
    "alain milliat": "Alain Milliat",
}

SMALL = {
    "de", "à", "et", "au", "aux", "la", "le", "les", "du", "des",
    "d'", "l'", "en", "sur", "pour", "avec", "sans", "ou", "un", "une",
    "a", "of", "and", "x", "the",
}

FORCE_ACRONYMS = {
    "USB", "IPX8", "BIO", "AOP", "SPF", "BTE", "IPA", "XXL", "XL", "XS",
    "UK", "PET", "NT", "MH", "RS", "TU", "S", "M", "L",
}

DRY_KW = re.compile(
    r"chips|pringles|cacahu[eè]te|cacahuete|snickers|twix|kinder|bounty|tobleron|"
    r"\bmars\b|lion\s*\d|crunch|m&m|dragibus|tagada|sabl[eé]|gressin|bricelet|"
    r"graines?|caramel|confiture|palmier|feuillet|doritos|lay'?s|brets|"
    r"biscuit|cookie|bonbon|guimauve|amandes?\s+truff|barre\s+chocol|"
    r"minis?\s+feuillet|minis?\s+palmier|so\s*chips|nougat|"
    r"boite\s+de\s+biscuit|petites?\s+boites?\s+de\s+biscuit",
    re.I,
)
FRESH_KW = re.compile(
    r"yaourt|yogurt|mousse|cr[eè]me\s*br[uû]l|puree|pur[eé]e|compote|compot|"
    r"club\b|burger|wrap|sandwich|salade|ravioli|spaghetti|gnochi|gnocchi|"
    r"poulet|b[oœ]euf|soupe|velout|riz\s+au\s+lait|good\s+bowl|formule|"
    r"tarte\s+[aà]|mini\s+tarte|nouilles|curry|jambon|thon|saumon|rillettes|"
    r"bocaux?\s+(du\s+bocage\s*-?\s*)?desserts?|quiche|panini|pizza|"
    r"p[aâ]tes|lasagne|tiramisu|cheesecake|fromage\s+blanc",
    re.I,
)
# Intentionally NO "rose" (couleur vs vin rosé) — use explicit drink brands instead.
ALCOOL_KW = re.compile(
    r"\bbi[eè]re\b|\bbeer\b|\bwine\b|\bvin\b|\brhum\b|\bwhisky\b|\bcidre\b|"
    r"\bchampagne\b|\bprosecco\b|\bgallia\b|\bheineken\b|\bduvel\b|"
    r"\bmort\s+subite\b|\bbacchante\b|\bd[eé]bauche\b|"
    r"\bros[eé]\s+(vin|wine|bouteille)|vin\s+ros[eé]",
    re.I,
)
BIERE_KW = re.compile(
    r"\bbi[eè]re\b|\bbeer\b|\bgallia\b|\bheineken\b|\bduvel\b|"
    r"\bmort\s+subite\b|\bbacchante\b|\bd[eé]bauche\b|\bipa\b",
    re.I,
)
PAP_KW = re.compile(
    r"chaussure|boardshort|maillot|tongs?|chaussette|casquette|bonnet|b[eé]ret|"
    r"short|t-shirt|tshirt|polo|sweat|pantalon|robe|jupe|veste|doudoune|"
    r"polaire|coupe.?vent|poncho|kimono|peignoir",
    re.I,
)
JEU_KW = re.compile(
    r"peluche|puzzle|coloriage|jouet|jeu\b|ballon|raquette|disney|stitch|"
    r"mickey|minnie|livre|cahier|cherche\s+et\s+trouve|bou[eé]e",
    re.I,
)
SOS_KW = re.compile(
    r"parapluie|cable|c[aâ]ble|usb|chargeur|deodorant|d[eé]odorant|"
    r"gel\s+hydro|tire[\s-]?bouchon|kit\s+couvert|adaptateur|batterie|powerbank",
    re.I,
)
COSM_KW = re.compile(
    r"nuxe|cr[eè]me\s|baume|d[eé]maquill|parfum|savon|shampo|gel\s+douche|"
    r"brumisateur|spray\s+facial|soin|lotion|s[eé]rum|huile\s+corps",
    re.I,
)
GOURDE_KW = re.compile(r"gourde", re.I)


# ---------------------------------------------------------------------------
# Nettoyage nom produit
# ---------------------------------------------------------------------------
def clean_product_name(name: object) -> object:
    if pd.isna(name):
        return name
    s = html.unescape(str(name)).strip()
    s = (
        s.replace("&#039;", "'")
        .replace("&amp;", "&")
        .replace("&quot;", '"')
        .replace("&apos;", "'")
    )
    s = re.sub(r"\s+", " ", s)

    # Unités entre parenthèses → hors parenthèses
    s = re.sub(
        r"\s*\(\s*(\d+[.,]?\d*\s*(?:cl|g|ml|l|cm|kg|mm|G|CL|ML|L)?)\s*\)",
        r" \1",
        s,
        flags=re.IGNORECASE,
    )
    s = re.sub(
        r"\s*\(\s*bouteille en verre\s*\)",
        " Bouteille En Verre",
        s,
        flags=re.IGNORECASE,
    )
    s = re.sub(r"\s*\(\s*canette\s*\)", " Canette", s, flags=re.IGNORECASE)
    # Slash espacé ; tirets de marque non touchés (Coca-Cola)
    s = re.sub(r"\s*/\s*", " / ", s)
    s = re.sub(r"\s+", " ", s).strip()

    lower_s = s.lower()
    for k, v in sorted(BRAND_MAP.items(), key=lambda x: -len(x[0])):
        if k in lower_s:
            s = re.compile(re.escape(k), re.IGNORECASE).sub(v, s)
            lower_s = s.lower()

    words = s.split(" ")
    result: list[str] = []
    for i, w in enumerate(words):
        if not w:
            continue
        m = re.match(r"^(\d+[.,]?\d*)(cl|g|ml|l|cm|kg|mm)$", w, re.I)
        if m:
            result.append(m.group(1) + m.group(2).lower())
            continue
        if re.match(r"^[\d./]+$", w):
            result.append(w)
            continue
        if w.upper() in FORCE_ACRONYMS:
            result.append(w.upper())
            continue
        if any(c in w for c in "-&'"):
            if w in {"Coca-Cola", "M&M's", "Red Bull"} or w.lower() in {
                "coca-cola",
                "m&m's",
            }:
                result.append(
                    {"coca-cola": "Coca-Cola", "m&m's": "M&M's"}.get(w.lower(), w)
                )
                continue
            parts = re.split(r"([-&'])", w)
            new_parts = []
            for p in parts:
                if p in "-&'":
                    new_parts.append(p)
                elif p:
                    if p.upper() in FORCE_ACRONYMS:
                        new_parts.append(p.upper())
                    else:
                        new_parts.append(
                            p[0].upper() + p[1:].lower() if len(p) > 1 else p.upper()
                        )
            result.append("".join(new_parts))
            continue
        lower = w.lower()
        if i > 0 and lower in SMALL:
            result.append(lower)
        else:
            result.append(w[0].upper() + w[1:].lower() if len(w) > 1 else w.upper())

    s = " ".join(result)
    s = re.sub(r"\bCoca-cola\b", "Coca-Cola", s)
    s = re.sub(r"\bCoca\s*-\s*Cola\b", "Coca-Cola", s, flags=re.I)
    s = re.sub(r"\bCoca\s*/\s*Cola\b", "Coca-Cola", s, flags=re.I)
    s = re.sub(r"\bM&m's\b", "M&M's", s, flags=re.I)
    s = re.sub(r"\bRed bull\b", "Red Bull", s, flags=re.I)
    s = re.sub(r"\bBiere\b", "Bière", s)
    s = re.sub(r"\bTobleronee\b", "Toblerone", s)
    s = re.sub(r"\bLay'S\b", "Lay's", s)
    s = re.sub(r"\bLays\b", "Lay's", s)
    s = re.sub(r"\bSan Bendetto\b", "San Benedetto", s, flags=re.I)
    s = re.sub(r"\bIpa\b", "IPA", s)
    s = re.sub(r"\bFuze tea\b", "Fuze Tea", s, flags=re.I)
    s = re.sub(r"\bMichel\s*&\s*Augustin\b", "Michel & Augustin", s, flags=re.I)
    return re.sub(r"\s+", " ", s).strip()


def map_gamme_series(s: pd.Series) -> pd.Series:
    return s.map(
        lambda x: GAMME_MAP.get(str(x).strip(), x) if pd.notna(x) else x
    )


def compute_categorie_row(type_, gamme_raw, gamme) -> str:
    if pd.isna(type_):
        return "Unknown"
    t = str(type_).strip().upper().replace(" ", "")
    if t in {"NON-F&B", "NONF&B"}:
        return "NonF&B"

    g_raw = str(gamme_raw).strip() if pd.notna(gamme_raw) else ""
    g = str(gamme).strip() if pd.notna(gamme) else ""

    if g in ("SALTY FOOD", "SUGARY FOOD"):
        if "(Fresh)" in g_raw:
            return "Fresh"
        if "(Dry)" in g_raw:
            return "Dry"
        # Ancien codage Accor (souvent imprécis hors mapping)
        if g_raw == "FOOD SALEE":
            return "Fresh"
        if g_raw == "FOOD SUCREE":
            return "Dry"
        return "Unknown"

    return g if g else "Unknown"


def mode_or_first(series: pd.Series):
    s = series.dropna()
    if s.empty:
        return pd.NA
    m = s.mode()
    return m.iloc[0] if len(m) else s.iloc[0]


# ---------------------------------------------------------------------------
# Amélioration du fichier de correctifs
# ---------------------------------------------------------------------------
def resolve_type(group: pd.DataFrame, name: str) -> str:
    # Vêtements / cosmétiques / lunettes : jamais F&B même si "rose" dans le nom
    if PAP_KW.search(name) or COSM_KW.search(name) or re.search(
        r"lunette|d[eé]odorant|respire\s+d[eé]odorant", name, re.I
    ):
        return "NON-F&B"
    if BIERE_KW.search(name) or ALCOOL_KW.search(name):
        return "F&B"
    types = [str(x).strip() for x in group["type"].dropna()]
    if not types:
        if any(
            g in (
                "ALCOOL",
                "SANS ALCOOL",
                "SALTY FOOD",
                "SUGARY FOOD",
                "FORMULE",
            )
            for g in group["gamme"].dropna().astype(str)
        ):
            return "F&B"
        return "NON-F&B"
    return Counter(types).most_common(1)[0][0]


def resolve_gamme(group: pd.DataFrame, name: str, type_: str) -> str:
    if BIERE_KW.search(name):
        return "ALCOOL"

    gammes = [
        GAMME_MAP.get(str(x).strip(), str(x).strip())
        for x in group["gamme"].dropna()
    ]
    gammes = [g for g in gammes if g]
    c = Counter(gammes) if gammes else Counter()

    if type_ == "NON-F&B":
        if GOURDE_KW.search(name):
            return "ACCESSOIRES"
        if PAP_KW.search(name):
            return "PAP"
        if JEU_KW.search(name):
            return "JEU_ENFANTS"
        if COSM_KW.search(name) or re.search(r"d[eé]odorant|respire", name, re.I):
            return "SOS" if re.search(r"d[eé]odorant|respire", name, re.I) else "COSMETIQUE"
        if SOS_KW.search(name):
            return "SOS"
        if re.search(
            r"lunette|serviette|gamelle|sac|tot\s*bag|raquette|bou[eé]e",
            name,
            re.I,
        ):
            if "JEU_ENFANTS" in c and re.search(r"bou[eé]e|raquette", name, re.I):
                return "JEU_ENFANTS"
            return "ACCESSOIRES"
        if "SOUVENIRS" in c and re.search(
            r"porte[\s-]?cl[eé]|souvenir|magnet|badge|b[eé]ret|bougie",
            name,
            re.I,
        ):
            return "SOUVENIRS"
        if c:
            return c.most_common(1)[0][0]
        return "ACCESSOIRES"

    # F&B
    if re.search(r"p[eé]pites?\s+de\s+chocolat|cookie|sabl[eé].*chocolat", name, re.I):
        return "SUGARY FOOD"
    if c:
        if "ALCOOL" in c and ALCOOL_KW.search(name):
            return "ALCOOL"
        if "SALTY FOOD" in c and "SUGARY FOOD" in c:
            if re.search(r"chocolat|bonbon|cookie|sucr", name, re.I):
                return "SUGARY FOOD"
        return c.most_common(1)[0][0]
    return "SANS ALCOOL"


def resolve_categorie(
    group: pd.DataFrame, name: str, type_: str, gamme: str
) -> str:
    if str(type_).upper().replace(" ", "") in {"NON-F&B", "NONF&B"}:
        return "NonF&B"
    if gamme not in ("SALTY FOOD", "SUGARY FOOD"):
        return gamme if pd.notna(gamme) and str(gamme) else "Unknown"

    modern = group[
        group["gamme_raw"]
        .astype(str)
        .str.contains(r"\(Dry\)|\(Fresh\)", na=False, regex=True)
    ]
    if len(modern):
        mc = [str(x) for x in modern["categorie"] if str(x) in ("Dry", "Fresh")]
        if mc and len(set(mc)) == 1:
            return mc[0]
        if mc:
            # Conflit modern : mots-clés produit
            if DRY_KW.search(name) and not FRESH_KW.search(name):
                return "Dry"
            if FRESH_KW.search(name) and not DRY_KW.search(name):
                return "Fresh"
            return Counter(mc).most_common(1)[0][0]

    if DRY_KW.search(name) and not FRESH_KW.search(name):
        return "Dry"
    if FRESH_KW.search(name) and not DRY_KW.search(name):
        return "Fresh"

    cats = [
        str(x).strip()
        for x in group["categorie"].dropna()
        if str(x).strip() in ("Dry", "Fresh")
    ]
    if cats:
        if len(set(cats)) == 1:
            return cats[0]
        if DRY_KW.search(name):
            return "Dry"
        if FRESH_KW.search(name):
            return "Fresh"
        return Counter(cats).most_common(1)[0][0]

    grs = group["gamme_raw"].dropna().astype(str)
    if any("(Fresh)" in g for g in grs):
        return "Fresh"
    if any("(Dry)" in g for g in grs):
        return "Dry"
    if any(g == "FOOD SALEE" for g in grs):
        return "Dry" if DRY_KW.search(name) else "Fresh"
    if any(g == "FOOD SUCREE" for g in grs):
        return "Fresh" if FRESH_KW.search(name) else "Dry"
    return "Unknown"


def improve_map(map_df: pd.DataFrame) -> pd.DataFrame:
    """Une ligne canonique par (hôtel, produit) avec correctifs cohérents."""
    m = map_df.copy()
    m["nom_boutique"] = m["nom_boutique"].astype(str).str.strip()
    m["nom_produit_raw"] = m["nom_produit_raw"].astype(str).str.strip()
    m["gamme"] = m["gamme"].map(
        lambda x: GAMME_MAP.get(str(x).strip(), x) if pd.notna(x) else x
    )

    rows = []
    for (boutique, prod), g in m.groupby(
        ["nom_boutique", "nom_produit_raw"], sort=False
    ):
        type_ = resolve_type(g, prod)
        gamme = resolve_gamme(g, prod, type_)
        cat = resolve_categorie(g, prod, type_, gamme)
        nom = clean_product_name(prod)
        rows.append(
            {
                "nom_boutique": boutique,
                "type_raw": mode_or_first(g["type_raw"]),
                "type": type_,
                "gamme_raw": mode_or_first(g["gamme_raw"]),
                "gamme": gamme,
                "nom_produit_raw": prod,
                "nom_produit": nom,
                "categorie": cat,
            }
        )
    out = pd.DataFrame(rows)

    nonfb = (
        out["type"]
        .astype(str)
        .str.upper()
        .str.replace(" ", "", regex=False)
        .eq("NON-F&B")
    )
    out.loc[nonfb, "categorie"] = "NonF&B"
    fb_fallback = ~nonfb & out["gamme"].isin(
        ["ALCOOL", "SANS ALCOOL", "FORMULE", "SOUVENIRS"]
    )
    out.loc[fb_fallback, "categorie"] = out.loc[fb_fallback, "gamme"]
    return out


def write_map(map_df: pd.DataFrame, path: Path, legend_src: Path | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    legend = None
    if legend_src and legend_src.exists():
        try:
            legend = pd.read_excel(legend_src, sheet_name="legende_regles", header=None)
        except Exception:
            legend = None
    if legend is None:
        legend = pd.DataFrame(
            {
                0: [
                    "Légende & Règles de nettoyage",
                    "",
                    "Règles TYPE",
                    "F&B",
                    "NON-F&B",
                    "",
                    "Règles GAMME",
                    "FOOD SALEE / SALTY FOOD (Fresh|Dry)",
                    "FOOD SUCREE / SUGARY FOOD (Fresh|Dry)",
                    "JEUX / ENFANTS",
                    "",
                    "Règles categorie",
                    "Fresh",
                    "Dry",
                    "NonF&B",
                    "Fallback",
                    "",
                    "Complétude",
                    "Une ligne canonique par (nom_boutique, nom_produit_raw)",
                    "Conflits Dry/Fresh résolus (encodage moderne + mots-clés)",
                    "Bières forcées en ALCOOL ; gourdes en ACCESSOIRES",
                    "Noms : title case, marques, unités hors parenthèses",
                ],
                1: [
                    "",
                    "",
                    "",
                    "Nourriture, boissons, alcool, formules, souvenirs comestibles",
                    "Accessoires, PAP, SOS, Jeux, Cosmétique, Souvenirs non comestibles",
                    "",
                    "",
                    "→ SALTY FOOD",
                    "→ SUGARY FOOD",
                    "→ JEU_ENFANTS",
                    "",
                    "",
                    "SALTY/SUGARY FOOD frais / réfrigérés",
                    "SALTY/SUGARY FOOD ambient / secs",
                    "Tous les TYPE = NON-F&B",
                    "Sinon valeur de gamme (SANS ALCOOL, ALCOOL, …)",
                    "",
                    "",
                    "Dédupliqué depuis le mapping multi-libellés source",
                    "Préférence (Dry)/(Fresh) explicite sur FOOD SALEE/SUCREE",
                    "Cas par cas dans improve_map()",
                    "Voir clean_product_name()",
                ],
            }
        )
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        map_df.to_excel(writer, sheet_name="produits_corriges", index=False)
        legend.to_excel(writer, sheet_name="legende_regles", index=False, header=False)


# ---------------------------------------------------------------------------
# Lookups
# ---------------------------------------------------------------------------
def build_lookups(map_df: pd.DataFrame):
    """Retourne deux DataFrames prêts pour un merge."""
    m = map_df.copy()
    m["nom_boutique"] = m["nom_boutique"].astype(str).str.strip()
    m["nom_produit_raw"] = m["nom_produit_raw"].astype(str).str.strip()
    # Normalise gammes du mapping au passage
    m["gamme"] = m["gamme"].map(
        lambda x: GAMME_MAP.get(str(x).strip(), x) if pd.notna(x) else x
    )

    by_hp = (
        m.drop_duplicates(subset=["nom_boutique", "nom_produit_raw"], keep="first")[
            [
                "nom_boutique",
                "nom_produit_raw",
                "type",
                "gamme",
                "nom_produit",
                "categorie",
            ]
        ].rename(
            columns={
                "type": "type_map_hp",
                "gamme": "gamme_map_hp",
                "nom_produit": "nom_produit_map_hp",
                "categorie": "categorie_map_hp",
            }
        )
    )

    by_p = (
        m.groupby("nom_produit_raw", as_index=False)
        .agg(
            type_map_p=("type", mode_or_first),
            gamme_map_p=("gamme", mode_or_first),
            nom_produit_map_p=("nom_produit", mode_or_first),
            categorie_map_p=("categorie", mode_or_first),
        )
    )
    return by_hp, by_p


# ---------------------------------------------------------------------------
# Nettoyage principal (vectorisé)
# ---------------------------------------------------------------------------
def clean_raw(
    raw_df: pd.DataFrame, by_hp: pd.DataFrame, by_p: pd.DataFrame
) -> pd.DataFrame:
    df = raw_df.copy()

    df["TYPE_RAW"] = df["TYPE"] if "TYPE" in df.columns else pd.NA
    df["GAMME_RAW"] = df["GAMME"] if "GAMME" in df.columns else pd.NA
    df["NOM_PRODUIT_RAW"] = df["NOM_PRODUIT"] if "NOM_PRODUIT" in df.columns else pd.NA

    df["_boutique_key"] = df["NOM_BOUTIQUE"].astype(str).str.strip()
    df["_produit_key"] = df["NOM_PRODUIT_RAW"].astype(str).str.strip()

    df = df.merge(
        by_hp,
        left_on=["_boutique_key", "_produit_key"],
        right_on=["nom_boutique", "nom_produit_raw"],
        how="left",
        suffixes=("", "_drop"),
    )
    df.drop(
        columns=[
            c
            for c in df.columns
            if c.endswith("_drop") or c in ("nom_boutique", "nom_produit_raw")
        ],
        inplace=True,
        errors="ignore",
    )

    df = df.merge(
        by_p,
        left_on="_produit_key",
        right_on="nom_produit_raw",
        how="left",
        suffixes=("", "_drop2"),
    )
    df.drop(
        columns=[
            c
            for c in df.columns
            if c.endswith("_drop2") or c == "nom_produit_raw"
        ],
        inplace=True,
        errors="ignore",
    )

    df["TYPE"] = (
        df["type_map_hp"]
        .combine_first(df["type_map_p"])
        .combine_first(df["TYPE_RAW"])
    )

    df["GAMME"] = (
        df["gamme_map_hp"]
        .combine_first(df["gamme_map_p"])
        .combine_first(map_gamme_series(df["GAMME_RAW"]))
    )
    # JEUX / ENFANTS restant éventuel
    df["GAMME"] = df["GAMME"].replace({"JEUX / ENFANTS": "JEU_ENFANTS"})

    print("  → Nettoyage des noms de produits…")
    cleaned_names = df["NOM_PRODUIT_RAW"].map(clean_product_name)
    df["NOM_PRODUIT"] = (
        df["nom_produit_map_hp"]
        .combine_first(df["nom_produit_map_p"])
        .combine_first(cleaned_names)
    )

    print("  → Calcul des catégories…")
    cat_from_map = df["categorie_map_hp"].combine_first(df["categorie_map_p"])
    cat_computed = pd.Series(
        [
            compute_categorie_row(t, gr, g)
            for t, gr, g in zip(df["TYPE"], df["GAMME_RAW"], df["GAMME"])
        ],
        index=df.index,
    )
    df["CATEGORIE"] = cat_from_map.combine_first(cat_computed)

    # Cohérence TYPE NON-F&B → categorie
    nonfb_mask = (
        df["TYPE"].astype(str).str.upper().str.replace(" ", "", regex=False)
        == "NON-F&B"
    )
    df.loc[nonfb_mask, "CATEGORIE"] = "NonF&B"

    drop_cols = [
        "_boutique_key",
        "_produit_key",
        "type_map_hp",
        "gamme_map_hp",
        "nom_produit_map_hp",
        "categorie_map_hp",
        "type_map_p",
        "gamme_map_p",
        "nom_produit_map_p",
        "categorie_map_p",
    ]
    df.drop(columns=[c for c in drop_cols if c in df.columns], inplace=True)

    core = [
        "TYPE_RAW",
        "TYPE",
        "GAMME_RAW",
        "GAMME",
        "NOM_PRODUIT_RAW",
        "NOM_PRODUIT",
        "CATEGORIE",
    ]
    other = [c for c in df.columns if c not in core]
    return df[other + core]


def resolve_map_path(path: Path) -> Path:
    if path.exists():
        return path
    if path == DEFAULT_MAP and DEFAULT_MAP_FALLBACK.exists():
        return DEFAULT_MAP_FALLBACK
    return path


def print_qa(clean_df: pd.DataFrame) -> None:
    print("\n── QA post-nettoyage ──")
    print(f"Lignes : {len(clean_df):,}")
    for col in ("TYPE", "GAMME", "CATEGORIE"):
        nnull = clean_df[col].isna().sum()
        print(f"  {col} nulls={nnull}")
        print(f"    {clean_df[col].value_counts(dropna=False).to_dict()}")
    # Bières encore SANS ALCOOL ?
    beer = clean_df[
        clean_df["NOM_PRODUIT_RAW"]
        .astype(str)
        .str.contains(r"bi[eè]re|Gallia IPA|Mort Subite", case=False, na=False)
    ]
    if len(beer):
        bad = beer[beer["GAMME"] != "ALCOOL"]
        print(f"  Bières non ALCOOL : {len(bad)} / {len(beer)}")
    # Chips Fresh ?
    chips = clean_df[
        clean_df["NOM_PRODUIT_RAW"].astype(str).str.contains(r"chips", case=False, na=False)
    ]
    if len(chips):
        print(f"  Chips CATEGORIE : {chips['CATEGORIE'].value_counts().to_dict()}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Nettoie hotel_sales_raw_data.xlsx → hotel_sales_raw_clean_data.xlsx"
    )
    parser.add_argument("--raw", type=Path, default=DEFAULT_RAW)
    parser.add_argument("--map", type=Path, default=DEFAULT_MAP)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--improve-map",
        action="store_true",
        help="Déduplique / corrige le mapping avant application",
    )
    parser.add_argument(
        "--map-out",
        type=Path,
        default=None,
        help="Où écrire le mapping amélioré (défaut = --map)",
    )
    parser.add_argument(
        "--map-src",
        type=Path,
        default=None,
        help="Source du mapping à améliorer (si différente de --map)",
    )
    args = parser.parse_args()

    map_path = resolve_map_path(args.map)
    if args.improve_map:
        src = args.map_src or map_path
        # Sources alternatives courantes
        if not src.exists():
            for cand in (
                Path("/home/laghmari/Téléchargements/hotels_produits_nettoyes.xlsx"),
                DEFAULT_MAP_FALLBACK,
                DEFAULT_MAP,
            ):
                if cand.exists():
                    src = cand
                    break
        if not src.exists():
            print(f"❌ Mapping source introuvable pour --improve-map : {src}")
            sys.exit(1)
        print(f"0. Amélioration mapping depuis {src}")
        raw_map = pd.read_excel(src, sheet_name="produits_corriges")
        print(f"   → {len(raw_map):,} lignes source")
        improved = improve_map(raw_map)
        map_out = args.map_out or map_path
        write_map(improved, map_out, legend_src=src)
        # copie à côté du script pour le default historique
        if map_out.resolve() != DEFAULT_MAP_FALLBACK.resolve():
            write_map(improved, DEFAULT_MAP_FALLBACK, legend_src=src)
        print(f"   → {len(improved):,} couples canoniques → {map_out}")
        map_path = map_out

    if not args.raw.exists():
        print(f"❌ Fichier brut introuvable : {args.raw.resolve()}")
        sys.exit(1)
    if not map_path.exists():
        print(f"❌ Fichier mapping introuvable : {map_path.resolve()}")
        print("   Place hotels_produits_nettoyes.xlsx dans data/ ou utilise --map")
        print("   Astuce : python clean_hotel_sales.py --improve-map")
        sys.exit(1)

    print(f"1. Mapping  : {map_path}")
    map_df = pd.read_excel(map_path, sheet_name="produits_corriges")
    print(f"   → {len(map_df):,} lignes de référence")

    print("2. Lookups…")
    by_hp, by_p = build_lookups(map_df)
    print(f"   → {len(by_hp):,} couples (hôtel, produit)")
    print(f"   → {len(by_p):,} produits uniques")

    print(f"3. Brut     : {args.raw}")
    raw_df = pd.read_excel(args.raw)
    print(f"   → {len(raw_df):,} lignes | colonnes : {list(raw_df.columns)}")

    required = {"NOM_BOUTIQUE", "NOM_PRODUIT"}
    missing = required - set(raw_df.columns)
    if missing:
        print(f"❌ Colonnes manquantes : {missing}")
        sys.exit(1)

    print("4. Nettoyage…")
    clean_df = clean_raw(raw_df, by_hp, by_p)

    print(f"5. Écriture : {args.out}")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    clean_df.to_excel(args.out, index=False, sheet_name="sales_clean")
    size_mo = args.out.stat().st_size / (1024 * 1024)
    print(f"   → {len(clean_df):,} lignes | {size_mo:.1f} Mo")

    print_qa(clean_df)

    print("\n✅ Terminé →", args.out.resolve())
    print("\nColonnes ajoutées / normalisées :")
    print("  TYPE_RAW          → TYPE")
    print("  GAMME_RAW         → GAMME")
    print("  NOM_PRODUIT_RAW   → NOM_PRODUIT")
    print("  CATEGORIE         (Fresh / Dry / NonF&B / ou fallback gamme)")


if __name__ == "__main__":
    main()
