#!/usr/bin/env python3
"""
1) Simplifie NATURE_PRODUIT via une table de mapping (ex. CASQUETTE MH100 → CASQUETTE).
2) Corrige PRIX_TTC_MARCHE / MARGE pour les lignes à marge ≤ 0
   avec des prix marché réalistes (supermarché / Decathlon France).

Écrit :
  - data/nature_produit_simplify_mapping.json
  - data/prix_marche_mapping.json
  - data/hotel_sales_raw_extended_data.xlsx (écrasé atomiquement)
"""
from __future__ import annotations

import json
import re
import shutil
import unicodedata
from pathlib import Path

import pandas as pd

DATA = Path(__file__).resolve().parent / "data"
EXT_PATH = DATA / "hotel_sales_raw_extended_data.xlsx"
NATURE_MAP_PATH = DATA / "nature_produit_simplify_mapping.json"
PRICE_MAP_PATH = DATA / "prix_marche_mapping.json"
TMP_OUT = Path("/tmp/hotel_sales_raw_extended_data_fixed.xlsx")


def _norm(s: object) -> str:
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return ""
    t = str(s).strip()
    if not t or t.lower() in {"nan", "none", "<na>", "nat"}:
        return ""
    t = unicodedata.normalize("NFKD", t)
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.upper()
    t = re.sub(r"[^A-Z0-9]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


# ---------------------------------------------------------------------------
# 1) NATURE_PRODUIT → famille simplifiée
#    Ordre : règles spécifiques d'abord, génériques ensuite.
# ---------------------------------------------------------------------------
# (pattern_regex, nature_simplifiee) — pattern testé sur nature normalisée
NATURE_RULES: list[tuple[re.Pattern[str], str]] = [
    # --- Non-F&B accessoires sport / plage ---
    (re.compile(r"^CASQUETTE|^ADIDAS CASQUETTE"), "CASQUETTE"),
    (re.compile(r"^MASQUE"), "MASQUE"),
    (re.compile(r"^LUNETTE?S? DE NATATION"), "LUNETTES DE NATATION"),
    (re.compile(r"^LUNETTE?S? DE SOLEIL"), "LUNETTES DE SOLEIL"),
    (re.compile(r"^GOURDE"), "GOURDE"),
    (re.compile(r"^TONGS?$|^TONGS\b"), "TONGS"),
    (re.compile(r"^ADAPTATEUR"), "ADAPTATEUR"),
    (re.compile(r"^CHARGEUR"), "CHARGEUR"),
    (re.compile(r"^CABLE"), "CABLE"),
    (re.compile(r"^ECOUTEUR"), "ECOUTEUR"),
    (re.compile(r"^BATTERIE DE SECOURS"), "BATTERIE DE SECOURS"),
    (re.compile(r"^PARAPLUIE|^MINI PARAPLUIE|^GRAND PARAPLUIE|^PETIT PARAPLUIE"), "PARAPLUIE"),
    (re.compile(r"^PONCHO|^PANCHO"), "PONCHO"),
    (re.compile(r"^BRASSARDS"), "BRASSARDS"),
    (re.compile(r"^BOUEE"), "BOUEE"),
    (re.compile(r"^MAILLOT DE BAIN|^BOXER DE BAIN"), "MAILLOT DE BAIN"),
    (re.compile(r"^BONNET DE BAIN"), "BONNET DE BAIN"),
    (re.compile(r"^CHAUSSURES AQUATIQUES|^AQUASHOES"), "CHAUSSURES AQUATIQUES"),
    (re.compile(r"^SERVIETTE DE PLAGE|^SERVIETTE DE BAIN|^MF COMPACT TOWEL"), "SERVIETTE"),
    (re.compile(r"^TROUSSE DE TOILETTE|^TROUSSE DE VOYAGE"), "TROUSSE"),
    (re.compile(r"^KIT DENTAIRE"), "KIT DENTAIRE"),
    (re.compile(r"^KIT RASAGE"), "KIT RASAGE"),
    (re.compile(r"^DEODORANT|^RESPIRE DEODORANT"), "DEODORANT"),
    (re.compile(r"^CREME SOLAIRE|^SPRAY PROTECTION SOLAIRE|^RITUALS CREME SOLAIRE"), "CREME SOLAIRE"),
    (re.compile(r"^BAUME A? ?LEVRE|^BAUME LEVRES|^STICK LEVRES|^NUXE BAUME LEVRES|^MIEL A LEVRES"), "BAUME LEVRES"),
    (re.compile(r"^GEL HYDROALCOOLIQUE|^SPRAY MAINS PROPRES"), "GEL HYDROALCOOLIQUE"),
    (re.compile(r"^SPRAY FACIAL|^BRUMISATEUR"), "SPRAY FACIAL"),
    (re.compile(r"^SPRAY REPULSIF|^ANTI MOUSTIQUE"), "ANTI MOUSTIQUE"),
    (re.compile(r"^PRESERVATIF"), "PRESERVATIF"),
    (re.compile(r"^TAMPONS|^SERVIETTE HYGIENIQUE|^CARRES LOVE"), "HYGIENE FEMININE"),
    (re.compile(r"^PELUCHE"), "PELUCHE"),
    (re.compile(r"^T SHIRT|^TSHIRT"), "T SHIRT"),
    (re.compile(r"^SHORT\b|^BOARDSHORT"), "SHORT"),
    (re.compile(r"^CHAUSSETTE|^SOCKS"), "CHAUSSETTES"),
    (re.compile(r"^BONNET\b"), "BONNET"),
    (re.compile(r"^ECHARPE|^SCARF"), "ECHARPE"),
    (re.compile(r"^PULL\b|^PULLOVER|^POLAIRE"), "POLAIRE"),
    (re.compile(r"^DOUDOUNE|^VESTE"), "VESTE"),
    (re.compile(r"^SAC A DOS|^SAC DE COURSES|^SAC BANANE|^RAINS |^TOTE BAG|^TOT BAG|^POCHETTE"), "SAC"),
    (re.compile(r"^ISOTHERME"), "ISOTHERME"),
    (re.compile(r"^MUG\b|^GAMELLE"), "MUG"),
    (re.compile(r"^TIRE BOUCHON"), "TIRE BOUCHON"),
    (re.compile(r"^CARTE POSTALE"), "CARTE POSTALE"),
    (re.compile(r"^CARTE SIM"), "CARTE SIM"),
    (re.compile(r"^PORTE CLE"), "PORTE CLE"),
    (re.compile(r"^BOUGIE"), "BOUGIE"),
    (re.compile(r"^FEUTRES|^CRAYONS|^BLOC A COLORIER|^MES COLORIAGES|^MON CAHIER|^COLORIAGE"), "COLORIAGE"),
    (re.compile(r"^PUZZLE|^LEGO|^RUBIK|^JEU |^UNO|^MIKADO|^QUI EST CE|^BORNES"), "JEU"),
    (re.compile(r"^BALLON|^RAQUETTE|^SET RAQUETTES|^FRITE DE PLAGE|^PALMS "), "SPORT PLAGE"),
    (re.compile(r"^CHAUFFERETTES"), "CHAUFFERETTES"),
    (re.compile(r"^BERET"), "BERET"),
    (re.compile(r"^LEGGING"), "LEGGING"),
    (re.compile(r"^GANTS"), "GANTS"),
    (re.compile(r"^TOUR DE COU"), "TOUR DE COU"),
    (re.compile(r"^CARRE DE SOIE"), "CARRE DE SOIE"),
    (re.compile(r"^TOUR EIFFEL"), "SOUVENIR"),
    (re.compile(r"^NESPRESSO"), "NESPRESSO"),
    (re.compile(r"^RITUALS"), "RITUALS"),
    (re.compile(r"^NUXE"), "NUXE"),
    (re.compile(r"^CREME MAINS|^CREME MAIN|^CREME CORPS|^CREME SOIN|^LAIT CORPS|^GOMMAGE|^HUILE DEMAQUILLANTE|^GEL LAVANT|^GELEE ACTIVE|^CREME RICHE|^DENTIFRICE|^SOIN NETTOYANT|^AVRIL |^POT CREME|^BAUME VISAGE"), "COSMETIQUE"),
    (re.compile(r"^PARFUM |^EAU SAVOU"), "PARFUM"),
    # --- Chips / snacking salé ---
    (re.compile(r"CHIP|PRINGLES|DORITOS|LAY.?S|SO ?CHIPS|BRETS "), "CHIPS"),
    (re.compile(r"^CACAHUETE|^CACAHUETES"), "CACAHUETES"),
    (re.compile(r"^GRAINES DE FOLIE|^MELANGE DE GRAINES|^GRAINES DE FOLIES"), "GRAINES"),
    (re.compile(r"^TUC\b|^GRISSIN|^GRESSIN|^MINI FEUILLETE|^MINIS FEUILLETE|^MINIS PALMIERS|^BISCUIT.*APERITIF|^SABLES APERITIF|^BRICELETS|^GRELOTS"), "APERITIF SALE"),
    (re.compile(r"^MINI SAUCISSON"), "SAUCISSON"),
    # --- Confiserie / chocolat ---
    (re.compile(r"^KINDER BUENO|^KINDERBUENO"), "KINDER BUENO"),
    (re.compile(r"^KINDER MAXI|^KINDER\b"), "KINDER"),
    (re.compile(r"^M AND MS|^M M S"), "M AND MS"),
    (re.compile(r"^TWIX\b"), "TWIX"),
    (re.compile(r"^SNICKERS"), "SNICKERS"),
    (re.compile(r"^MARS\b"), "MARS"),
    (re.compile(r"^LION\b"), "LION"),
    (re.compile(r"^BOUNTY"), "BOUNTY"),
    (re.compile(r"^TOBLERONE"), "TOBLERONE"),
    (re.compile(r"^KIT KAT"), "KIT KAT"),
    (re.compile(r"^CRUNCH"), "CRUNCH"),
    (re.compile(r"^SMARTIES"), "SMARTIES"),
    (re.compile(r"^SPECIAL K"), "SPECIAL K"),
    (re.compile(r"^DRAGIBUS|^HARIBO DRAGIBUS"), "DRAGIBUS"),
    (re.compile(r"^FRAISE TAGADA|^FRAISES TAGADA|^TAGADA"), "FRAISE TAGADA"),
    (re.compile(r"^HARIBO|^CONFISERIE|^BONBON|^SACHETS DE BONBONS|^OURSONS GUIMAUVE|^SACHET OURSONS|^GUIMAUVE|^ORANGETTES|^NOUGAT|^PASTILLE|^PATES DE FRUITS"), "CONFISERIE"),
    (re.compile(r"^BARRE CHOCOL|^BARRE DE CEREALE|^BARRES |^BLAST |^NEWTREE|^L INCROYABLE BARRE|^MONKA "), "BARRE"),
    (re.compile(r"^TABLETTE|^CARRES DE CHOCOLAT|^PETIT CARRE|^TRUFFES CHOCOLAT|^AMANDES TRUFFEES|^TOMME EN CHOCOLAT|^CHOCOLAT |^GAUFRETTES TORTINA|^TORTINA "), "CHOCOLAT"),
    (re.compile(r"^COOKIE|^BISCUIT|^MADELEINE|^SABLES |^PETITS SABLES|^SHORTBREAD|^BOITES? DE BISCUITS|^PETITE BOITE DE BISCUITS|^ASSORTIMENT DE BISCUITS|^MUFFIN|^BROWNIE|^GAUFRES |^LOAF |^CAKE |^TRANCHE DE PANETTONE|^MINI MOELLEUX|^PETIT FINANC"), "BISCUIT"),
    # --- Boissons ---
    (re.compile(r"^COCA COLA ZERO"), "COCA COLA ZERO"),
    (re.compile(r"^COCA COLA CHERRY"), "COCA COLA CHERRY"),
    (re.compile(r"^COCA COLA"), "COCA COLA"),
    (re.compile(r"^SPRITE"), "SPRITE"),
    (re.compile(r"^FANTA"), "FANTA"),
    (re.compile(r"^ORANGINA"), "ORANGINA"),
    (re.compile(r"^SCHWEPPES"), "SCHWEPPES"),
    (re.compile(r"^OASIS"), "OASIS"),
    (re.compile(r"^ICE TEA|^FUZE TEA|^VITAO TEA"), "ICE TEA"),
    (re.compile(r"^RED BULL"), "RED BULL"),
    (re.compile(r"^VITTEL"), "VITTEL"),
    (re.compile(r"^EVIAN"), "EVIAN"),
    (re.compile(r"^PERRIER"), "PERRIER"),
    (re.compile(r"^SAN PELLEGRINO"), "SAN PELLEGRINO"),
    (re.compile(r"^BADOIT"), "BADOIT"),
    (re.compile(r"^L EAU NEUVE|^EAU NEUVE"), "EAU NEUVE"),
    (re.compile(r"^SAN BENEDETTO"), "SAN BENEDETTO"),
    (re.compile(r"^CRISTALLINE|^EAU PLATE CRISTALINE|^EAU GAZEUSE CRISTALINE"), "CRISTALINE"),
    (re.compile(r"^EAU PLATE OCEAN|^EAU GAZEUSE OCEAN|^EAU PLATE$|^EAU GAZEUSE$"), "EAU"),
    (re.compile(r"^HEINEKEN|^BIERE HEINEKEN"), "HEINEKEN"),
    (re.compile(r"^BIERE |^GALLIA|^CORONA|^DESPERADOS|^TOURTEL|^DUVEL|^MORT SUBITE|^BACCHANTE|^LA DEBAUCHE|^SESSION PALE"), "BIERE"),
    (re.compile(r"^CHAMPAGNE"), "CHAMPAGNE"),
    (re.compile(r"^VIN\b|^CHABLY|^CHATEAU |^IGP |^MOULIN A VENT"), "VIN"),
    (re.compile(r"^LIQUEUR|^GENEPI"), "LIQUEUR"),
    (re.compile(r"^JUS |^NECTAR |^PLEIN FRUIT|^MARCEL BIO|^LEAMO |^BAHIA |^CARROT SUNSET|^MINUTE MAID|^PULCO |^BELVOIR |^HUGO LE MARAICHER|^SUPER ANTIOXYDANT|^CHILLED |^KEFIR |^KOMBUCHA|^SHOZU |^TAO PURE"), "JUS"),
    (re.compile(r"^LIMONADE"), "LIMONADE"),
    # --- Frais / plats ---
    (re.compile(r"^YAOURT"), "YAOURT"),
    (re.compile(r"^CLUB |^SANDWICH|^MEGA SANDWICH|^SODEBO SANDWICH|^SANSWICH|^F SANDWICH|^IL PAGNOTTO|^SUEDOIS |^LA FRENCH BAGUETTE|^FORMULE SANDWICH"), "SANDWICH"),
    (re.compile(r"^WRAP "), "WRAP"),
    (re.compile(r"^BURGER |^PALMS BURGER"), "BURGER"),
    (re.compile(r"^FRENCH TACOS"), "TACOS"),
    (re.compile(r"^PASTA BOX|^PASTA BOLOGNAISE|^SPAGHETTI |^GNOCHI|^GNOCCHI|^RAVIOLI |^RAVIOLE |^NOUILLES |^PATES |^CROZETS|^CROZET "), "PATES"),
    (re.compile(r"^RISOTTO|^GOOD BOWL|^POKE BOWL|^SALADE |^BOULGOUR"), "SALADE BOWL"),
    (re.compile(r"^SOUPE |^GASPACHO|^VELOUTE "), "SOUPE"),
    (re.compile(r"^POULET |^B UF |^FILET |^FILETS |^SAUMON |^CONFIT CANARD|^JOUE DE BOEUF|^PECHE DU JOUR|^TATAKI |^PARMIGIANA|^TARTIFLETTE|^QUICHE "), "PLAT"),
    (re.compile(r"^BOCAUX |^TERRINE |^RILLETTES |^HOUMMOUS|^HOUMOUS|^TAPENADE|^POIVRONADE|^TARAMA|^OLIVES |^PESTO |^SARDINES |^VENTRECHE |^PATE BASQUE|^OEUF DE SAUMON"), "TRAITEUR"),
    (re.compile(r"^MOUSSE AU CHOCOLAT|^CREME BRULEE|^CREME VANILLE|^CREME CAFE|^RIZ AU LAIT|^COMPOTE|^COMP POMME|^PUREE POMME|^PANNA COTTA|^LE PETIT POT DE CHOCOLAT|^FONDANT |^TARTE |^MINI TARTE|^CITRON A LA CREME"), "DESSERT"),
    (re.compile(r"^CONFITURE"), "CONFITURE"),
    (re.compile(r"^MIEL "), "MIEL"),
    (re.compile(r"^KIT COUVERTS"), "KIT COUVERTS"),
    (re.compile(r"^BENTO |^SALADE BOUTIQUE|^PALM SUSHI"), "PLAT"),
    (re.compile(r"^UNBEKANNT|^K2101|^KJ2203"), "DIVERS"),
]


def simplify_nature(nature: object) -> str:
    n = _norm(nature)
    if not n:
        return ""
    for pat, target in NATURE_RULES:
        if pat.search(n):
            return target
    # fallback : 1er mot significatif (retire codes type MH100)
    words = [w for w in n.split() if not re.fullmatch(r"[A-Z]{0,3}\d{2,4}[A-Z]?", w)]
    if not words:
        return n
    # 1-2 premiers mots max pour rester générique
    if len(words) == 1:
        return words[0]
    # si 2e mot est un déterminant / de / a / l → garder 2-3 mots utiles
    stop = {"DE", "DU", "DES", "LA", "LE", "LES", "A", "AU", "AUX", "EN", "ET", "L", "D"}
    if words[1] in stop and len(words) >= 3:
        return " ".join(words[:3])
    return " ".join(words[:2]) if words[1] not in stop else words[0]


# ---------------------------------------------------------------------------
# 2) Prix marché unitaires TTC (€) — sources supermarché / Decathlon France
#    Clé = NATURE simplifiée (ou NOM_PRODUIT exact pour overrides).
# ---------------------------------------------------------------------------
# Prix indicatifs rayon France (Carrefour / Leclerc / Decathlon / Amazon FR)
# Objectif : prix d'achat client hors hôtel, strictement < prix hôtel typique.
UNIT_MARKET_BY_NATURE: dict[str, float] = {
    # Eaux
    "VITTEL": 0.70,
    "EVIAN": 0.75,
    "PERRIER": 0.85,
    "SAN PELLEGRINO": 0.95,
    "BADOIT": 0.85,
    "EAU NEUVE": 1.80,
    "SAN BENEDETTO": 0.90,
    "CRISTALINE": 0.40,
    "EAU": 0.50,
    # Softs
    "COCA COLA": 1.00,
    "COCA COLA ZERO": 1.00,
    "COCA COLA CHERRY": 1.10,
    "SPRITE": 1.00,
    "FANTA": 1.00,
    "ORANGINA": 1.05,
    "SCHWEPPES": 1.00,
    "OASIS": 1.00,
    "ICE TEA": 1.00,
    "RED BULL": 1.80,
    "JUS": 1.50,
    "LIMONADE": 1.20,
    # Alcool
    "HEINEKEN": 1.40,
    "BIERE": 1.80,
    "VIN": 6.00,
    "CHAMPAGNE": 18.00,
    "LIQUEUR": 12.00,
    # Confiserie
    "KINDER BUENO": 1.20,
    "KINDER": 1.10,
    "TWIX": 1.00,
    "SNICKERS": 1.00,
    "MARS": 1.00,
    "LION": 1.00,
    "BOUNTY": 1.00,
    "TOBLERONE": 1.40,
    "KIT KAT": 1.00,
    "CRUNCH": 1.00,
    "SMARTIES": 1.20,
    "SPECIAL K": 1.30,
    "M AND MS": 1.20,
    "DRAGIBUS": 1.80,
    "FRAISE TAGADA": 1.80,
    "CONFISERIE": 1.50,
    "BARRE": 1.50,
    "CHOCOLAT": 2.50,
    "BISCUIT": 1.80,
    # Snacks
    "CHIPS": 1.50,
    "CACAHUETES": 1.00,
    "GRAINES": 2.00,
    "APERITIF SALE": 1.50,
    "SAUCISSON": 2.50,
    # Frais
    "YAOURT": 0.70,
    "SANDWICH": 3.50,
    "WRAP": 3.80,
    "BURGER": 4.50,
    "TACOS": 5.00,
    "PATES": 4.50,
    "SALADE BOWL": 5.00,
    "SOUPE": 2.50,
    "PLAT": 5.50,
    "TRAITEUR": 3.50,
    "DESSERT": 1.80,
    "CONFITURE": 2.50,
    "MIEL": 4.00,
    # Non-F&B
    "ADAPTATEUR": 9.00,
    "CHARGEUR": 12.00,
    "CABLE": 8.00,
    "ECOUTEUR": 15.00,
    "BATTERIE DE SECOURS": 15.00,
    "GOURDE": 5.00,
    "CASQUETTE": 10.00,
    "MASQUE": 7.00,
    "LUNETTES DE NATATION": 6.00,
    "LUNETTES DE SOLEIL": 12.00,
    "TONGS": 6.00,
    "PARAPLUIE": 10.00,
    "PONCHO": 8.00,
    "BRASSARDS": 5.00,
    "BOUEE": 8.00,
    "MAILLOT DE BAIN": 12.00,
    "BONNET DE BAIN": 4.00,
    "CHAUSSURES AQUATIQUES": 10.00,
    "SERVIETTE": 8.00,
    "TROUSSE": 8.00,
    "KIT DENTAIRE": 3.50,
    "KIT RASAGE": 2.50,
    "DEODORANT": 4.00,
    "CREME SOLAIRE": 8.00,
    "BAUME LEVRES": 3.00,
    "GEL HYDROALCOOLIQUE": 2.00,
    "SPRAY FACIAL": 5.00,
    "ANTI MOUSTIQUE": 6.00,
    "PRESERVATIF": 4.00,
    "HYGIENE FEMININE": 3.00,
    "PELUCHE": 12.00,
    "T SHIRT": 10.00,
    "SHORT": 12.00,
    "CHAUSSETTES": 5.00,
    "BONNET": 8.00,
    "ECHARPE": 10.00,
    "POLAIRE": 15.00,
    "VESTE": 25.00,
    "SAC": 15.00,
    "ISOTHERME": 12.00,
    "MUG": 8.00,
    "TIRE BOUCHON": 5.00,
    "CARTE POSTALE": 1.00,
    "CARTE SIM": 10.00,
    "PORTE CLE": 4.00,
    "BOUGIE": 8.00,
    "COLORIAGE": 3.50,
    "JEU": 8.00,
    "SPORT PLAGE": 8.00,
    "CHAUFFERETTES": 3.00,
    "BERET": 15.00,
    "LEGGING": 12.00,
    "GANTS": 8.00,
    "TOUR DE COU": 6.00,
    "CARRE DE SOIE": 12.00,
    "SOUVENIR": 8.00,
    "NESPRESSO": 0.50,
    "RITUALS": 8.00,
    "NUXE": 12.00,
    "COSMETIQUE": 8.00,
    "PARFUM": 20.00,
    "KIT COUVERTS": 1.50,
    "DIVERS": 5.00,
}

# Overrides nom produit exact (si besoin fin) — unit €
UNIT_MARKET_BY_NOM: dict[str, float] = {
    "VITTEL 50CL": 0.70,
    "VITTEL 50 CL": 0.70,
    "VITTEL EN VERRE 50CL": 0.90,
    "COCA COLA 33CL": 1.00,
    "COCA COLA ZERO 33CL": 1.00,
    "L EAU NEUVE 50CL": 1.80,
    "SAN PELLEGRINO 50CL": 0.95,
    "SAN PELLEGRINO BOUTEILLE EN VERRE 50CL": 1.20,
    "KINDER BUENO 43G": 1.20,
    "RED BULL REGULAR 25 CL": 1.80,
    "EVIAN 33 CL": 0.70,
    "ADAPTATEUR UNIVERSEL": 9.00,
    "GOURDE": 5.00,
    "GOURDE EN VERRE NOVOTEL": 6.00,
    "KIT DENTAIRE COLGATE": 3.50,
    "CASQUETTE ENFANT MH100": 8.00,
    "CASQUETTE MH100": 10.00,
}


def unit_market_for_row(nom: str, nature_simple: str, unit_ttc: float) -> float:
    """Prix unitaire marché ; garanti strictement < unit_ttc si unit_ttc > 0."""
    nom_n = _norm(nom)
    nature_n = _norm(nature_simple)

    price = None
    if nom_n in UNIT_MARKET_BY_NOM:
        price = UNIT_MARKET_BY_NOM[nom_n]
    elif nature_n in UNIT_MARKET_BY_NATURE:
        price = UNIT_MARKET_BY_NATURE[nature_n]
    else:
        # défaut : ~55 % du prix hôtel (marge hôtel ~45 %)
        price = max(0.30, unit_ttc * 0.55) if unit_ttc > 0 else 0.50

    if unit_ttc <= 0:
        # retour / gratuit : marché = ttc (marge 0) — on force quand même une petite marge abs
        return max(0.01, abs(price) * 0.5)

    # marge strictement positive : marché < prix vente
    # si le prix web est trop haut (ou égal), plafonner à 70 % du TTC hôtel
    max_market = unit_ttc * 0.70
    if price >= unit_ttc:
        price = max(0.05, min(price * 0.5, max_market))
    # garde-fou final
    if price >= unit_ttc:
        price = unit_ttc * 0.70
    # minimum raisonnable
    price = max(0.05, round(price, 2))
    if price >= unit_ttc:
        price = round(unit_ttc * 0.70, 2)
        if price >= unit_ttc:
            price = max(0.01, unit_ttc - 0.10)
    return float(price)


def main() -> None:
    print("1. Load", EXT_PATH)
    df = pd.read_excel(EXT_PATH)
    print(f"   {df.shape}")

    # --- Nature mapping ---
    natures = sorted({_norm(x) for x in df["NATURE_PRODUIT"].fillna("").astype(str).unique()})
    nature_map = {n: simplify_nature(n) for n in natures if n}
    nature_map[""] = ""
    # also map raw as-is keys from file
    raw_natures = df["NATURE_PRODUIT"].fillna("").astype(str)
    full_nature_map: dict[str, str] = {}
    for raw in raw_natures.unique():
        full_nature_map[raw] = simplify_nature(raw)

    before_n = raw_natures.nunique()
    df["NATURE_PRODUIT"] = raw_natures.map(lambda x: full_nature_map.get(x, simplify_nature(x)))
    after_n = df["NATURE_PRODUIT"].nunique()
    print(f"2. NATURE_PRODUIT : {before_n} → {after_n} valeurs")
    print("   top natures :")
    print(df["NATURE_PRODUIT"].value_counts().head(25).to_string())

    NATURE_MAP_PATH.write_text(
        json.dumps(
            {k: v for k, v in sorted(full_nature_map.items(), key=lambda x: x[0])},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"   mapping → {NATURE_MAP_PATH}")

    # --- Marge / prix marché ---
    q = pd.to_numeric(df["QUANTITE"], errors="coerce").fillna(1.0)
    prix_ttc = pd.to_numeric(df["PRIX_TTC"], errors="coerce").fillna(0.0)
    abs_q = q.abs().where(q != 0, other=1.0)
    unit_ttc = prix_ttc / abs_q

    bad_mask = (prix_ttc - pd.to_numeric(df["PRIX_TTC_MARCHE"], errors="coerce").fillna(0)) <= 0
    print(f"3. Lignes marge≤0 avant : {int(bad_mask.sum())} ({100*bad_mask.mean():.1f}%)")

    # construire table produit (NOM_PRODUIT, nature, unit_ttc_med, unit_marche_new)
    prod_stats = (
        df.assign(_unit_ttc=unit_ttc, _q=q)
        .groupby("NOM_PRODUIT", dropna=False)
        .agg(
            n=("_unit_ttc", "size"),
            nature=("NATURE_PRODUIT", "first"),
            marque=("MARQUE", "first"),
            unit_ttc_med=("_unit_ttc", "median"),
            prix_ttc_med=("PRIX_TTC", "median"),
        )
        .reset_index()
    )
    prod_stats["unit_marche_new"] = [
        unit_market_for_row(nom, nat, float(uttc) if pd.notna(uttc) else 0.0)
        for nom, nat, uttc in zip(
            prod_stats["NOM_PRODUIT"],
            prod_stats["nature"],
            prod_stats["unit_ttc_med"],
        )
    ]
    prod_stats["marge_unit"] = prod_stats["unit_ttc_med"] - prod_stats["unit_marche_new"]

    # appliquer uniquement si marge actuelle ≤ 0 (conserver les marges déjà positives)
    unit_market_old = pd.to_numeric(df["PRIX_TTC_MARCHE"], errors="coerce") / abs_q
    marge_old = prix_ttc - pd.to_numeric(df["PRIX_TTC_MARCHE"], errors="coerce")

    nom_to_unit_mkt = dict(zip(prod_stats["NOM_PRODUIT"], prod_stats["unit_marche_new"]))
    unit_market_new = df["NOM_PRODUIT"].map(nom_to_unit_mkt)
    # fallback per-row
    missing = unit_market_new.isna()
    if missing.any():
        unit_market_new = unit_market_new.copy()
        for i in df.index[missing]:
            unit_market_new.at[i] = unit_market_for_row(
                df.at[i, "NOM_PRODUIT"],
                df.at[i, "NATURE_PRODUIT"],
                float(unit_ttc.at[i]) if pd.notna(unit_ttc.at[i]) else 0.0,
            )

    # fusion : si ancienne marge > 0, garder ancien ; sinon nouveau
    keep_old = marge_old > 0
    unit_final = unit_market_old.where(keep_old, other=unit_market_new)
    # re-forcer marge > 0 partout
    need_fix = (unit_ttc - unit_final) <= 0
    if need_fix.any():
        unit_final = unit_final.copy()
        for i in df.index[need_fix]:
            ut = float(unit_ttc.at[i]) if pd.notna(unit_ttc.at[i]) else 0.0
            unit_final.at[i] = unit_market_for_row(
                df.at[i, "NOM_PRODUIT"], df.at[i, "NATURE_PRODUIT"], ut
            )

    df["PRIX_TTC_MARCHE"] = (unit_final * q).astype(float).round(4)
    df["MARGE"] = (prix_ttc - df["PRIX_TTC_MARCHE"]).astype(float).round(4)

    still_bad = (df["MARGE"] <= 0).sum()
    print(f"   Lignes marge≤0 après : {still_bad}")
    print(f"   MARGE mean={df['MARGE'].mean():.3f} median={df['MARGE'].median():.3f} sum={df['MARGE'].sum():.2f}")

    # table mapping prix (produits touchés)
    price_rows = []
    for _, r in prod_stats.iterrows():
        price_rows.append(
            {
                "NOM_PRODUIT": r["NOM_PRODUIT"] if pd.notna(r["NOM_PRODUIT"]) else "",
                "NATURE_PRODUIT": r["nature"] if pd.notna(r["nature"]) else "",
                "MARQUE": r["marque"] if pd.notna(r["marque"]) else "",
                "n": int(r["n"]),
                "PRIX_TTC_unit_med": round(float(r["unit_ttc_med"]), 4) if pd.notna(r["unit_ttc_med"]) else None,
                "PRIX_TTC_MARCHE_unit": round(float(r["unit_marche_new"]), 4),
                "MARGE_unit": round(float(r["marge_unit"]), 4) if pd.notna(r["marge_unit"]) else None,
            }
        )
    PRICE_MAP_PATH.write_text(
        json.dumps(price_rows, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"   mapping prix → {PRICE_MAP_PATH} ({len(price_rows)} produits)")

    # sanity samples
    print("\n4. Échantillon par nature (median unit) :")
    sample = (
        df.assign(u_ttc=unit_ttc, u_m=unit_final)
        .groupby("NATURE_PRODUIT")
        .agg(n=("MARGE", "size"), ttc=("u_ttc", "median"), marche=("u_m", "median"), marge=("MARGE", "median"))
        .sort_values("n", ascending=False)
        .head(20)
    )
    print(sample.to_string())

    print("\n5. Write excel…")
    df.to_excel(TMP_OUT, index=False, na_rep="")
    shutil.move(str(TMP_OUT), str(EXT_PATH))
    print(f"   done {EXT_PATH} size={EXT_PATH.stat().st_size} cols={len(df.columns)}")
    print(f"   NATURE unique={df['NATURE_PRODUIT'].nunique()}  marge<=0={int((df['MARGE']<=0).sum())}")


if __name__ == "__main__":
    main()
