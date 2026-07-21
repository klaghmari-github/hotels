# ProximityPrep — Étape 3

Indicateurs de proximité autour de l’hôtel : **commerces par catégorie** et **présence de plage**.

## Objectif

À partir des coords RodPrep (`hotel_lat` / `hotel_lon`) et du **code Accor** (`hotel_code`) :

1. **Commerces** — pour chaque catégorie OSM et chaque rayon **100 → 500 m** (pas de 100 m) :  
   nombre de commerces à distance ≤ rayon.
2. **Plage** — pour chaque rayon **1 → 5 km** (pas de 1 km) :  
   indicateur **0/1** (au moins une plage dans le rayon).

## Architecture

| Module | Classe | Rôle |
|--------|--------|------|
| `prepare/proximity_prep/features.py` | `ProximityFeatures` | Calcul pur : point → features (Overpass) |
| `prepare/proximity_prep/prep.py` | `ProximityPrep` | I/O hôtels RodPrep, orchestration, écriture Output |

## Entrées (depuis RodPrep)

| Champ | Rôle |
|-------|------|
| `hotel_code` | Code Accor — clé de jointure |
| `hotel_name` | Nom (fallback géocode si pas de coords) |
| `hotel_city` | Ville (fallback géocode) |
| `hotel_lat` / `hotel_lon` | Point de calcul (prioritaire) |

## Sorties — commerces

Rayons : **100, 200, 300, 400, 500** m (cumulatif : distance ≤ R).

### Par catégorie OSM

| Préfixe | Catégories |
|---------|------------|
| F&B | `convenience`, `bakery`, `supermarket`, `alcohol`, `confectionery`, `beverages`, `grocery`, `ice_cream`, `fast_food` |
| Non-F&B | `cosmetics`, `gift`, `tobacco`, `kiosk`, `pharmacy`, `chemist` |

Colonnes : `commerce_{categorie}_{R}m`  
Ex. `commerce_bakery_100m`, `commerce_pharmacy_500m`.

### Agrégats

| Colonne | Définition |
|---------|------------|
| `commerce_fb_{R}m` | Somme des catégories F&B dans le rayon R |
| `commerce_non_fb_{R}m` | Somme des catégories non-F&B dans le rayon R |

## Sorties — plage

| Colonne | Définition |
|---------|------------|
| `plage_1km` … `plage_5km` | `1` s’il existe une plage à ≤ N km, sinon `0` |
| `plage_distance_km` | Distance à la plage la plus proche (km), NaN si aucune ≤ 5 km |

Tags OSM plage : `natural=beach`, `leisure=beach_resort`, `leisure=swimming_area`.

## Exemple de ligne

```
hotel_code          H2075
commerce_bakery_100m     1
commerce_bakery_200m     2
…
commerce_fb_500m        12
commerce_non_fb_500m     3
plage_1km                1
plage_2km                1
…
plage_5km                1
plage_distance_km     0.13
```

## Exécution

```bash
python run_prepare.py
# ou
python -c "from prepare import ProximityPrep, default_paths; p=default_paths(); \
  prep=ProximityPrep(p.proximity_input, p.proximity_output); \
  prep.fill_input_from_rod(p.rod_output); print(prep.run())"
```
