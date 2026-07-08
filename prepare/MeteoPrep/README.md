# MeteoPrep — Étape 2

Récupération et structuration des données météo mensuelles par hôtel, avec libellés lisibles et imputation des valeurs manquantes.

## Objectif

Produire une table `hotel_code × annee × mois` avec des indicateurs météo renommés (température, humidité, précipitations…) pour les années 2024 et 2025.

## Fichiers

| Dossier | Contenu |
|---------|---------|
| `Input/` | `hotels.parquet` / `hotels.csv` (produit par RodPrep) |
| `Output/` | `meteo_monthly.parquet`, `meteo_monthly.csv` |
| `Explore/` | `explore.ipynb` — exploration pas-à-pas (entrées, enrichissement, renommage, imputation) ; remplit `Output/` |
| `Src/meteo_prep/prep.py` | Classe `MeteoPrep` |

## Entrées

| Champ source | Origine | Description |
|--------------|---------|-------------|
| `hotel_code` | RodPrep | Code hôtel canonique |
| `hotel_name` | RodPrep | Nom affiché |
| `hotel_brand` | RodPrep | Marque |
| `hotel_city` | RodPrep | Ville |
| `hotel_lat` | RodPrep | Latitude |
| `hotel_lon` | RodPrep | Longitude |
| `hotel_adresse` | Dérivé | Copie de `hotel_city` (utilisé si lat/lon absentes) |

## Source météo (API / cache)

Données horaires Meteostat via `EnrichHotelService`, agrégées par mois. Clés brutes dans le feature store :

| Préfixe brut | Exemple |
|--------------|---------|
| `d_m{MM}_{metric}_{stat}` | `d_m03_temp_mean` |

Métriques brutes : `temp`, `dwpt`, `rhum`, `prcp`, `snow`, `wspd`, `pres`, `tsun`.  
Statistiques : `mean`, `min`, `max`.

## Traitement

1. Pour chaque hôtel, appel `EnrichHotelService.enrich()` (cache feature store ou calcul).
2. Renommage des colonnes météo en libellés lisibles.
3. Génération d'une ligne par `(hotel_code, annee, mois)` pour 2024 et 2025.
4. Imputation des trous par hôtel et par année.

## Sorties calculées

| Champ | Méthode |
|-------|---------|
| `hotel_code` | Reprise entrée |
| `hotel_name` | Reprise entrée |
| `annee` | 2024 ou 2025 (constante `TARGET_YEARS`) |
| `mois` | 1 à 12 |
| `meteo_temperature_c_mean` | Renommage de `d_m{MM}_temp_mean` |
| `meteo_temperature_c_min` | Renommage de `d_m{MM}_temp_min` |
| `meteo_temperature_c_max` | Renommage de `d_m{MM}_temp_max` |
| `meteo_point_rosee_c_{stat}` | `dwpt` → point de rosée (°C) |
| `meteo_humidite_pct_{stat}` | `rhum` → humidité relative (%) |
| `meteo_precipitations_mm_{stat}` | `prcp` → précipitations (mm) |
| `meteo_neige_mm_{stat}` | `snow` → neige (mm) |
| `meteo_vent_kmh_{stat}` | `wspd` → vent (km/h) |
| `meteo_pression_hpa_{stat}` | `pres` → pression (hPa) |
| `meteo_ensoleillement_min_{stat}` | `tsun` → ensoleillement (minutes) |

`{stat}` ∈ {`mean`, `min`, `max`}.

## Formules et règles

**Renommage :**

```
meteo_{READABLE_MAP[metric]}_{stat}
```

avec `READABLE_MAP = {temp: temperature_c, dwpt: point_rosee_c, rhum: humidite_pct, …}`.

**Imputation (par `hotel_code`, `annee`) :**

1. `ffill()` puis `bfill()` sur la série mensuelle.
2. Si valeur encore manquante : moyenne de la colonne sur l'année.
3. Sinon : `0.0`.

**Note :** le profil météo provient du cache enrichissement (fenêtre glissante ~12 mois). Les années 2024 et 2025 reçoivent le même profil mensuel type tant que l'API ne fournit pas d'historique annuel distinct par hôtel.

## Exécution

```bash
python run_prepare.py   # sans --skip-meteo
```