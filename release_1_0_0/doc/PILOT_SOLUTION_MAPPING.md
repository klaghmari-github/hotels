# Mapping hôtel ↔ solution (pilotes)

**Source de vérité** (release_1_0_0) :  
`data/files/input/rod_pilot_concepts.json` et `rod_pilot_concepts_flat.xlsx`.

Mise à jour métier 2026-08 (correction des erreurs Simply / Liberty / Connected).

## Liste canonique

| hotel_code | Hôtel | solution | partenaire |
|------------|--------|----------|------------|
| H2075 | Ibis budget Nice | **SIMPLY** | Adixon |
| HB6A3 | Ibis budget Strasbourg Centre République | **CONNECTED** | Selfly |
| H0373 | Mercure Paris Montmartre Sacré-Cœur | **CONNECTED** | Selfly |
| H1249 | Mercure Rennes Centre Gare | **CONNECTED** | Boost |
| HB5I0 | Novotel Megève Mont-Blanc | **LIBERTY** | Adixon |
| H3546 | Novotel Paris Centre Tour Eiffel | **CONNECTED** | Digitizme |

## Corrections appliquées

| Avant | Après |
|-------|--------|
| HB6A3 = SIMPLY | **CONNECTED / Selfly** |
| H6188 Mercure Paris Boulogne = LIBERTY (pilote) | **retiré des pilotes** |
| — | **H1249 Rennes = CONNECTED / Boost** ajouté aux concepts |

## Données ventes

- `t_sales` / raw : tickets existants pour H2075, HB6A3, H0373, H3546, HB5I0, **H6188** (historique Boulogne).
- **HB6A3** : `SOLUTION` forcé à `connected` en base.
- **H1249 Rennes** : présent dans `t_hotel_data` et concepts, **pas encore de lignes dans `t_sales`** → ne participe pas aux LOO / coeffs tant que les ventes ne sont pas chargées.
- **H6188** : peut rester dans `t_sales` (liberty) mais n’est plus dans `t_pilot_concepts` / `t_hotel_params`.

## Fichiers mis à jour

- `data/files/input/rod_pilot_concepts.json`
- `data/files/input/rod_pilot_concepts_flat.xlsx` (+ colonne `partenaire`)
- `data/files/input/v1_hotel_params.xlsx` (solutions + partenaire ; sans H6188)
- `data/files/input/hotel_clients.xlsx` (sans H6188)
- DuckDB : `t_sales` (HB6A3), `t_hotel_params`, `t_pilot_concepts`, `t_dataset_pivot`, `t_rich_data`, tables LOO

## Rebuild partiel recommandé (pas toute la sim_v2)

```bash
# recharger concepts / params v1
python scripts/p_table_view.py t_pilot_concepts
python scripts/p_table_view.py t_hotel_params
# vues assortiment (rangs par solution)
python scripts/p_table_view.py v_product_mean_rank_by_solution
```

Pour un recalcul LOO / coeffs sim_v2 complets après nouvelles ventes Rennes :  
`python run.py sim-v2 --rebuild` (long).
