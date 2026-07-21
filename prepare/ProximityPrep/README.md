# ProximityPrep — Étape 3

Extraction des données de proximité : commerces alimentaires / non alimentaires et distance à la plage.

## Objectif

Produire une table à grain `hotel_code` (code Accor) avec les indicateurs géographiques utilisables par le modèle, en libellés explicites.

**Même contrat que MeteoPrep** : les coordonnées viennent de RodPrep ; on ne regéocode pas si `hotel_lat` / `hotel_lon` sont présents.

## Architecture

| Module | Classe | Rôle |
|--------|--------|------|
| `Src/proximity_prep/prep.py` | `ProximityPrep` | Orchestration : I/O hôtels, délégation POI/plage, écriture `Output/` |
| `rod_ia.domain.services.enrich_hotel` | `EnrichHotelService` | Géocode (fallback), Overpass POI, distance plage, cache feature store |

## Fichiers

| Dossier | Contenu |
|---------|---------|
| `Input/` | `hotels.parquet` / `hotels.csv` (identité issue de RodPrep) |
| `Output/` | `proximity.parquet`, `proximity.csv` |
| `Explore/` | `explore.ipynb` — exploration pas-à-pas ; remplit `Output/` |
| `Src/proximity_prep/prep.py` | Classe `ProximityPrep` |

## Entrées (identité hôtel)

| Champ | Origine | Rôle |
|-------|---------|------|
| `hotel_code` | RodPrep (`code_h`) | **Code Accor** — clé de jointure (jamais un nom ni un slug) |
| `hotel_name` | RodPrep | Nom affiché ; fallback géocode si lat/lon absents |
| `hotel_brand` | RodPrep | Marque (propagée si présente) |
| `hotel_city` | RodPrep | Ville (fallback géocode) |
| `hotel_lat` | RodPrep | **Latitude** — point POI/plage (prioritaire) |
| `hotel_lon` | RodPrep | **Longitude** — point POI/plage (prioritaire) |

Sans `hotel_code` valide, la ligne est **exclue** de l'input (`fill_input_from_rod`).  
Sans `hotel_lat` / `hotel_lon`, fallback géocode par `hotel_name` + `hotel_city`.

## Source géographique (API / cache)

Données produites par `EnrichHotelService` et stockées dans `feature_store/hotels/{hotel_code}/geo/enriched.json` (clé = **code Accor**).

Si `lat`/`lon` sont fournis à `enrich()`, Nominatim est **ignoré**.

### POI commerces (rayons 0,1 et 0,5 km)

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
| `d_nearest_{type}_m` | Distance au commerce le plus proche par type |

Plages : tags OSM `natural=beach`, `leisure=beach_resort`, `leisure=swimming_area` (rayon 5 km).

## Traitement

1. `fill_input_from_rod` : copie identité depuis `RodPrep/Output/hotel_lookup` (drop `hotel_code` null).
2. Pour chaque hôtel :
   - si `hotel_lat` / `hotel_lon` OK → POI + plage sur ce point (`geo_source=rod_coords`) ;
   - sinon → géocode par nom + ville puis POI (`geo_source=name_geocode`) ;
   - échec → ligne avec zéros / NaN (`geo_source=failed`).
3. Renommage en colonnes lisibles.
4. Une ligne par `hotel_code` Accor.

## Sorties calculées

| Champ | Méthode |
|-------|---------|
| `hotel_code` | Code Accor RodPrep |
| `hotel_name` | Reprise entrée |
| `hotel_lat`, `hotel_lon` | Coords utilisées (Rod ou géocode) |
| `geo_source` | `rod_coords` \| `name_geocode` \| `failed` |
| `plage_distance_km` | `d_nearest_beach_km` ou `nearest_beach_km` |
| `commerce_fb_100m` | `d_poi_fb_0_0_1km` |
| `commerce_fb_500m` | `d_poi_fb_0_0_5km` |
| `commerce_non_fb_100m` | `d_poi_not_fb_0_0_1km` |
| `commerce_non_fb_500m` | `d_poi_not_fb_0_0_5km` |
| `distance_{type}_m` | Pour chaque clé `d_nearest_{type}_m` |

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

**Identité — ne pas confondre :**

| Identifiant | Exemple | Rôle |
|-------------|---------|------|
| `hotel_code` (Accor / code_h) | `H2075` | Clé prepare / AllPrep |
| Slug registre | `ibis-budget-nice` | Registry interne (hors sortie Proximity) |
| `hotel_name` / `nom_hotel` | `Ibis budget Nice` | Libellé, jointure ventes |

## Exécution

```bash
python run_prepare.py   # sans --skip-proximity
```

Ou en Python :

```python
from proximity_prep.prep import ProximityPrep
prep = ProximityPrep("prepare/ProximityPrep/Input", "prepare/ProximityPrep/Output")
prep.fill_input_from_rod("prepare/RodPrep/Output")
frame = prep.run()
```

Ou notebook : `prepare/ProximityPrep/Explore/explore.ipynb`.
