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
import unicodedata
from collections import Counter
from pathlib import Path

import pandas as pd

DEFAULT_RAW = Path("data/hotel_sales_raw_data.xlsx")
DEFAULT_MAP = Path("data/hotels_produits_nettoyes.xlsx")
DEFAULT_MAP_FALLBACK = Path("hotels_produits_nettoyes.xlsx")
DEFAULT_OUT = Path("data/hotel_sales_raw_clean_data.xlsx")

# ---------------------------------------------------------------------------
# Canon TYPE / GAMME (colonnes normalisées ; RAW inchangés)
# ---------------------------------------------------------------------------
# TYPE : F_B | NON_F_B
# GAMME : slugs stables (underscore), alignés sales_prep / DuckDB sanitize
TYPE_CANON = ("F_B", "NON_F_B")

GAMME_MAP = {
    # food
    "FOOD SALEE": "FOOD_SALEE",
    "FOOD SUCREE": "FOOD_SUCREE",
    "FOOD SALÉE": "FOOD_SALEE",
    "FOOD SUCRÉE": "FOOD_SUCREE",
    "SALTY FOOD": "FOOD_SALEE",
    "SUGARY FOOD": "FOOD_SUCREE",
    "SALTY FOOD (FRESH)": "FOOD_SALEE",
    "SALTY FOOD (DRY)": "FOOD_SALEE",
    "SUGARY FOOD (FRESH)": "FOOD_SUCREE",
    "SUGARY FOOD (DRY)": "FOOD_SUCREE",
    "SALTY-FOOD": "FOOD_SALEE",
    "SUGARY-FOOD": "FOOD_SUCREE",
    "FOOD_SALEE": "FOOD_SALEE",
    "FOOD_SUCREE": "FOOD_SUCREE",
    "SALTY_FOOD": "FOOD_SALEE",
    "SUGARY_FOOD": "FOOD_SUCREE",
    # boissons
    "SANS ALCOOL": "SANS_ALCOOL",
    "SANS-ALCOOL": "SANS_ALCOOL",
    "SANS_ALCOOL": "SANS_ALCOOL",
    "ALCOOL": "ALCOOL",
    # non-f&b
    "FORMULE": "FORMULE",
    "ACCESSOIRES": "ACCESSOIRES",
    "PAP": "PAP",
    "SOS": "SOS",
    "JEUX / ENFANTS": "JEUX_ENFANTS",
    "JEUX ENFANTS": "JEUX_ENFANTS",
    "JEU_ENFANTS": "JEUX_ENFANTS",
    "JEUX_ENFANTS": "JEUX_ENFANTS",
    "COSMETIQUE": "COSMETIQUE",
    "COSMÉTIQUE": "COSMETIQUE",
    "SOUVENIRS": "SOUVENIRS",
    "REF": "REF",
}

CANON_GAMMES = set(GAMME_MAP.values())

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

# Couleurs / tailles / conditionnements à retirer pour NATURE_PRODUIT
_COLOR_TOKENS = {
    "noir", "noire", "noirs", "noires", "black",
    "blanc", "blanche", "blancs", "blanches", "white",
    "bleu", "bleue", "bleus", "bleues", "blue",
    "rouge", "red",
    "vert", "verte", "verts", "vertes", "green",
    "jaune", "yellow",
    "orange",
    "rose", "pink",
    "violet", "violette", "purple",
    "marine", "navy",
    "turquoise", "menthe", "pastel",
    "gris", "grise", "grey", "gray",
    "beige", "marron", "brown",
    "dore", "doree", "dorees", "gold",
    "argent", "silver",
    "petrol", "petrol", "kaki", "ivoire",
    "multicolore", "imprimee", "imprime",
}
_SIZE_TOKENS = {
    "xs", "s", "m", "l", "xl", "xxl", "xxxl", "tu", "tu*", "t.u",
    "taille", "size",
    "femme", "femmes", "homme", "hommes", "fille", "filles",
    "garcon", "garcons", "garçon", "garçons",
    "enfant", "enfants", "adulte", "adultes", "mixte",
    "bebe", "bébé",
}
_PACK_TOKENS = {
    "pet", "bte", "canette", "can", "slim", "btl", "bouteille",
    "verre", "plastique", "alu", "aluminium",
    "pack", "lot",
}


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


def nature_produit(name: object) -> object:
    """
    Nature de produit (similaires regroupés) :

    - retire volumes (33cl, 50cl, 45g, 1,5l, SPF 30, cm, kg…)
    - retire tailles (XS/S/M/L/XL/TU, 11-30 kg)
    - retire couleurs (noir, bleu, rose…)
    - retire genre (homme/femme/enfant) et conditionnement (PET, BTE, canette)
    - normalise marques fréquentes (Coca-Cola, tongs…)

    Ex. « Coca-Cola PET 50cl » → « Coca-Cola »
        « Coca-Cola Zero Slim BTE 33cl » → « Coca-Cola Zero »
        « Tongs Femme 100 Noir » → « Tongs »
        « Short Running Homme Dry Noir L » → « Short Running Dry »
    """
    if name is None or (isinstance(name, float) and pd.isna(name)):
        return pd.NA
    s = clean_product_name(name)
    if pd.isna(s):
        return pd.NA
    s = str(s)
    low0 = s.lower()

    # --- Marques / familles connues en premier (avant strip couleur) ---
    if re.search(r"\btongs?\b|\bthong\b", low0):
        return "Tongs"
    if "coca" in low0:
        if re.search(r"\bzero\b", low0):
            return "Coca-Cola Zero"
        if re.search(r"\bcherry\b", low0):
            return "Coca-Cola Cherry"
        if re.search(r"\blight\b", low0):
            return "Coca-Cola Light"
        return "Coca-Cola"
    if re.search(r"\bred\s*bull\b|\bredbull\b", low0):
        return "Red Bull"
    if re.search(r"\bsprite\b", low0):
        return "Sprite"
    if re.search(r"\bfanta\b", low0):
        return "Fanta"
    if re.search(r"\bperrier\b", low0):
        return "Perrier"
    if re.search(r"\bvittel\b", low0):
        return "Vittel"
    if re.search(r"\bevian\b", low0):
        return "Evian"
    if re.search(r"\borangina\b", low0):
        return "Orangina"
    if re.search(r"\bice\s*tea\b|\blipton\b|\bfuze\s*tea\b|\bfuse\s*tea\b", low0):
        return "Ice Tea"
    if re.search(r"\bpringles\b", low0):
        return "Pringles"
    if re.search(r"\bdoritos\b", low0):
        return "Doritos"
    if re.search(r"\blay'?s\b", low0):
        return "Chips Lay's" if "chip" in low0 else "Lay's"
    if re.search(r"\bkinder\s+bueno", low0):
        if re.search(r"\bwhite\b|\bblanc\b", low0):
            return "Kinder Bueno White"
        return "Kinder Bueno"
    if re.search(r"\bm&m", low0):
        return "M&M's Peanut" if "peanut" in low0 else "M&M's"
    if re.search(r"\bsan\s*pellegrino\b", low0):
        return "San Pellegrino"
    if re.search(r"\bschweppes\b", low0):
        return "Schweppes"

    # Unités / volumes / dimensions
    s = re.sub(
        r"\b\d+[.,]?\d*\s*(?:cl|ml|l|g|kg|cm|mm|m)\b",
        " ",
        s,
        flags=re.I,
    )
    s = re.sub(r"\b\d+[.,]?\d*(?:cl|ml|l|g|kg|cm|mm)\b", " ", s, flags=re.I)
    s = re.sub(r"\b\d+\s*[-x×]\s*\d+\s*(?:kg|cm|mm|g|uk)?\b", " ", s, flags=re.I)
    s = re.sub(r"\buk\s*\d+[.,]?\d*(?:\s*[-/]\s*\d+[.,]?\d*)?\b", " ", s, flags=re.I)
    s = re.sub(r"\b\d+\s*%\b", " ", s)
    s = re.sub(r"\bSPF\s*\d+\b", " ", s, flags=re.I)
    s = re.sub(r"\bcatégorie\s*\d+\b", " ", s, flags=re.I)
    s = re.sub(r"\bcategorie\s*\d+\b", " ", s, flags=re.I)
    s = re.sub(r"\b[A-Z]{1,3}\d{2,4}[A-Z]?\b", " ", s)
    s = re.sub(r"\b\d{2,4}\b", " ", s)
    s = re.sub(r"\([^)]*\)", " ", s)
    s = re.sub(r"\[[^\]]*\]", " ", s)

    # "red" est une couleur mais aussi marque → ne pas strip si seul
    color_drop = _COLOR_TOKENS - {"red"}  # Red Bull déjà géré plus haut
    words = re.split(r"[\s/_\-]+", s)
    kept: list[str] = []
    for w in words:
        if not w:
            continue
        wl = w.lower().strip(".,;:*+")
        if not wl:
            continue
        if wl in color_drop or wl in _SIZE_TOKENS or wl in _PACK_TOKENS:
            continue
        if re.fullmatch(r"\d+[.,]?\d*", wl):
            continue
        kept.append(w)

    s = " ".join(kept)
    s = re.sub(r"\s+", " ", s).strip(" -/")
    if s and (s.isupper() or s.islower()):
        s = s.title()
    return s if s else pd.NA


def _slug_key(value: object) -> str:
    """Clé de lookup : upper, sans accents, espaces/tirets → underscore."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    s = str(value).strip()
    if not s or s.lower() in {"nan", "none", "<na>", "nat"}:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.upper().replace("&", "_")
    s = re.sub(r"[^A-Z0-9]+", "_", s)
    return re.sub(r"_+", "_", s).strip("_")


def normalize_type(value: object) -> object:
    """Canon TYPE : F_B | NON_F_B."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return pd.NA
    key = _slug_key(value)
    if not key:
        return pd.NA
    # F&B variants
    if key in {"F_B", "FB", "F_AND_B", "FOOD", "F_B_"}:
        return "F_B"
    if key in {
        "NON_F_B",
        "NON_FB",
        "NONF_B",
        "NONFB",
        "N_F_B",
        "NFB",
        "NON_FOOD",
        "NON_F_AND_B",
    }:
        return "NON_F_B"
    # already almost-canon
    if key.replace("-", "_") == "F_B":
        return "F_B"
    if "NON" in key and ("F_B" in key or key.endswith("FB") or "FOOD" in key):
        return "NON_F_B"
    if key in {"F_B", "NON_F_B"}:
        return key
    return pd.NA


def normalize_gamme(value: object) -> object:
    """Canon GAMME (underscore). Conserve valeur sluguée si inconnue."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return pd.NA
    raw = str(value).strip()
    if not raw or raw.lower() in {"nan", "none", "<na>"}:
        return pd.NA
    # exact map (case-sensitive keys in GAMME_MAP)
    if raw in GAMME_MAP:
        return GAMME_MAP[raw]
    upper = raw.upper().strip()
    if upper in GAMME_MAP:
        return GAMME_MAP[upper]
    # strip parentheticals e.g. "SALTY FOOD (Fresh)"
    base = re.sub(r"\s*\([^)]*\)\s*", " ", upper).strip()
    base = re.sub(r"\s+", " ", base)
    if base in GAMME_MAP:
        return GAMME_MAP[base]
    # slug lookup
    key = _slug_key(raw)
    slug_map = {_slug_key(k): v for k, v in GAMME_MAP.items()}
    if key in slug_map:
        return slug_map[key]
    # partial food
    if "SALTY" in key or key in {"FOOD_SALEE", "FOODSALEE"}:
        return "FOOD_SALEE"
    if "SUGARY" in key or key in {"FOOD_SUCREE", "FOODSUCREE"}:
        return "FOOD_SUCREE"
    if "SANS" in key and "ALCOOL" in key:
        return "SANS_ALCOOL"
    if key == "ALCOOL":
        return "ALCOOL"
    if "JEU" in key:
        return "JEUX_ENFANTS"
    if key in CANON_GAMMES:
        return key
    # fallback : slug upper
    return key if key else pd.NA


def map_gamme_series(s: pd.Series) -> pd.Series:
    return s.map(normalize_gamme)


def map_type_series(s: pd.Series) -> pd.Series:
    return s.map(normalize_type)


def compute_categorie_row(type_, gamme_raw, gamme) -> str:
    if pd.isna(type_):
        return "Unknown"
    t = normalize_type(type_)
    if t == "NON_F_B":
        return "NonF&B"

    g_raw = str(gamme_raw).strip() if pd.notna(gamme_raw) else ""
    g = normalize_gamme(gamme) if pd.notna(gamme) else ""
    g = str(g) if pd.notna(g) else ""

    if g in ("FOOD_SALEE", "FOOD_SUCREE", "SALTY FOOD", "SUGARY FOOD"):
        if "(Fresh)" in g_raw or "(fresh)" in g_raw:
            return "Fresh"
        if "(Dry)" in g_raw or "(dry)" in g_raw:
            return "Dry"
        # Ancien codage Accor (souvent imprécis hors mapping)
        if g_raw.upper() in {"FOOD SALEE", "FOOD SALÉE"}:
            return "Fresh"
        if g_raw.upper() in {"FOOD SUCREE", "FOOD SUCRÉE"}:
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
        return "NON_F_B"
    if BIERE_KW.search(name) or ALCOOL_KW.search(name):
        return "F_B"
    types = [normalize_type(x) for x in group["type"].dropna()]
    types = [str(t) for t in types if pd.notna(t)]
    if not types:
        gammes = [normalize_gamme(g) for g in group["gamme"].dropna()]
        gammes = {str(g) for g in gammes if pd.notna(g)}
        if gammes & {
            "ALCOOL",
            "SANS_ALCOOL",
            "FOOD_SALEE",
            "FOOD_SUCREE",
            "FORMULE",
        }:
            return "F_B"
        return "NON_F_B"
    return Counter(types).most_common(1)[0][0]


def resolve_gamme(group: pd.DataFrame, name: str, type_: str) -> str:
    if BIERE_KW.search(name):
        return "ALCOOL"

    gammes = [normalize_gamme(x) for x in group["gamme"].dropna()]
    gammes = [str(g) for g in gammes if pd.notna(g)]
    c = Counter(gammes) if gammes else Counter()
    type_n = normalize_type(type_)

    if type_n == "NON_F_B" or type_ == "NON-F&B":
        if GOURDE_KW.search(name):
            return "ACCESSOIRES"
        if PAP_KW.search(name):
            return "PAP"
        if JEU_KW.search(name):
            return "JEUX_ENFANTS"
        if COSM_KW.search(name) or re.search(r"d[eé]odorant|respire", name, re.I):
            return "SOS" if re.search(r"d[eé]odorant|respire", name, re.I) else "COSMETIQUE"
        if SOS_KW.search(name):
            return "SOS"
        if re.search(
            r"lunette|serviette|gamelle|sac|tot\s*bag|raquette|bou[eé]e",
            name,
            re.I,
        ):
            if "JEUX_ENFANTS" in c and re.search(r"bou[eé]e|raquette", name, re.I):
                return "JEUX_ENFANTS"
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
        return "FOOD_SUCREE"
    if c:
        if "ALCOOL" in c and ALCOOL_KW.search(name):
            return "ALCOOL"
        if "FOOD_SALEE" in c and "FOOD_SUCREE" in c:
            if re.search(r"chocolat|bonbon|cookie|sucr", name, re.I):
                return "FOOD_SUCREE"
        return c.most_common(1)[0][0]
    return "SANS_ALCOOL"


def resolve_categorie(
    group: pd.DataFrame, name: str, type_: str, gamme: str
) -> str:
    if normalize_type(type_) == "NON_F_B":
        return "NonF&B"
    g = normalize_gamme(gamme)
    g = str(g) if pd.notna(g) else ""
    if g not in ("FOOD_SALEE", "FOOD_SUCREE", "SALTY FOOD", "SUGARY FOOD"):
        return g if g else "Unknown"

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
def _ensure_raw_column(df: pd.DataFrame, raw_col: str, src_col: str) -> None:
    """
    Garantit ``raw_col`` = original intact.
    - Si RAW déjà présent et non vide → on le garde (ne pas écraser).
    - Sinon on copie depuis ``src_col`` avant normalisation.
    """
    if raw_col in df.columns:
        raw = df[raw_col]
        # si entièrement NA, reprendre src
        if raw.notna().any():
            return
    if src_col in df.columns:
        df[raw_col] = df[src_col]
    else:
        df[raw_col] = pd.NA


def clean_raw(
    raw_df: pd.DataFrame, by_hp: pd.DataFrame, by_p: pd.DataFrame
) -> pd.DataFrame:
    df = raw_df.copy()

    # RAW intacts (ne pas écraser si déjà posés par un run précédent)
    _ensure_raw_column(df, "TYPE_RAW", "TYPE")
    _ensure_raw_column(df, "GAMME_RAW", "GAMME")
    _ensure_raw_column(df, "NOM_PRODUIT_RAW", "NOM_PRODUIT")

    df["_boutique_key"] = (
        df["NOM_BOUTIQUE"].astype(str).str.strip()
        if "NOM_BOUTIQUE" in df.columns
        else ""
    )
    df["_produit_key"] = df["NOM_PRODUIT_RAW"].astype(str).str.strip()

    if by_hp is not None and not by_hp.empty:
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
    else:
        for c in ("type_map_hp", "gamme_map_hp", "nom_produit_map_hp", "categorie_map_hp"):
            df[c] = pd.NA

    if by_p is not None and not by_p.empty:
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
    else:
        for c in ("type_map_p", "gamme_map_p", "nom_produit_map_p", "categorie_map_p"):
            df[c] = pd.NA

    # TYPE normalisé (map correctifs → canon F_B / NON_F_B)
    type_mapped = df["type_map_hp"].combine_first(df["type_map_p"])
    df["TYPE"] = map_type_series(type_mapped.combine_first(df["TYPE_RAW"]))

    # GAMME normalisée
    gamme_mapped = df["gamme_map_hp"].combine_first(df["gamme_map_p"])
    df["GAMME"] = map_gamme_series(gamme_mapped.combine_first(df["GAMME_RAW"]))

    print("  → Nettoyage des noms de produits…")
    cleaned_names = df["NOM_PRODUIT_RAW"].map(clean_product_name)
    # mapping produit prioritaire, puis clean_product_name sur RAW
    mapped_names = df["nom_produit_map_hp"].combine_first(df["nom_produit_map_p"])
    # re-clean mapped names too (espaces, Title Case, marques)
    df["NOM_PRODUIT"] = mapped_names.map(
        lambda x: clean_product_name(x) if pd.notna(x) else pd.NA
    ).combine_first(cleaned_names)

    print("  → Nature produit (similaires sans taille/couleur/volume)…")
    df["NATURE_PRODUIT"] = df["NOM_PRODUIT"].map(nature_produit)

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

    # Cohérence TYPE NON_F_B → categorie
    nonfb_mask = df["TYPE"].astype(str).eq("NON_F_B")
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
        "NATURE_PRODUIT",
        "CATEGORIE",
    ]
    other = [c for c in df.columns if c not in core]
    return df[other + core]


def renorm_identifiers(df: pd.DataFrame) -> pd.DataFrame:
    """
    Re-normalise TYPE / GAMME / NOM_PRODUIT en place sur un fichier déjà
    extended/clean, **sans toucher** TYPE_RAW / GAMME_RAW / NOM_PRODUIT_RAW.
    """
    out = df.copy()
    prev_type = df["TYPE"] if "TYPE" in df.columns else pd.Series(pd.NA, index=df.index)
    prev_gamme = df["GAMME"] if "GAMME" in df.columns else pd.Series(pd.NA, index=df.index)
    prev_prod = (
        df["NOM_PRODUIT"] if "NOM_PRODUIT" in df.columns else pd.Series(pd.NA, index=df.index)
    )

    _ensure_raw_column(out, "TYPE_RAW", "TYPE")
    _ensure_raw_column(out, "GAMME_RAW", "GAMME")
    _ensure_raw_column(out, "NOM_PRODUIT_RAW", "NOM_PRODUIT")

    # Priorité RAW → sinon re-normalise l'ancienne colonne normalisée
    out["TYPE"] = map_type_series(out["TYPE_RAW"]).combine_first(
        map_type_series(prev_type)
    )
    out["GAMME"] = map_gamme_series(out["GAMME_RAW"]).combine_first(
        map_gamme_series(prev_gamme)
    )
    from_raw = out["NOM_PRODUIT_RAW"].map(clean_product_name)
    from_prev = prev_prod.map(
        lambda x: clean_product_name(x) if pd.notna(x) else pd.NA
    )
    out["NOM_PRODUIT"] = from_raw.combine_first(from_prev)
    out["NATURE_PRODUIT"] = out["NOM_PRODUIT"].map(nature_produit)

    # CATEGORIE
    out["CATEGORIE"] = [
        compute_categorie_row(t, gr, g)
        for t, gr, g in zip(out["TYPE"], out["GAMME_RAW"], out["GAMME"])
    ]
    out.loc[out["TYPE"].astype(str).eq("NON_F_B"), "CATEGORIE"] = "NonF&B"
    return out


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
        "--renorm-extended",
        type=Path,
        default=None,
        metavar="XLSX",
        help=(
            "Re-normalise TYPE/GAMME/NOM_PRODUIT sur un fichier extended "
            "(défaut si flag sans path : data/hotel_sales_raw_extended_data.xlsx). "
            "Ne touche pas *_RAW."
        ),
        nargs="?",
        const=Path("data/hotel_sales_raw_extended_data.xlsx"),
    )
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

    # Mode dédié : re-normaliser le fichier extended sans toucher *_RAW
    if args.renorm_extended is not None:
        path = args.renorm_extended
        if not path.exists():
            # alias fréquent
            alt = Path("data/hotel_sales_extended_raw_data.xlsx")
            if alt.exists():
                path = alt
        if not path.exists():
            print(f"❌ Fichier introuvable : {path}")
            sys.exit(1)
        print(f"Re-normalisation TYPE / GAMME / NOM_PRODUIT sur {path}")
        print("  (*_RAW intacts)")
        df = pd.read_excel(path)
        before_t = df["TYPE"].nunique() if "TYPE" in df.columns else 0
        before_g = df["GAMME"].nunique() if "GAMME" in df.columns else 0
        before_p = df["NOM_PRODUIT"].nunique() if "NOM_PRODUIT" in df.columns else 0
        out = renorm_identifiers(df)
        print_qa(out)
        out.to_excel(path, index=False)
        print(
            f"✅ Écrit {path} | TYPE {before_t}→{out['TYPE'].nunique()} | "
            f"GAMME {before_g}→{out['GAMME'].nunique()} | "
            f"PRODUIT {before_p}→{out['NOM_PRODUIT'].nunique()}"
        )
        return

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
    print("  NATURE_PRODUIT    (similaires sans taille/couleur/volume)")
    print("  CATEGORIE         (Fresh / Dry / NonF&B / ou fallback gamme)")


if __name__ == "__main__":
    main()
