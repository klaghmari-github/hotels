# ProximityPrep — Étape 3

Extraction des données de proximité : commerces alimentaires / non alimentaires et distance à la plage.

## Objectif

Produire une table à grain `hotel_code` avec les indicateurs géographiques utilisables par le modèle, en libellés explicites.

## Fichiers

| Dossier | Contenu |
|---------|---------|
| `Input/` | `hotels.parquet` (copie de `RodPrep/Output/hotel_lookup`) |
| `Output/` | `proximity.parquet`, `proximity.csv` |
| `Src/proximity_prep/prep.py` | Classe `ProximityPrep` |

## Entrées

| Champ source | Origine | Description |
|--------------|---------|-------------|
| `hotel_code` | RodPrep | Code hôtel |
| `hotel_name` | RodPrep | Nom (pour géocodage si cache absent) |
| `hotel_city` | RodPrep | Ville |
| `hotel_lat`, `hotel_lon` | RodPrep | Coordonnées (optionnel, enrichissement les recalcule) |

## Source géographique (API / cache)

Données produites par `EnrichHotelService` et stockées dans `feature_store/hotels/{code}/geo/enriched.json`.

### POI commerces (rayons 0,1 à 0,5 km)

Comptage de nodes OpenStreetMap (`shop=*`) par rayon et par famille :

| Champ source (cache) | Description |
|---------------------|-------------|
| `d_poi_fb_0_0_1km` | Commerces F&B dans 100 m |
| `d_poi_fb_0_0_5km` | Commerces F&B dans 500 m |
| `d_poi_not_fb_0_0_1km` | Commerces non-F&B dans 100 m |
| `d_poi_not_fb_0_0_5km` | Commerces non-F&B dans 500 m |

Familles F&B : convenience, bakery, supermarket, alcohol, fast_food…  
Familles non-F&B : cosmetics, gift, pharmacy, kiosk, tobacco…

### Distances ponctuelles

| Champ source (cache) | Description |
|---------------------|-------------|
| `d_nearest_beach_m` | Distance minimale à une plage (m) |
| `d_nearest_beach_km` | Idem en kilomètres |
| `d_nearest_{type}_m` | Distance au commerce le plus proche par type (alcohol, kiosk, tobacco…) |

Plages : tags OSM `natural=beach`, `leisure=beach_resort`, `leisure=swimming_area` (rayon 5 km).

## Traitement

1. Pour chaque hôtel : `EnrichHotelService.enrich(hotel_name, city, hotel_id)`.
2. Lecture POI et `nearest` depuis le cache ou calcul (géocode + Overpass).
3. Renommage en colonnes lisibles.
4. Une ligne par hôtel.

## Sorties calculées

| Champ | Méthode |
|-------|---------|
| `hotel_code` | Reprise entrée |
| `hotel_name` | Reprise entrée |
| `plage_distance_km` | `d_nearest_beach_km` ou `nearest_beach_km` |
| `commerce_fb_100m` | `d_poi_fb_0_0_1km` |
| `commerce_fb_500m` | `d_poi_fb_0_0_5km` |
| `commerce_non_fb_100m` | `d_poi_not_fb_0_0_1km` |
| `commerce_non_fb_500m` | `d_poi_not_fb_0_0_5km` |
| `distance_{type}_m` | Pour chaque clé `d_nearest_{type}_m` (ex. `distance_beach_m`, `distance_alcohol_m`) |

## Formules et règles

**Distance plage :**

```
plage_distance_km = min(distance OSM vers plage) / 1000
```

Si aucune plage dans le rayon : sentinelle `99999` m (conservée telle quelle).

**Comptage POI :**

```
commerce_fb_{rayon} = COUNT(nodes shop ∈ FB_TYPES dans rayon)
```

Rayons : 0,1 km et 0,5 km.

## Exécution

```bash
python run_prepare.py   # sans --skip-proximity
```