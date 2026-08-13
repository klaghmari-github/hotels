# Sources brutes — inventaire pour déplacement du projet

Tout ce qui est nécessaire pour reconstruire / comprendre les données de base
de `release_1_0_0` est regroupé ici (ou déjà à la racine de `data/files/input/`).

Les pipelines runtime lisent surtout les fichiers **à la racine** de `input/`.
Le dossier `_raw_sources/` conserve les **originaux** et étapes intermédiaires
(export SQL, Excel ROD métier, mappings) pour ne rien perdre au déplacement.

## Racine `data/files/input/` (chargés par le code)

| Fichier | Rôle |
|---------|------|
| `hotel_sales_raw_extended_data.xlsx` (+ `.parquet`) | Ventes pilotes enrichies (source sim_v2 / ML) |
| `hotel_sales_data.xlsx` | Ventes agrégées / allégées |
| `hotel_data.xlsx` | Référentiel hôtels (services, TO, etc.) |
| `hotel_clients.xlsx` | Chambres / TO / guests par hôtel |
| `hotel_brand_data.xlsx` | Stats marques Accor |
| `hotel_concepts.xlsx` | Concepts / solutions |
| `hotel_proximity_data.xlsx` | Commerces concurrents (géo) |
| `hotel_weather_data.xlsx` | Météo mensuelle |
| `hotel_holidays_data.xlsx` | Vacances / jours fériés |
| `scenarios.xlsx` | Scénarios sim_v2 |
| `v1_pilot_defaults.xlsx` / `sim_v1_pilot_defaults.json` | Règles / coeffs R1–R4 sim_v1 |
| `v1_hotel_params.xlsx` | Params hôtels pilotes v1 |
| `rod_pilot_concepts.json` / `_flat.xlsx` | Mapping hôtel ↔ solution |
| `rod_reference.json` | Coûts + leviers par concept (ROI, capex, cost_lines) |
| `couts.xlsx` | Détail des coûts (Excel source) |
| `simulateur_data.xlsx` | Données simulateur Excel |
| `nature_produit_simplify_mapping.json` | Mapping natures produit |
| `prix_marche_mapping.json` | Prix marché (scraping) pour marges |

## `_raw_sources/ventes/`

| Fichier | Rôle |
|---------|------|
| `001.queryVentes.csv` | Export SQL brut des ventes (origine) |
| `hotel_sales_raw_data.xlsx` | Ventes brutes avant nettoyage |
| `hotel_sales_raw_clean_data.xlsx` | Après nettoyage |
| `hotel_sales_raw_extended_data.*` | Version étendue (natures, marges…) |
| `hotel_sales_data.xlsx` | Version allégée |

## `_raw_sources/rod_excel/`

| Fichier | Rôle |
|---------|------|
| `ROD - Simulateurs + détail des coûts.xlsx` | Excel métier simulateurs + coûts |
| `ROD - Paramètres & règles + projections nb. d'hôtels.xlsx` | Paramètres & règles ROD |
| `Analyse du poids des catégories de produit (2024-2025).xlsm` | Analyse catégories |
| `Récapitulatif de l'ensemble des données ROD (2).xlsx` | Récap données |
| `v1_pilot_defaults.xlsx` / `sim_v1_pilot_defaults.json` | Coeffs sim_v1 |
| `rod_excel_sheets.json` / `_live.json` | Feuilles/règles extraites |
| `scenarios.xlsx`, `simulateur_data.xlsx` | Scénarios / data simulateur |

## `_raw_sources/couts/`

| Fichier | Rôle |
|---------|------|
| `couts.xlsx` | Grille de coûts Excel |
| `rod_reference.json` | Coûts structurés par solution (utilisé par le code ROI) |

## `_raw_sources/referentiels/`

Hôtels, pilotes, proximité, météo, holidays, brands, concepts, `v1_hotel_params`.

## `_raw_sources/mapping/`

Mappings natures, prix marché, produits nettoyés, dictionnaire de champs, bases sales model, marges.

## `_raw_sources/docs/`

HTML / MD d’audit des règles simulateurs et consignes.

## Chaîne ventes (rappel)

```
001.queryVentes.csv
  → hotel_sales_raw_data.xlsx
  → hotel_sales_raw_clean_data.xlsx
  → hotel_sales_raw_extended_data.xlsx   ← runtime sim_v2
```

## Règles simulateur v1 + coûts

```
Excel ROD (Simulateurs + coûts, Paramètres & règles)
  → v1_pilot_defaults.xlsx / sim_v1_pilot_defaults.json   (R1–R4, coeffs marge)
  → couts.xlsx + rod_reference.json                        (coûts / capex / ROI)
```

Généré le : 2026-08-13 — pour portabilité du package `release_1_0_0`.
